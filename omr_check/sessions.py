from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .domain import Mark, MarkState
from .recognition import Reading


@dataclass
class Session:
    id: str
    user_id: int
    exam_id: str
    directory: Path
    reading: Reading
    expires_at: float
    revision: int = 0
    edits: list[dict] = field(default_factory=list)

    def audit(self):
        value = {"session_id": self.id, "exam_id": self.exam_id, "template": self.reading.template_id,
                 "alignment": self.reading.alignment, "revision": self.revision, "expires_at": self.expires_at,
                 "marks": [{"number": m.number, "state": m.state.value, "choices": list(m.choices), "strengths": list(m.strengths)} for m in self.reading.marks], "edits": self.edits}
        temporary = self.directory / "reading.tmp"
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(self.directory / "reading.json")


def parse_corrections(value: str) -> dict[int, Mark]:
    tokens = value.replace(",", " ").split()
    if not tokens or len(tokens) > 100:
        raise ValueError("Use /fix 12=A 27=blank 40=invalid 51=A+B")
    result = {}
    for token in tokens:
        try:
            left, right = token.split("=", 1)
            number = int(left)
            if number in result:
                raise ValueError("Repeated question")
            right = right.upper()
            if right == "BLANK":
                mark = Mark(number, MarkState.BLANK)
            elif right == "INVALID":
                mark = Mark(number, MarkState.INVALID)
            else:
                choices = tuple(right.split("+"))
                mark = Mark(number, MarkState.SINGLE if len(choices) == 1 else MarkState.MULTIPLE, choices)
            result[number] = mark
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid correction: {token}. Use 12=A, 27=blank, 40=invalid, or 51=A+B") from exc
    return result


class SessionStore:
    def __init__(self, directory: Path, ttl_minutes: int):
        self.directory = directory / "sessions"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_minutes * 60
        self.items: dict[int, Session] = {}
        # Sessions are intentionally not resumed after a restart: confirmations cannot
        # accidentally apply to a stale recognition result.
        self.cleanup()

    def cleanup(self):
        now = time.time()
        for owner, item in list(self.items.items()):
            if item.expires_at <= now:
                self.discard(owner)
        active = {s.directory.name for s in self.items.values()}
        for directory in self.directory.iterdir():
            if directory.is_dir() and directory.name not in active and directory.stat().st_mtime < now-self.ttl:
                shutil.rmtree(directory)

    def allocate(self) -> Path:
        directory = self.directory / uuid.uuid4().hex
        directory.mkdir()
        return directory

    def create(self, owner: int, exam_id: str, directory: Path, reading: Reading) -> Session:
        self.discard(owner)
        item = Session(uuid.uuid4().hex[:12], owner, exam_id, directory, reading, time.time()+self.ttl)
        self.items[owner] = item
        item.audit()
        return item

    def get(self, owner: int) -> Session:
        self.cleanup()
        if owner not in self.items:
            raise ValueError("No active reading. Upload your OMR photo with its exam name")
        return self.items[owner]

    def discard(self, owner: int):
        old = self.items.pop(owner, None)
        if old:
            shutil.rmtree(old.directory, ignore_errors=True)
