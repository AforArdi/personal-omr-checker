from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import replace
from pathlib import Path

import cv2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .catalog import Catalog
from .domain import MarkState, grade
from .recognition import RecognitionError, Recognizer
from .reporting import format_grade, reading_text
from .sessions import SessionStore, parse_corrections
from .settings import ROOT, Settings


class Bot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.catalog = Catalog(settings.keys)
        self.recognizer = Recognizer(ROOT / "assets")
        self.sessions = SessionStore(settings.data_dir, settings.ttl_minutes)
        self.selected: dict[int, str] = {}

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
        exams = self.catalog.search(query) if query else sorted(self.catalog.exams.values(), key=lambda e:(e.collection,e.name))
        lines = ["Available exams (names ignore capitalization):"]
        lines += [f"{e.name} [{e.collection}]" + (" — key awaiting verification" if not e.verified else "") for e in exams]
        await self.send(update, "\n".join(lines) if exams else "No matching exams. Try /exams biology or /exams model")

    async def choose(self, update, query: str):
        matches = self.catalog.match(query)
        if len(matches) == 1:
            return matches[0]
        if matches:
            await self.send(update, "This name exists in more than one collection. Use one of these exact IDs:\n"+"\n".join(f"{e.id}: {e.name} [{e.collection}]" for e in matches))
        else:
            suggestions = self.catalog.search(query)
            await self.send(update, "Exam not found. Use /exams to see the names." + ("\nPossible matches:\n"+"\n".join(f"{e.name} [{e.collection}]" for e in suggestions[:8]) if suggestions else ""))
        return None

    async def exam(self, update, context):
        owner = self.owner(update)
        if owner is None:
            return
        selected = await self.choose(update, " ".join(context.args))
        if selected:
            self.selected[owner] = selected.id
            self.sessions.discard(owner)
            await self.send(update, f"Selected: {selected.name} [{selected.collection}]\nNow send your OMR image as a file. A new caption can select another exam.")

    async def media(self, update, context):
        owner = self.owner(update)
        if owner is None:
            return
        self.sessions.cleanup()
        message = update.effective_message
        name = (message.caption or "").strip() or self.selected.get(owner, "")
        if not name:
            await self.send(update, "Add the exam name as the image caption, or choose it with /exam NAME first")
            return
        exam = await self.choose(update, name)
        if not exam:
            return
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

    async def callback(self, update, context):
        await update.callback_query.answer()
        if self.owner(update) is None:
            return
        if update.callback_query.data.startswith("confirm:"):
            await self.confirm(update,context)
        else:
            try:
                session=self.sessions.get(self.owner(update))
                if update.callback_query.data.split(":")[1] != session.id:
                    raise ValueError("This preview was replaced")
                await self.cancel(update,context)
            except ValueError as exc:
                await self.send(update,str(exc))


def run():
    settings = Settings.from_env()
    bot = Bot(settings)
    # Sequential processing keeps each user's upload/review/confirm lifecycle ordered.
    app = Application.builder().token(settings.token).concurrent_updates(False).build()
    for command in ("start","exams","exam","fix","confirm","cancel","whoami"):
        app.add_handler(CommandHandler(command,getattr(bot,command)))
    app.add_handler(CallbackQueryHandler(bot.callback,pattern=r"^(confirm|cancel):[a-f0-9]{12}:\d+$"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE,bot.media))

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
