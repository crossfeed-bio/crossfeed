import json
import os

from crossfeed.attribution import edge_citations, render_attribution, studies_with_edges
from crossfeed.mgrowthdb import effect_from_logratio, records_to_network
from crossfeed.model import Edge, InteractionNetwork, Node

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "example_interactions.json")


def _records():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def test_effect_logic():
    assert effect_from_logratio(0.3, 0.01) == "facilitation"
    assert effect_from_logratio(-0.3, 0.01) == "inhibition"
    assert effect_from_logratio(0.3, 0.50) == "neutral"     # not significant
    assert effect_from_logratio(None, None) == "neutral"


def test_build_and_roundtrip():
    net = records_to_network(_records(), meta={"slice": "test"})
    assert net.validate() == []
    assert len(net.nodes) == 3          # fp, bh, ri
    assert len(net.edges) == 2
    # the significant positive edge is facilitation; the non-significant one is neutral
    effects = sorted(e.effect for e in net.edges)
    assert effects == ["facilitation", "neutral"]
    # round-trip through JSON is lossless
    net2 = InteractionNetwork.from_dict(json.loads(net.to_json()))
    assert net2.validate() == []
    assert net2.to_dict() == net.to_dict()


def test_edge_level_attribution():
    net = records_to_network(_records())
    cites = edge_citations(net)
    assert cites and all(c["studies"] for c in cites)       # every edge carries at least one study
    by_study = studies_with_edges(net)
    assert len(by_study["SYNTHETIC-EXAMPLE"]) == 2          # the study resolves to its two edges
    assert "edge level" in render_attribution(net).lower()


def test_missing_study_is_invalid():
    net = InteractionNetwork()
    net.add_node(Node("a"))
    net.add_node(Node("b"))
    net.add_edge(Edge("a", "b", "facilitation", study_ids=("nope",)))
    assert any("unknown study" in p for p in net.validate())


def test_edge_without_study_is_invalid():
    e = Edge("a", "b", "facilitation")      # no study_ids
    assert any("edge-level attribution" in p for p in e.validate())
