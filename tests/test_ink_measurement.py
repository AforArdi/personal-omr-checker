"""The local paper measurement must rescue dense fills, not sparse symbols."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from omr_check.domain import MarkState
from omr_check.recognition import classify, paper_ink_fraction


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=["practice-book", "retina"])
def printed_template(request):
    spec = next(
        item
        for item in json.loads((ROOT / "assets/templates.json").read_text())
        if item["id"] == request.param
    )
    image = cv2.imread(str(ROOT / "assets" / spec["image"]))
    assert image is not None
    centers = np.array(spec["centers"], dtype=np.float32)
    radius = spec["radius"] * (0.78 if request.param == "practice-book" else 0.60)
    return image, centers, radius, spec["radius"]


def local_strengths(image, reference, centers, radius):
    strengths = []
    for x, y in centers:
        observed = paper_ink_fraction(image, x, y, radius)
        baseline = paper_ink_fraction(reference, x, y, radius)
        assert observed is not None and baseline is not None
        strengths.append(max(0.0, (observed - baseline) / max(0.3, 1 - baseline)))
    return strengths


@pytest.mark.parametrize("shape", ["empty", "tick", "cross", "half", "red-ring"])
def test_local_paper_measurement_does_not_promote_sparse_marks(printed_template, shape):
    reference, centers, radius, bubble_radius = printed_template
    image = reference.copy()
    x, y = map(lambda value: round(float(value)), centers[0, 0])
    size = max(3, round(radius))
    if shape == "tick":
        cv2.line(image, (x-size, y), (x-1, y+size//2), (0, 0, 0), 1)
        cv2.line(image, (x-1, y+size//2), (x+size, y-size), (0, 0, 0), 1)
    elif shape == "cross":
        cv2.line(image, (x-size, y-size), (x+size, y+size), (0, 0, 0), 1)
        cv2.line(image, (x-size, y+size), (x+size, y-size), (0, 0, 0), 1)
    elif shape == "half":
        cv2.ellipse(image, (x, y), (round(bubble_radius), round(bubble_radius)), 0, 90, 270, (0, 0, 0), -1)
    elif shape == "red-ring":
        # Printed form ink is sparse even where its red component is dark.
        cv2.circle(image, (x, y), round(bubble_radius), (50, 30, 130), 1)

    strengths = local_strengths(image, reference, centers[0], radius)
    assert strengths[0] < 0.72, (shape, strengths)
    assert classify(1, strengths).state != MarkState.SINGLE, (shape, strengths)


def test_local_paper_measurement_keeps_two_dense_fills_multiple(printed_template):
    reference, centers, radius, bubble_radius = printed_template
    image = reference.copy()
    for x, y in centers[0, :2]:
        cv2.circle(
            image,
            (round(float(x)), round(float(y))),
            round(bubble_radius),
            (0, 0, 0),
            -1,
        )
    strengths = local_strengths(image, reference, centers[0], radius)
    mark = classify(1, strengths)
    assert mark.state == MarkState.MULTIPLE, strengths
    assert mark.choices == ("A", "B")
