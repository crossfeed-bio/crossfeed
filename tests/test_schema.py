"""The neutral-format contract: the shipped schema matches the code, and validation catches breakage."""
import json

from grownet.mgrowthdb import records_to_network
from grownet.schema import SCHEMA_DOC, SCHEMA_FILE, schema_json, validate_document


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
    from grownet.model import InteractionNetwork
    doc = _dropout_doc()
    assert doc["edges"][0]["evidence"] == "dropout"
    assert list(doc["edges"][0]["community"]) == ["a", "b", "c"]
    assert validate_document(doc) == []
    edge = InteractionNetwork.from_dict(json.loads(json.dumps(doc))).edges[0]
    assert edge.evidence == "dropout" and edge.community == ("a", "b", "c")


def test_unknown_evidence_rejected():
    from grownet.model import Edge
    doc = _dropout_doc()
    doc["edges"][0]["evidence"] = "direct"
    assert any("evidence" in p for p in validate_document(doc))
    assert any("evidence" in p for p in Edge("a", "b", "facilitation", study_ids=("S1",), evidence="direct").validate())


def test_community_must_be_a_list_of_ids():
    doc = _dropout_doc()
    doc["edges"][0]["community"] = "a b c"
    assert any("community" in p for p in validate_document(doc))


def test_document_without_the_new_fields_still_valid():
    from grownet.model import InteractionNetwork
    doc = _good_doc()
    for edge in doc["edges"]:
        del edge["evidence"], edge["community"]
    assert validate_document(doc) == []
    edge = InteractionNetwork.from_dict(doc).edges[0]
    assert edge.evidence is None and edge.community == ()


# ---- cautions and experiments of origin (#47) -----------------------------------------------------

def test_cautions_and_experiments_round_trip_and_validate():
    from grownet.model import InteractionNetwork
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


def test_node_identity_fields_validate_and_a_wrong_identity_is_rejected():
    recs = [{"source": "ncbi:1", "target": "b", "source_taxon_id": "1", "source_species": "x y",
             "source_identity": "ncbi", "target_identity": "name", "effect": "facilitation", "study_id": "S1"}]
    doc = records_to_network(recs).to_dict()
    assert validate_document(doc) == []
    doc["nodes"][0]["identity"] = "guessed"
    assert any("identity" in p for p in validate_document(doc))


def test_a_document_from_the_previous_version_is_still_valid_and_named():
    """Karoline, 2026-10-04, taking the recommendation: the id moves to v1 because `significance` changed
    meaning. A file written by 0.1.x stays valid, since nothing about its own content changed; what it
    must not do is pass for a v1 file, which is what the id now tells a reader. It moved again to v2 with
    the optional arc fields of #118, so that an installed 0.2.0 reads the daily network as a format it
    does not know and derives live rather than failing on a field it cannot build (#121)."""
    from grownet.model import KNOWN_SCHEMAS, PREVIOUS_SCHEMAS, SCHEMA
    from grownet.schema import validate_document
    assert SCHEMA == "grownet.interaction_network/v2"
    assert PREVIOUS_SCHEMAS == ("grownet.interaction_network/v1", "grownet.interaction_network/v0")
    assert KNOWN_SCHEMAS == (SCHEMA, *PREVIOUS_SCHEMAS)

    doc = {"schema": SCHEMA, "nodes": [], "edges": [], "studies": []}
    assert validate_document(doc) == []
    for older in PREVIOUS_SCHEMAS:
        assert validate_document({**doc, "schema": older}) == []
    problems = validate_document({**doc, "schema": "grownet.interaction_network/v3"})
    assert problems and "expected one of" in problems[0]


def test_the_daily_all_network_is_used_only_when_it_speaks_this_version():
    """A published file from 0.1.x holds the old meaning of `significance`, so a 0.2.0 page derives live
    rather than showing those numbers as if they were the new ones."""
    import datetime

    from grownet import published
    from grownet.model import PREVIOUS_SCHEMAS, SCHEMA
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {"format": published.FORMAT,
               "network": {"schema": SCHEMA, "meta": {"derived_at": now}}}
    assert published.fresh(payload)
    old = {"format": published.FORMAT,
           "network": {"schema": PREVIOUS_SCHEMAS[0], "meta": {"derived_at": now}}}
    assert not published.fresh(old)
