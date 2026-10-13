"""What a reader cannot see one drop-out arc at a time, said in the report (#207, #209)."""
from grownet.mgrowthdb import records_to_network
from grownet.report import _design_lines, opposed_designs, shared_references


def _arc(source, target, effect, strength, evidence, with_=1.0, medium="WC", study="S8", q=0.01):
    return {"source": source, "target": target, "source_name": source.upper(), "target_name": target.upper(),
            "effect": effect, "strength": strength, "status": "present", "evidence": evidence,
            "metric_with": with_, "medium": medium, "study_id": study, "metric": "auc", "q_value": q}


def test_drop_out_arcs_against_one_full_community_are_grouped():
    """#209: every drop-out arc to a target shares the full community's measurement, so part of each is
    the target's level and not the removal. Grouped by that measurement, within one study and medium."""
    arcs = [_arc(s, "t", "inhibition", -1.0, "dropout", with_=3.5) for s in "abc"]
    arcs += [_arc("d", "t", "inhibition", -1.0, "dropout", with_=3.5, medium="other")]   # another medium
    arcs += [_arc("e", "u", "inhibition", -1.0, "dropout", with_=2.0)]                     # alone
    arcs += [_arc("f", "t", "inhibition", -1.0, "biculture", with_=3.5)]                   # not a drop-out
    arcs += [_arc("g", "t", "inhibition", -1.0, "dropout", with_=2.0)]                     # another reference
    arcs += [_arc(s, "v", "inhibition", -1.0, "dropout", with_=5.0) for s in "hi"]          # a group of two
    net = records_to_network(arcs)
    groups = shared_references(net.edges)
    assert [(g[0], g[2], g[3]) for g in groups] == [("t", "WC", 3), ("v", "WC", 2)], groups
    text = "\n".join(_design_lines(net, net.edges))
    assert "drop-out arcs sharing one reference: 5 arcs in 2 group(s)" in text
    assert "  T: 3 arcs, S8, in WC" in text


def test_a_pair_measured_both_ways_with_opposite_effects_is_named_as_a_result():
    """#207, and Karoline's decision on it: the pair alone and inside a community pulling opposite ways is
    a higher-order interaction, measured, so both arcs are named together and neither overrides."""
    arcs = [_arc("r", "b", "inhibition", -2.54, "biculture", q=0.0014),
            _arc("r", "b", "facilitation", 2.13, "dropout", q=0.0002),
            _arc("x", "y", "facilitation", 1.0, "biculture"), _arc("x", "y", "facilitation", 0.8, "dropout")]
    net = records_to_network(arcs)
    opposed = opposed_designs(net.edges)
    assert [(s, t) for s, t, _ in opposed] == [("r", "b")], "agreeing designs are not listed"
    text = "\n".join(_design_lines(net, net.edges))
    assert "A result, not an error" in text and "higher-order interaction" in text
    assert "R -> B: inhibition -2.54 (biculture, q 0.0014, WC); facilitation +2.13 (dropout, q 0.0002, WC)" in text


def test_nothing_is_said_when_there_is_nothing_to_say():
    net = records_to_network([_arc("a", "b", "facilitation", 1.0, "biculture")])
    assert _design_lines(net, net.edges) == []
