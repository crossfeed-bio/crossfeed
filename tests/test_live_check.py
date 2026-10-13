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
    # the build-failure issue only when nothing was published: not for a live check, not for a failed
    # description or a failed close step after a successful publish (found in review)
    assert "if: failure() && steps.publish.outcome != 'success'" in wf
    assert "OUTCOME: ${{ steps.live.outputs.outcome }}" in wf
    # a failed description has its own issue, and does not stop the live check (found in review)
    assert "if: always() && steps.describe.outcome == 'failure'" in wf
    live = wf[wf.index("id: live"):wf.index("run: python packaging/live_check.py out")]
    assert "if: always() && steps.publish.outcome == 'success'" in live
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


def test_a_check_that_could_not_run_is_not_reported_as_a_broken_property(tmp_path, monkeypatch, capsys):
    """Found in review: an mGrowthDB outage made the check raise, exit 1, and open an issue saying arcs broke
    a property while naming none. It now exits 2, says it could not run, and tells the workflow."""
    import live_check
    monkeypatch.setattr(live_check, "check_published", lambda out: ([], "All"))
    monkeypatch.setattr(live_check, "check_glv_mode",
                        lambda: (_ for _ in ()).throw(RuntimeError("mGrowthDB could not be read")))
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert live_check.main(str(tmp_path)) == 2
    assert "outcome=error" in output.read_text() and "could not run" in capsys.readouterr().out
    # but a published file grownet cannot read is a broken property, not a check that could not run: it
    # is local and was just written, and every copy's fetch would refuse it (found in review)
    monkeypatch.setattr(live_check, "check_published",
                        lambda out: (_ for _ in ()).throw(TypeError("Edge.__init__() missing 'source'")))
    output.write_text("")
    assert live_check.main(str(tmp_path)) == 1 and "outcome=violation" in output.read_text()
    # and a real violation is still a violation
    monkeypatch.setattr(live_check, "check_published", lambda out: (["All: weight 0.5 is not |strength|"], "All"))
    monkeypatch.setattr(live_check, "check_glv_mode", lambda: ([], "gLV"))
    output.write_text("")
    assert live_check.main(str(tmp_path)) == 1 and "outcome=violation" in output.read_text()



def test_the_checks_the_first_tests_did_not_reach():
    """Found in review by deleting each check in turn: these survived the suite."""
    # a censored arc that carries a strength
    assert any("has no ratio" in p for p in network_problems(_net([_censored(strength=1.0)]), "x"))
    # neither a medium nor a condition
    assert any("medium or condition" in p for p in network_problems(_net([_quantified(medium="")]), "x"))
    # an arc citing a study the network does not list
    net = _net([_quantified()])
    net.edges[0] = __import__("dataclasses").replace(net.edges[0], study_ids=("S404",))
    assert any("does not list" in p for p in network_problems(net, "x"))


def test_the_published_file_and_its_legacy_copy_are_checked(tmp_path, monkeypatch):
    """`check_published` reads the current file, the arcs below the threshold and the /v3 copy; each part
    is shown to catch what it is for."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    assert live_check.check_published(str(out))[0] == [], "a clean publish has nothing to report"
    legacy = json.loads((out / "all_result.json").read_text())
    legacy["network"]["edges"][0]["window"] = 30.0                           # a field /v3 does not declare
    (out / "all_result.json").write_text(json.dumps(legacy))
    assert any("does not declare" in p and "window" in p for p in live_check.check_published(str(out))[0])
    legacy["network"]["edges"][0].pop("window")
    legacy["network"]["edges"] = legacy["network"]["edges"] + legacy["network"]["edges"]   # arcs doubled
    (out / "all_result.json").write_text(json.dumps(legacy))
    assert any("different number of arcs" in p for p in live_check.check_published(str(out))[0])


def test_a_glv_check_that_found_no_coefficient_says_so(monkeypatch):
    import live_check

    from grownet import gui
    monkeypatch.setattr(gui, "run_query", lambda *a, **k: {"network": _net([_quantified()]), "errors": []})
    problems, _ = live_check.check_glv_mode("S1")
    assert any("ran on nothing" in p for p in problems)


def test_an_invalid_legacy_file_and_a_present_arc_among_the_absent_ones_are_caught(tmp_path, monkeypatch):
    """Round 2 of the review: deleting the legacy-validity check, or the absent-status check, survived."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    legacy_path = out / "all_result.json"
    legacy = json.loads(legacy_path.read_text())
    legacy["network"]["edges"][0]["effect"] = "not an effect"             # invalid, same arc count
    legacy_path.write_text(json.dumps(legacy))
    assert any("all_result.json: invalid" in p for p in live_check.check_published(str(out))[0])
    current_path = out / "all_result.v4.json"
    current = json.loads(current_path.read_text())
    edge = dict(current["network"]["edges"][0], status="present")
    current["absent"] = {**current["network"], "edges": [edge]}
    current_path.write_text(json.dumps(current))
    assert any("below the threshold" in p and "status present" in p
               for p in live_check.check_published(str(out))[0])


def test_mgrowthdb_errors_in_the_glv_study_mean_could_not_run(tmp_path, monkeypatch):
    """Round 2: ignoring `result["errors"]` of the gLV-mode study survived."""
    import live_check

    from grownet import gui
    monkeypatch.setattr(gui, "run_query", lambda *a, **k: {"network": _net([_quantified()]),
                                                            "errors": ["S2: HTTP 503"]})
    monkeypatch.setattr(live_check, "check_published", lambda out: ([], "All"))
    assert live_check.main(str(tmp_path)) == 2
