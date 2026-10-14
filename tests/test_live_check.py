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
    describe = wf[wf.index("- name: describe what was published"):wf.index("- name: say when the description")]
    assert "id: describe" in describe, "without the id the stale-description issue never opens or closes"
    closing = wf[wf.index("- name: close the description issue"):]
    assert "if: always() && steps.describe.outcome == 'success'" in closing[:200]
    assert 'Failed again ($OUTCOME)' in wf
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


def test_a_broken_older_file_is_named_as_that_file(tmp_path, monkeypatch):
    """Round 3 of the review: a truncated all_result.json was reported as "the published file could not be
    read", which reads as the current file, and the current file's results were thrown away."""
    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    (out / "all_result.json").write_text("{truncated")
    problems, what = live_check.check_published(str(out))
    assert any(p.startswith("all_result.json: could not be read") for p in problems), problems
    assert what.startswith("All:"), "the current file was still checked"
    # a file that parses but is malformed, which is what a bug in the legacy strip would write: `"nodes":
    # null` raised in the field walk and reported the CURRENT file as unreadable (round 4 of the review)
    import json
    good = json.loads((out / "all_result.v4.json").read_text())
    good["network"]["schema"] = "grownet.interaction_network/v3"
    # a network that is not there at all is named as that file too, which the edges probe is for
    (out / "all_result.json").write_text(json.dumps({**good, "network": None}))
    problems, what = live_check.check_published(str(out))
    assert any(p.startswith("all_result.json: could not be read") for p in problems), problems
    assert what.startswith("All:")
    for key in ("nodes", "studies"):
        broken = json.loads(json.dumps(good))
        broken["network"][key] = None
        (out / "all_result.json").write_text(json.dumps(broken))
        problems, what = live_check.check_published(str(out))
        assert f"all_result.json: invalid: {key} must be a list of objects" in problems, problems
        assert what.startswith("All:"), "the current file was still checked"



def test_an_older_file_that_was_not_written_is_named(tmp_path, monkeypatch):
    """Round 3 of the review: deleting the "not written" problem left the suite green."""
    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    (out / "all_result.json").unlink()
    problems, _ = live_check.check_published(str(out))
    assert any(p.startswith("all_result.json: not written, so copies reading grownet.interaction_network/v3")
               for p in problems), problems


def test_the_older_file_s_arcs_below_the_threshold_are_checked_too(tmp_path, monkeypatch):
    """Round 5 of the review: the older-format loop checked `network` only. 0.4.0 reads `absent` too: one
    dropped served no arc below the threshold, and `absent.edges: null` made every 0.4.0 copy derive All
    live, while the check said nothing."""
    import copy
    import dataclasses
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query

    def with_one_below(*a, **k):
        # the double gives no arc below the threshold at the defaults, so one of its arcs is put there
        result = run_query(FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False)
        absent = copy.deepcopy(result["network"])
        # two, while the network has one, so comparing with the wrong network's count is caught (round 6)
        first = absent.edges[0]
        absent.edges = [dataclasses.replace(first, status="absent"),
                        dataclasses.replace(first, status="absent", source=first.target, target=first.source)]
        return {**result, "absent": absent}
    monkeypatch.setattr(publish_all, "run_query", with_one_below)
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    clean = json.loads((out / "all_result.json").read_text())
    assert clean["absent"]["edges"], "an arc below the threshold, so there is one to lose"
    assert live_check.check_published(str(out))[0] == []

    def problems_with(change):
        broken = json.loads(json.dumps(clean))
        change(broken)
        (out / "all_result.json").write_text(json.dumps(broken))
        return live_check.check_published(str(out))[0]

    below = "all_result.json, below the threshold"
    assert f"{below}: missing, while the current file has it" in problems_with(lambda d: d.update(absent=None))
    assert f"{below}: invalid: edges must be a list of objects" in problems_with(
        lambda d: d["absent"].update(edges=None))
    assert any(p.startswith(f"{below}: says grownet.interaction_network/v4") for p in problems_with(
        lambda d: d["absent"].update(schema="grownet.interaction_network/v4")))
    assert any(p.startswith(f"{below}: edges carry fields") and "window" in p for p in problems_with(
        lambda d: d["absent"]["edges"][0].update(window=30.0)))
    assert f"{below}: a different number of arcs than the current one" in problems_with(
        lambda d: d["absent"].update(edges=d["absent"]["edges"] * 2))


def test_a_file_its_reader_would_refuse_is_a_problem(tmp_path, monkeypatch):
    """Round 6 of the review: a file in another result format, with no time it was derived at, or derived
    by another derivation passed the check while every copy refused it and derived All live."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    assert live_check.check_published(str(out))[0] == []
    current = json.loads((out / "all_result.v4.json").read_text())
    older = json.loads((out / "all_result.json").read_text())

    def problems_with(name, doc, change):
        broken = json.loads(json.dumps(doc))
        change(broken)
        (out / name).write_text(json.dumps(broken))
        try:
            return live_check.check_published(str(out))[0]
        finally:
            (out / name).write_text(json.dumps(doc))

    # the current file, as this version's reader sees it
    assert any("would not be served at the defaults: it is in the format" in p for p in problems_with(
        "all_result.v4.json", current, lambda d: d.update(format="grownet.all_result/v9")))
    assert any("would not be served at the defaults: it carries no time" in p for p in problems_with(
        "all_result.v4.json", current, lambda d: d["network"]["meta"].pop("derived_at")))
    assert any("would not be served at the defaults: it was derived by the integrated" in p for p in problems_with(
        "all_result.v4.json", current, lambda d: d["network"]["meta"]["settings"].update(derivation="integrated")))
    # the older file, as its readers see it
    assert ("all_result.json: its format is 'grownet.all_result/v9', and readers of "
            "grownet.interaction_network/v3 accept 'grownet.all_result/v1'") in problems_with(
        "all_result.json", older, lambda d: d.update(format="grownet.all_result/v9"))
    assert "all_result.json: its derived_at differs from the current file's" in problems_with(
        "all_result.json", older, lambda d: d["network"]["meta"].update(derived_at="2020-01-01T00:00:00+00:00"))
    # the derivation is judged against what its readers' defaults ask for, not against the current file,
    # which moves with this version's defaults (round 7)
    assert ("all_result.json: its derivation is 'integrated', and readers of grownet.interaction_network/v3 "
            "accept 'replicate'") in problems_with(
        "all_result.json", older, lambda d: d["network"]["meta"]["settings"].update(derivation="integrated"))
    # a file that records no derivation is served by them, so it is not a problem
    assert problems_with("all_result.json", older, lambda d: d["network"]["meta"]["settings"].pop("derivation")) == []


def test_an_older_file_judged_by_its_readers_after_a_move_of_the_current_format(tmp_path, monkeypatch):
    """Round 7 of the review: no test moved `published.FORMAT`, so comparing the older file's format with
    the current file's, not with what its readers read, survived; nor did any older file lack derived_at,
    which 0.4.0 refuses."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    import grownet.published as published
    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    clean = {name: (out / name).read_text() for name in ("all_result.v4.json", "all_result.json")}
    monkeypatch.setattr(published, "FORMAT", "grownet.all_result/v2")
    for name, text in clean.items():
        doc = json.loads(text)
        doc["format"] = "grownet.all_result/v2"
        (out / name).write_text(json.dumps(doc))
    problems = live_check.check_published(str(out))[0]
    assert any(p.startswith("all_result.json: its format is 'grownet.all_result/v2'") for p in problems), problems
    monkeypatch.undo()
    for name, text in clean.items():
        (out / name).write_text(text)
    doc = json.loads(clean["all_result.json"])
    doc["network"]["meta"].pop("derived_at")
    (out / "all_result.json").write_text(json.dumps(doc))
    assert "all_result.json: its derived_at differs from the current file's" in live_check.check_published(str(out))[0]


def test_after_a_move_of_the_default_derivation_the_older_file_is_judged_by_its_readers(tmp_path, monkeypatch):
    """Round 8 of the review: the round-7 test changed only the older file, so judging it by the current
    file's derivation again survived. Here the default moves to integrated and both files follow it: the
    current file is served by this version, and the /v3 file is refused by 0.4.0, which asks for replicate.
    Without a format a file is refused too."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet import gui
    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    clean = (out / "all_result.json").read_text()
    monkeypatch.setitem(gui.DEFAULTS, "derivation", "integrated")
    for name in ("all_result.v4.json", "all_result.json"):
        doc = json.loads((out / name).read_text())
        doc["network"]["meta"]["settings"]["derivation"] = "integrated"
        (out / name).write_text(json.dumps(doc))
    problems = live_check.check_published(str(out))[0]
    assert ("all_result.json: its derivation is 'integrated', and readers of grownet.interaction_network/v3 "
            "accept 'replicate'") in problems, problems
    assert not any(p.startswith("All:") for p in problems), problems
    monkeypatch.undo()
    for name in ("all_result.v4.json",):
        doc = json.loads((out / name).read_text())
        doc["network"]["meta"]["settings"]["derivation"] = "replicate"
        (out / name).write_text(json.dumps(doc))
    doc = json.loads(clean)
    doc.pop("format")
    (out / "all_result.json").write_text(json.dumps(doc))
    assert ("all_result.json: its format is None, and readers of grownet.interaction_network/v3 accept "
            "'grownet.all_result/v1'") in live_check.check_published(str(out))[0]


def test_a_correctly_rounded_ratio_is_never_flagged_and_a_loose_check_is_said_to_be():
    """Craig's agent on #281, correcting the first-order bound it had given: honest rounding reaches the
    corner (|s| + U) / (sd - U), which the old bound missed at every sd (by 2x at sd 1e-4). Every corner of
    every arc here passes the exact bound. Where the bound passes a tenth of the value the check is loose,
    and said to be, but still made: skipping it lost gross errors the bound catches (round 12 of the
    review: strength 0 written with a ratio of 5 passed)."""
    import live_check
    u = live_check.HALF_UNIT
    for sd in (0.02, 0.005, 0.001, 0.0005, 0.0002, 0.0001):
        for strength in (0.0, 0.0001, 0.05, 0.3, 1.0, 4.0):
            tolerance = live_check.ratio_tolerance(strength, sd)
            for true_s in (strength - u, strength, strength + u):
                for true_sd in (sd - u, sd, sd + u):
                    if true_sd <= 0 or true_s < 0:
                        continue
                    written = round(true_s / true_sd, 4)
                    assert abs(written - strength / sd) <= tolerance, (sd, strength, true_s, true_sd)
    # at the sd of the earlier test, strength 0.3: the honest corner deviates by 0.0401, which the old
    # first-order bound (0.04005) flagged as corrupt and the exact one allows
    corner = abs(round((0.3 + u) / (0.02 - u), 4) - 0.3 / 0.02)
    old = u / 0.02 + 0.3 * u / 0.02 ** 2 + u
    assert old < corner <= live_check.ratio_tolerance(0.3, 0.02), (old, corner)
    from grownet.mgrowthdb import records_to_network

    def arc(source, strength, sd, eos):
        return {"source": source, "target": "b", "effect": "facilitation" if strength >= 0 else "inhibition",
                "strength": strength, "sd": sd, "effect_over_sd": eos, "study_id": "S1"}
    net = records_to_network([arc("a", 1.0, 0.0001, 10000.0),     # loose: the bound is half the value
                              arc("c", 1.0, 0.2, 5.0),             # tight
                              arc("d", 0.5, 0.0, 10000.0)])        # no sd above the rounding: not checked
    assert live_check.ratio_coverage(net) == (1, 1)
    note = live_check.coverage_note(net, None)
    assert "checked only loosely on 1 arc(s)" in note and "not checked on 1 arc(s)" in note
    # a gross error where the check is loose is still caught: strength 0 written with a ratio of 5
    assert any("effect_over_sd" in p for p in network_problems(records_to_network([arc("a", 0.0, 0.3, 5.0)]), "x"))


def test_the_published_check_says_where_its_ratio_check_was_loose(tmp_path, monkeypatch):
    """Round 12 of the review: replacing the count in `check_published` by 0 left the suite green, so the
    summary's "checked only loosely" was untested where it is said."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    assert "loosely" not in live_check.check_published(str(out))[1]
    doc = json.loads((out / "all_result.v4.json").read_text())
    # the double's arc has no strength, so it is given one, with an sd at the smallest a file can carry;
    # other properties may break, and only the summary is read here
    edge = doc["network"]["edges"][0]
    edge.update(strength=1.0, weight=1.0, effect="facilitation", sd=0.0001, effect_over_sd=10000.0)
    (out / "all_result.v4.json").write_text(json.dumps(doc))
    assert "effect_over_sd checked only loosely on 1 arc(s)" in live_check.check_published(str(out))[1]
    # and the arcs below the threshold count too (round 13: the double has none, so leaving them out
    # of the note survived): one more loose arc there makes two
    doc["absent"] = {**doc["network"], "edges": [{**edge, "status": "absent"}]}
    (out / "all_result.v4.json").write_text(json.dumps(doc))
    assert "effect_over_sd checked only loosely on 2 arc(s)" in live_check.check_published(str(out))[1]
    # and an arc of the network that cannot be checked is counted beside the below-threshold part, as the
    # loose ones are (round 14: keeping only the last part's unchecked count survived)
    doc["network"]["edges"].append({**edge, "source": edge["target"], "target": edge["source"], "sd": 0.0})
    (out / "all_result.v4.json").write_text(json.dumps(doc))
    assert "effect_over_sd not checked on 1 arc(s)" in live_check.check_published(str(out))[1]


def test_the_arcs_below_the_threshold_are_checked_against_the_networks_k(tmp_path, monkeypatch):
    """Craig's agent on #281, 2026-10-13: the published part below the threshold carries `absence: null`,
    so its arcs, the ones the threshold defines, were never checked against it: one labeled absent whose
    |strength| 1.0 is above k * sd = 1 * 0.5 passed. It is checked against the network's k now."""
    import json

    import live_check
    import publish_all
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    doc = json.loads((out / "all_result.v4.json").read_text())
    edge = {**doc["network"]["edges"][0], "strength": 1.0, "weight": 1.0, "effect": "facilitation", "sd": 0.5,
            "effect_over_sd": 2.0, "status": "absent"}
    doc["absent"] = {**doc["network"], "edges": [edge], "meta": {**doc["network"]["meta"], "absence": None}}
    (out / "all_result.v4.json").write_text(json.dumps(doc))
    problems = live_check.check_published(str(out))[0]
    assert any(p.startswith("All, below the threshold:") and "status absent with |strength| 1.0" in p
               for p in problems), problems



def test_an_honest_corner_arc_passes_the_arc_check_itself_and_gl_v_mode_says_where_it_was_loose(monkeypatch):
    """Round 12 of the review: the corner test called `ratio_tolerance` only, so putting the first-order
    bound back inline in `arc_problems` survived; and the gLV-mode summary's coverage note was untested."""
    import live_check

    from grownet import gui
    from grownet.mgrowthdb import records_to_network
    honest = records_to_network([{"source": "a", "target": "b", "effect": "facilitation", "strength": 0.3,
                                  "sd": 0.02, "effect_over_sd": 15.0401, "study_id": "S1"}])
    assert not [p for p in network_problems(honest, "x") if "effect_over_sd" in p]
    loose = records_to_network([{"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0,
                                 "sd": 0.0001, "effect_over_sd": 10000.0, "study_id": "S1",
                                 "coefficient": 1e-9, "coefficient_unit": "1/(h x Cells/mL)"}])
    monkeypatch.setattr(gui, "run_query", lambda *a, **k: {"network": loose, "errors": []})
    _problems, what = live_check.check_glv_mode("S1")
    assert what.startswith("gLV mode, S1: 1 arcs") and "checked only loosely on 1 arc(s)" in what, what


def test_the_ratio_floor_and_the_smallest_sd():
    """Round 12 of the review: the floor's value was unpinned (0.5 passed), and no honest arc at the
    smallest sd a file carries went through the arc check: true 1.00004 / 6e-5, written 1.0, 0.0001 and
    16667.3333, must not be called corrupt."""
    import live_check

    from grownet.mgrowthdb import records_to_network
    honest = records_to_network([{"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0,
                                  "sd": 0.0001, "effect_over_sd": 16667.3333, "study_id": "S1"}])
    assert not [p for p in network_problems(honest, "x") if "effect_over_sd" in p]
    # the check is loose where the rounding bound reaches k, the absence threshold (Craig's agent on #281,
    # 2026-10-13: "tie it to `k` rather than to a tenth"). |s| 0.1: at sd 0.002 the bound is
    # 5e-5 * 0.102 / (0.002 * 0.00195) + 5e-5 = 1.308, past k = 1; at sd 0.003 it is 0.582, within it
    edge = {"source": "a", "target": "b", "effect": "facilitation", "strength": 0.1, "study_id": "S1"}
    past = records_to_network([{**edge, "sd": 0.002, "effect_over_sd": 50.0}])
    within = records_to_network([{**edge, "sd": 0.003, "effect_over_sd": 33.3333}])
    assert live_check.ratio_coverage(past) == (1, 0) and live_check.ratio_coverage(within) == (0, 0)
    # and it tightens with k: at k = 0.5 the 0.582 is past it
    assert live_check.ratio_coverage(within, 0.5) == (1, 0)
    assert live_check.ratio_tolerance(0.1, 0.002) == pytest.approx(1.308, abs=1e-3)


def test_make_r_check_fails_on_a_skipped_r_test(tmp_path):
    """Round 12 of the review: the guard test pinned text, so `exit 0` in place of `exit 1` kept it green.
    The Makefile's own guard line is run on a planted summary."""
    import re
    import subprocess

    import pytest
    makefile = ROOT / "Makefile"
    if not makefile.exists():
        pytest.skip("no Makefile in this tree (an unpacked sdist)")
    if sys.platform == "win32":
        # `make r-check` runs on Unix; the bash a Windows runner finds is not the shell make would use there
        pytest.skip("make r-check is a Unix recipe")
    line = next(x.strip() for x in makefile.read_text().splitlines() if "SKIP 0 |" in x and "grep" in x)
    rout = tmp_path / "grownet.Rcheck" / "tests"
    rout.mkdir(parents=True)
    planted = (("[ FAIL 0 | WARN 0 | SKIP 1 | PASS 119 ]", 1), ("[ FAIL 0 | WARN 0 | SKIP 0 | PASS 126 ]", 0))
    for summary, code in planted:
        (rout / "testthat.Rout").write_text(summary + "\n")
        done = subprocess.run(["bash", "-c", re.sub(r"^@", "", line)], cwd=tmp_path, capture_output=True)
        assert (done.returncode != 0) == bool(code), (summary, done.returncode)
    ci = (ROOT / ".github" / "workflows" / "ci.yml")
    if ci.exists():
        step = ci.read_text().split("- name: refuse a skipped R test", 1)[1].split("- name:", 1)[0]
        assert "continue-on-error" not in step
