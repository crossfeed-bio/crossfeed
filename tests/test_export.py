"""GraphML export: well-formed, directed, and it keeps effect, attribution, and null handling right."""
from xml.etree import ElementTree as ET

from crossfeed.export import to_graphml
from crossfeed.mgrowthdb import records_to_network

NS = {"g": "http://graphml.graphdrawing.org/xmlns"}


def _net():
    recs = [
        {"source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
         "strength": 1.2, "significance": 0.01, "condition": "C", "method": "m", "study_id": "S1"},
        {"source": "a", "target": "c", "effect": "neutral", "strength": None, "significance": None,
         "study_id": "S1"},
    ]
    return records_to_network(recs)


def test_graphml_is_well_formed_and_directed():
    root = ET.fromstring(to_graphml(_net()))
    assert root.find("g:graph", NS).get("edgedefault") == "directed"
    assert len(root.findall(".//g:node", NS)) == 3
    assert len(root.findall(".//g:edge", NS)) == 2


def test_graphml_edge_carries_effect_and_attribution():
    root = ET.fromstring(to_graphml(_net()))
    edge = [e for e in root.findall(".//g:edge", NS) if e.get("target") == "b"][0]
    data = {d.get("key"): d.text for d in edge.findall("g:data", NS)}
    assert data["e_effect"] == "facilitation"
    assert data["e_study_ids"] == "S1"
    assert data["e_strength"] == "1.2"


def test_graphml_omits_null_numbers():
    root = ET.fromstring(to_graphml(_net()))
    neutral = [e for e in root.findall(".//g:edge", NS) if e.get("target") == "c"][0]
    keys = {d.get("key") for d in neutral.findall("g:data", NS)}
    assert "e_strength" not in keys and "e_significance" not in keys
