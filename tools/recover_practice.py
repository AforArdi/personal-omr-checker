"""Recover missing practice-book OCR cells using the printed 50-row grids.

Detected question cells anchor row spacing; available number reads anchor the
question offset. Output remains a source-linked draft for visual verification.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .extract_keys import ROOT,load,ocr_strip


def recover(path):
    raw=json.loads(path.read_text(encoding="utf-8"))
    image=load(ROOT/"omr-check-answer-sheet-images"/raw["source"])
    number=raw["source"].split("-")[-1].split(".")[0]
    layouts=json.loads((ROOT/"data/source_layouts.json").read_text(encoding="utf-8"))[number]
    output=[]
    for left,right,name in layouts:
        x0,x1=left*image.shape[1],right*image.shape[1]
        width=x1-x0
        for half in (0,1):
            low=x0+width*half*.5
            high=low+width*.32
            cells=[b for b in raw["boxes"] if low+width*.04<b[0]+b[2]/2<high and width*.18<b[2]<width*.42]
            if len(cells)<20:continue
            median=np.median([b[3] for b in cells])
            cells=sorted([b for b in cells if median*.65<b[3]<median*1.4],key=lambda b:b[1]+b[3]/2)
            ys=[]; kept=[]
            for b in cells:
                y=b[1]+b[3]/2
                if not ys or y-ys[-1]>median*.45:ys.append(y);kept.append(b)
            if len(ys)<20:continue
            steps=np.diff(ys); pitch=float(np.median(steps))
            positions=[0]
            for delta in steps:positions.append(positions[-1]+max(1,round(delta/pitch)))
            if positions[-1]>53:continue
            votes=[]
            for record in raw["readings"]:
                q=record["question"]
                center=record["number_box"][0]+record["number_box"][2]/2
                if not (low<center<high and (1<=q<=50 if half==0 else 51<=q<=100)):continue
                y=record["number_box"][1]+record["number_box"][3]/2
                near=int(np.argmin(abs(np.array(ys)-y)))
                if abs(ys[near]-y)<pitch*.4:votes.append(q-positions[near])
            if not votes:continue
            offset,support=Counter(votes).most_common(1)[0]
            if support<2 or support/len(votes)<.65:continue
            q=np.array(positions)+offset
            expected=np.arange(1,51)+half*50
            yvalues=np.interp(expected,q,ys)
            # Extrapolate only to the grid's edge, at most two missing cells.
            if expected[0]<q[0]:yvalues[expected<q[0]]=ys[0]+(expected[expected<q[0]]-q[0])*pitch
            if expected[-1]>q[-1]:yvalues[expected>q[-1]]=ys[-1]+(expected[expected>q[-1]]-q[-1])*pitch
            if q[0]-expected[0]>2 or expected[-1]-q[-1]>2:continue
            edge=np.polyfit(ys,[b[0]+b[2] for b in kept],1)
            glyph_boxes=[]; number_boxes=[]
            for number,y in zip(expected,yvalues):
                letter_x=int(np.polyval(edge,y))
                letter_w=round(width*.18)
                h=round(median*.72)
                glyph_boxes.append((letter_x,max(0,round(y-h/2)),letter_w,h))
                number_boxes.append((round(letter_x-width*.31),max(0,round(y-h/2)),round(width*.31),h))
            answers=ocr_strip(image,glyph_boxes,"ABCD")
            for index,(q,y) in enumerate(zip(expected,yvalues)):
                answer,confidence=answers.get(index,("",0))
                if not answer or any(c not in "ABCD" for c in answer) or len(set(answer))!=len(answer):continue
                output.append(dict(question=int(q),answer=sorted(answer),confidence=confidence,box=glyph_boxes[index],number_box=number_boxes[index],method="grid-recovery",sequence_support=support))
    return dict(source=raw["source"],readings=output)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--only");args=parser.parse_args()
    source=ROOT/"var/key-extraction";target=ROOT/"var/key-recovered";target.mkdir(parents=True,exist_ok=True)
    for path in sorted(source.glob("model-ans-pic-*.json")):
        if args.only and path.name!=args.only:continue
        if (target/path.name).exists():continue
        result=recover(path)
        (target/path.name).write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(f"{path.name}: {len(result['readings'])} recovered glyph reads",flush=True)


if __name__=="__main__":main()
