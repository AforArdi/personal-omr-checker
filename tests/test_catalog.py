import json

import pytest

from omr_check.catalog import Catalog


def write(tmp_path,exams):
    file=tmp_path/"keys.json"
    file.write_text(json.dumps({"schema_version":1,"exams":exams}),encoding="utf-8")
    return file


def key(id="retina-test",collection="Retina",name="Paper Final: Zoology"):
    return {"id":id,"name":name,"collection":collection,"status":"verified","answers":{str(i):["A"] for i in range(1,101)},"issues":[]}


def test_capitalization_spacing_and_punctuation(tmp_path):
    catalog=Catalog(write(tmp_path,[key()]))
    assert catalog.match("PAPER FINAL: ZOOLOGY")[0].id=="retina-test"
    assert catalog.match(" paper   final-zoology ")[0].id=="retina-test"
    assert not catalog.match("Paper Final: Zoolog")


def test_ambiguous_name_returns_all_matches(tmp_path):
    catalog=Catalog(write(tmp_path,[key(),key("practice-test","Practice book")]))
    assert len(catalog.match("paper final zoology"))==2
    assert len(catalog.match("retina-test"))==1


def test_missing_or_unresolved_verified_keys_rejected(tmp_path):
    item=key(); del item["answers"]["50"]
    with pytest.raises(ValueError): Catalog(write(tmp_path,[item]))
    item=key(); item["issues"]=["Check Q74"]
    with pytest.raises(ValueError): Catalog(write(tmp_path,[item]))


def test_unverified_incomplete_key_can_be_reviewed(tmp_path):
    item=key(); item["status"]="draft"; item["answers"]={"1":["B","C"]}
    catalog=Catalog(write(tmp_path,[item]))
    assert not catalog.match(item["name"])[0].verified
