from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .domain import Exam


def normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold(), re.UNICODE))


class Catalog:
    def __init__(self, file: Path):
        raw = json.loads(file.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 1:
            raise ValueError("Unsupported answer database version")
        self.exams: dict[str, Exam] = {}
        self.index: dict[str, set[str]] = {}
        for item in raw["exams"]:
            answers = {}
            for number, value in item["answers"].items():
                n = int(number)
                if not 1 <= n <= 100:
                    raise ValueError("Question numbers must be 1–100")
                if value is None:
                    if item.get("status") == "verified":
                        raise ValueError("Verified keys cannot contain unresolved answers")
                    continue
                if not isinstance(value, (str, list)):
                    raise ValueError("Accepted answers must be a letter or list of letters")
                if n in answers:
                    raise ValueError(f"Duplicate question {n} in {item['id']}")
                values = value if isinstance(value, list) else list(value)
                if not values or any(c not in ("A", "B", "C", "D") for c in values) or len(set(values)) != len(values):
                    raise ValueError(f"Invalid key entry {item['id']} / {n}")
                answers[n] = frozenset(values)
            if any(n not in range(1, 101) for n in answers):
                raise ValueError("Question numbers must be 1–100")
            verified = item.get("status") == "verified"
            if verified and (set(answers) != set(range(1, 101)) or item.get("issues")):
                raise ValueError(f"Verified key {item['id']} has missing answers or open issues")
            exam = Exam(item["id"], item["name"], item["collection"], answers, verified, tuple(item.get("aliases", [])))
            if exam.id in self.exams:
                raise ValueError("Duplicate exam ID")
            self.exams[exam.id] = exam
            for name in (exam.id, exam.name, *exam.aliases):
                self.index.setdefault(normalize_name(name), set()).add(exam.id)

    def match(self, query: str) -> list[Exam]:
        # Never silently fuzzy-match an exam. Similar names may have different keys.
        return [self.exams[i] for i in sorted(self.index.get(normalize_name(query), set()))]

    def search(self, query: str) -> list[Exam]:
        tokens = set(normalize_name(query).split())
        return sorted((e for e in self.exams.values() if tokens and tokens <= set(normalize_name(e.name + " " + e.collection).split())), key=lambda e: (e.collection, e.name))
