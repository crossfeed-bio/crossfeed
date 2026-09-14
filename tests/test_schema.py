"""The neutral-format contract: the shipped schema matches the code, and validation catches breakage."""
import json

from crossfeed.mgrowthdb import records_to_network
from crossfeed.schema import SCHEMA_DOC, SCHEMA_FILE, schema_json, validate_document


def _good_doc():
    recs = [{
        "source": "a", "target": "b", "source_name": "A", "target_name": "B",
        "effect": "facilitation", "strength": 1.0, "significance": 0.01, "study_id": "S1",
    }]
    return records_to_network(recs).to_dict()


def test_shipped_schema_matches_code():
    # the file downstream tools validate against must equal the canonical schema in the code
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        assert json.load(f) == SCHEMA_DOC


def test_schema_json_parses():
    assert json.loads(schema_json()) == SCHEMA_DOC


def test_valid_document_passes():
    assert validate_document(_good_doc()) == []


def test_missing_study_ids_rejected():
    doc = _good_doc()
    doc["edges"][0]["study_ids"] = []
    assert any("study_ids" in p for p in validate_document(doc))


def test_bad_effect_rejected():
    doc = _good_doc()
    doc["edges"][0]["effect"] = "magic"
    assert any("effect" in p for p in validate_document(doc))


def test_wrong_schema_rejected():
    doc = _good_doc()
    doc["schema"] = "something/v9"
    assert any("schema" in p for p in validate_document(doc))


def test_dangling_edge_endpoint_rejected():
    doc = _good_doc()
    doc["edges"][0]["target"] = "ghost"
    assert any("node" in p for p in validate_document(doc))


def test_non_object_rejected():
    assert validate_document([1, 2, 3]) == ["document is not a JSON object"]
