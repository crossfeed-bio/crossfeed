"""The check that reads what grownet derives from the live corpus (#237), proven on constructed arcs.

The check itself runs in the all-network workflow against mGrowthDB; the suite stays offline, so here
every property is shown to hold on a well-formed network and to catch the violation it is for.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
from live_check import network_problems  # noqa: E402

from grownet.mgrowthdb import records_to_network  # noqa: E402


def _quantified(source="a", target="b", mw=2.0, mwo=1.0, sd=0.5, q=0.01, evidence="biculture", **extra):
    strength = round(math.log2(mw / mwo), 4)
    return {"source": source, "target": target, "source_name": source.upper(), "target_name": target.upper(),
            "effect": "facilitation" if strength > 0 else "inhibition", "strength": strength,
            "weight": abs(strength), "sd": sd, "se": sd / 2, "effect_over_sd": round(abs(strength) / sd, 4),
            "q_value": q, "p_value": q / 2, "significance": round(-math.log10(q), 4), "status": "present",
            "outcome": "quantified", "evidence": evidence, "metric": "auc", "metric_with": mw,
            "metric_without": mwo, "n_with": 3, "n_without": 3, "experiments": ["E1"], "medium": "WC",
            "partner_abundance": 2e8, "study_id": "S1", "study_citation": "A study", **extra}


def _censored(**extra):
    return {"source": "c", "target": "b", "source_name": "C", "target_name": "B", "effect": "facilitation",
            "strength": None, "status": "present", "outcome": "obligate", "evidence": "biculture",
            "metric": "auc", "metric_with": 2.0, "metric_without": 0.0, "n_with": 3, "n_without": 3,
            "experiments": ["E2"], "medium": "WC", "bound_rule": "the rule's own words", "strength_bound": 2.5,
            "partner_abundance": 1e8, "study_id": "S1", "study_citation": "A study", **extra}


def _net(records, derivation="replicate"):
    return records_to_network(records, meta={"settings": {"derivation": derivation}, "absence": {"k": 1.0}})


def test_a_well_formed_network_has_no_violation():
    assert network_problems(_net([_quantified(), _censored()]), "x") == []


@pytest.mark.parametrize("change, says", [
    ({"strength": 1.01, "weight": 1.01}, "is not log2(metric_with / metric_without)"),   # #224's class
    ({"weight": 0.5}, "is not |strength|"),
    ({"effect": "inhibition"}, "disagrees with the sign"),
    ({"significance": 3.0}, "is not -log10(q_value)"),
    ({"effect_over_sd": 9.0}, "is not |strength| / sd"),
    ({"metric_with": None}, "missing metric_with"),
    ({"q_value": None}, "missing q_value"),
    ({"experiments": []}, "missing experiments"),
    ({"partner_abundance": None}, "missing partner_abundance"),
    ({"status": "absent"}, "status absent with |strength|"),
])
def test_each_property_catches_its_violation(change, says):
    problems = network_problems(_net([_quantified(**change)]), "x")
    assert any(says in p for p in problems), problems


def test_a_censored_arc_must_say_its_rule_and_have_no_ratio():
    assert any("missing bound_rule" in p for p in network_problems(_net([_censored(bound_rule="")]), "x"))
    # the bound itself may be absent: the rule bounds nothing away from zero, and says so
    assert network_problems(_net([_censored(strength_bound=None)]), "x") == []


def test_an_undetermined_arc_needs_no_test():
    """No spread, so no t-test and status None: legitimate, 2 of the All network's arcs today."""
    arc = _quantified()
    arc.update({"sd": None, "se": None, "q_value": None, "p_value": None, "significance": None,
                "effect_over_sd": None, "status": None})
    assert network_problems(_net([arc]), "x") == []


def test_the_log2_identity_is_the_comparison_s_and_the_coefficient_identity_the_fit_s():
    """Under the integrated form strength is near log2 of the ratio and not equal (the help says so), and
    the coefficient is exactly (metric_with - metric_without) / partner_abundance: measured live on
    SMGDB00000002 before this was written."""
    off = _quantified(strength=0.9, weight=0.9, effect_over_sd=1.8)
    assert network_problems(_net([off], "integrated"), "x") == []
    good = _quantified(coefficient=(2.0 - 1.0) / 2e8, coefficient_unit="1/(h x Cells/mL)")
    assert network_problems(_net([good], "integrated"), "x") == []
    bad = _quantified(coefficient=2 * (2.0 - 1.0) / 2e8, coefficient_unit="1/(h x Cells/mL)")
    assert any("is not (metric_with - metric_without)" in p for p in network_problems(_net([bad], "integrated"), "x"))
    assert any("with no unit" in p for p in network_problems(_net([_quantified(coefficient=1e-9)], "integrated"), "x"))


def test_the_network_level_properties():
    assert any("no arcs at all" in p for p in network_problems(_net([]), "x"))
    net = _net([_quantified()])
    net.meta["mystery"] = 1
    assert any("does not declare" in p for p in network_problems(net, "x"))
    net = _net([_quantified()])
    net.meta.update({"complete": False, "errors": ["S9: 404"]})
    assert any("could not read everything" in p for p in network_problems(net, "x"))
    assert any("nothing to cite" in p for p in network_problems(_net([_quantified(study_citation="")]), "x"))


def test_the_workflow_runs_it_after_publishing_with_its_own_issue():
    path = ROOT / ".github" / "workflows" / "all-network.yml"
    if not path.exists():
        pytest.skip("no .github in this tree (an unpacked sdist)")
    wf = path.read_text(encoding="utf-8")
    assert wf.index("gh release upload all-network") < wf.index("python packaging/live_check.py out")
    assert "--label live-check-failed" in wf
    # the build-failure issue does not fire for a live-check failure, and its closing depends on the publish
    assert "if: failure() && steps.live.outcome != 'failure'" in wf
    assert "if: always() && steps.publish.outcome == 'success'" in wf


def test_the_effect_over_sd_tolerance_follows_each_arc_s_own_rounding():
    """Craig's agent, on #281: recomputing |strength| / sd from two rounded values carries an error of up to
    U/sd + |strength| U/sd^2. A fixed 1e-3 sat three times above today's worst honest residual and would
    have cried wolf on a smaller sd. The bound is per arc: honest rounding passes at a small sd, and a
    corruption of 0.01 is still caught at an ordinary one."""
    # strength 0.3 at sd 0.02: honest rounding can move the ratio by 0.04, and the old fixed tolerance,
    # 1e-3 of a ratio of 15, was 0.015, so a residual of 0.03 cried wolf there and passes here
    honest = _quantified(mw=2 ** 0.3, sd=0.02, effect_over_sd=round(0.3 / 0.02 + 0.03, 4))
    assert not any("effect_over_sd" in p for p in network_problems(_net([honest]), "x"))
    corrupt = _quantified(effect_over_sd=round(1.0 / 0.5 + 0.01, 4))
    assert any("effect_over_sd" in p for p in network_problems(_net([corrupt]), "x"))

