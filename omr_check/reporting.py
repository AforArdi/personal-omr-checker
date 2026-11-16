from .domain import Grade, Mark, MarkState


def reading_text(marks: list[Mark]) -> str:
    labels = {MarkState.BLANK: "blank", MarkState.INVALID: "invalid", MarkState.UNCERTAIN: "REVIEW"}
    return "\n".join("  |  ".join(f"{m.number}: {labels.get(m.state, '+'.join(m.choices))}" for m in marks[i:i+5]) for i in range(0, 100, 5))


def format_grade(result: Grade) -> str:
    def q_list(kind: str) -> str:
        nums = result.numbers(kind)
        return ", ".join(f"Q{n}" for n in nums) if nums else "none"

    correct = result.numbers("correct")
    wrong = result.numbers("wrong")
    blank = result.numbers("blank")
    multiple = result.numbers("multiple")
    invalid = result.numbers("invalid")

    lines = [
        result.exam_name,
        f"Score: {result.score:.2f} / 100",
        f"Correct: {len(correct)}",
        f"Wrong answers: {len(wrong)}",
        f"Unanswered: {len(blank)}",
        f"Multiple-marked: {len(multiple)}",
        f"Invalid-marked: {len(invalid)}",
        "",
        f"Wrong question numbers: {q_list('wrong')}",
        f"Unanswered question numbers: {q_list('blank')}",
        f"Multiple-marked question numbers: {q_list('multiple')}",
        f"Invalid-marked question numbers: {q_list('invalid')}",
    ]
    details = [
        f"Q{q.number}: {'+'.join(q.selected) or q.outcome} → {' or '.join(q.accepted)}"
        for q in result.questions
        if q.outcome in {"wrong", "multiple", "invalid"}
    ]
    if details:
        lines += ["", "Your answer → accepted answer:", *details]
    return "\n".join(lines)
