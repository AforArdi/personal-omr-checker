from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .domain import Mark, MarkState
from .alignment import StructuralAligner

Image.MAX_IMAGE_PIXELS = 35_000_000
cv2.setNumThreads(2)


class RecognitionError(ValueError):
    pass


def load_image(path: Path, width: int = 1000) -> np.ndarray:
    try:
        with Image.open(path) as im:
            if im.width * im.height > 35_000_000:
                raise RecognitionError("Image is too large; use a photo below 35 megapixels")
            im = ImageOps.exif_transpose(im).convert("RGB")
            if min(im.size) < 400:
                raise RecognitionError("Image resolution is too low. Send the original photo as a file")
            target_w = width if im.width <= im.height else round(im.width * width / im.height)
            target_h = round(im.height * width / im.width) if im.width <= im.height else width
            if (im.width, im.height) != (target_w, target_h):
                im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
            return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise RecognitionError("Cannot read this image. Send a JPEG or PNG photo") from exc


def ink_mask(image: np.ndarray, threshold: int = 155) -> np.ndarray:
    # Red-channel illumination normalization suppresses the red form printing.
    red = image[:, :, 2]
    background = cv2.GaussianBlur(red, (0, 0), 18)
    normalized = cv2.divide(red, np.maximum(background, 1), scale=255)
    return normalized < threshold


@dataclass
class Template:
    id: str
    image: np.ndarray
    centers: np.ndarray
    radius: float
    roi: list[int]
    keypoints: tuple
    descriptors: np.ndarray


@dataclass
class Reading:
    template_id: str
    marks: list[Mark]
    aligned: np.ndarray
    annotated: np.ndarray
    alignment: dict
    sampling_centers: np.ndarray | None = None


def classify(number: int, strengths: list[float]) -> Mark:
    strong = tuple("ABCD"[i] for i, strength in enumerate(strengths) if strength >= 0.72)
    faint = [strength for strength in strengths if 0.18 < strength < 0.72]
    state = MarkState.UNCERTAIN if faint else MarkState.MULTIPLE if len(strong) > 1 else MarkState.SINGLE if strong else MarkState.BLANK
    note = "Partial shading or a nonstandard mark: inspect this row" if faint else ""
    return Mark(number, state, strong, tuple(round(v, 3) for v in strengths), note)


class Recognizer:
    def __init__(self, directory: Path):
        self.sift = cv2.SIFT_create(nfeatures=9000, contrastThreshold=0.015)
        self.templates = []
        for spec in json.loads((directory / "templates.json").read_text(encoding="utf-8")):
            reference = cv2.imread(str(directory / spec["image"]))
            if reference is None:
                raise ValueError("Missing OMR reference image")
            mask = np.zeros(reference.shape[:2], np.uint8)
            x0, y0, x1, y1 = spec["roi"]
            mask[y0:y1, x0:x1] = 255
            kp, desc = self.sift.detectAndCompute(cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), mask)
            self.templates.append(Template(spec["id"], reference, np.array(spec["centers"], np.float32), spec["radius"], spec["roi"], kp, desc))
        geometry=json.loads((directory/'layout_geometry.json').read_text(encoding='utf-8'))
        self.structural=StructuralAligner(self.templates,geometry)

    def read(self, path: Path) -> Reading:
        cv2.setRNGSeed(0)
        image = load_image(path)
        for rotation in (0, 1, 2, 3):
            rotated = np.ascontiguousarray(np.rot90(image, rotation))
            if rotated.shape[1] != 1000:
                rotated = cv2.resize(rotated, (1000, round(rotated.shape[0] * 1000 / rotated.shape[1])))
            match = self.structural.align(rotated)
            if match is not None:
                coverage, template, aligned, evidence = match
                metrics = {'method': evidence.method, 'circle_coverage': round(coverage, 4),
                           'validated_rows_per_column': evidence.row_coverage, 'rotation_quarters': rotation}
                return self._finish_reading(template, aligned, metrics, evidence.centers, evidence.supported)
        return self._read_legacy(path)

    def _read_legacy(self, path: Path) -> Reading:
        cv2.setRNGSeed(0)
        image = load_image(path)
        best = None
        for rotation in (0, 1, 2, 3):
            rotated = np.ascontiguousarray(np.rot90(image, rotation))
            # Normalize width after a landscape/portrait rotation.
            if rotated.shape[1] != 1000:
                rotated = cv2.resize(rotated, (1000, round(rotated.shape[0] * 1000 / rotated.shape[1])))
            kp, desc = self.sift.detectAndCompute(cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY), None)
            if desc is None:
                continue
            for template in self.templates:
                candidate = self._align(template, rotated, kp, desc)
                if candidate and (best is None or candidate[0] > best[0]):
                    best = candidate
            if best is not None and best[0] > 150:
                break
        if best is None:
            raise RecognitionError("I could not locate and cross-check all four complete answer columns safely. Include the column headings and bottom row in the photo; keep all four black corner squares visible on Retina sheets. Send the original JPEG/PNG as a file if possible")
        _, template, aligned, metrics = best
        metrics['method'] = 'feature_fallback'
        return self._finish_reading(template, aligned, metrics)

    @staticmethod
    def _fraction(mask, x, y, r):
        x0, x1 = int(x - r - 1), int(x + r + 2)
        y0, y1 = int(y - r - 1), int(y + r + 2)
        if x0 < 0 or y0 < 0 or x1 > mask.shape[1] or y1 > mask.shape[0]: return None
        yy, xx = np.ogrid[y0:y1, x0:x1]
        disk = (xx - x)**2 + (yy - y)**2 <= r * r
        return float(mask[y0:y1, x0:x1][disk].mean())

    def _finish_reading(self, template, aligned, metrics, centers=None, supported=None):
        centers = template.centers if centers is None else centers
        threshold = 155 if template.id == "practice-book" else 210
        observed = ink_mask(aligned, threshold)
        baseline = ink_mask(template.image, threshold)
        marks = []
        for number, (row, reference_row) in enumerate(zip(centers, template.centers), 1):
            strengths = []
            for (x, y), (rx, ry) in zip(row, reference_row):
                r = template.radius * (0.78 if template.id == "practice-book" else 0.60)
                obs = self._fraction(observed, x, y, r)
                ref = self._fraction(baseline, rx, ry, r)
                strengths.append(0.4 if obs is None or ref is None else max(0.0, (obs - ref) / max(0.3, 1.0 - ref)))
            mark = classify(number, strengths)
            if supported is not None and (supported[number - 1].sum() + len(mark.choices)) < 2:
                mark = Mark(number, MarkState.UNCERTAIN, mark.choices, mark.strengths, 'Printed cells in this row need review')
            marks.append(mark)
        annotated = self.annotate(template, aligned, marks, centers)
        return Reading(template.id, marks, aligned, annotated, metrics, centers)

    def _align(self, template, image, kp, desc):
        matcher = cv2.BFMatcher(cv2.NORM_L2)
        pairs = matcher.knnMatch(template.descriptors, desc, k=2)
        matches = [a for pair in pairs if len(pair) == 2 for a, b in [pair] if a.distance < 0.68 * b.distance]
        if len(matches) < 25:
            return None
        source = np.float32([template.keypoints[m.queryIdx].pt for m in matches])
        target = np.float32([kp[m.trainIdx].pt for m in matches])
        transform, inliers = cv2.findHomography(target, source, cv2.RANSAC, 2.2)
        if transform is None or inliers is None:
            return None
        selected = inliers.ravel().astype(bool)
        count = int(selected.sum())
        if count < 25 or count / len(matches) < 0.20:
            return None
        points = source[selected]
        x0, y0, x1, y1 = template.roi
        # Evidence must span all four columns and the top/bottom, not one repeated row.
        if np.ptp(points[:, 0]) < (x1-x0)*0.70 or np.ptp(points[:, 1]) < (y1-y0)*0.72:
            return None
        for col in range(4):
            bounds = template.centers[col*25:(col+1)*25].reshape(-1, 2)
            hit = points[(points[:, 0] >= bounds[:, 0].min()-20) & (points[:, 0] <= bounds[:, 0].max()+20)]
            if len(hit) < 3:
                return None
        expected = template.centers.reshape(-1, 1, 2)
        original = cv2.perspectiveTransform(expected, np.linalg.inv(transform)).reshape(-1, 2)
        h, w = image.shape[:2]
        if np.any(original[:, 0] < 8) or np.any(original[:, 0] > w-8) or np.any(original[:, 1] < 8) or np.any(original[:, 1] > h-8):
            return None
        # Reject folds/flips and extreme perspective; do not trust a numerical fit alone.
        quad = cv2.perspectiveTransform(np.float32([[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]]), np.linalg.inv(transform))[0]
        if not cv2.isContourConvex(quad) or cv2.contourArea(quad, oriented=True) <= 0:
            return None
        aligned = cv2.warpPerspective(image, transform, (template.image.shape[1], template.image.shape[0]), borderValue=(255,255,255))
        # Book pages are not perfectly planar. Use locally consistent feature
        # residuals to compensate small smooth curvature after global alignment.
        projected_all = cv2.perspectiveTransform(target.reshape(-1,1,2), transform).reshape(-1,2)
        residuals = projected_all-source
        close = np.linalg.norm(residuals,axis=1)<10.0
        controls = source[close]
        offsets = residuals[close]
        if template.id == "retina" and len(controls)>=40:
            height,width=aligned.shape[:2]
            gx=np.linspace(0,width-1,max(2,width//40))
            gy=np.linspace(0,height-1,max(2,height//40))
            field=np.zeros((len(gy),len(gx),2),np.float32)
            for iy,y in enumerate(gy):
                for ix,x in enumerate(gx):
                    distance=np.linalg.norm(controls-[x,y],axis=1)
                    near=np.argsort(distance)[:12]
                    near=near[distance[near]<100]
                    if len(near)>=4:
                        field[iy,ix]=np.median(offsets[near],axis=0)
            field=cv2.resize(field,(width,height),interpolation=cv2.INTER_LINEAR)
            yy,xx=np.mgrid[:height,:width].astype(np.float32)
            aligned=cv2.remap(aligned,xx+field[:,:,0],yy+field[:,:,1],cv2.INTER_CUBIC,borderValue=(255,255,255))
        reprojection = cv2.perspectiveTransform(target[selected].reshape(-1,1,2), transform).reshape(-1,2)
        error = float(np.median(np.linalg.norm(reprojection-points, axis=1)))
        if error > 1.2:
            return None
        return count, template, aligned, {"inliers": count, "median_error_px": round(error, 3)}

    @staticmethod
    def annotate(template: Template, aligned: np.ndarray, marks: list[Mark], centers=None) -> np.ndarray:
        output = aligned.copy()
        colors = {MarkState.SINGLE:(30,150,30), MarkState.BLANK:(180,110,0), MarkState.MULTIPLE:(0,0,220), MarkState.INVALID:(0,0,220), MarkState.UNCERTAIN:(0,150,240)}
        for mark, row in zip(marks, template.centers if centers is None else centers):
            color = colors[mark.state]
            for choice, (x,y) in zip("ABCD", row):
                if choice in mark.choices:
                    cv2.circle(output, (round(float(x)),round(float(y))), round(template.radius+2), color, 2)
            x,y = row[0]
            cv2.putText(output, str(mark.number), (int(x)-30,int(y)+3), cv2.FONT_HERSHEY_SIMPLEX, .25, color, 1, cv2.LINE_AA)
            if mark.state in (MarkState.UNCERTAIN, MarkState.BLANK, MarkState.INVALID):
                cv2.rectangle(output,(int(row[0][0]-10),int(y-10)),(int(row[-1][0]+10),int(row[-1][1]+10)),color,1)
        x0,y0,x1,y1 = template.roi
        return output[max(0,y0-20):min(output.shape[0],y1+20),max(0,x0-20):min(output.shape[1],x1+20)]
