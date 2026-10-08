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


def test_validate_names_a_misspelled_key_without_calling_the_file_invalid():
    """`from_dict` drops a key it does not know, which is what keeps an older grownet working on a newer
    file, so `grownet validate` is the only place a misspelling is caught at all (#142 item 10).

    It is a **note**, not a problem (#155 item 5). Calling it a problem contradicted the schema's own
    sentence that a network from a later version still validates, and it skipped the referential-integrity
    pass, which runs only when there are no problems: one unrecognized field turned off every other check,
    including the one that catches an edge citing a study the document does not hold.
    """
    from grownet.model import SCHEMA
    from grownet.schema import validate_document
    doc = {"schema": SCHEMA, "nodes": [{"id": "a"}, {"id": "b"}],
           "studies": [{"id": "S1", "citation": "c"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"],
                      "coefficent": 1.0}]}                       # one letter missing
    notes = []
    assert validate_document(doc, notes) == []                    # valid: the reader drops the key
    assert any("'coefficent'" in n and "does not declare" in n for n in notes), notes
    # and the correctly spelled one is not reported at all
    doc["edges"][0] = {**doc["edges"][0], "coefficient": 1.0}
    del doc["edges"][0]["coefficent"]
    notes = []
    assert validate_document(doc, notes) == [] and notes == []
    # the integrity pass still runs beside an undeclared key, which is what the old behavior skipped
    broken = {**doc, "edges": [{**doc["edges"][0], "from_the_future": 1, "study_ids": ["S404"]}]}
    notes = []
    problems = validate_document(broken, notes)
    assert any("S404" in p for p in problems), problems
    assert any("'from_the_future'" in n for n in notes), notes


def test_validate_names_the_version_without_misstating_what_it_means():
    """The note about `significance` belongs to /v0 alone: that is where it is the corrected p-value. It
    moved to -log10 of it in /v1, which is why the id moved then, and /v2 changed no field's meaning. The
    test was `read != SCHEMA`, so the /v2 bump extended the note to /v1 files and told their readers the
    opposite of the truth, in the one command that exists to say how to read a file (found 2026-10-07)."""
    import json
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    from grownet.model import SCHEMA
    doc = {"nodes": [{"id": "a"}, {"id": "b"}], "studies": [{"id": "S1", "citation": "c"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"],
                      "significance": 1.699, "q_value": 0.02}]}
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        said = {}
        for schema in (SCHEMA, "grownet.interaction_network/v1", "grownet.interaction_network/v0"):
            path = Path(tmp) / "net.json"
            path.write_text(json.dumps({**doc, "schema": schema}), encoding="utf-8")
            # the subprocess does not inherit pytest's `pythonpath` setting, which is in-process only,
            # so it finds `grownet` only where the package happens to be installed. The suite also runs
            # from an unpacked sdist, where it is not (the package job installs pytest and nothing else),
            # and this test was the only one that shells out to the tool: it failed there with "No module
            # named grownet" while every other job was green. Carrying the path makes the subprocess use
            # the same source the test imported (found 2026-10-07).
            env = {**os.environ,
                   "PYTHONPATH": os.pathsep.join([str(root / "src"), str(root),
                                                  os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
            got = subprocess.run([sys.executable, "-m", "grownet", "validate", str(path)],
                                 capture_output=True, text=True, cwd=root, check=True, env=env)
            said[schema] = got.stdout
    # only a /v0 file is told that its `significance` is the corrected p-value
    assert "corrected p-value" in said["grownet.interaction_network/v0"]
    assert "corrected p-value" not in said["grownet.interaction_network/v1"]
    assert "corrected p-value" not in said[SCHEMA]
    # and a /v1 file is still told which version it is, since that is the point of the id
    assert "grownet.interaction_network/v1" in said["grownet.interaction_network/v1"]


def test_the_schema_and_validate_are_strict_in_the_same_direction():
    """#155 item 5. The document root carried `additionalProperties: False` while `node`, `study` and
    `edge` declared nothing of the kind, so a future **top-level** key was invalid to the schema and
    valid to `grownet validate`, and a future **record** key was the other way round: the two halves of
    one contract disagreed about the same documents, in opposite directions.

    Both are now permissive, which is what the schema's own sentence promises ("Keys not declared here
    are allowed, so a network from a later version still validates") and what the reader does. The
    standalone viewer preserves unknown top-level fields on export, so the strict root meant it could
    write a file this schema rejected.
    """
    from grownet.model import SCHEMA
    from grownet.schema import SCHEMA_DOC, validate_document
    doc = SCHEMA_DOC
    assert "additionalProperties" not in doc, doc.get("additionalProperties")
    for kind in ("node", "study", "edge"):
        assert "additionalProperties" not in doc["definitions"][kind], kind

    base = {"schema": SCHEMA, "nodes": [{"id": "a"}, {"id": "b"}],
            "studies": [{"id": "S1", "citation": "c"}],
            "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"]}]}
    # and `validate` accepts a key at either level, naming the record one
    for where, newer in (("top level", {**base, "from_the_future": 1}),
                         ("a record", {**base, "edges": [{**base["edges"][0], "from_the_future": 1}]})):
        notes = []
        assert validate_document(newer, notes) == [], where
    assert notes and "from_the_future" in notes[0]


def test_a_new_record_field_cannot_ship_under_an_unchanged_format_id():
    """Craig's agent on #154, after #121 added optional arc fields under an unchanged format id and the
    daily artifact reached installed readers that could not build them: "commit a manifest of the
    format's declared fields, and have `checks/gate.py` fail when the live `Edge`, `Node` or `Study`
    fields differ from the manifest while `SCHEMA` is unchanged ... it would have stopped #121 at the
    gate rather than four days downstream."

    The register entry asked for a convention. A convention is what #121 missed, so this is a check.
    """
    import json
    import sys
    from dataclasses import fields
    from pathlib import Path

    from grownet.model import SCHEMA, Edge, Node, Study

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "checks"))
    from gate import check_format_fields  # noqa: E402

    # the committed manifest describes the code as it stands
    assert check_format_fields([]) == []
    manifest = json.loads((root / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    assert manifest["current"] == SCHEMA
    for kind, cls in (("edge", Edge), ("node", Node), ("study", Study)):
        assert sorted(manifest["formats"][SCHEMA][kind]) == sorted(f.name for f in fields(cls)), kind

    # and the check is what refuses the three ways this can go wrong, read off the manifest rather than
    # by editing the live dataclasses, which the gate reads from the running package
    def verdict(current, formats):
        path = root / "schema" / "format_fields.json"
        kept = path.read_text(encoding="utf-8")
        try:
            path.write_text(json.dumps({"current": current, "formats": formats}), encoding="utf-8")
            return check_format_fields([])
        finally:
            path.write_text(kept, encoding="utf-8")

    live = {k: sorted(f.name for f in fields(c))
            for k, c in (("edge", Edge), ("node", Node), ("study", Study))}

    # a field added to the code and not to the format: what #121 did
    short = {**live, "edge": [f for f in live["edge"] if f != "rate_mismatch_to_zero"]}
    problems = verdict(SCHEMA, {SCHEMA: short})
    assert any("rate_mismatch_to_zero" in p and "move SCHEMA to a new id" in p for p in problems), problems

    # a field the format records and the code dropped: breaking, and named as such
    extra = {**live, "node": [*live["node"], "a_field_that_was_removed"]}
    problems = verdict(SCHEMA, {SCHEMA: extra})
    assert any("a_field_that_was_removed" in p and "has shipped is a breaking change" in p
               for p in problems), problems

    # the id moved and the manifest was not told
    problems = verdict("grownet.interaction_network/v9", {"grownet.interaction_network/v9": live})
    assert any("says the current format is" in p for p in problems), problems
    assert any("has no entry for" in p for p in problems), problems


def test_the_format_check_refuses_to_answer_from_stale_bytecode(monkeypatch):
    """Its verdict comes from the live dataclasses, so a stale `.pyc` can answer for code that is no
    longer on disk, and that answer is a PASS.

    Craig's agent hit it by accident on #168 while testing this check against the #121 mistake: CPython
    invalidates bytecode on (source mtime in whole seconds, source size), and two format ids of the same
    length are the same size, so editing an id and reverting it inside one second leaves bytecode CPython
    considers current. A developer who runs the gate, sees it fail, reverts and runs it again meets it.

    So the id is read out of `model.py` as text and compared with the imported one. Here the imported one
    is moved instead of the file, which is the same disagreement the stale bytecode produces.
    """
    import sys
    from pathlib import Path

    import grownet.model

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "checks"))
    from gate import check_format_fields  # noqa: E402

    on_disk = grownet.model.SCHEMA
    monkeypatch.setattr(grownet.model, "SCHEMA", "grownet.interaction_network/v9")
    problems = check_format_fields([])
    assert any("your bytecode is stale" in p for p in problems), problems
    assert any("__pycache__" in p for p in problems), problems
    # and it names both ids, so the reader can see which way round it is
    assert any("grownet.interaction_network/v9" in p and on_disk in p for p in problems), problems

    # and it is the ONLY problem reported, because every other verdict this function can reach comes
    # from the same poisoned import, the field comparison included. Reported together, the manifest line
    # said "model.py says /v9" while the file said otherwise and prescribed moving `current` to an id
    # the source does not contain (Craig's agent on #176)
    assert len(problems) == 1, problems
