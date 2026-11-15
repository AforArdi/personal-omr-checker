from decimal import Decimal

import pytest

from omr_check.domain import Exam, Mark, MarkState, grade
from omr_check.sessions import parse_corrections


def exam(verified=True):
    return Exam("test", "Test", "Fixture", {n:frozenset("A") for n in range(1,101)}, verified)


def reading(state=MarkState.SINGLE, choices=("A",)):
    return [Mark(n,state,choices) for n in range(1,101)]


def test_perfect_and_all_blank_and_negative():
    assert grade(exam(),reading(),confirmed=True).score == Decimal(100)
    assert grade(exam(),reading(MarkState.BLANK,()),confirmed=True).score == Decimal(0)
    assert grade(exam(),reading(choices=("B",)),confirmed=True).score == Decimal(-25)


def test_loss_from_100_is_not_subtracted_twice():
    marks=reading()
    for n in range(80,92): marks[n]=Mark(n+1,MarkState.SINGLE,("B",))
    for n in range(92,100): marks[n]=Mark(n+1,MarkState.BLANK)
    result=grade(exam(),marks,confirmed=True)
    assert result.score == Decimal(77)
    assert result.numbers("wrong") == list(range(81,93))
    assert result.numbers("blank") == list(range(93,101))


def test_either_accepted_choice_but_double_fill_still_wrong():
    key=exam()
    key.answers[74]=frozenset("BC")
    for choice in ("B","C"):
        marks=reading(); marks[73]=Mark(74,MarkState.SINGLE,(choice,))
        assert grade(key,marks,confirmed=True).score == Decimal(100)
    marks[73]=Mark(74,MarkState.MULTIPLE,("B","C"))
    assert grade(key,marks,confirmed=True).score == Decimal("98.75")


def test_invalid_marks_have_same_penalty_as_wrong():
    assert grade(exam(),reading(MarkState.INVALID),confirmed=True).score == Decimal(-25)


@pytest.mark.parametrize("kind",["unconfirmed","unverified","uncertain","duplicate","missing"])
def test_never_grade_unresolved_or_untrusted_inputs(kind):
    key=exam(kind!="unverified"); marks=reading()
    if kind=="uncertain": marks[0]=Mark(1,MarkState.UNCERTAIN)
    if kind=="duplicate": marks[1]=marks[0]
    if kind=="missing": marks.pop()
    with pytest.raises(ValueError):
        grade(key,marks,confirmed=kind!="unconfirmed")


def test_corrections_preserve_multiple_and_invalid_states():
    values=parse_corrections("1=a 2=blank 3=invalid 4=B+C")
    assert values[1].choices == ("A",)
    assert values[2].state == MarkState.BLANK
    assert values[3].state == MarkState.INVALID
    assert values[4].state == MarkState.MULTIPLE


@pytest.mark.parametrize("value",["0=A","101=B","1=X","1=A+A","1=A 1=B","1=", "1=AB"])
def test_reject_invalid_corrections(value):
    with pytest.raises(ValueError): parse_corrections(value)
