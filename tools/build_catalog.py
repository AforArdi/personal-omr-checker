"""Assemble source-linked DRAFT answer keys. Never marks OCR as verified."""
import json
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image,ImageOps

ROOT=Path(__file__).resolve().parents[1]


def slug(value):
    return re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-")


def main():
    layouts=json.loads((ROOT/"data/source_layouts.json").read_text(encoding="utf-8"))
    exams={}
    observations=defaultdict(lambda:defaultdict(list))
    def register(name,collection,source,aliases=()):
        identifier=("practice-" if collection=="Practice book" else "retina-")+slug(name)
        if identifier not in exams:
            exams[identifier]={"id":identifier,"name":name,"collection":collection,"aliases":list(aliases),"status":"draft","revision":0,"sources":[],"answers":{str(n):None for n in range(1,101)},"provenance":{},"issues":[]}
        if source not in exams[identifier]["sources"]:exams[identifier]["sources"].append(source)
        return identifier
    for number,spans in layouts.items():
        source=f"model-ans-pic-{number}.jpg"
        for left,right,name in spans:
            aliases=[]
            match=re.fullmatch(r"Model Test-(\d+)",name)
            if match:aliases=[f"Model Test {int(match[1])}"]
            register(name,"Practice book",source,aliases)
    retina={
      "model-test-one":"Model Test-01","model-test-two":"Model Test-02","model-test-three":"Model Test-03","model-test-four":"Model Test-04","model-test-five":"Model Test-05",
      "paper-final-botany":"Paper Final: Botany","paper-final-zoology":"Paper Final: Zoology",
      "paper-final-chemistry-1st":"Paper Final: Chemistry 1st","paper-final-chemistry-2nd":"Paper Final: Chemistry 2nd",
      "paper-final-physics-1st":"Paper Final: Physics 1st","paper-final-physics-2nd":"Paper Final: Physics 2nd",
      "paper-final-english":"Paper Final: English","paper-final-gk-tendencies-human-qualities":"Paper Final: GK, Tendencies and Human Qualities",
      "subject-final-biology":"Subject Final: Biology","subject-final-chemistry":"Subject Final: Chemistry","subject-final-physics":"Subject Final: Physics",
      "subject-final-english-gk-tendencies-human-qualities":"Subject Final: English & GK, Tendencies and Human Qualities",
    }
    for stem,name in retina.items():
        aliases=[stem]
        match=re.fullmatch(r"Model Test-(\d+)",name)
        if match:aliases.append(f"Model Test {int(match[1])}")
        for half in (1,2):register(name,"Retina",f"{stem}-{half}.jpg",aliases)
    for path in sorted(list((ROOT/"var/key-extraction").glob("*.json"))+list((ROOT/"var/key-recovered").glob("*.json"))+list((ROOT/"var/key-extraction-v2").glob("*.json"))):
        extracted=json.loads(path.read_text(encoding="utf-8"));source=extracted["source"]
        practice=re.fullmatch(r"model-ans-pic-(\d+)\.jpg",source)
        if practice:
            with Image.open(ROOT/"omr-check-answer-sheet-images"/source) as raw:width=ImageOps.exif_transpose(raw).width
            spans=layouts[practice[1]]
            for record in extracted["readings"]:
                x=(record["box"][0]+record["box"][2]/2)/width
                for left,right,name in spans:
                    if left<x<right:
                        observations["practice-"+slug(name)][record["question"]].append(dict(record,source=source))
                        break
        else:
            stem=re.sub(r"-[12]\.jpg$","",source)
            if stem not in retina:continue
            identifier="retina-"+slug(retina[stem])
            for record in extracted["readings"]:observations[identifier][record["question"]].append(dict(record,source=source))
    for identifier,exam in exams.items():
        for number,candidates in observations[identifier].items():
            selected=max(candidates,key=lambda c:c["confidence"])
            exam["answers"][str(number)]=selected["answer"]
            exam["provenance"][str(number)]=selected
            distinct={tuple(c["answer"]) for c in candidates}
            if len(distinct)>1:exam["issues"].append(f"Q{number}: conflicting OCR reads — compare original")
            elif selected["confidence"]<65:exam["issues"].append(f"Q{number}: low OCR confidence — compare original")
        missing=[str(n) for n in range(1,101) if exam["answers"][str(n)] is None]
        if missing:exam["issues"].append("Unresolved questions: "+", ".join(missing))
        exam["issues"].append("Every answer requires comparison with its printed source before verification")
    manual=ROOT/'data/manual_verified_keys.json'
    if manual.exists():
        for checked in json.loads(manual.read_text(encoding='utf-8')):
            exams[checked['id']].update(checked)
    destination=ROOT/"data/answer_keys.json"
    if destination.exists():
        old=json.loads(destination.read_text(encoding="utf-8"))
        # Never overwrite an existing reviewed or manually edited key.
        for exam in old["exams"]:
            if exam.get("review") or exam.get("status")=="verified":exams[exam["id"]]=exam
    result={"schema_version":1,"scoring":{"correct":"1","wrong":"-0.25","multiple":"-0.25","invalid":"-0.25","blank":"0","allow_negative":True},"exams":list(exams.values())}
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    count=sum(sum(v is not None for v in e["answers"].values()) for e in result["exams"])
    print(f"{len(exams)} exams; {count}/{len(exams)*100} answer candidates; {sum(e['status']=='verified' for e in exams.values())} verified",flush=True)


if __name__=="__main__":main()
