from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
from dataclasses import replace
from pathlib import Path

import cv2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .catalog import Catalog
from .domain import Exam, MarkState, grade
from .recognition import RecognitionError, Recognizer
from .reporting import format_grade, reading_text
from .sessions import SessionStore, parse_corrections
from .settings import ROOT, Settings


def make_exam_token(exam_id: str) -> str:
    """Stable token derived strictly from the immutable exam ID."""
    return hashlib.sha256(exam_id.encode("utf-8")).hexdigest()[:12]


class Bot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.catalog = Catalog(settings.keys)
        self.recognizer = Recognizer(ROOT / "assets")
        self.sessions = SessionStore(settings.data_dir, settings.ttl_minutes)
        self.selected: dict[int, str] = {}
        self.exam_id_to_token: dict[str, str] = {}
        self.token_to_exam_id: dict[str, str] = {}
        for exam_id in self.catalog.exams:
            token = make_exam_token(exam_id)
            if token in self.token_to_exam_id and self.token_to_exam_id[token] != exam_id:
                raise ValueError(f"Exam token collision detected: {exam_id} and {self.token_to_exam_id[token]} produce token {token}")
            self.exam_id_to_token[exam_id] = token
            self.token_to_exam_id[token] = exam_id
        self.query_cache: dict[str, str] = {}

    def exam_token(self, exam_id: str) -> str:
        return self.exam_id_to_token.get(exam_id) or make_exam_token(exam_id)

    def exam_by_token(self, token: str) -> Exam | None:
        exam_id = self.token_to_exam_id.get(token)
        if exam_id and exam_id in self.catalog.exams:
            return self.catalog.exams[exam_id]
        return None

    def _render_exams_page(self, query: str, page: int = 1, page_size: int = 5) -> tuple[str, InlineKeyboardMarkup | None]:
        clean_query = query.strip()
        exams = self.catalog.search(clean_query) if clean_query else sorted(self.catalog.exams.values(), key=lambda e: (e.collection, e.name))
        total = len(exams)
        if not exams:
            return "No matching exams. Try /exams biology or /exams model", None
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        page_exams = exams[start:start + page_size]

        header = f"Available exams{' for ' + repr(clean_query) if clean_query else ''} (Page {page}/{total_pages}, total {total}):"
        lines = [header]
        for e in page_exams:
            status = "" if e.verified else " — key awaiting verification"
            lines.append(f"• {e.name} [{e.collection}] (ID: {e.id}){status}")

        buttons = []
        for e in page_exams:
            label = f"Select: {e.name[:25]} [{e.collection[:10]}]"
            buttons.append([InlineKeyboardButton(label, callback_data=f"sel:{self.exam_token(e.id)}")])

        nav = []
        q_token = "all"
        if clean_query:
            q_token = hashlib.sha256(clean_query.encode()).hexdigest()[:8]
            self.query_cache[q_token] = clean_query

        if page > 1:
            nav.append(InlineKeyboardButton("« Prev", callback_data=f"page:{page-1}:{q_token}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"page:{page+1}:{q_token}"))

        if nav:
            buttons.append(nav)
        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    def owner(self, update: Update) -> int | None:
        user = update.effective_user
        if user is None or update.effective_chat is None or update.effective_chat.type != "private":
            return None
        if self.settings.allowed_users and user.id not in self.settings.allowed_users:
            return None
        return user.id

    async def send(self, update: Update, text: str):
        # Plain text, not HTML/Markdown: source exam names cannot inject markup.
        pending = ""
        for line in text.splitlines():
            if len(pending)+len(line)+1 > 3800:
                await update.effective_message.reply_text(pending)
                pending = ""
            pending += line+"\n"
        if pending:
            await update.effective_message.reply_text(pending.rstrip())

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.owner(update) is None:
            return
        await self.send(update, "Send an original JPEG/PNG OMR image as a file and put the exam name in its caption. Either supported OMR layout works with any exam.\n\n/exams [words] — find an exam\n/exam NAME — select an exam before uploading\n/fix 12=A 27=blank 40=invalid 51=A+B — correct a reading\n/confirm — grade the reviewed reading\n/cancel — delete the current reading\n/whoami — show your Telegram ID\n\nOnly shaded black bubbles are valid. Double fills, ticks, and crosses are wrong. Unclear readings need review; they are never silently scored. Scores may be negative.")

    async def whoami(self, update, context):
        if update.effective_user:
            await update.effective_message.reply_text(f"Your Telegram user ID: {update.effective_user.id}")

    async def exams(self, update, context):
        if self.owner(update) is None:
            return
        query = " ".join(context.args)
        text, markup = self._render_exams_page(query, page=1)
        if markup:
            await update.effective_message.reply_text(text, reply_markup=markup)
        else:
            await self.send(update, text)

    async def choose(self, update, query: str):
        clean = query.strip()
        if not clean:
            return None
        matches = self.catalog.match(clean)
        if len(matches) == 1:
            return matches[0]
        if matches:
            text = "This name exists in more than one collection. Use one of these exact IDs:\n" + "\n".join(f"{e.id}: {e.name} [{e.collection}]" for e in matches)
            buttons = [[InlineKeyboardButton(f"Select: {e.name[:25]} [{e.collection[:10]}]", callback_data=f"sel:{self.exam_token(e.id)}")] for e in matches]
            await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            suggestions = self.catalog.search(clean)
            if suggestions:
                text = "Exam not found. Use /exams to see the names.\nPossible matches:\n" + "\n".join(f"{e.name} [{e.collection}]" for e in suggestions[:8])
                buttons = [[InlineKeyboardButton(f"Select: {e.name[:25]} [{e.collection[:10]}]", callback_data=f"sel:{self.exam_token(e.id)}")] for e in suggestions[:5]]
                await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await self.send(update, "Exam not found. Use /exams to see the names.")
        return None

    async def exam(self, update, context):
        owner = self.owner(update)
        if owner is None:
            return
        query = " ".join(context.args).strip()
        if not query:
            await self.send(update, "Usage: /exam NAME\nSelect an exam before uploading your OMR sheet.\n\nExamples:\n/exam Paper Final English [Practice book]\n/exam retina-model-test-01\n\nUse /exams to search or browse available exams.")
            return
        selected = await self.choose(update, query)
        if selected:
            self.selected[owner] = selected.id
            await self.send(update, f"Selected: {selected.name} [{selected.collection}] (ID: {selected.id})\nNow send your OMR image as a file. A new caption can select another exam.")

    async def media(self, update, context):
        owner = self.owner(update)
        if owner is None:
            return
        self.sessions.cleanup()
        message = update.effective_message
        caption = (message.caption or "").strip()
        if caption:
            exam = await self.choose(update, caption)
            if not exam:
                return
        else:
            selected_id = self.selected.get(owner)
            if not selected_id or selected_id not in self.catalog.exams:
                await self.send(update, "Add the exam name as the image caption, or choose it with /exam NAME first")
                return
            exam = self.catalog.exams[selected_id]
        media = message.document or (message.photo[-1] if message.photo else None)
        if media is None:
            return
        if message.document and message.document.mime_type not in {"image/jpeg", "image/png"}:
            await self.send(update, "Please send a JPEG or PNG image file")
            return
        if media.file_size and media.file_size > 19_000_000:
            await self.send(update, "Please send an image smaller than 19 MB")
            return
        self.sessions.discard(owner)
        directory = self.sessions.allocate()
        try:
            await self.send(update, "Reading the 100-question answer grid…")
            downloaded = await media.get_file()
            source = directory / "original.image"
            await downloaded.download_to_drive(source)
            reading = await asyncio.to_thread(self.recognizer.read, source)
            session = self.sessions.create(owner, exam.id, directory, reading)
            await self.preview(update, session)
        except (RecognitionError, ValueError) as exc:
            self.sessions.discard(owner)
            shutil.rmtree(directory, ignore_errors=True)
            await self.send(update, str(exc))
        except Exception:
            self.sessions.discard(owner)
            shutil.rmtree(directory, ignore_errors=True)
            raise

    async def preview(self, update, session):
        exam = self.catalog.exams[session.exam_id]
        file = session.directory / "preview.jpg"
        cv2.imwrite(str(file), session.reading.annotated)
        with file.open("rb") as stream:
            await update.effective_message.reply_document(stream, filename="detected-answers.jpg", caption=f"{exam.name}\nLayout: {session.reading.template_id}\nGreen: single · Blue: blank · Red: multiple/invalid · Orange: review")
        await self.send(update, reading_text(session.reading.marks))
        unclear = [m.number for m in session.reading.marks if m.state == MarkState.UNCERTAIN]
        text = "Check the detected choices against your paper. Corrections change the reading, not the answer key."
        if unclear:
            text += "\nResolve these rows with /fix before grading: "+", ".join(map(str,unclear))
        if not exam.verified:
            text += "\nThis exam key is awaiting source verification. You can review recognition, but final grading is blocked."
        buttons = [[InlineKeyboardButton("Confirm reading & grade", callback_data=f"confirm:{session.id}:{session.revision}")], [InlineKeyboardButton("Cancel",callback_data=f"cancel:{session.id}:{session.revision}")]]
        await update.effective_message.reply_text(text,reply_markup=InlineKeyboardMarkup(buttons))

    async def fix(self, update, context):
        owner = self.owner(update)
        if owner is None:
            return
        try:
            session = self.sessions.get(owner)
            changes = parse_corrections(" ".join(context.args))
            for number, change in changes.items():
                previous = session.reading.marks[number-1]
                session.edits.append({"question": number, "before": {"state":previous.state.value,"choices":previous.choices}, "after":{"state":change.state.value,"choices":change.choices}})
                session.reading.marks[number-1] = change
            session.revision += 1
            template = next(t for t in self.recognizer.templates if t.id == session.reading.template_id)
            session.reading.annotated = self.recognizer.annotate(template,session.reading.aligned,session.reading.marks,session.reading.sampling_centers)
            session.audit()
            await self.preview(update,session)
        except ValueError as exc:
            await self.send(update,str(exc))

    async def confirm(self, update, context):
        owner = self.owner(update)
        if owner is None:
            return
        try:
            session = self.sessions.get(owner)
            if update.callback_query:
                _, identifier, revision = update.callback_query.data.split(":")
                if identifier != session.id or int(revision) != session.revision:
                    raise ValueError("This preview was replaced. Confirm the latest preview")
            # Reload so verified key changes never require restarting the bot.
            catalog = Catalog(self.settings.keys)
            exam = catalog.exams[session.exam_id]
            result = grade(exam,session.reading.marks,confirmed=True)
            await self.send(update,format_grade(result))
            self.sessions.discard(owner)
        except (ValueError,KeyError) as exc:
            await self.send(update,str(exc))

    async def cancel(self, update, context):
        owner = self.owner(update)
        if owner is not None:
            self.sessions.discard(owner)
            await self.send(update,"Reading deleted. Send another image with its exam name whenever you are ready")

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        owner = self.owner(update)
        if owner is None:
            return
        data = query.data or ""
        if data == "noop":
            return
        if data.startswith("sel:"):
            token = data.split(":", 1)[1]
            exam = self.exam_by_token(token)
            if exam:
                self.selected[owner] = exam.id
                await self.send(update, f"Selected: {exam.name} [{exam.collection}] (ID: {exam.id})\nNow send your OMR image as a file. A new caption can select another exam.")
            else:
                await self.send(update, "This exam is no longer available. Use /exams to browse available exams.")
        elif data.startswith("page:"):
            parts = data.split(":", 2)
            if len(parts) == 3:
                try:
                    page = int(parts[1])
                except ValueError:
                    return
                q_token = parts[2]
                if q_token != "all" and q_token not in self.query_cache:
                    msg = "This search has expired. Please run /exams [words] again to search."
                    try:
                        await query.edit_message_text(msg)
                    except Exception:
                        if query.message:
                            await query.message.reply_text(msg)
                        else:
                            await self.send(update, msg)
                    return
                search_query = "" if q_token == "all" else self.query_cache[q_token]
                text, markup = self._render_exams_page(search_query, page=page)
                try:
                    await query.edit_message_text(text, reply_markup=markup)
                except Exception:
                    if query.message:
                        await query.message.reply_text(text, reply_markup=markup)
                    else:
                        await self.send(update, text)
        elif data.startswith("confirm:"):
            await self.confirm(update, context)
        elif data.startswith("cancel:"):
            try:
                session = self.sessions.get(owner)
                if data.split(":")[1] != session.id:
                    raise ValueError("This preview was replaced")
                await self.cancel(update, context)
            except ValueError as exc:
                await self.send(update, str(exc))


def run():
    settings = Settings.from_env()
    bot = Bot(settings)
    # Sequential processing keeps each user's upload/review/confirm lifecycle ordered.
    app = Application.builder().token(settings.token).concurrent_updates(False).build()
    for command in ("start", "exams", "exam", "fix", "confirm", "cancel", "whoami"):
        app.add_handler(CommandHandler(command, getattr(bot, command)))
    app.add_handler(CallbackQueryHandler(bot.callback))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, bot.media))

    async def on_error(update,context):
        # Never log request URLs or exception strings: Telegram URLs contain the token.
        logging.getLogger(__name__).error("Bot operation failed (%s)",type(context.error).__name__)
        if isinstance(update,Update) and bot.owner(update) is not None:
            await bot.send(update,"This operation could not finish. Try again or upload a clearer original image")

    app.add_error_handler(on_error)
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print("OMR bot starting. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=["message","callback_query"])
