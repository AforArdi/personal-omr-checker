from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class MarkState(StrEnum):
    SINGLE = "single"
    BLANK = "blank"
    MULTIPLE = "multiple"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class Mark:
    number: int
    state: MarkState
    choices: tuple[str, ...] = ()
    strengths: tuple[float, ...] = ()
    note: str = ""

    def __post_init__(self):
        if not 1 <= self.number <= 100:
            raise ValueError("Question number must be 1–100")
        if any(c not in "ABCD" or len(c) != 1 for c in self.choices):
            raise ValueError("Choices must be A, B, C, or D")
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("Duplicate choices")
        if self.state == MarkState.SINGLE and len(self.choices) != 1:
            raise ValueError("A single mark requires exactly one choice")
        if self.state == MarkState.BLANK and self.choices:
            raise ValueError("A blank answer cannot contain choices")
        if self.state == MarkState.MULTIPLE and len(self.choices) < 2:
            raise ValueError("A multiple mark requires at least two choices")


@dataclass(frozen=True)
class Exam:
    id: str
    name: str
    collection: str
    answers: dict[int, frozenset[str]]
    verified: bool
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionResult:
    number: int
    outcome: str
    selected: tuple[str, ...]
    accepted: tuple[str, ...]


@dataclass(frozen=True)
class Grade:
    exam_name: str
    score: Decimal
    questions: tuple[QuestionResult, ...]

    def numbers(self, outcome: str) -> list[int]:
        return [q.number for q in self.questions if q.outcome == outcome]


def grade(exam: Exam, marks: list[Mark], *, confirmed: bool) -> Grade:
    """No clamping: C - 0.25(W + M + I), equivalent to 100 - 1.25E - B."""
    if not confirmed:
        raise ValueError("Confirm the detected reading before grading")
    if not exam.verified:
        raise ValueError("This answer key has not been verified against its source")
    expected = set(range(1, 101))
    if set(exam.answers) != expected or any(not a or not a <= set("ABCD") for a in exam.answers.values()):
        raise ValueError("Exam must contain 100 valid answer entries")
    if len(marks) != 100 or {m.number for m in marks} != expected:
        raise ValueError("Reading must contain each question 1–100 exactly once")
    if any(m.state == MarkState.UNCERTAIN for m in marks):
        raise ValueError("Resolve all uncertain readings before grading")
    score = Decimal(0)
    results = []
    for mark in sorted(marks, key=lambda m: m.number):
        accepted = exam.answers[mark.number]
        if mark.state == MarkState.SINGLE:
            outcome = "correct" if mark.choices[0] in accepted else "wrong"
        else:
            outcome = mark.state.value
        score += Decimal(1) if outcome == "correct" else Decimal(0) if outcome == "blank" else Decimal("-0.25")
        results.append(QuestionResult(mark.number, outcome, mark.choices, tuple(sorted(accepted))))
    return Grade(exam.name, score, tuple(results))
