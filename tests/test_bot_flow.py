import asyncio
import shutil
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omr_check.bot import Bot
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
        # Retina sample has exactly 14 uncertain rows
        assert len(uncertain_rows) == 14

        # Attempt to confirm while uncertain marks exist MUST be blocked
        confirm_update = make_update(user_id=2002, callback_data=f"confirm:{session.id}:0")
        await bot.callback(confirm_update, ctx)
        blocked_reply = confirm_update.effective_message.reply_text.call_args[0][0]
        assert "Resolve all uncertain readings before grading" in blocked_reply

        # Session still exists and was NOT scored
        assert bot.sessions.get(2002) is not None

        # Fix all 14 uncertain rows using /fix
        fix_args = [
            "38=A", "42=D", "60=A", "62=B", "63=A", "64=C", "65=D", "66=D",
            "68=A", "69=C", "70=A", "91=A", "95=D", "96=C",
        ]
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
        assert "Wrong:" in result_reply
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
