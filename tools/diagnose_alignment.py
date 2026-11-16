"""Inspect geometric form anchors without exposing any Telegram credentials."""
from pathlib import Path
import json

import cv2
import numpy as np

from omr_check.recognition import load_image


def red_mask(image):
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    return (((hsv[:,:,0]<25)|(hsv[:,:,0]>140))&(hsv[:,:,1]>20)&(hsv[:,:,2]>25)).astype(np.uint8)*255


def panels(image):
    mask=red_mask(image)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    found=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if h<image.shape[0]*.22 or not .10<w/h<.40:continue
        area=cv2.contourArea(contour)
        if area<w*h*.65:continue
        polygon=cv2.approxPolyDP(contour,cv2.arcLength(contour,True)*.015,True)
        found.append(dict(box=[x,y,w,h],area=round(area),quad=polygon.reshape(-1,2).tolist()))
    return found,mask


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'var/alignment-diagnostics';out.mkdir(parents=True,exist_ok=True)
    paths=list((root/'assets').glob('*.jpg'))+list((root/'omr-exam-paper-example').glob('*.jpg'))
    report={}
    for path in paths:
        image=load_image(path)
        found,mask=panels(image)
        overlay=image.copy()
        for index,panel in enumerate(found):
            cv2.polylines(overlay,[np.array(panel['quad'],np.int32)],True,(0,200,0),2)
            x,y,_,_=panel['box'];cv2.putText(overlay,str(index),(x,y),cv2.FONT_HERSHEY_SIMPLEX,.6,(200,0,0),2)
        cv2.imwrite(str(out/(path.stem+'-panels.jpg')),overlay)
        cv2.imwrite(str(out/(path.stem+'-red.png')),mask)
        report[path.name]=found
        print(path.name,found,flush=True)
        if path.parent.name=='omr-exam-paper-example':
            from omr_check.alignment import find_columns,_column_view,red_print
            for quad in find_columns(image):
                profile=(red_print(_column_view(image,quad))[:,35:150]>0).mean(axis=1)
                profile=np.convolve(profile,np.ones(5)/5,mode='same')
                edges=np.diff(np.r_[False,profile>.40,False].astype(np.int8))
                bands=[(int(a),int(b)) for a,b in zip(np.where(edges==1)[0],np.where(edges==-1)[0]) if b-a>=6]
                print('  PROFILE',quad.tolist(),'top',profile[:35].mean(),'bands',bands,flush=True)
    (out/'panels.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
