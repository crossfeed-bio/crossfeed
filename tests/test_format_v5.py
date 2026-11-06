"""The arc's measurement technique, the field of grownet.interaction_network/v5 (#305).

Karoline, 2026-11-06: "Is the measurement technique recorded as an arc attribute? If not, please add."
"""
import math
import xml.etree.ElementTree as ET

import pytest

from grownet.derive import _merged, techniques_of
from grownet.export import to_graphml
from grownet.growth import GrowthCurve, Replicate
from grownet.mgrowthdb import records_to_network
from grownet.model import SCHEMA, InteractionNetwork
from grownet.schema import validate_document


def _replicate(*curves):
    return Replicate(tuple(GrowthCurve(species, (0.0, 1.0), (1.0, 2.0), "h", unit, technique)
                           for species, unit, technique in curves))


def test_the_technique_is_every_distinct_technique_the_target_was_measured_by():
    # the target "t" by qpcr in two replicates and by fc in a third, its partner by 16s, which is not the
    # target's and is not counted; sorted, so the same set always reads the same
    reps = [_replicate(("t", "Cells/mL", "qpcr"), ("p", "reads", "16s")),
            _replicate(("t", "Cells/mL", "qpcr")), _replicate(("t", "Cells/mL", "fc"))]
    assert techniques_of(reps[:2], "t") == "qpcr"
    assert techniques_of(reps, "t") == "fc; qpcr"
    assert techniques_of(reps, "nobody") == ""
    # a curve whose technique mGrowthDB did not record is named as such, not dropped, so "qpcr" alone is
    # never claimed for an arc that also rests on an unrecorded one
    assert techniques_of([reps[0], _replicate(("t", "OD600", ""))], "t") == "qpcr; unrecorded"


def test_an_arc_of_the_comparison_records_the_technique_of_its_target():
    """The fake study measures every strain by qpcr (tests/test_gui.py)."""
    from test_gui import _query
    edges = _query()["network"].edges
    assert edges and {e.technique for e in edges} == {"qpcr"}


def test_an_arc_of_the_integrated_form_records_the_technique_of_its_target():
    """The integrated form's row is fitted over the co-culture and the target's monoculture rate, so its
    technique covers both; the fake measures both by qpcr. The curves are the ones
    tests/test_integrated.py fits a row from."""
    from test_growth_rates import _client, _co, _mono
    from test_integrated import _simulate

    from grownet.integrated import IntegratedDeriver
    mono_a = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    mono_b = _simulate([0.3], [[-3.0e-10]], [5.0e8])
    co = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])

    def series(times, values, which=0):
        return [(t, row[which], None) for t, row in zip(times, values, strict=True)]

    client = _client({(1, "A"): series(*mono_a), (2, "B"): series(*mono_b),
                      (3, "A"): series(*co, 0), (3, "B"): series(*co, 1)})
    exps = [_mono("E1", "A", [(1, "r1")]), _mono("E2", "B", [(2, "r1")]), _co("E3", "A", "B", [(3, "r1")])]
    records, _ = IntegratedDeriver(client=client).derive({"id": "S1"}, exps)
    arc = next(r for r in records if r["target_name"] == "A" and r["source_name"] == "B")
    assert math.isfinite(arc["coefficient"]) and arc["technique"] == "qpcr"


def test_a_merged_arc_names_every_technique_its_arcs_rest_on():
    """Until #305's question is settled, Merge parallel arcs merges across techniques, as it did before the
    field existed, and says so the way it says which media it crossed: every distinct value, joined."""
    def arc(technique, strength):
        return {"source": "a", "target": "b", "effect": "facilitation", "strength": strength, "status": "present",
                "outcome": "quantified", "technique": technique, "study_id": "S1", "condition": "c",
                "method": "m", "experiments": [], "quality": [], "cautions": [], "notes": [], "community": []}
    assert _merged([arc("qpcr", 1.0), arc("qpcr", 2.0)])["technique"] == "qpcr"
    assert _merged([arc("qpcr", 1.0), arc("fc", 2.0), arc("qpcr", 3.0)])["technique"] == "qpcr; fc"


def test_the_v5_field_reaches_the_file_graphml_and_validation():
    net = records_to_network([{
        "source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
        "strength": 1.0, "study_id": "S1", "technique": "fc"}])
    doc = net.to_dict()
    assert doc["schema"] == SCHEMA == "grownet.interaction_network/v5"
    assert doc["edges"][0]["technique"] == "fc"
    notes = []
    assert validate_document(doc, notes) == [] and not [n for n in notes if "declare" in n], notes
    assert InteractionNetwork.from_dict(doc).edges[0].technique == "fc"
    graphml = ET.fromstring(to_graphml(net))
    keys = {k.get("attr.name") for k in graphml.iter("{http://graphml.graphdrawing.org/xmlns}key")}
    assert "technique" in keys


@pytest.mark.parametrize("schema", ["grownet.interaction_network/v4", "grownet.interaction_network/v3"])
def test_an_older_file_still_reads_and_validates(schema):
    """An addition, not a change of meaning: a file without the field is valid and reads with it empty."""
    doc = {"schema": schema, "meta": {}, "studies": [{"id": "S1"}], "nodes": [{"id": "a"}, {"id": "b"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"]}]}
    assert validate_document(doc) == []
    assert InteractionNetwork.from_dict(doc).edges[0].technique == ""
