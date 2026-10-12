"""The five fields of grownet.interaction_network/v4 (Karoline, 2026-10-12, on #266, #217 and #209)."""
import xml.etree.ElementTree as ET

from grownet.derive import against_other_removals, metric_unit, strain_identities
from grownet.export import to_graphml
from grownet.mgrowthdb import records_to_network
from grownet.model import SCHEMA, InteractionNetwork
from grownet.schema import validate_document


def test_the_unit_of_the_two_metric_values_follows_the_metric():
    """#214: 190 of 223 live arcs carried no unit for metric_with and metric_without."""
    assert metric_unit("auc", "Cells/mL", "h") == "Cells/mL x h"
    assert metric_unit("max", "Cells/mL", "h") == "Cells/mL"
    assert metric_unit("growth_rate:easylinear:5", "Cells/mL", "h") == "1/h"
    assert metric_unit("auc", "", "h") == "" and metric_unit("unknown", "Cells/mL", "h") == ""


def _drop(source, strength, with_=3.5, target="t", medium="WC"):
    return {"source": source, "target": target, "evidence": "dropout", "strength": strength,
            "metric_with": with_, "study_id": "S8", "medium": medium, "metric": "auc"}


def test_a_drop_out_arc_against_the_other_removals_of_its_target():
    """#209 option 2: what this removal did beyond the level its group shares, the median of the others."""
    group = [_drop("a", 1.0), _drop("b", 2.0), _drop("c", 4.0)]
    pair = [_drop("d", 1.0, with_=9.0), _drop("e", 3.0, with_=9.0)]          # two: no reference
    other = {"source": "x", "target": "t", "evidence": "biculture", "strength": 5.0, "metric_with": 3.5,
             "study_id": "S8", "medium": "WC", "metric": "auc"}
    records = [*group, *pair, other]
    against_other_removals(records)
    assert [r["vs_other_removals"] for r in group] == [1.0 - 3.0, 2.0 - 2.5, 4.0 - 1.5]
    assert [r["vs_other_removals"] for r in pair] == [None, None]
    assert other["vs_other_removals"] is None, "a biculture arc has no group of removals"
    # another reference is another group: same target, another medium
    split = [_drop("a", 1.0), _drop("b", 2.0), _drop("c", 4.0, medium="other")]
    against_other_removals(split)
    assert [r["vs_other_removals"] for r in split] == [None, None, None]


def test_a_refused_taxon_id_is_kept_and_said_not_to_be_a_join_key():
    """#217 option b: SMGDB00000008 gives 1506553 to two strains. The id stays, the node says why it is not
    the identity, and the node id is the name, as before."""
    exps = [{"communityStrains": [{"name": "Lachnoclostridium clostridioforme 2_1_49FAA", "NCBId": 1506553},
                                  {"name": "Lachnoclostridium symbiosum WAL-14673", "NCBId": 1506553},
                                  {"name": "Bacteroides ovatus 3_8_47FAA", "NCBId": 665954}]}]
    ids = strain_identities(exps, [])
    refused = ids["Lachnoclostridium symbiosum WAL-14673"]
    assert refused["taxon_id"] == "1506553" and refused["identity"] == "name"
    assert "1506553" in refused["taxon_id_refused"] and "not a join key" in refused["taxon_id_refused"]
    assert ids["Bacteroides ovatus 3_8_47FAA"]["taxon_id_refused"] == ""


def test_every_v4_field_reaches_the_file_graphml_and_validation():
    net = records_to_network([{
        "source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
        "strength": 1.0, "study_id": "S1", "metric_unit": "Cells/mL x h", "window": 30.0, "window_unit": "h",
        "vs_other_removals": -0.5, "source_taxon_id": "1506553",
        "source_taxon_id_refused": "mGrowthDB gives taxon id 1506553 to different strains in this study"}])
    doc = net.to_dict()
    assert doc["schema"] == SCHEMA == "grownet.interaction_network/v4"
    (edge,) = doc["edges"]
    assert (edge["metric_unit"], edge["window"], edge["window_unit"], edge["vs_other_removals"]) == \
        ("Cells/mL x h", 30.0, "h", -0.5)
    node = next(n for n in doc["nodes"] if n["id"] == "a")
    assert node["taxon_id_refused"].startswith("mGrowthDB gives taxon id 1506553")
    notes = []
    assert validate_document(doc, notes) == [] and not [n for n in notes if "declare" in n], notes
    # and back: a v4 file reads into the same fields
    again = InteractionNetwork.from_dict(doc)
    assert again.edges[0].window == 30.0 and again.nodes["a"].taxon_id_refused == node["taxon_id_refused"]
    graphml = ET.fromstring(to_graphml(net))
    keys = {k.get("attr.name") for k in graphml.iter("{http://graphml.graphdrawing.org/xmlns}key")}
    assert {"metric_unit", "window", "window_unit", "vs_other_removals", "taxon_id_refused"} <= keys


def test_a_v3_file_still_reads_and_validates():
    """Additions, not changes of meaning: a v3 document without the five fields is valid and reads."""
    doc = {"schema": "grownet.interaction_network/v3", "meta": {}, "studies": [{"id": "S1"}],
           "nodes": [{"id": "a"}, {"id": "b"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"]}]}
    assert validate_document(doc) == []
    net = InteractionNetwork.from_dict(doc)
    assert net.edges[0].metric_unit == "" and net.edges[0].window is None
