"""The sub-properties of `meta`, declared (#117).

Craig, approving the 0.2.0 stack on 2026-10-05: "`meta` is still unconstrained in the schema, which is
pre-existing rather than a regression, though the release that moves the version is the natural place to
declare those sub-properties."

Three constraints the issue sets, each with a test here: `meta` stays permissive, so a key it does not
declare still validates; a declared key of the wrong type does not; and what the format promises is
marked as such, so a reader knows which keys to depend on.
"""
import json

from grownet import model, schema


def _doc(**meta):
    return {"schema": model.SCHEMA, "meta": meta, "nodes": [], "edges": [], "studies": []}


def test_the_promised_keys_are_declared_with_their_types():
    declared = schema.SCHEMA_DOC["properties"]["meta"]["properties"]
    for key in ("tool", "tool_version", "derived_on", "derived_at", "source_db"):
        assert declared[key]["type"] == "string"
    assert declared["provisional"]["type"] == "string"
    for key in ("absence", "statistics", "settings", "data", "growth_rates"):
        assert declared[key]["type"] == "object"
    for key in ("species", "studies"):
        assert declared[key]["type"] == "array"


def test_the_schema_says_which_keys_a_current_derivation_always_writes():
    """A reader has to know which of these to depend on, which is Craig's point.

    The wording changed on 2026-10-07 (#142 item 15): these eight said "a promise of the format" while
    `meta` has no `required` list, so `meta = {}` validates and the word did work the file does not back.
    A `required` list is the wrong fix, since one shape validates /v0, /v1 and /v2 and an older artifact
    without `statistics` or `absence` would start failing, against what #141 promises about 0.1.x and
    0.2.x files. So the description says what is true: a current derivation writes these, and their
    meaning is fixed. `provisional` is among them and is conditional by design, which its own description
    says: it is present while the derivation is provisional."""
    declared = schema.SCHEMA_DOC["properties"]["meta"]["properties"]
    promised = ("tool", "tool_version", "derived_on", "derived_at", "source_db", "provisional",
                "absence", "statistics")
    for key in promised:
        assert "part of the format" in declared[key]["description"], key
        assert "every current derivation" in declared[key]["description"], key
    for key in ("settings", "selection", "hidden", "filters"):
        assert "recorded" in declared[key]["description"], key
    # and none of them is required, which is what keeps an older artifact valid
    assert "required" not in schema.SCHEMA_DOC["properties"]["meta"]
    assert schema.validate_document({**_doc(), "meta": {}}) == []


def test_a_meta_key_the_schema_does_not_declare_still_validates():
    """`meta` stays permissive, so a network written by a later version validates here, and so do the
    fixtures and the daily All network."""
    assert "additionalProperties" not in schema.SCHEMA_DOC["properties"]["meta"]
    assert schema.validate_document(_doc(something_new={"a": 1})) == []


def test_a_declared_key_of_the_wrong_type_does_not_validate():
    problems = schema.validate_document(_doc(tool_version=3))
    assert any("tool_version" in p for p in problems)
    assert any("string" in p for p in problems)
    assert schema.validate_document(_doc(absence=[1, 2])) != []
    assert schema.validate_document(_doc(species="Blautia")) != []        # an array, not a string
    assert schema.validate_document(_doc(tool_version="0.3.0", species=["Blautia"])) == []


def test_the_shipped_schema_file_matches_what_the_code_declares():
    """The gate checks this too; here it fails fast while the declarations are being written."""
    from pathlib import Path
    shipped = json.loads(Path(__file__).resolve().parents[1]
                         .joinpath("schema/interaction_network.schema.json").read_text())
    assert shipped == json.loads(schema.schema_json())


def test_a_network_derived_today_still_validates():
    """Every key a real run writes is either declared with the type it has or left alone."""
    from grownet.gui import DEFAULTS
    from grownet.mgrowthdb import records_to_network
    net = records_to_network(
        [{"source": "a", "target": "b", "source_name": "A", "target_name": "B",
          "effect": "facilitation", "strength": 1.0, "status": "present", "outcome": "quantified",
          "study_id": "S1", "metric": "growth_rate:easylinear:5"}],
        meta={"source_db": "mGrowthDB (live)", "query": "species", "species": ["A"], "studies": ["S1"],
              "settings": dict(DEFAULTS), "selection": {"media": []}, "absence": {"k": 1.0},
              "statistics": {"correction": "bh"}, "hidden": {"absent": 0}})
    assert schema.validate_document(json.loads(json.dumps(net.to_dict()))) == []
