from pathlib import Path
import json
import cv2
import numpy as np
from omr_check.recognition import Recognizer,load_image
from omr_check.alignment import find_columns,column_groups,validate_grid,refine_columns

root=Path(__file__).resolve().parents[1]
r=Recognizer(root/'assets')
spec=json.loads((root/'assets/layout_geometry.json').read_text())
for path in (root/'omr-exam-paper-example').glob('*.jpg'):
    im=load_image(path)
    for layout,group in column_groups(im,find_columns(im)):
        t=next(t for t in r.templates if t.id==layout)
        quads=np.array(spec[layout]['columns'],np.float32)
        aligned=np.full_like(t.image,255)
        for source,target in zip(group,quads):
            patch=cv2.warpPerspective(im,cv2.getPerspectiveTransform(source,target),(aligned.shape[1],aligned.shape[0]),borderValue=(255,255,255))
            mask=np.zeros(aligned.shape[:2],np.uint8);cv2.fillConvexPoly(mask,target.astype(np.int32),255)
            aligned[mask>0]=patch[mask>0]
        for phase,image in [('before',aligned),('after',refine_columns(aligned,t,quads))]:
            ev=validate_grid(image,t,strict=False)
            print(path.name,phase,'coverage',ev.coverage if ev else None,flush=True)
            if ev:
                for i in range(4):
                    section=ev.supported[i*25:(i+1)*25]
                    print(' ',i,'options',section.sum(axis=0).tolist(),'first',int(section[:3].sum()),'last',int(section[-3:].sum()),'missingrows',(np.where(section.sum(axis=1)<2)[0]+1).tolist(),flush=True)
            overlay=image.copy()
            for row in t.centers:
                for x,y in row:cv2.drawMarker(overlay,(round(float(x)),round(float(y))),(255,0,0),cv2.MARKER_CROSS,8,1)
            cv2.imwrite(str(root/f'var/alignment-diagnostics/{layout}-{phase}-centers.jpg'),overlay)
