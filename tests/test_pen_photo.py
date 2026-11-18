"""Recognition ground truth from a real photograph with reflective pen fills.

These choices were transcribed from the paper, independently of exam keys.
The source fixture is required so a fresh checkout cannot silently skip it.
"""

import json
from pathlib import Path

import cv2
import pytest

from omr_check.domain import MarkState
from omr_check.recognition import Recognizer


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def pen_photo_recognizer():
    return Recognizer(ROOT / "assets")


@pytest.mark.parametrize("variant", ["original", "jpeg-720", "rotated-90"])
def test_reflective_pen_photo_preserves_every_answer(
    pen_photo_recognizer, tmp_path, variant
):
    fixture = FIXTURES / "practice_pen_glare.jpg"
    truth_file = FIXTURES / "practice_pen_glare_expected.json"
    assert fixture.is_file(), "The real pen-photo regression fixture is required"
    assert truth_file.is_file(), "The manually verified reading is required"
    truth = json.loads(truth_file.read_text(encoding="utf-8"))
    expected = truth["answers"]
    assert len(expected) == 100

    if variant == "original":
        path = fixture
    else:
        source = cv2.imread(str(fixture))
        assert source is not None
        if variant == "jpeg-720":
            height, width = source.shape[:2]
            transformed = cv2.resize(
                source,
                (720, round(height * 720 / width)),
                interpolation=cv2.INTER_AREA,
            )
            path = tmp_path / "pen-photo-720.jpg"
            assert cv2.imwrite(
                str(path), transformed, [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
        else:
            transformed = cv2.rotate(source, cv2.ROTATE_90_CLOCKWISE)
            path = tmp_path / "pen-photo-rotated.png"
            assert cv2.imwrite(str(path), transformed)

    reading = pen_photo_recognizer.read(path)
    assert reading.template_id == truth["layout"]
    assert len(reading.marks) == 100
    assert {mark.number for mark in reading.marks} == set(range(1, 101))
    assert sum(mark.state == MarkState.SINGLE for mark in reading.marks) == 90
    assert sum(mark.state == MarkState.BLANK for mark in reading.marks) == 10
    assert not any(mark.state == MarkState.UNCERTAIN for mark in reading.marks)

    for mark in reading.marks:
        choice = expected[mark.number - 1]
        expected_state = MarkState.BLANK if choice == "-" else MarkState.SINGLE
        expected_choices = () if choice == "-" else (choice,)
        assert (mark.state, mark.choices) == (expected_state, expected_choices), (
            variant,
            mark.number,
            choice,
            mark.state,
            mark.choices,
            mark.strengths,
            mark.note,
        )
