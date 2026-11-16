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


def test_displayed_label_resolves_uniquely(tmp_path):
    k1 = key(id="retina-eng", collection="Retina", name="Paper Final English")
    k2 = key(id="practice-eng", collection="Practice book", name="Paper Final English")
    catalog = Catalog(write(tmp_path, [k1, k2]))

    # Ambiguous without collection
    ambig = catalog.match("Paper Final English")
    assert len(ambig) == 2

    # Exact displayed label resolves unambiguously
    res_practice = catalog.match("Paper Final English [Practice book]")
    assert len(res_practice) == 1
    assert res_practice[0].id == "practice-eng"

    res_retina = catalog.match("Paper Final English [Retina]")
    assert len(res_retina) == 1
    assert res_retina[0].id == "retina-eng"

    # Case and spacing in displayed label
    res_case = catalog.match("  paper  final  english   [practice   book]  ")
    assert len(res_case) == 1
    assert res_case[0].id == "practice-eng"


def test_keyword_search_across_id_name_collection_alias(tmp_path):
    k1 = key(id="retina-eng", collection="Retina", name="Paper Final English")
    k1["aliases"] = ["Final English", "FE"]
    k2 = key(id="practice-bio", collection="Practice book", name="Model Test Biology")
    catalog = Catalog(write(tmp_path, [k1, k2]))

    # Search by alias and collection
    res = catalog.search("final english retina")
    assert len(res) == 1
    assert res[0].id == "retina-eng"

    # Search by ID token
    res2 = catalog.search("retina eng")
    assert len(res2) == 1
    assert res2[0].id == "retina-eng"

    # Search by alias alone
    res3 = catalog.search("fe")
    assert len(res3) == 1
    assert res3[0].id == "retina-eng"

    # Search by collection alone
    res4 = catalog.search("practice")
    assert len(res4) == 1
    assert res4[0].id == "practice-bio"

