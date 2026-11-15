import json
from pathlib import Path
import cv2
from omr_check.recognition import Recognizer
from omr_check.domain import MarkState
ROOT=Path(__file__).resolve().parents[1]
recognizer=Recognizer(ROOT/'assets')
expected=json.loads((ROOT/'data/sample_expected.json').read_text())
for name,item in expected.items():
    result=recognizer.read(ROOT/'omr-exam-paper-example'/item['file'])
    mismatches=[]
    for mark,answer in zip(result.marks,item['answers']):
        actual=mark.choices[0] if mark.state==MarkState.SINGLE else '-' if mark.state==MarkState.BLANK else mark.state.value
        if actual!=answer:mismatches.append((mark.number,answer,actual,mark.strengths))
    print(name,result.template_id,len(mismatches),'mismatches',mismatches,flush=True)
    cv2.imwrite(str(ROOT/'var'/f'{name}-checked.jpg'),result.annotated)
    (ROOT/'var'/f'{name}-checked.json').write_text(json.dumps({'template':result.template_id,'marks':[{'number':m.number,'state':m.state.value,'choices':m.choices,'strengths':m.strengths} for m in result.marks]},indent=2))
