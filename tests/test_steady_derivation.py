"""The steady-state derivation as a choice of the search (#310, task #313): chemostat runs in, arcs out.

Karoline, 2026-11-06: "can we have a third inference method just for gLV mode and chemostat, off by
default". The runs are the invented ones of tests/test_subcommunity_inputs.py: B = [[-1, -0.25],
[-0.1, -0.5]] per 1e8 Cells/mL, a alone at 1e8, b alone at 2e8, together at 0.526316e8 and 1.894737e8, and
each run with a stated 4 h batch period, so the row scales are 0.5 - 0.04 = 0.46 and 0.3 - 0.04 = 0.26.
"""
import math

import pytest
from test_steady_state import _chemostat
from test_subcommunity_inputs import PAIR_A, PAIR_B, RUN, UNIT, _runs, _startup

from grownet import gui
from grownet.mgrowthdb import records_to_network
from grownet.subcommunity import SteadyStateDeriver


def _derive(extra_runs=(), extra_curves=None):
    client, exps = _runs(extra_runs, extra_curves)
    return SteadyStateDeriver(client=client).derive({"id": "S1", "name": "an invented study"}, exps)


def _arc(records, source, target):
    return next(r for r in records if r["source_name"] == source and r["target_name"] == target)


def test_each_identified_coefficient_becomes_an_arc_with_its_strength_and_coefficient():
    records, _ = _derive()
    on_a = _arc(records, "b", "a")
    # strength log2(1 + B_ab x_b*), x_b* b's abundance in the largest community holding both:
    # 1 - 0.25 * 1.894737 = 0.526316, log2 = -0.92600
    # (strengths are rounded to 4 decimals, as every derivation's are)
    assert on_a["strength"] == pytest.approx(math.log2(1 - 0.25 * PAIR_B / UNIT), abs=5e-5)
    assert on_a["effect"] == "inhibition" and on_a["outcome"] == "quantified"
    # the coefficient in 1/(h x Cells/mL): the row scale 0.46 times B_ab = -0.25e-8
    assert on_a["coefficient"] == pytest.approx(0.46 * -0.25 / UNIT, rel=1e-6)
    assert on_a["coefficient_unit"] == "1/(h x Cells/mL)"
    assert on_a["fitted_rate"] == pytest.approx(0.46, abs=1e-6)          # r_a - D, the row's scale
    assert on_a["fitted_self"] == pytest.approx(0.46 * -1.0 / UNIT, rel=1e-6)
    on_b = _arc(records, "a", "b")
    assert on_b["strength"] == pytest.approx(math.log2(1 - 0.1 * PAIR_A / UNIT), abs=5e-5)
    assert on_b["coefficient"] == pytest.approx(0.26 * -0.1 / UNIT, rel=1e-6)
    # what the arc says about how it was made
    assert on_a["metric"] == "steady_state:subcommunities" and "chemostat" in on_a["condition"]
    assert on_a["cultivation_mode"] == "chemostat" and on_a["evidence"] == "biculture"
    assert any("batch period" in n for n in on_a["notes"])               # where its row scale came from


def test_the_arcs_carry_a_spread_from_the_vessels_and_make_a_valid_network():
    """Two vessels per run give each row a bootstrap spread, and the strength's sd follows from it
    (d strength / d B = x / ((1 + B x) ln 2)). Here the vessels are identical, so the spread is 0; what this
    pins is that a replicated row has one at all, which a single-vessel row does not (test_subcommunity)."""
    records, _ = _derive()
    for r in records:
        assert r["sd"] is not None and r["sd"] >= 0
    net = records_to_network(records)
    assert not net.validate()
    assert {e.metric for e in net.edges} == {"steady_state:subcommunities"}


def test_a_row_without_a_scale_stays_scaled_and_says_so():
    """b's monoculture says nothing about when the pump started, so b's row has no scale: its coefficient
    is B itself, in units of r_b - D, and it says so; a's row is unchanged."""
    import copy

    client, exps = _runs()
    exps = copy.deepcopy(exps)
    exps[1]["description"] = "No perturbations."                          # b alone: no batch period stated
    records, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    on_b = _arc(records, "a", "b")
    assert on_b["coefficient"] == pytest.approx(-0.1 / UNIT, rel=1e-6)
    assert on_b["coefficient_unit"] == "1/Cells/mL, in units of r_i - D"
    assert on_b["fitted_rate"] is None
    assert any("does not say when the dilution started" in n for n in on_b["notes"])


def test_what_the_design_does_not_determine_is_named_not_derived():
    """A third organism c alone, never with a or b: its coefficients with them are named in the skipped
    reasons, and no arc involves c."""
    alone = _chemostat("E8", "c alone", ["c"], [(11, "V1")], description=RUN)
    records, skipped = _derive([alone], {(11, "c"): _startup(0.4, 0.04, 4.0, 3.0 * UNIT)})
    assert not any("c" in (r["source_name"], r["target_name"]) for r in records)
    reasons = " ".join(why for _, why in skipped)
    assert "no community holds both" in reasons


def test_the_setting_offers_it_off_by_default():
    assert "steady" in gui.DERIVATIONS and gui.DEFAULTS["derivation"] == "replicate"
    assert isinstance(gui.chosen_deriver({"derivation": "steady"}), SteadyStateDeriver)
    page = gui.render_form("tok")
    assert '<option value="steady"' in page
    from grownet.__main__ import build_parser
    assert build_parser().parse_args(["derive", "--live", "--all", "--derivation", "steady"]).derivation == "steady"
    # it reads chemostats only, so the settings of the comparison are recorded as not read
    assert {"metric", "rate_method", "include_dropout", "include_non_batch"} <= set(SteadyStateDeriver.ignores)


def test_glv_mode_keeps_the_steady_state_derivation_and_counts_as_on_with_it():
    """It is "just for gLV mode and chemostat": pressing gLV mode with it chosen keeps it rather than
    switching to the integrated form, and the switch shows as on."""
    on = gui.glv_mode({**gui.DEFAULTS, "derivation": "steady"})
    assert on["derivation"] == "steady" and gui.glv_mode_on(on)
    assert gui.glv_mode(dict(gui.DEFAULTS))["derivation"] == "integrated"      # otherwise as before


def test_an_empty_result_says_what_this_derivation_needs():
    from grownet.gui import _empty_reason
    result = {"settings": {**gui.DEFAULTS, "derivation": "steady"}, "studies": ["S1"], "resolved": [("x", {})],
              "errors": [], "network": None, "hidden": {}, "skipped": [("b -> a [chemostat]", "no community "
                                                                        "holds both a and b at a steady state")]}
    reason = _empty_reason(result)
    assert "continuous cultures" in reason and "Derivation" in reason
