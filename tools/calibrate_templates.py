"""Reproduce initial reference assets from the supplied blank forms."""
import json
from pathlib import Path

import cv2
import numpy as np

from omr_check.recognition import load_image

ROOT = Path(__file__).resolve().parents[1]
SPECS = [
    ("practice-book", "model-ans-pics-omr-sheet.jpg", [140,578,645,1234], 7.1, [
        [[191,625],[254,625],[174,1200],[239,1202]],
        [[312,624],[374,624],[299,1206],[365,1209]],
        [[434,623],[497,623],[428,1212],[494,1213]],
        [[557,623],[622,623],[557,1213],[624,1212]],
    ]),
    ("retina", "retina-ans-sheet.jpg", [180,558,774,1205], 9.0, [
        [[224,597],[311,598],[218,1173],[303,1173]],
        [[374,600],[458,600],[364,1177],[450,1179]],
        [[517,601],[601,602],[514,1183],[600,1183]],
        [[663,603],[748,603],[665,1183],[749,1184]],
    ]),
]


def main():
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    specs = []
    for name, source, roi, radius, columns in SPECS:
        image = load_image(ROOT / "omr-check-answer-sheet-images" / source)
        centers = []
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        circles = cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1,12,param1=70,param2=12,minRadius=5,maxRadius=11)
        available = circles[0,:,:2] if circles is not None else np.empty((0,2))
        for a,b,c,d in map(lambda col: np.array(col,float), columns):
            for row in range(25):
                left = a+(c-a)*row/24
                right = b+(d-b)*row/24
                line=[]
                for option in range(4):
                    point=left+(right-left)*option/3
                    if len(available):
                        dist=np.linalg.norm(available-point,axis=1)
                        if dist.min()<6:
                            point=available[dist.argmin()]
                    line.append([round(float(v),2) for v in point])
                centers.append(line)
        cv2.imwrite(str(out / f"{name}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY,95])
        specs.append(dict(id=name,image=f"{name}.jpg",roi=roi,radius=radius,centers=centers))
    (out/"templates.json").write_text(json.dumps(specs,indent=2),encoding="utf-8")
    print("Created two templates with 400 bubble centers each")


if __name__ == "__main__":
    main()
