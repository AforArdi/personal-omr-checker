"""Conservative source-key extraction. OCR creates DRAFT keys, never approval.

Each answer is tied to an explicit printed question-number cell. Missing or
conflicting reads are retained as issues; explanation text is never used as a key.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[1]
cv2.setNumThreads(1)
os.environ.setdefault("OMP_THREAD_LIMIT","1")
if Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists():
    pytesseract.pytesseract.tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def load(path):
    with Image.open(path) as image:
        return cv2.cvtColor(np.array(ImageOps.exif_transpose(image).convert("RGB")),cv2.COLOR_RGB2BGR)


def cells(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,35,12)
    vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,55)))
    horizontal=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(25,1)))
    grid=vertical|horizontal
    grid=cv2.morphologyEx(grid,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(grid,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if 30<w<320 and 20<h<210 and w*h<43000:
            if not any(abs(x-a)<4 and abs(y-b)<4 and abs(w-c)<6 and abs(h-d)<6 for a,b,c,d in boxes):
                boxes.append((x,y,w,h))
    return sorted(boxes,key=lambda b:(b[1],b[0])),grid


def ocr_strip(image,boxes,whitelist,psm=6):
    """One isolated cell per fixed-height line; box-to-line mapping cannot shift."""
    if not boxes: return {}
    height=72; width=180
    strip=np.full((height*len(boxes),width),255,np.uint8)
    for index,(x,y,w,h) in enumerate(boxes):
        crop=image[max(0,y+4):min(image.shape[0],y+h-4),max(0,x+4):min(image.shape[1],x+w-4)]
        if not crop.size: continue
        crop=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        crop=cv2.normalize(crop,None,0,255,cv2.NORM_MINMAX)
        crop=cv2.threshold(crop,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
        # Remove rule remnants that touch the crop's edge, retaining actual glyphs.
        inv=255-crop
        n,labels,stats,_=cv2.connectedComponentsWithStats(inv)
        for label in range(1,n):
            left,top,cw,ch,area=stats[label]
            if (cw>crop.shape[1]*.7 and ch<crop.shape[0]*.45) or (ch>crop.shape[0]*.8 and cw<crop.shape[1]*.12):
                crop[labels==label]=255
        ys,xs=np.where(crop<128)
        if not len(xs): continue
        crop=crop[ys.min():ys.max()+1,xs.min():xs.max()+1]
        scale=min(42/crop.shape[0],110/crop.shape[1])
        crop=cv2.resize(crop,(max(1,round(crop.shape[1]*scale)),max(1,round(crop.shape[0]*scale))))
        x0=(width-crop.shape[1])//2; y0=index*height+(height-crop.shape[0])//2
        strip[y0:y0+crop.shape[0],x0:x0+crop.shape[1]]=crop
    data=pytesseract.image_to_data(strip,config=f"--psm {psm} -c tessedit_char_whitelist={whitelist}",output_type=pytesseract.Output.DICT)
    readings=defaultdict(list)
    for i,text in enumerate(data["text"]):
        text=text.strip()
        if text:
            row=int((data["top"][i]+data["height"][i]/2)//height)
            if 0<=row<len(boxes): readings[row].append((text,float(data["conf"][i])))
    return {row:("".join(t for t,c in values),min(c for t,c in values)) for row,values in readings.items()}


def adjacent_pairs(boxes):
    pairs=[]
    for left in boxes:
        x,y,w,h=left
        possible=[right for right in boxes if 0<=right[0]-(x+w)<12 and abs(right[1]-y)<max(9,h*.14) and abs(right[3]-h)<max(10,h*.2)]
        if possible:
            right=min(possible,key=lambda r:abs(r[1]-y))
            pairs.append((left,right))
    return pairs


def extract(path):
    image=load(path)
    boxes,grid=cells(image)
    pairs=adjacent_pairs(boxes)
    questions={}
    answers={}
    readings=[]
    for index,(left,right) in enumerate(pairs):
        number,nc=questions.get(index,("",0)); answer,ac=answers.get(index,("",0))
        if number.isdigit() and 1<=int(number)<=100 and re.fullmatch(r"[ABCD]{1,4}",answer) and len(set(answer))==len(answer):
            readings.append(dict(question=int(number),answer=sorted(answer),confidence=round(min(nc,ac),2),box=right,number_box=left))
    # Cell contours can be broken by page curvature. Fit the narrow printed
    # columns, then OCR continuous column strips with original y coordinates.
    readings.extend(column_reads(image,boxes,0.60 if path.name.startswith("model-ans-pic-") else 1.0))
    unique={}
    for record in readings:
        key=(record['question'],round((record['box'][0]+record['box'][2]/2)/70))
        if key not in unique or record['confidence']>unique[key]['confidence']:
            unique[key]=record
    return image,boxes,grid,list(unique.values())


def column_reads(image,boxes,answer_ratio=1.0):
    clusters=[]
    for box in sorted(boxes,key=lambda b:b[0]+b[2]/2):
        center=box[0]+box[2]/2
        if clusters and abs(center-np.median([b[0]+b[2]/2 for b in clusters[-1]]))<42:
            clusters[-1].append(box)
        else:
            clusters.append([box])
    clusters=[c for c in clusters if len(c)>=12 and np.ptp([b[1] for b in c])>image.shape[0]*.35]
    results=[]
    for index,col in enumerate(clusters):
        y=np.array([b[1]+b[3]/2 for b in col])
        left=np.polyfit(y,[b[0] for b in col],min(2,len(col)-1))
        right=np.polyfit(y,[b[0]+b[2] for b in col],min(2,len(col)-1))
        y0=0
        y1=image.shape[0]
        yy=np.arange(y0,y1,dtype=np.float32)
        l=np.polyval(left,yy)+7; r=np.polyval(right,yy)-7
        xx=l[:,None]+(r-l)[:,None]*np.linspace(0,1,160)[None,:]
        strip=cv2.remap(image,xx.astype(np.float32),np.broadcast_to(yy[:,None],xx.shape).copy(),cv2.INTER_CUBIC,borderValue=(255,255,255))
        gray=cv2.cvtColor(strip,cv2.COLOR_BGR2GRAY)
        binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,35,12)
        lines=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(45,1)))
        clean=255-(binary & ~cv2.dilate(lines,np.ones((2,1),np.uint8)))
        results.append((col,left,right,clean,y0))
    if not results: return []
    mosaic=np.full((image.shape[0],200*len(results)),255,np.uint8)
    for index,(_,_,_,clean,y0) in enumerate(results):
        mosaic[y0:y0+clean.shape[0],index*200+20:index*200+180]=clean
    cv2.imwrite(str(ROOT/".runtime/ocr-mosaic.png"),mosaic)
    decoded=[[[],[]] for _ in results]
    for index,(_,_,_,clean,y0) in enumerate(results):
        data=pytesseract.image_to_data(clean,config='--psm 6 -c tessedit_char_whitelist=0123456789',output_type=pytesseract.Output.DICT)
        for i,text in enumerate(data['text']):
            text=text.strip()
            if text:
                decoded[index][0].append((text,y0+data['top'][i]+data['height'][i]/2,float(data['conf'][i]),data['height'][i]))
    (ROOT/".runtime/ocr-decoded.json").write_text(json.dumps(decoded,indent=2),encoding="utf-8")
    records=[]
    from collections import Counter
    for index,(col,left,right,clean,y0) in enumerate(results):
        nums=[w for w in decoded[index][0] if w[0].isdigit() and 1<=int(w[0])<=100]
        if len(nums)<10: continue
        n,labels,stats,centroids=cv2.connectedComponentsWithStats(255-clean)
        glyphs=sorted([(int(y),int(y+h),float(cy)) for (_,y,w,h,area),(cx,cy) in zip(stats[1:],centroids[1:]) if h>=12 and h<100 and w>=4 and area>=35 and 30<cx<130],key=lambda g:g[2])
        groups=[]
        for glyph in glyphs:
            if groups and abs(glyph[2]-np.mean([g[2] for g in groups[-1]]))<16:
                groups[-1].append(glyph)
            else: groups.append([glyph])
        rows=[(min(g[0] for g in group),max(g[1] for g in group)) for group in groups]
        centers=np.array([(a+b)/2 for a,b in rows])
        if not len(centers): continue
        votes=[]
        for text,y,confidence,height in nums:
            nearest=int(np.argmin(abs(centers-y)))
            if abs(centers[nearest]-y)<18: votes.append(int(text)-nearest)
        if not votes: continue
        offset,count=Counter(votes).most_common(1)[0]
        if count<8 or count/max(1,len(votes))<.55: continue
        center=np.median([b[0]+b[2]/2 for b in col])
        others=[item for item in results if 30<np.median([b[0]+b[2]/2 for b in item[0]])-center<220]
        number_width=float(np.median([b[2] for b in col]))
        others=[item for item in others if np.median([b[0]+b[2]/2 for b in item[0]])-center<number_width*1.3]
        if others:
            answer_col,al,ar,_,_=min(others,key=lambda item:np.median([b[0]+b[2]/2 for b in item[0]]))
        else:
            al=right.copy()
            ar=right+(right-left)*answer_ratio
        selected=[]; boxes_for_ocr=[]
        for row_index,(a,b) in enumerate(rows):
            number=row_index+offset
            if not 1<=number<=100: continue
            y=(a+b)/2
            x=int(np.polyval(al,y)); w=int(np.polyval(ar,y)-x)
            selected.append((number,y))
            boxes_for_ocr.append((max(0,x),max(0,a-8),w,b-a+16))
        answers=ocr_strip(image,boxes_for_ocr,'ABCD')
        for row_index,(number,y) in enumerate(selected):
            answer,confidence=answers.get(row_index,('',0))
            if not re.fullmatch('[ABCD]{1,4}',answer) or len(set(answer))!=len(answer): continue
            box=boxes_for_ocr[row_index]
            nx=int(np.polyval(left,y)); nw=int(np.polyval(right,y)-nx)
            records.append(dict(question=number,answer=sorted(answer),confidence=confidence,box=box,number_box=[nx,box[1],nw,box[3]],method='sequence-anchored-column',sequence_support=count))
    return records



def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="omr-check-answer-sheet-images")
    parser.add_argument("--only")
    parser.add_argument("--output",default="var/key-extraction-v2")
    args=parser.parse_args()
    out=ROOT/args.output; out.mkdir(parents=True,exist_ok=True)
    source=ROOT/args.source
    files=[source/args.only] if args.only else sorted(p for p in source.glob("*.jpg") if re.match(r"(?:model-ans-pic-\d+|model-test-.+|paper-final-.+|subject-final-.+)\.jpg$",p.name))
    for path in files:
        output=out/(path.stem+".json")
        if output.exists() and not args.only:
            continue
        image,boxes,grid,readings=extract(path)
        output.write_text(json.dumps({"source":path.name,"boxes":boxes,"readings":readings},indent=2),encoding="utf-8")
        overlay=image.copy()
        for i,item in enumerate(readings):
            x,y,w,h=item["box"]
            cv2.rectangle(overlay,(x,y),(x+w,y+h),(0,150,0),2)
            cv2.putText(overlay,f"{item['question']}={''.join(item['answer'])}",(x,y-3),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,220),2)
        cv2.imwrite(str(out/(path.stem+"-detected.jpg")),overlay)
        print(f"{path.name}: {len(boxes)} cells; {len(readings)} paired question/answer reads",flush=True)


if __name__=="__main__": main()
