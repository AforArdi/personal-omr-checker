from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from omr_check.domain import MarkState
from omr_check.recognition import Recognizer, RecognitionError, classify, load_image

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def recognizer():
    return Recognizer(ROOT/"assets")


def test_partial_marks_are_not_guessed():
    assert classify(1,[.3,0,0,0]).state==MarkState.UNCERTAIN
    assert classify(1,[.9,.9,0,0]).state==MarkState.MULTIPLE


def test_practice_book_real_sample(recognizer):
    file=ROOT/"omr-exam-paper-example/20261115_191159.jpg"
    if not file.exists(): pytest.skip("Source photo not distributed")
    result=recognizer.read(file)
    assert result.template_id=="practice-book"
    assert [m.choices for m in result.marks[:3]]==[("A",),("A",),("C",)]
    assert all(m.state==MarkState.BLANK for m in result.marks[3:])


def test_retina_real_sample(recognizer):
    file=ROOT/"omr-exam-paper-example/20261115_191044.jpg"
    if not file.exists(): pytest.skip("Source photo not distributed")
    result=recognizer.read(file)
    assert result.template_id=="retina"
    expected={1:"C",2:"A",3:"A",5:"D",26:"B",27:"C",51:"A",54:"B",76:"D",100:"B"}
    for number,choice in expected.items():
        assert result.marks[number-1].state==MarkState.SINGLE
        assert result.marks[number-1].choices==(choice,)
    for number in (4,7,9,10,25,30,34,58,67,75,77,87,88,89):
        assert result.marks[number-1].state==MarkState.BLANK


@pytest.mark.parametrize("template_id",["retina","practice-book"])
def test_double_fill_and_tick_on_known_template(recognizer,tmp_path,template_id):
    template=next(t for t in recognizer.templates if t.id==template_id)
    image=template.image.copy()
    for center in template.centers[0][:2]:
        cv2.circle(image,tuple(map(lambda x:round(float(x)),center)),round(template.radius), (0,0,0),-1)
    x,y=map(int,template.centers[1][0])
    cv2.line(image,(x-4,y-2),(x,y+3),(0,0,0),2)
    cv2.line(image,(x,y+3),(x+5,y-4),(0,0,0),2)
    file=tmp_path/"marks.jpg"; cv2.imwrite(str(file),image)
    result=recognizer.read(file)
    assert result.template_id==template_id
    assert result.marks[0].state==MarkState.MULTIPLE
    assert result.marks[1].state==MarkState.UNCERTAIN


def test_unrelated_image_is_rejected(recognizer,tmp_path):
    image=np.full((1400,1000,3),255,np.uint8)
    cv2.putText(image,"Not an OMR sheet",(100,400),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),3)
    file=tmp_path/"other.jpg"; cv2.imwrite(str(file),image)
    with pytest.raises(RecognitionError): recognizer.read(file)


def test_incomplete_grid_is_rejected(recognizer, tmp_path):
    golden = json.loads((ROOT / "data/sample_expected.json").read_text())
    for name, item in golden.items():
        file = ROOT / "omr-exam-paper-example" / item["file"]
        if not file.exists():
            continue
        source = load_image(file)
        crop = source[510:990, 125:800] if name == "retina" else source[480:960, 105:670]
        assert min(crop.shape[:2]) >= 400
        path = tmp_path / f"incomplete_{name}.jpg"
        cv2.imwrite(str(path), crop)
        with pytest.raises(RecognitionError) as exc_info:
            recognizer.read(path)
        assert "complete answer columns safely" in str(exc_info.value)


def test_full_sample_never_confidently_misreads_a_question(recognizer):
    golden=json.loads((ROOT/'data/sample_expected.json').read_text())
    for name,item in golden.items():
        file=ROOT/'omr-exam-paper-example'/item['file']
        if not file.exists(): continue
        result=recognizer.read(file)
        assert result.template_id==name
        for mark,expected in zip(result.marks,item['answers']):
            if mark.state==MarkState.UNCERTAIN:
                continue
            actual=mark.choices[0] if mark.state==MarkState.SINGLE else '-' if mark.state==MarkState.BLANK else mark.state.value
            assert actual==expected,(name,mark.number,actual,expected)


def test_canva_30marked_regression(recognizer):
    file = ROOT / "tests/fixtures/canva_30marked.png"
    assert file.exists(), "Canva regression fixture must be tracked under tests/fixtures/canva_30marked.png"
    result = recognizer.read(file)
    assert result.template_id == "practice-book"
    assert result.alignment.get("method") == "column_frames"
    assert result.alignment.get("circle_coverage", 0) >= 0.90
    assert result.alignment.get("validated_rows_per_column") == [25, 25, 25, 25]

    expected_marks = {
        1: "A", 2: "A", 3: "C", 4: "D", 5: "A",
        6: "B", 7: "B", 8: "D", 9: "A", 10: "A",
        11: "B", 12: "A", 13: "D", 14: "D", 15: "C",
        16: "D", 17: "C", 18: "C", 19: "A", 20: "A",
        21: "B", 22: "D", 23: "B", 24: "C", 25: "A",
        26: "C", 27: "B", 28: "C", 29: "B", 30: "A",
    }

    # Verify every single question from 1 to 100
    for mark in result.marks:
        # Crucial requirement: ZERO uncertain rows
        assert mark.state != MarkState.UNCERTAIN, f"Q{mark.number} should not be uncertain, strengths={mark.strengths}"
        if mark.number in expected_marks:
            assert mark.state == MarkState.SINGLE, f"Q{mark.number} expected single fill, got {mark.state}"
            assert mark.choices == (expected_marks[mark.number],), f"Q{mark.number} expected {expected_marks[mark.number]}, got {mark.choices}"
        else:
            assert mark.state == MarkState.BLANK, f"Q{mark.number} expected blank, got {mark.state} with choices {mark.choices}"

    # Specifically verify the 4 previously uncertain rows: Q12, Q13, Q14, Q19
    for q_num, exp_choice in [(12, "A"), (13, "D"), (14, "D"), (19, "A")]:
        m = result.marks[q_num - 1]
        assert m.state == MarkState.SINGLE
        assert m.choices == (exp_choice,)

