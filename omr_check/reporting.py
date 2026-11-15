from .domain import Grade, Mark, MarkState


def reading_text(marks: list[Mark]) -> str:
    labels = {MarkState.BLANK: "blank", MarkState.INVALID: "invalid", MarkState.UNCERTAIN: "REVIEW"}
    return "\n".join("  |  ".join(f"{m.number}: {labels.get(m.state, '+'.join(m.choices))}" for m in marks[i:i+5]) for i in range(0, 100, 5))


def format_grade(result: Grade) -> str:
    def numbers(kind):
        return ", ".join(map(str, result.numbers(kind))) or "none"
    lines = [result.exam_name, f"Score: {result.score:.2f} / 100", f"Correct: {len(result.numbers('correct'))}",
             f"Wrong: {len(result.numbers('wrong'))}", f"Unanswered: {len(result.numbers('blank'))}",
             f"Multiple: {len(result.numbers('multiple'))} | Invalid: {len(result.numbers('invalid'))}", "",
             f"Wrong questions: {numbers('wrong')}", f"Unanswered: {numbers('blank')}",
             f"Multiple-marked: {numbers('multiple')}", f"Invalid-marked: {numbers('invalid')}"]
    details = [f"Q{q.number}: {'+'.join(q.selected) or q.outcome} → {' or '.join(q.accepted)}"
               for q in result.questions if q.outcome in {"wrong", "multiple", "invalid"}]
    if details:
        lines += ["", "Your answer → accepted answer", *details]
    return "\n".join(lines)
