from pathlib import Path
import json
import cv2
import numpy as np
from omr_check.recognition import Recognizer,load_image
from omr_check.alignment import marker_quads,square_markers,identify_layout,predict_centers,validate_grid,locate_rows,_column_view

root=Path(__file__).resolve().parents[1]
reader=Recognizer(root/'assets');a=reader.structural;t=a.templates['retina']
print('reference',a.reference_markers,flush=True)
quads=np.array(a.specifications['retina']['columns'],np.float32)
im=load_image(root/'var/recognition-regressions/retina-crop-jpeg.jpg')
print('points',square_markers(im),flush=True)
for i,source in enumerate(marker_quads(im)):
    aligned=cv2.warpPerspective(im,cv2.getPerspectiveTransform(source,a.reference_markers),(t.image.shape[1],t.image.shape[0]),borderValue=(255,255,255))
    print('layout',identify_layout(aligned,quads),flush=True)
    for q in quads:
        rows=locate_rows(_column_view(aligned,q),'retina')
        print('rows',rows.tolist() if rows is not None else None,flush=True)
    predicted=predict_centers(aligned,t,quads,quads)
    print('predicted',predicted is not None,flush=True)
    if predicted is not None:
        evidence=validate_grid(aligned,t,strict=False,predicted=predicted)
        print('coverage',evidence.coverage,evidence.row_coverage,[evidence.supported[j*25:(j+1)*25].sum(axis=0).tolist() for j in range(4)],flush=True)
    cv2.imwrite(str(root/f'var/alignment-diagnostics/marker-{i}.jpg'),aligned)
