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
    must not do is pass for a current file, which is what the id tells a reader.

    It moved again to v2 with 0.3.0, for a reason about readers rather than fields: `published.fresh`
    checks the id before an installed copy uses the daily All network, and an installed 0.2.0 builds its
    edges with Edge(**e), so a 0.3.0 artifact under the old id was accepted and then raised. Moving the
    id makes that copy derive live, which is what the check is for (found 2026-10-06)."""
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

    # and a document from a later version is read as far as it goes rather than raising on a field this
    # reader does not know, which is how a 0.3.0 network reached an installed 0.2.0
    from grownet.model import InteractionNetwork
    net = InteractionNetwork.from_dict({
        "schema": SCHEMA, "nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
        "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"],
                   "something_a_later_version_added": 1.0}], "studies": []})
    assert len(net.edges) == 1 and net.edges[0].effect == "facilitation"


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


def test_every_field_the_model_carries_is_declared_in_the_shipped_schema():
    """#142 item 10: `coefficient_sd`, `coefficient_n` and `coefficient_sd_from_rate_stage` were emitted
    and not declared, and nothing asserted that the two agree, so the schema and the model drifted in
    both directions. This closes the loop for all three record kinds."""
    from dataclasses import fields

    from grownet.model import Edge, Node, Study
    from grownet.schema import declared_keys
    for kind, cls in (("edge", Edge), ("node", Node), ("study", Study)):
        carried = {f.name for f in fields(cls)}
        declared = declared_keys(kind)
        assert carried - declared == set(), f"{kind}: emitted and not declared: {sorted(carried - declared)}"
        assert declared - carried == set(), f"{kind}: declared and not emitted: {sorted(declared - carried)}"


def test_validate_names_a_misspelled_key_the_reader_drops():
    """`from_dict` drops a key it does not know, which is what keeps an older grownet working on a newer
    file, so `grownet validate` is the only place a misspelling is caught at all (#142 item 10)."""
    from grownet.model import SCHEMA
    from grownet.schema import validate_document
    doc = {"schema": SCHEMA, "nodes": [{"id": "a"}, {"id": "b"}],
           "studies": [{"id": "S1", "citation": "c"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"],
                      "coefficent": 1.0}]}                       # one letter missing
    problems = validate_document(doc)
    assert any("'coefficent'" in p and "does not declare" in p for p in problems), problems
    # and the correctly spelled one is not reported
    doc["edges"][0] = {**doc["edges"][0], "coefficient": 1.0}
    del doc["edges"][0]["coefficent"]
    assert validate_document(doc) == []
