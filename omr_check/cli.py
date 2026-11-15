from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import Catalog
from .domain import Mark, MarkState, grade
from .reporting import format_grade
from .settings import ROOT


def main():
    parser = argparse.ArgumentParser(description="Reviewable OMR checker")
    parser.add_argument("--keys",type=Path,default=ROOT/"data/answer_keys.json")
    subs = parser.add_subparsers(dest="command",required=True)
    subs.add_parser("bot",help="Run the Telegram bot")
    review=subs.add_parser("review-keys",help="Review and verify source keys locally")
    review.add_argument("--port",type=int,default=8765)
    subs.add_parser("exams",help="List exam names and verification status")
    subs.add_parser("validate-keys",help="Check key structure and report missing questions")
    inspect=subs.add_parser("inspect",help="Recognize either OMR layout without needing an exam")
    inspect.add_argument("image",type=Path)
    inspect.add_argument("--output",type=Path,default=ROOT/"var/latest")
    scoring=subs.add_parser("grade",help="Grade a confirmed reading against a verified key")
    scoring.add_argument("--exam",required=True)
    scoring.add_argument("--reading",required=True,type=Path)
    scoring.add_argument("--confirm",action="store_true")
    args=parser.parse_args()
    try:
        if args.command == "review-keys":
            from .review import serve
            serve(args.keys,args.port)
            return
        if args.command == "bot":
            from .bot import run
            run()
            return
        if args.command == "inspect":
            from .recognition import Recognizer
            from .reporting import reading_text
            import cv2
            reading=Recognizer(ROOT/"assets").read(args.image)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            payload={"template":reading.template_id,"alignment":reading.alignment,"marks":[{"number":m.number,"state":m.state.value,"choices":m.choices,"strengths":m.strengths,"note":m.note} for m in reading.marks]}
            args.output.with_suffix(".json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
            cv2.imwrite(str(args.output.with_suffix(".jpg")),reading.annotated)
            print(reading.template_id,reading.alignment)
            print(reading_text(reading.marks))
            return
        catalog=Catalog(args.keys)
        if args.command in {"exams","validate-keys"}:
            incomplete=0
            for exam in catalog.exams.values():
                missing=sorted(set(range(1,101))-set(exam.answers))
                print(f"{exam.id}: {exam.name} [{exam.collection}] — {'VERIFIED' if exam.verified else 'DRAFT'}; {len(exam.answers)}/100 answers")
                if missing:
                    incomplete+=1
                    print("  Missing:",", ".join(map(str,missing)))
            print(f"{len(catalog.exams)} exams; {sum(e.verified for e in catalog.exams.values())} verified; {incomplete} incomplete")
            return
        matches=catalog.match(args.exam)
        if len(matches)!=1:
            raise ValueError("Exam name is missing or ambiguous. Run exams and use its exact ID")
        raw=json.loads(args.reading.read_text(encoding="utf-8"))
        marks=[Mark(m["number"],MarkState(m["state"]),tuple(m.get("choices",[]))) for m in raw["marks"]]
        print(format_grade(grade(matches[0],marks,confirmed=args.confirm)))
    except (ValueError,FileNotFoundError,KeyError) as exc:
        parser.exit(2,f"{exc}\n")


if __name__ == "__main__":
    main()
