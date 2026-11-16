import asyncio
import json
import shutil
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omr_check.bot import Bot, make_exam_token
from omr_check.domain import Mark, MarkState
from omr_check.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


class DummyFile:
    def __init__(self, source_path: Path):
        self.source_path = source_path

    async def download_to_drive(self, destination: Path):
        shutil.copyfile(self.source_path, destination)


def make_update(user_id=12345, text="", caption="", document=None, callback_data=None):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = user_id
    update.effective_chat.type = "private"

    msg = MagicMock()
    msg.text = text
    msg.caption = caption
    msg.document = document
    msg.photo = []
    msg.reply_text = AsyncMock()
    msg.reply_document = AsyncMock()
    update.effective_message = msg

    if callback_data:
        cb = MagicMock()
        cb.data = callback_data
        cb.answer = AsyncMock()
        cb.edit_message_text = AsyncMock()
        cb.message = msg
        update.callback_query = cb
    else:
        update.callback_query = None

    return update


def make_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


@pytest.fixture
def bot_instance(tmp_path):
    settings = Settings(
        token="DUMMY_TOKEN",
        data_dir=tmp_path / "sessions",
        keys=ROOT / "data/answer_keys.json",
        allowed_users=(),
        ttl_minutes=15,
    )
    return Bot(settings)


def test_full_upload_preview_fix_confirm_flow_practice(bot_instance):
    sample_path = ROOT / "omr-exam-paper-example/20261115_191159.jpg"
    if not sample_path.exists():
        pytest.skip("Source photo not distributed")

    async def _test():
        bot = bot_instance

        # Step 1: Upload practice book sample with exam caption
        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        doc.file_size = 500_000
        doc.get_file = AsyncMock(return_value=DummyFile(sample_path))

        upload_update = make_update(
            user_id=1001,
            caption="Paper Final-01 Biology 1st Paper",
            document=doc,
        )
        ctx = make_context()

        await bot.media(upload_update, ctx)

        # Verify session was created
        session = bot.sessions.get(1001)
        assert session.exam_id == "practice-paper-final-01-biology-1st-paper"
        assert session.revision == 0
        assert len(session.reading.marks) == 100

        # Practice book sample has Q1=A, Q2=A, Q3=C, and 97 blanks (0 uncertain)
        assert session.reading.marks[0].choices == ("A",)
        assert session.reading.marks[1].choices == ("A",)
        assert session.reading.marks[2].choices == ("C",)
        assert session.reading.marks[3].state == MarkState.BLANK

        # Verify preview was sent (document and reply_text with buttons)
        assert upload_update.effective_message.reply_document.called
        assert upload_update.effective_message.reply_text.called

        # Step 2: Test correction (/fix)
        # Correct Q4 to B
        fix_update = make_update(user_id=1001)
        fix_ctx = make_context(args=["4=B"])
        await bot.fix(fix_update, fix_ctx)

        session = bot.sessions.get(1001)
        assert session.revision == 1
        assert session.reading.marks[3].state == MarkState.SINGLE
        assert session.reading.marks[3].choices == ("B",)
        assert len(session.edits) == 1
        assert session.edits[0]["question"] == 4

        # Step 3: Stale confirmation protection
        # Trying to confirm with old revision 0 must fail
        stale_update = make_update(user_id=1001, callback_data=f"confirm:{session.id}:0")
        await bot.callback(stale_update, ctx)
        stale_reply = stale_update.effective_message.reply_text.call_args[0][0]
        assert "This preview was replaced" in stale_reply

        # Step 4: Confirm latest revision (revision 1)
        confirm_update = make_update(user_id=1001, callback_data=f"confirm:{session.id}:1")
        await bot.callback(confirm_update, ctx)

        # Verify result message was sent
        confirm_reply = confirm_update.effective_message.reply_text.call_args[0][0]
        assert "Paper Final-01 Biology 1st Paper" in confirm_reply
        assert "Score:" in confirm_reply
        # Session must be discarded after confirmation
        with pytest.raises(ValueError, match="No active reading"):
            bot.sessions.get(1001)

    asyncio.run(_test())


def test_retina_sample_uncertain_guard_and_resolution(bot_instance):
    sample_path = ROOT / "omr-exam-paper-example/20261115_191044.jpg"
    if not sample_path.exists():
        pytest.skip("Source photo not distributed")

    async def _test():
        bot = bot_instance

        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        doc.file_size = 500_000
        doc.get_file = AsyncMock(return_value=DummyFile(sample_path))

        # Select exam beforehand via /exam
        exam_update = make_update(user_id=2002)
        exam_ctx = make_context(args=["retina-model-test-01"])
        await bot.exam(exam_update, exam_ctx)
        assert bot.selected[2002] == "retina-model-test-01"

        # Upload Retina sample without caption (uses selected)
        upload_update = make_update(user_id=2002, document=doc)
        ctx = make_context()
        await bot.media(upload_update, ctx)

        session = bot.sessions.get(2002)
        uncertain_rows = [m.number for m in session.reading.marks if m.state == MarkState.UNCERTAIN]
        if not uncertain_rows:
            # When the clean photo aligns with zero uncertain rows,
            # introduce an uncertain reading row to verify the guard
            session.reading.marks[37] = Mark(38, MarkState.UNCERTAIN, note="Partial shading or a nonstandard mark: inspect this row")
            uncertain_rows = [38]
            fix_args = ["38=A"]
        else:
            golden = json.loads((ROOT / "data/sample_expected.json").read_text())["retina"]["answers"]
            fix_args = [f"{q}={golden[q-1] if golden[q-1] != '-' else 'A'}" for q in uncertain_rows]

        # Attempt to confirm while uncertain marks exist MUST be blocked
        confirm_update = make_update(user_id=2002, callback_data=f"confirm:{session.id}:0")
        await bot.callback(confirm_update, ctx)
        blocked_reply = confirm_update.effective_message.reply_text.call_args[0][0]
        assert "Resolve all uncertain readings before grading" in blocked_reply

        # Session still exists and was NOT scored
        assert bot.sessions.get(2002) is not None

        # Fix uncertain rows using /fix
        fix_update = make_update(user_id=2002)
        fix_ctx = make_context(args=fix_args)
        await bot.fix(fix_update, fix_ctx)

        session = bot.sessions.get(2002)
        assert session.revision == 1
        # Check that no uncertain rows remain
        assert not any(m.state == MarkState.UNCERTAIN for m in session.reading.marks)

        # Now confirm the resolved reading
        confirm_ok = make_update(user_id=2002, callback_data=f"confirm:{session.id}:1")
        await bot.callback(confirm_ok, ctx)

        result_reply = confirm_ok.effective_message.reply_text.call_args[0][0]
        assert "Model Test-01" in result_reply
        assert "Score:" in result_reply
        assert "Correct:" in result_reply
        assert "Wrong answers:" in result_reply
        assert "Unanswered:" in result_reply

    asyncio.run(_test())


def test_cancel_flow(bot_instance):
    sample_path = ROOT / "omr-exam-paper-example/20261115_191159.jpg"
    if not sample_path.exists():
        pytest.skip("Source photo not distributed")

    async def _test():
        bot = bot_instance
        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        doc.file_size = 500_000
        doc.get_file = AsyncMock(return_value=DummyFile(sample_path))

        upload_update = make_update(
            user_id=3003,
            caption="practice-paper-final-01-biology-1st-paper",
            document=doc,
        )
        await bot.media(upload_update, make_context())
        assert bot.sessions.get(3003) is not None

        # Cancel via command
        cancel_update = make_update(user_id=3003)
        await bot.cancel(cancel_update, make_context())
        with pytest.raises(ValueError, match="No active reading"):
            bot.sessions.get(3003)
        reply = cancel_update.effective_message.reply_text.call_args[0][0]
        assert "Reading deleted" in reply

    asyncio.run(_test())


def test_ambiguous_exam_name_prompts_user(bot_instance):
    async def _test():
        bot = bot_instance
        update = make_update(user_id=4004)
        ctx = make_context(args=["Model Test-01"])  # Exists in both Practice and Retina!
        await bot.exam(update, ctx)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "This name exists in more than one collection" in reply
        assert "practice-model-test-01" in reply
        assert "retina-model-test-01" in reply

    asyncio.run(_test())


def test_exam_without_args_shows_concise_help(bot_instance):
    async def _test():
        bot = bot_instance
        update = make_update(user_id=5001)
        await bot.exam(update, make_context(args=[]))
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Usage: /exam NAME" in reply
        assert "Examples:" in reply
    asyncio.run(_test())


def test_exam_select_by_displayed_label(bot_instance):
    async def _test():
        bot = bot_instance
        update = make_update(user_id=5002)
        await bot.exam(update, make_context(args=["Paper", "Final", "English", "[Practice", "book]"]))
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Selected: Paper Final English [Practice book]" in reply
        assert "(ID: practice-paper-final-english)" in reply
        assert bot.selected[5002] == "practice-paper-final-english"
    asyncio.run(_test())


def test_exams_pagination_and_navigation(bot_instance):
    async def _test():
        bot = bot_instance
        update = make_update(user_id=5003)
        await bot.exams(update, make_context(args=["english"]))
        call = update.effective_message.reply_text.call_args
        text = call[0][0]
        markup = call[1]["reply_markup"]
        assert "Page 1/" in text
        assert markup is not None
        button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
        assert any("Select:" in t for t in button_texts)
    asyncio.run(_test())


def test_callback_selection(bot_instance):
    async def _test():
        bot = bot_instance
        token = bot.exam_token("practice-paper-final-english")
        update = make_update(user_id=5004, callback_data=f"sel:{token}")
        await bot.callback(update, make_context())
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Selected: Paper Final English [Practice book]" in reply
        assert "(ID: practice-paper-final-english)" in reply
        assert bot.selected[5004] == "practice-paper-final-english"
    asyncio.run(_test())


def test_invalid_caption_does_not_fall_back_silently(bot_instance):
    async def _test():
        bot = bot_instance
        bot.selected[5005] = "practice-paper-final-english"
        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        doc.file_size = 500_000
        sample_path = ROOT / "omr-exam-paper-example/20261115_191159.jpg"
        if not sample_path.exists():
            sample_path = ROOT / "ui-screenshots/answer-omr-1 (1).png"
        doc.get_file = AsyncMock(return_value=DummyFile(sample_path))
        update = make_update(user_id=5005, caption="Completely Nonexistent Exam 999", document=doc)
        await bot.media(update, make_context())
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Exam not found" in reply
        # Must NOT have created a reading session with the pre-selected exam
        with pytest.raises(ValueError, match="No active reading"):
            bot.sessions.get(5005)
    asyncio.run(_test())


def test_session_exam_id_remains_unchanged_when_new_exam_selected(bot_instance):
    sample_path = ROOT / "omr-exam-paper-example/20261115_191159.jpg"
    if not sample_path.exists():
        pytest.skip("Source photo not distributed")
    async def _test():
        bot = bot_instance
        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        doc.file_size = 500_000
        doc.get_file = AsyncMock(return_value=DummyFile(sample_path))

        # Upload with exam A
        upload_update = make_update(
            user_id=5006,
            caption="practice-paper-final-01-biology-1st-paper",
            document=doc,
        )
        await bot.media(upload_update, make_context())
        session = bot.sessions.get(5006)
        assert session.exam_id == "practice-paper-final-01-biology-1st-paper"

        # Now select exam B via /exam
        exam_update = make_update(user_id=5006)
        await bot.exam(exam_update, make_context(args=["Paper Final English [Practice book]"]))
        assert bot.selected[5006] == "practice-paper-final-english"

        # The existing session must STILL have its original exam_id
        session_after = bot.sessions.get(5006)
        assert session_after.exam_id == "practice-paper-final-01-biology-1st-paper"
    asyncio.run(_test())


def test_pagination_callback_flow(bot_instance):
    async def _test():
        bot = bot_instance
        # 1. Search for biology (matches multiple exams, > 5 exams so multiple pages)
        search_update = make_update(user_id=6001)
        await bot.exams(search_update, make_context(args=["biology"]))
        call = search_update.effective_message.reply_text.call_args
        text = call[0][0]
        markup = call[1]["reply_markup"]
        assert "Page 1/" in text

        # Find the next page button
        nav_buttons = [btn for row in markup.inline_keyboard for btn in row if btn.callback_data.startswith("page:2:")]
        assert len(nav_buttons) == 1
        page2_cb = nav_buttons[0].callback_data

        # 2. Trigger pagination callback
        cb_update = make_update(user_id=6001, callback_data=page2_cb)
        await bot.callback(cb_update, make_context())
        cb_update.callback_query.edit_message_text.assert_called_once()
        page2_text = cb_update.callback_query.edit_message_text.call_args[0][0]
        assert "Page 2/" in page2_text

    asyncio.run(_test())


def test_pagination_callback_expired_query_token(bot_instance):
    async def _test():
        bot = bot_instance
        # Callback with an unknown/expired query token
        cb_update = make_update(user_id=6002, callback_data="page:2:nonexistent_hash_999")
        await bot.callback(cb_update, make_context())
        # Must ask user to search again, rather than silently showing all exams
        edit_call = cb_update.callback_query.edit_message_text.call_args
        msg = edit_call[0][0] if edit_call else cb_update.effective_message.reply_text.call_args[0][0]
        assert "This search has expired" in msg
        assert "run /exams [words] again" in msg

    asyncio.run(_test())


def test_invalid_selection_token_rejected_safely(bot_instance):
    async def _test():
        bot = bot_instance
        cb_update = make_update(user_id=6003, callback_data="sel:invalid_token_123")
        await bot.callback(cb_update, make_context())
        reply = cb_update.effective_message.reply_text.call_args[0][0]
        assert "This exam is no longer available" in reply
        assert 6003 not in bot.selected

    asyncio.run(_test())


def test_stable_tokens_survive_catalog_mutation(tmp_path):
    def make_keys_file(path: Path, exam_items: list[dict]):
        data = {"schema_version": 1, "exams": exam_items}
        path.write_text(json.dumps(data), encoding="utf-8")

    def make_exam_dict(eid: str, name: str):
        return {
            "id": eid,
            "name": name,
            "collection": "Practice book",
            "status": "verified",
            "answers": {str(i): ["A"] for i in range(1, 101)},
            "issues": []
        }

    # Initial Catalog with 3 exams: E1, E2, E3
    keys_file_a = tmp_path / "keys_a.json"
    make_keys_file(keys_file_a, [
        make_exam_dict("exam-1", "Exam One"),
        make_exam_dict("exam-2", "Exam Two"),
        make_exam_dict("exam-3", "Exam Three"),
    ])
    settings_a = Settings(token="DUMMY", allowed_users=frozenset(), keys=keys_file_a, data_dir=tmp_path / "s1", ttl_minutes=15)
    bot_a = Bot(settings_a)

    token_e1_a = bot_a.exam_token("exam-1")
    token_e2_a = bot_a.exam_token("exam-2")
    token_e3_a = bot_a.exam_token("exam-3")

    # Modified Catalog: E3 removed, E0 added at beginning, order swapped: [E0, E2, E1]
    keys_file_b = tmp_path / "keys_b.json"
    make_keys_file(keys_file_b, [
        make_exam_dict("exam-0", "Exam Zero"),
        make_exam_dict("exam-2", "Exam Two"),
        make_exam_dict("exam-1", "Exam One"),
    ])
    settings_b = Settings(token="DUMMY", allowed_users=frozenset(), keys=keys_file_b, data_dir=tmp_path / "s2", ttl_minutes=15)
    bot_b = Bot(settings_b)

    # 1. Tokens must remain completely stable across catalog reordering/additions
    assert bot_b.exam_token("exam-1") == token_e1_a
    assert bot_b.exam_token("exam-2") == token_e2_a

    async def _test():
        # 2. Clicking old button for E1 in Bot B resolves to Exam One, never redirected to E0 or E2
        update_e1 = make_update(user_id=7001, callback_data=f"sel:{token_e1_a}")
        await bot_b.callback(update_e1, make_context())
        assert bot_b.selected[7001] == "exam-1"
        reply = update_e1.effective_message.reply_text.call_args[0][0]
        assert "Selected: Exam One [Practice book] (ID: exam-1)" in reply

        # 3. Clicking old button for removed E3 in Bot B is safely rejected, never redirects
        update_e3 = make_update(user_id=7002, callback_data=f"sel:{token_e3_a}")
        await bot_b.callback(update_e3, make_context())
        assert 7002 not in bot_b.selected
        reply_e3 = update_e3.effective_message.reply_text.call_args[0][0]
        assert "This exam is no longer available" in reply_e3

    asyncio.run(_test())


def test_token_collision_detected(tmp_path, monkeypatch):
    keys_file = tmp_path / "keys_coll.json"
    data = {
        "schema_version": 1,
        "exams": [
            {
                "id": "exam-alpha",
                "name": "Exam Alpha",
                "collection": "Retina",
                "status": "verified",
                "answers": {str(i): ["A"] for i in range(1, 101)},
                "issues": []
            },
            {
                "id": "exam-beta",
                "name": "Exam Beta",
                "collection": "Retina",
                "status": "verified",
                "answers": {str(i): ["A"] for i in range(1, 101)},
                "issues": []
            }
        ]
    }
    keys_file.write_text(json.dumps(data), encoding="utf-8")
    settings = Settings(token="DUMMY", allowed_users=frozenset(), keys=keys_file, data_dir=tmp_path / "s_coll", ttl_minutes=15)

    # Force a token collision between two different exams
    monkeypatch.setattr("omr_check.bot.make_exam_token", lambda eid: "same_token_collision")

    with pytest.raises(ValueError, match="Exam token collision detected"):
        Bot(settings)

