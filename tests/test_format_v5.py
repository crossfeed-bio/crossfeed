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
    # A's monoculture by flow cytometry, its co-culture by qpcr: the row rests on both, and says so. Taken
    # from the co-culture alone it would read "qpcr" (found in review)
    client.bioreplicates[1]["measurementContexts"][0]["techniqueType"] = "fc"
    records, _ = IntegratedDeriver(client=client).derive({"id": "S1"}, exps)
    arc = next(r for r in records if r["target_name"] == "A" and r["source_name"] == "B")
    assert arc["technique"] == "fc; qpcr"


def test_a_dropout_arc_records_the_technique_of_its_target():
    """The drop-out comparison builds its own record; the fake measures every strain by qpcr. Every arc of
    the hand-computed drop-out design of tests/test_derive.py carries it."""
    from test_derive import _dropout_study

    from grownet.derive import interactions_from_replicates
    client, study, exps = _dropout_study()
    records, _ = interactions_from_replicates(client, study, exps)
    assert records and {r["evidence"] for r in records} == {"dropout"}
    assert {r["technique"] for r in records} == {"qpcr"}


def test_a_merged_arc_names_every_technique_its_arcs_rest_on():
    """Merge parallel arcs merges across techniques (Karoline, 2026-11-06, on #305: "I think that measurement
    techniques should agree to the point that arcs with different measurement techniques can be merged",
    and asked whether to allow it, "Yes, allow it"), and says so the way it says which media it crossed:
    every distinct value, joined."""
    from grownet.derive import merge_parallel
    def arc(technique, strength):
        return {"source": "a", "target": "b", "effect": "facilitation", "strength": strength, "status": "present",
                "outcome": "quantified", "technique": technique, "study_id": "S1", "condition": "c",
                "method": "m", "experiments": [], "quality": [], "cautions": [], "notes": [], "community": []}
    assert _merged([arc("qpcr", 1.0), arc("qpcr", 2.0)])["technique"] == "qpcr"
    # sorted, as a single arc's are, so the same set reads the same whichever arc came first
    assert _merged([arc("qpcr", 1.0), arc("fc", 2.0), arc("qpcr", 3.0)])["technique"] == "fc; qpcr"
    assert _merged([arc("fc", 1.0), arc("qpcr; unrecorded", 2.0)])["technique"] == "fc; qpcr; unrecorded"
    # and the merge itself does not keep them apart: a qpcr arc of 1.0 and an fc arc of 3.0 between the
    # same pair, same sign, become one arc, the median 2.0 of two
    (one,), meta = merge_parallel([arc("qpcr", 1.0), arc("fc", 3.0)])
    assert (one["merged_arcs"], one["strength"], one["technique"], meta["merged"]) == (2, 2.0, "fc; qpcr", 1)


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
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    keys = {k.get("attr.name") for k in graphml.iter(f"{ns}key")}
    assert "technique" in keys
    # declared and written: the value is on the edge
    assert [d.text for d in graphml.iter(f"{ns}data") if d.get("key") == "e_technique"] == ["fc"]


@pytest.mark.parametrize("schema", ["grownet.interaction_network/v4", "grownet.interaction_network/v3"])
def test_an_older_file_still_reads_and_validates(schema):
    """An addition, not a change of meaning: a file without the field is valid and reads with it empty."""
    doc = {"schema": schema, "meta": {}, "studies": [{"id": "S1"}], "nodes": [{"id": "a"}, {"id": "b"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"]}]}
    assert validate_document(doc) == []
    assert InteractionNetwork.from_dict(doc).edges[0].technique == ""


def test_a_genus_node_lists_the_strains_it_stands_for():
    """Karoline, 2026-11-06, asked whether a genus node should list its strain ids, in the same unreleased
    format move as `technique`: "Yes, add it". It did not: a genus node kept no strain id, and the strains
    were named only on its arcs. `merged_nodes` is the strain node ids of that genus among the network's
    arcs, sorted; empty on every node without Merge to genus."""
    from grownet.derive import merge_genus

    def arc(source, source_name, target, target_name, strength):
        return {"source": source, "target": target, "source_name": source_name, "target_name": target_name,
                "source_taxon_id": source.split(":")[-1], "target_taxon_id": target.split(":")[-1],
                "source_identity": "ncbi", "target_identity": "ncbi", "effect": "facilitation",
                "strength": strength, "status": "present", "outcome": "quantified", "study_id": "S1",
                "condition": "c", "method": "m", "experiments": [], "quality": [], "cautions": [], "notes": [],
                "community": []}
    # Alpha has two strains among the arcs, Beta one; Alpha one -> Beta and Alpha three -> Beta merge into
    # one genus arc, so the network holds two nodes
    arcs = [arc("ncbi:3", "Alpha three", "ncbi:2", "Beta two", 1.0),
            arc("ncbi:1", "Alpha one", "ncbi:2", "Beta two", 3.0)]
    by_strain = records_to_network(arcs)
    assert all(node.merged_nodes == () for node in by_strain.nodes.values())
    edges, _ = merge_genus(arcs, merge=True)
    net = records_to_network(edges)
    assert net.nodes["Alpha"].merged_nodes == ("ncbi:1", "ncbi:3")
    assert net.nodes["Beta"].merged_nodes == ("ncbi:2",)
    # in every file: JSON (and back), GraphML joined by "; " as the arc lists are, and valid
    import json
    doc = json.loads(net.to_json())                       # as the file holds it
    assert next(n for n in doc["nodes"] if n["id"] == "Alpha")["merged_nodes"] == ["ncbi:1", "ncbi:3"]
    assert InteractionNetwork.from_dict(doc).nodes["Alpha"].merged_nodes == ("ncbi:1", "ncbi:3")
    notes = []
    assert validate_document(doc, notes) == [] and not [n for n in notes if "declare" in n], notes
    graphml = ET.fromstring(to_graphml(net))
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    alpha = next(n for n in graphml.iter(f"{ns}node") if n.get("id") == "Alpha")
    assert [d.text for d in alpha.iter(f"{ns}data") if d.get("key") == "n_merged_nodes"] == ["ncbi:1; ncbi:3"]


def test_a_genus_node_lists_its_strains_from_every_arc_of_the_genus():
    """The strains of a genus node come from every arc of that genus, not from one merged arc: Alpha one
    meets Beta and Alpha three meets Gamma, two genus arcs, and the Alpha node stands for both strains."""
    from grownet.derive import merge_genus

    def arc(source, source_name, target, target_name):
        return {"source": source, "target": target, "source_name": source_name, "target_name": target_name,
                "source_taxon_id": source.split(":")[-1], "target_taxon_id": target.split(":")[-1],
                "source_identity": "ncbi", "target_identity": "ncbi", "effect": "facilitation",
                "strength": 1.0, "status": "present", "outcome": "quantified", "study_id": "S1",
                "condition": "c", "method": "m", "experiments": [], "quality": [], "cautions": [], "notes": [],
                "community": []}
    edges, _ = merge_genus([arc("ncbi:1", "Alpha one", "ncbi:2", "Beta two"),
                            arc("ncbi:3", "Alpha three", "ncbi:4", "Gamma four")], merge=True)
    net = records_to_network(edges)
    assert len(net.edges) == 2
    assert net.nodes["Alpha"].merged_nodes == ("ncbi:1", "ncbi:3")
    assert (net.nodes["Beta"].merged_nodes, net.nodes["Gamma"].merged_nodes) == (("ncbi:2",), ("ncbi:4",))


def test_a_steady_state_arc_records_how_its_runs_were_measured():
    """The steady-state derivation's arcs carry the technique of their chemostat group, as every arc of
    /v5 does: they had an empty one (found in review). The invented runs are all qPCR."""
    from test_steady_derivation import _derive
    records, _ = _derive()
    assert records and {r["technique"] for r in records} == {"qpcr"}
