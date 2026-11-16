"""Reproduce realistic upload variations from the two supplied real samples."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np

from omr_check.recognition import Recognizer,RecognitionError,load_image
from omr_check.alignment import StructuralAligner,find_columns,column_groups,locate_rows,_column_view

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'var/recognition-regressions'


def make_cases():
    OUT.mkdir(parents=True,exist_ok=True)
    golden=json.loads((ROOT/'data/sample_expected.json').read_text())
    result=[]
    for layout,spec in golden.items():
        source=load_image(ROOT/'omr-exam-paper-example'/spec['file'])
        crop=source[510:1235,125:800] if layout=='retina' else source[480:1200,105:670]
        cropped=cv2.resize(crop,(720,round(crop.shape[0]*720/crop.shape[1])))
        small=cv2.resize(crop,(640,round(crop.shape[0]*640/crop.shape[1])))
        h,w=cropped.shape[:2]
        transform=cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),np.float32([[35,20],[w-20,2],[w-2,h-30],[2,h-5]]))
        perspective=cv2.warpPerspective(cropped,transform,(w,h),borderValue=(255,255,255))
        incomplete=crop[:480,:]
        for name,image,answers in [
            ('original',source,spec['answers']),
            ('crop-jpeg',cropped,spec['answers']),
            ('crop-640',small,spec['answers']),
            ('rotated',cv2.rotate(cropped,cv2.ROTATE_90_CLOCKWISE),spec['answers']),
            ('perspective',perspective,spec['answers']),
            ('incomplete-grid',incomplete,None),
        ]:
            path=OUT/f'{layout}-{name}.jpg'
            if not path.exists():cv2.imwrite(str(path),image,[cv2.IMWRITE_JPEG_QUALITY,75])
            result.append((layout,name,path,answers))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',default='fixed');parser.add_argument('--structural-only',action='store_true');parser.add_argument('--case',action='append');args=parser.parse_args()
    reader=Recognizer(ROOT/'assets')
    structural=StructuralAligner(reader.templates,json.loads((ROOT/'assets/layout_geometry.json').read_text()))
    report=[]
    for layout,name,path,expected in make_cases():
        if args.case and name not in args.case:continue
        start=time.perf_counter()
        item={'layout':layout,'case':name}
        try:
            if args.structural_only:
                image=load_image(path)
                groups=column_groups(image,find_columns(image))
                item['groups']=[{'layout':kind,'rows':[None if (rows:=locate_rows(_column_view(image,q),kind)) is None else [round(float(rows[0]),1),round(float(rows[-1]),1)] for q in group]} for kind,group in groups]
                result=structural.align(image)
                item['accepted']=result is not None
                if result:item.update(template=result[1].id,coverage=result[0],rows=result[3].row_coverage)
            else:
                result=reader.read(path)
                if expected is None:
                    item.update(accepted=True,template=result.template_id,unexpected_accept=True)
                else:
                    errors=[];uncertain=[]
                    for mark,answer in zip(result.marks,expected):
                        if mark.state.value=='uncertain':uncertain.append(mark.number);continue
                        actual=mark.choices[0] if mark.state.value=='single' else '-' if mark.state.value=='blank' else mark.state.value
                        if actual!=answer:errors.append({'question':mark.number,'expected':answer,'actual':actual})
                    item.update(accepted=True,template=result.template_id,alignment=result.alignment,confident_errors=errors,uncertain=uncertain)
                    cv2.imwrite(str(OUT/f'{layout}-{name}-{args.phase}-preview.jpg'),result.annotated)
        except RecognitionError as exc:
            item.update(accepted=False,error=str(exc))
        item['seconds']=round(time.perf_counter()-start,2)
        report.append(item)
        print(json.dumps(item),flush=True)
        (OUT/f'{args.phase}.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
