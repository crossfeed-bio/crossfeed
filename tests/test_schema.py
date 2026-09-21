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


# ---- edge evidence and community (#11) ----------------------------------------------------------------

def _dropout_doc():
    recs = [{"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0, "study_id": "S1",
             "evidence": "dropout", "community": ["a", "b", "c"]}]
    return records_to_network(recs).to_dict()


def test_dropout_edge_round_trips_and_validates():
    from crossfeed.model import InteractionNetwork
    doc = _dropout_doc()
    assert doc["edges"][0]["evidence"] == "dropout"
    assert list(doc["edges"][0]["community"]) == ["a", "b", "c"]
    assert validate_document(doc) == []
    edge = InteractionNetwork.from_dict(json.loads(json.dumps(doc))).edges[0]
    assert edge.evidence == "dropout" and edge.community == ("a", "b", "c")


def test_unknown_evidence_rejected():
    from crossfeed.model import Edge
    doc = _dropout_doc()
    doc["edges"][0]["evidence"] = "direct"
    assert any("evidence" in p for p in validate_document(doc))
    assert any("evidence" in p for p in Edge("a", "b", "facilitation", study_ids=("S1",), evidence="direct").validate())


def test_community_must_be_a_list_of_ids():
    doc = _dropout_doc()
    doc["edges"][0]["community"] = "a b c"
    assert any("community" in p for p in validate_document(doc))


def test_document_without_the_new_fields_still_valid():
    from crossfeed.model import InteractionNetwork
    doc = _good_doc()
    for edge in doc["edges"]:
        del edge["evidence"], edge["community"]
    assert validate_document(doc) == []
    edge = InteractionNetwork.from_dict(doc).edges[0]
    assert edge.evidence is None and edge.community == ()


# ---- cautions and experiments of origin (#47) -----------------------------------------------------

def test_cautions_and_experiments_round_trip_and_validate():
    from crossfeed.model import InteractionNetwork
    recs = [{"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0, "study_id": "S1",
             "cautions": ["two_replicates"], "experiments": ["E1", "E2"]}]
    doc = records_to_network(recs).to_dict()
    assert validate_document(doc) == []
    edge = InteractionNetwork.from_dict(doc).edges[0]
    assert edge.cautions == ("two_replicates",) and edge.experiments == ("E1", "E2")


def test_an_unknown_caution_or_a_non_string_experiment_is_rejected():
    doc = _dropout_doc()
    doc["edges"][0]["cautions"] = ["few_replicates"]
    assert any("cautions" in p for p in validate_document(doc))
    doc = _dropout_doc()
    doc["edges"][0]["experiments"] = [7]
    assert any("experiments" in p for p in validate_document(doc))
