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


def _as_study(record, study):
    """A record as if fitted in study `study` alone: its study, its fit and the studies it rests on."""
    meta = {"id": study, "citation": study, "license": "", "url": ""}
    return {**record, "study_id": study, "fitted_group": f"{record.get('condition', '')} in {study}",
            "studies": [meta]}


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
    # its own evidence: the coefficient is fitted to every community holding the pair, so it is effective, and
    # "biculture" (a direct mono against bi-culture comparison) was false of it (found in review)
    assert on_a["cultivation_mode"] == "chemostat" and on_a["evidence"] == "steady_state"
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


def test_the_strength_sd_is_the_rows_bootstrap_spread_carried_through_the_strength():
    """Vessels that differ give each row a spread, and the arc's sd is that spread times
    |d strength / d B| = |x / ((1 + B x) ln 2)|, with x the partner's abundance on the arc and B its
    coefficient over the row scale. The vessels of the other test are identical, so an sd of 0, or one
    without the factor, passed it (found in review)."""
    from test_subcommunity_inputs import _runs

    from grownet.subcommunity import chemostat_groups, fit, pool
    client, exps = _runs(extra_curves={(2, "a"): _startup(0.5, 0.04, 4.0, 1.1 * UNIT),
                                       (4, "b"): _startup(0.3, 0.04, 4.0, 1.85 * UNIT),
                                       (6, "a"): _startup(0.5, 0.04, 4.0, 0.95 * PAIR_A),
                                       (6, "b"): _startup(0.3, 0.04, 4.0, 1.04 * PAIR_B)})
    records, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    (group,) = chemostat_groups(client, exps)
    rows = fit(pool(group["communities"]))["rows"]               # the deriver's own draws and seed
    for arc in records:
        i, j = arc["target_name"], arc["source_name"]
        b, x = arc["coefficient"] / arc["fitted_rate"], arc["partner_abundance"]
        expected = abs(x / ((1 + b * x) * math.log(2))) * rows[i]["sd"][j]
        assert expected > 0.01 and arc["sd"] == pytest.approx(expected, abs=1e-4)
        assert arc["coefficient_sd"] == pytest.approx(arc["fitted_rate"] * rows[i]["sd"][j], rel=1e-9)


def test_a_row_resting_on_a_single_vessel_has_no_spread_and_its_arcs_stay_undetermined():
    """One vessel per run: no bootstrap, so no sd, and presence is not decided (decision 5 of #310); an sd
    of 0 would have made every such arc present (found in review)."""
    from test_growth_rates import _client

    from grownet.derive import output_meta
    curves = {(1, "a"): _startup(0.5, 0.04, 4.0, 1.0 * UNIT), (3, "b"): _startup(0.3, 0.04, 4.0, 2.0 * UNIT),
              (5, "a"): _startup(0.5, 0.04, 4.0, PAIR_A), (5, "b"): _startup(0.3, 0.04, 4.0, PAIR_B)}
    exps = [_chemostat("E1", "a alone", ["a"], [(1, "V1")], description=RUN),
            _chemostat("E2", "b alone", ["b"], [(3, "V1")], description=RUN),
            _chemostat("E3", "a with b", ["a", "b"], [(5, "V1")], description=RUN)]
    records, _ = SteadyStateDeriver(client=_client(curves)).derive({"id": "S1", "name": "x"}, exps)
    assert records and all(r["sd"] is None and r["coefficient_sd"] is None for r in records)
    edges, _ = output_meta(records)
    assert edges and all(e["status"] is None for e in edges)


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
    # one line per organism, not per coefficient: a and b each never met c
    assert "no community holds it at a steady state with c" in reasons


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
    assert "continuous culture" in reason and "Derivation" in reason


# ---- the gLV package from it (#317) ------------------------------------------------------------------------

def _package(records):
    from grownet import integrated, matrix
    net = records_to_network(records, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}})
    rates = matrix.for_nodes(net, integrated.fitted_rates(records), {})
    return net, rates, matrix.glv_payload(net, rates), matrix.readme_from(matrix.coefficients(net, rates), net, rates)


def test_the_package_holds_the_generating_glv_with_the_dilution_folded_in():
    """The rates are the row scales r - D (0.46 and 0.26), the matrix is (r - D) B in 1/(h x Cells/mL), and so
    the package's equilibrium, the solution of A x = -r, is the pair the chemostat held: 0.526316e8 and
    1.894737e8 (a row's scale cancels at a steady state)."""
    records, _ = _derive()
    net, rates, payload, readme = _package(records)
    assert {rates[n]["name"]: round(rates[n]["rate"], 6) for n in rates} == {"a": 0.46, "b": 0.26}
    (block,) = payload["matrices"]
    order = block["organisms"]
    A = {(order[i], order[j]): block["interactions"][i][j] for i in range(2) for j in range(2)}
    assert A[("a", "a")] == pytest.approx(0.46 * -1.0 / UNIT, rel=1e-6)
    assert A[("a", "b")] == pytest.approx(0.46 * -0.25 / UNIT, rel=1e-6)
    assert A[("b", "a")] == pytest.approx(0.26 * -0.1 / UNIT, rel=1e-6)
    assert A[("b", "b")] == pytest.approx(0.26 * -0.5 / UNIT, rel=1e-6)
    equilibrium = dict(zip(order, block["equilibrium"], strict=True))
    assert equilibrium == pytest.approx({"a": PAIR_A, "b": PAIR_B}, rel=1e-6)
    # and the README says how its cells were made, in this derivation's own words
    assert payload["caveats"]["derivation"] == "steady"
    assert "1 + sum_j B[i][j] N_j = 0" in readme and "dilution" in readme.lower()


def test_a_row_without_a_scale_gives_no_cell_and_says_why():
    """Its coefficient is in units of r_b - D, which cannot sit in a matrix of 1/(h x Cells/mL): b has no rate
    and its row's cell is named rather than mixed in."""
    import copy

    client, exps = _runs()
    exps = copy.deepcopy(exps)
    exps[1]["description"] = "No perturbations."
    records, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    net, rates, payload, readme = _package(records)
    assert all(rates[n]["name"] != "b" or rates[n].get("rate") is None for n in rates)
    assert "in units of r_i - D" in readme


def test_the_steady_state_check_is_not_run_on_its_own_chemostats():
    from grownet.gui import STEADY_CHECK_CIRCULAR
    assert "fitted to these chemostat steady states" in STEADY_CHECK_CIRCULAR


def test_the_readme_states_the_assumptions_of_this_derivation_not_of_the_batch_ones():
    records, _ = _derive()
    readme = " ".join(_package(records)[3].split())
    assert "INTERACTIONS ARE EFFECTIVE AND ADD UP" in readme and "measured between two of them" not in readme


# ---- what a search is told when the design cannot determine a row (the state of mGrowthDB today) --------
#
# Karoline, 2026-11-06: "There will be cases when the available sub-communities are insufficient to make
# the derivation (the current state of mGrowthDB). Is the error message in this case informative?" It was
# not: one line per coefficient (30 for six organisms), a headline naming one organism's wash-out, and a
# closing sentence about the default derivation.

def _one_community():
    """Like SMGDB00000011 today: one unperturbed chemostat of three organisms, no monoculture, no pair."""
    three = _chemostat("E9", "No perturbations", ["a", "b", "c"], [(12, "V1")], description=RUN)
    from test_growth_rates import _client
    curves = {(12, "a"): _startup(0.5, 0.04, 4.0, 0.5 * UNIT), (12, "b"): _startup(0.3, 0.04, 4.0, 1.5 * UNIT),
              (12, "c"): _startup(0.4, 0.04, 4.0, 0.8 * UNIT)}
    return _client(curves), [three]


def test_an_insufficient_design_says_so_once_per_group_and_once_per_organism():
    client, exps = _one_community()
    records, skipped = SteadyStateDeriver(client=client).derive({"id": "S11", "name": "x"}, exps)
    assert records == []
    whats = [what for what, _ in skipped]
    assert not any(" -> " in w for w in whats), "no line per coefficient"
    group = next(why for what, why in skipped if what.startswith("chemostat group at D 0.04"))
    assert "1 community at an unperturbed steady state" in group and "no row is determined" in group
    assert "its monoculture and a pair with each partner" in group
    per_organism = [why for what, why in skipped if what.startswith(("a [", "b [", "c ["))]
    assert len(per_organism) == 3
    assert all("1 community holds it at a steady state, for 3 unknowns" in why for why in per_organism)


def test_the_page_leads_with_what_the_design_lacks():
    from grownet.gui import _empty_reason
    client, exps = _one_community()
    _, skipped = SteadyStateDeriver(client=client).derive({"id": "S11", "name": "x"}, exps)
    result = {"settings": {**gui.DEFAULTS, "derivation": "steady"}, "studies": ["S11"], "resolved": [("x", {})],
              "errors": [], "network": None, "hidden": {}, "skipped": skipped}
    reason = _empty_reason(result)
    assert reason.startswith("No chemostat design here determines a row.")
    assert "1 community at an unperturbed steady state" in reason
    assert "drop-out designs" not in reason and "pairwise (two-member) co-cultures" not in reason


def test_the_command_line_names_the_study_it_derived_not_the_last_reason_it_printed(monkeypatch, capsys,
                                                                                   tmp_path):
    """`_emit` printed the reasons in a loop whose variable shadowed its own `label`, so an empty network was
    announced as "NO interactions were derived for <the last reason's subject>"; on main too, for every
    derivation (found answering Karoline's question)."""
    from grownet.__main__ import main
    client, exps = _one_community()
    client.studies = {"S11": {"id": "S11", "name": "x", "experiments": [{"id": e["id"]} for e in exps]}}
    client.experiments = {e["id"]: e for e in exps}
    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", lambda **kw: client)
    monkeypatch.setattr("grownet.fetch.prefetch_studies", lambda *a, **k: None)
    main(["derive", "S11", "--live", "--derivation", "steady", "--out", str(tmp_path / "n.json")])
    err = capsys.readouterr().err
    headline = next(line for line in err.splitlines() if "NO interactions were derived" in line)
    assert "for S11" in headline
    assert "No chemostat design here determines a row." in err
    assert "drop-out designs" not in err
    assert "--derivation steady" in err and "Advanced settings" not in err     # its own control


def test_the_rates_say_they_are_r_less_d_from_a_chemostat_start_up_not_batch_rates():
    """The rates of this derivation are r_i - D, read from a chemostat's start-up: they were labelled the
    integrated form's, "batch experiments only", in the rates file, the report and the package (found in
    review)."""
    from grownet import integrated, matrix
    from grownet.subcommunity import METRIC
    records, _ = _derive()
    rates = integrated.fitted_rates(records, METRIC)
    assert {r["method"] for r in rates.values()} == {METRIC}
    rule = matrix.rate_rule(METRIC)
    assert "r_i - D" in rule and "start-up" in rule and "batch experiments only" not in rule


def _at_dilution(d: float, study: str, three_runs=False):
    """The invented two-species design run at dilution rate d (the same steady states; the start-ups differ, so
    the scales and the fitted values do), as
    study `study`; with `three_runs`, a second run of the pair too."""
    from test_growth_rates import _client
    # long enough to settle at D 0.2 too, where b rises at 0.1 per h: at 48 h it was still rising inside the
    # window its steady state is read in (found in a fourth review), which the derivation now refuses
    END = 150.0
    ids = {"a": (21, 22), "b": (23, 24), "ab": (25, 26)}
    curves = {**{(i, "a"): _startup(0.5, d, 4.0, UNIT, end=END) for i in ids["a"]},
              **{(i, "b"): _startup(0.3, d, 4.0, 2 * UNIT, end=END) for i in ids["b"]},
              **{(i, "a"): _startup(0.5, d, 4.0, PAIR_A, end=END) for i in ids["ab"]},
              **{(i, "b"): _startup(0.3, d, 4.0, PAIR_B, end=END) for i in ids["ab"]}}
    text = f"{d:.3f}"
    exps = [_chemostat("F1", "a alone", ["a"], [(ids["a"][0], "V1"), (ids["a"][1], "V2")], dilution=text,
                       description=RUN),
            _chemostat("F2", "b alone", ["b"], [(ids["b"][0], "V1"), (ids["b"][1], "V2")], dilution=text,
                       description=RUN),
            _chemostat("F3", "a with b", ["a", "b"], [(ids["ab"][0], "V1"), (ids["ab"][1], "V2")], dilution=text,
                       description=RUN)]
    records, _ = SteadyStateDeriver(client=_client(curves)).derive({"id": study, "name": study}, exps)
    return records


def test_rates_at_two_dilution_rates_are_not_merged_into_one():
    """r_i - D is a different number at each dilution rate: the median of 0.46 at D 0.04 and 0.30 at D 0.2 was
    0.38, r_i - D at neither, and keeping each organism's first D read mixed dilution rates across organisms
    and changed with the order of the records (found in review). One D for the package, the one most rows were
    fitted at, the lowest on a tie; the other is named, and its capacity is not taken either."""
    from grownet import integrated
    from grownet.subcommunity import METRIC
    slow, fast = _at_dilution(0.04, "S1"), _at_dilution(0.2, "S2")
    assert {r["fitted_rate_dilution"] for r in slow} == {0.04} and {r["fitted_rate_dilution"] for r in fast} == {0.2}
    for records in (slow + fast, fast + slow):                       # either order: the same package
        by_name = {r["name"]: r for r in integrated.fitted_rates(records, METRIC).values()}
        assert by_name["a"]["rate"] == pytest.approx(0.46, abs=1e-6)
        assert by_name["b"]["rate"] == pytest.approx(0.26, abs=1e-6)
        assert by_name["a"]["dilution"] == by_name["b"]["dilution"] == 0.04
        assert any("another dilution rate, 0.2 per h" in u for u in by_name["a"]["other_units"])
        # K = -1/B_ii at D 0.04, 1e8 and 2e8; the D 0.2 rows are not merged into them
        assert by_name["a"]["capacity"] == pytest.approx(1.0 * UNIT, rel=1e-6)
        assert by_name["b"]["capacity"] == pytest.approx(2.0 * UNIT, rel=1e-6)
    # more rows at D 0.2: that D is the package's, for every organism
    more = fast + [_as_study(r, "S3") for r in fast]
    by_name = {r["name"]: r for r in integrated.fitted_rates(slow + more, METRIC).values()}
    assert by_name["a"]["rate"] == pytest.approx(0.30, abs=1e-6) and by_name["b"]["dilution"] == 0.2


def test_with_no_row_scaled_the_command_line_reads_no_batch_rate_in_its_place(monkeypatch, capsys):
    """The help says the scale is never a batch growth rate; with no row scaled, the command line read the
    batch monocultures instead (found in review)."""
    import types

    from grownet import __main__ as cli
    from grownet.model import InteractionNetwork

    def refuse(*_args, **_kwargs):
        raise AssertionError("batch growth rates read under the steady-state derivation")
    monkeypatch.setattr("grownet.derive.growth_rates", refuse)
    a = types.SimpleNamespace(derivation="steady", rate_method="easylinear", rate_window=5, spike_factor=None,
                              capacity_max_fall=None)
    net = InteractionNetwork()
    found, _ = cli._rates_of(a, None, ["S1"], net, [], records=[])
    assert found == {} and "No batch growth rate is read" in capsys.readouterr().err


def test_the_second_box_selects_the_chemostat_runs_it_names():
    """Naming one community in the second box keeps it and the monocultures under its conditions, and drops
    a run at another dilution rate, as the other derivations read the box."""
    faster = _chemostat("E7", "a alone, faster", ["a"], [(10, "V1"), (11, "V2")], dilution="0.1",
                        description=RUN)
    client, exps = _runs([faster], {(10, "a"): _startup(0.5, 0.1, 4.0, 0.8 * UNIT),
                                    (11, "a"): _startup(0.5, 0.1, 4.0, 0.8 * UNIT)})
    every, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    named, skipped = SteadyStateDeriver(client=client, selection={"experiments": ["E3"]}).derive(
        {"id": "S1", "name": "x"}, exps)
    assert named and {r["condition"] for r in named} == {r["condition"] for r in every if "0.04" in r["condition"]}
    assert not any("E7" in r["experiments"] for r in named)
    assert any(what == "monocultures kept alongside the experiments named" for what, _ in skipped)


def test_the_page_and_the_command_line_describe_the_steady_state_derivation_when_it_is_chosen(capsys):
    """The Derivation hint names all three; pressing gLV mode with steady chosen says steady was kept, not
    "the derivation on the integrated form"; the command line names its own switch in an empty result and
    does not announce a growth property it does not read (found in review)."""
    from grownet import __main__ as cli
    assert "Or steady" in gui.render_form("tok")
    assert "steady-state derivation kept" in gui.GLV_MODE_STEADY_MESSAGE
    result = {"settings": {**gui.DEFAULTS, "derivation": "steady"}, "studies": ["S1"], "resolved": [("x", {})],
              "errors": [], "network": None, "hidden": {}, "skipped": []}
    assert "--derivation steady" in gui._empty_reason(result, command_line=True)
    assert "Advanced settings" in gui._empty_reason(result)
    a = cli.build_parser().parse_args(["derive", "--live", "--all", "--glv-mode", "--derivation", "steady"])
    capsys.readouterr()
    cli._resolve(a)
    err = capsys.readouterr().err
    assert "steady derivation" in err and "the comparison on the growth rate" not in err


def test_a_fitted_row_without_a_scale_is_left_out_of_the_package_for_that_reason():
    """b's row was fitted, in units of its r_b - D, which no start-up gave: the package said "no growth rate
    ... nothing on it can be fitted", against its own line naming b's row's unit (found in review)."""
    import copy

    from grownet import matrix
    client, exps = _runs()
    exps = copy.deepcopy(exps)
    exps[1]["description"] = "No perturbations."                          # b alone: no batch period stated
    records, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    net, rates, _payload, _readme = _package(records)
    got = matrix.coefficients(net, rates)
    left = dict(got["left_out"])
    assert "fitted in units of its own r_i - D" in left["b"] and "nothing on it" not in left["b"]
    # and nothing else in the package says b could not be fitted (found in a second review)
    readme = matrix.readme_from(got, net, rates)
    assert "could not be fitted" not in readme and "cannot be fitted" not in readme.replace(
        "has no term in this model and cannot be fitted", "")
    assert not any("could not be fitted" in why for _, _, why in got["across_units"])
    # nor that every arc compares two organisms directly
    assert "compares two organisms directly" not in readme and "evidence steady_state" in readme


def test_the_command_line_report_carries_the_notes_it_points_to():
    """With no row scaled, the command line said the report says why each organism has no rate, and the
    report did not; nor did it carry the steady-state check's refusal, which the page's report does (found in
    a second review). The report prints every note it is given."""
    from grownet import __main__ as cli
    from grownet.report import report_text
    a = cli.build_parser().parse_args(["derive", "S1", "--live", "--derivation", "steady", "--report-rates",
                                       "--steady-check"])
    notes = cli._report_notes(a, {})
    assert notes == [gui.STEADY_NO_RATE, gui.STEADY_CHECK_CIRCULAR]
    assert cli._report_notes(a, {"a": {"rate": 0.46}}) == [gui.STEADY_CHECK_CIRCULAR]
    records, _ = _derive()
    result = {"study": "S1", "entries": [], "resolved": [], "unresolved": [], "studies": ["S1"], "rates": {},
              "skipped": [], "errors": [], "network": records_to_network(records), "notes": notes}
    text = report_text(result)
    assert "No batch growth rate is read" in text and "no steady-state check" in text


def test_an_empty_result_after_a_filter_does_not_say_the_study_holds_no_chemostat():
    """The second box or Technique removed the study's chemostat run: "these studies hold no continuous
    culture" was false, and "the reasons say" pointed at no reasons (found in a second review)."""
    from grownet.subcommunity import empty_reason
    boxed = empty_reason([("study S1", "no experiment of this study matches the media, experiments or studies "
                                        "entered")], command_line=True)
    assert "hold no" not in boxed and "after the second box left some out" in boxed
    assert "The reasons say" not in boxed            # every reason is the box's, none says what a study held
    bare = empty_reason([], command_line=True)
    assert "hold no" not in bare and "Technique" in bare and "The reasons say" not in bare


def test_two_runs_of_the_pair_are_one_community_on_the_arcs():
    """A second run of a with b (E4) is pooled with the first: the arcs list both experiments, and with the
    pair being the only community holding both, the leave-one-out note says it cannot be predicted without
    it, rather than predicting it exactly from its own twin."""
    twin = _chemostat("E4", "a with b again", ["a", "b"], [(7, "V1"), (8, "V2")], description=RUN)
    curves = {(i, "a"): _startup(0.5, 0.04, 4.0, PAIR_A) for i in (7, 8)}
    curves.update({(i, "b"): _startup(0.3, 0.04, 4.0, PAIR_B) for i in (7, 8)})
    records, _ = _derive([twin], curves)
    on_a = _arc(records, "b", "a")
    assert {"E3", "E4"} <= set(on_a["experiments"])
    assert any("(2 runs) not predicted" in n for n in on_a["notes"])


def test_a_community_is_the_mean_over_its_vessels():
    """Three vessels at 0.9, 1.0 and 1.4 (x 1e8) of a alone: the community's abundance is their mean, 1.1e8,
    the statistic the bootstrap draws; the median, 1.0e8, or the check's own value, would not be."""
    from test_growth_rates import _client

    from grownet.subcommunity import chemostat_groups
    curves = {(i, "a"): _startup(0.5, 0.04, 4.0, k * UNIT) for i, k in ((1, 0.9), (2, 1.0), (3, 1.4))}
    exps = [_chemostat("E1", "a alone", ["a"], [(1, "V1"), (2, "V2"), (3, "V3")], description=RUN)]
    (group,) = chemostat_groups(_client(curves), exps)
    assert group["communities"][0]["abundance"]["a"] == pytest.approx(1.1 * UNIT, rel=1e-9)


def test_the_command_line_names_the_rates_as_this_derivation_s():
    """Where the rates are used, not only where they are made: the network's growth-rate rule names r_i - D
    from a chemostat start-up (found in a second review: the label was tested in the function only)."""
    import types

    from grownet import __main__ as cli
    records, _ = _derive()
    net = records_to_network(records)
    a = types.SimpleNamespace(derivation="steady", rate_method="easylinear", rate_window=5, spike_factor=None,
                              capacity_max_fall=None)
    found, _ = cli._rates_of(a, None, ["S1"], net, [], records=records)
    rule = net.meta["growth_rates"]["rule"]
    assert found and rule.startswith("steady_state:subcommunities") and "batch experiments only" not in rule
    assert "at the dilution rate 0.04 per h" in rule


def _renamed(records, names):
    """The records with organisms renamed, as another study's organisms."""
    out = []
    for r in records:
        r = dict(r)
        for side in ("source", "target"):
            new = names[r[f"{side}_name"]]
            r[f"{side}_name"], r[side] = new, f"name:{new}"
        out.append(r)
    return out


def test_an_organism_fitted_only_at_another_dilution_rate_is_named_with_that_reason():
    """c and d were fitted only at D 0.2, and the package is at D 0.04 (a and b, two rows each... a tie broken
    to the lowest): they are not in it, and the README said they had "no growth rate ... nothing on it can be
    fitted" (found in a third review). It names the dilution rate instead."""
    from grownet import integrated, matrix
    from grownet.subcommunity import METRIC
    records = _at_dilution(0.04, "S1") + _renamed(_at_dilution(0.2, "S2"), {"a": "c", "b": "d"})
    net = records_to_network(records, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}})
    rates = matrix.for_nodes(net, integrated.fitted_rates(records, METRIC), {})
    left = dict(matrix.coefficients(net, rates)["left_out"])
    assert "fitted at the dilution rate 0.2 per h" in left["c"] and "0.04 per h" in left["c"]
    assert "nothing on it" not in left["c"]


def test_the_package_dilution_rate_counts_rows_not_arcs():
    """One organism with three partners at D 0.1 is one row; two organisms with one partner each at D 0.05 are
    two rows: D 0.05 is the package's (it counted arcs and chose 0.1, found in a third review)."""
    from grownet import integrated
    from grownet.subcommunity import METRIC

    def row(target, partner, d):
        return {"target": target, "target_name": target, "source": partner, "fitted_rate": 0.4,
                "fitted_rate_unit": "1/h", "fitted_rate_dilution": d, "fitted_self": -0.4e-8, "study_id": "S"}
    records = [row("a", p, 0.1) for p in ("x", "y", "z")] + [row("x", "a", 0.05), row("y", "a", 0.05)]
    rates = integrated.fitted_rates(records, METRIC)
    assert rates["x"]["dilution"] == 0.05 and "a" not in rates
    assert "0.1 per h" in rates.no_rate["a"][1]


def test_a_run_s_wash_out_is_reported_by_the_derivation():
    """a with b, and a with b and c where c washed out: the two end with the same members and are pooled, and
    c's wash-out is still reported, under its own run (pooled before the fit, it was lost: found in a third
    review)."""
    lost = _chemostat("E4", "a with b, c lost", ["a", "b", "c"], [(7, "V1"), (8, "V2")], description=RUN)
    curves = {(i, "a"): _startup(0.5, 0.04, 4.0, PAIR_A) for i in (7, 8)}
    curves.update({(i, "b"): _startup(0.3, 0.04, 4.0, PAIR_B) for i in (7, 8)})
    curves.update({(i, "c"): _startup(0.3, 0.04, 4.0, 0.001 * UNIT) for i in (7, 8)})
    records, skipped = _derive([lost], curves)
    assert any(what.startswith("c in a with b, c lost") and "washed out" in why for what, why in skipped)
    # and the arcs' community is the members present: c is in none
    assert records and all(len(r["community"]) == 2 for r in records)


def test_the_package_is_at_one_dilution_rate_in_its_cells_too():
    """a and b fitted at D 0.04 (S1) and D 0.2 (S2): the package is at 0.04, and its cells hold the D 0.04
    coefficients alone, the D 0.2 arcs named as left out; a cell was the median of both while the README
    said one dilution rate (found in a third review). Here the D 0.2 coefficients are 0.3 B and 0.1 B, unlike
    the D 0.04 ones, 0.46 B and 0.26 B."""
    from grownet import integrated, matrix
    from grownet.subcommunity import METRIC
    records = _at_dilution(0.04, "S1") + _at_dilution(0.2, "S2")
    net = records_to_network(records, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}})
    rates = matrix.for_nodes(net, integrated.fitted_rates(records, METRIC), {})
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    order = block["organisms"]
    A = {(order[i], order[j]): block["matrix"][i][j] for i in range(2) for j in range(2)}
    assert A[("a", "b")] == pytest.approx(0.46 * -0.25 / UNIT, rel=1e-6)
    assert A[("b", "a")] == pytest.approx(0.26 * -0.1 / UNIT, rel=1e-6)
    named = " ".join(why for _, _, why in got["arcs_left_out"])
    assert "fitted at the dilution rate 0.2 per h" in named


def test_a_steady_arc_carries_its_weight():
    records, _ = _derive()
    assert all(r["weight"] == round(abs(r["strength"]), 4) for r in records if r["strength"] is not None)


def test_a_dilution_rate_of_many_digits_still_fills_the_cells():
    """D = 1/24 per h: the condition writes it as 0.0416667, and read back it never equalled the package's
    0.041666..., so every cell was left out with a reason naming the same D twice (found in a fourth review)."""
    from grownet import integrated, matrix
    from grownet.subcommunity import METRIC
    records = _at_dilution(1 / 24, "S1")
    net = records_to_network(records, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}})
    rates = matrix.for_nodes(net, integrated.fitted_rates(records, METRIC), {})
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    assert all(v != 0 for row in block["matrix"] for v in row) and not got["pairs_left_out"]


def test_a_genus_keeps_the_package_dilution_rate():
    """Merged to genus, a node's rate entry is the median of its strains', and it lost the package's dilution
    rate, so a genus's cells took arcs at every dilution rate (found in a fourth review). Two Bacteroides
    strains with Prevotella at D 0.04, one also at D 0.2, other organisms at 0.04 so the package is there."""
    from grownet import integrated, matrix
    from grownet.derive import output_meta
    from grownet.subcommunity import METRIC
    raw = (_renamed(_at_dilution(0.04, "S1"), {"a": "Bacteroides alpha", "b": "Prevotella copri"})
           + _renamed(_at_dilution(0.04, "S2"), {"a": "Bacteroides beta", "b": "Prevotella copri"})
           + _renamed(_at_dilution(0.2, "S3"), {"a": "Bacteroides alpha", "b": "Prevotella copri"})
           + _renamed(_at_dilution(0.04, "F1"), {"a": "Clostridium c", "b": "Dorea d"}))
    edges, meta = output_meta([dict(r) for r in raw], merge_genera=True)
    net = records_to_network(edges, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}, **meta})
    rates = matrix.for_nodes(net, integrated.fitted_rates(raw, METRIC), {})
    bacteroides = next(r for r in rates.values() if r["name"] == "Bacteroides")
    assert bacteroides["dilution"] == 0.04
    got = matrix.coefficients(net, rates)
    named = " ".join(w for *_, w in got["pairs_left_out"] + got["arcs_left_out"])
    assert "0.2" in named and "Merge to genus" in named


def test_the_rate_comes_from_the_medium_the_capacity_comes_from():
    """a fitted in Wilkins-Chalgren (r - D 0.46, two studies) and in Gifu (0.86, 0.90 and 0.94, three
    studies): the capacity is Gifu's, where more rows were fitted, and so is the rate, 0.90; over every row it
    would be 0.86 (the median of five). The median over both media beside Gifu's capacity gave a diagonal that
    belonged to no fit (found in a fourth review; the first test of it could not tell the two apart, found in
    a fifth)."""
    from grownet import integrated
    from grownet.subcommunity import METRIC
    wc, _ = _derive()
    wc2 = [_as_study(r, "S5") for r in wc]
    gifu = [{**_as_study(r, study), "medium": "Gifu Anaerobic Medium",
             "fitted_rate": r["fitted_rate"] + up,
             "fitted_self": r["fitted_self"] / r["fitted_rate"] * (r["fitted_rate"] + up)}
            for study, up in (("S2", 0.40), ("S3", 0.44), ("S4", 0.48)) for r in wc]
    by_name = {r["name"]: r for r in integrated.fitted_rates(wc + wc2 + gifu, METRIC).values()}
    assert by_name["a"]["capacity_medium"] == "Gifu Anaerobic Medium"
    assert by_name["a"]["rate"] == pytest.approx(0.90, abs=1e-6)


def test_a_row_scale_is_the_median_over_every_monoculture_run():
    """Two monoculture runs of a at one dilution rate, rising at 0.5 and at 0.7 per h: the scale is the median
    over their vessels, 0.56 whichever run is read first. It was the last run's (found in a fifth review)."""
    from test_growth_rates import _client

    from grownet.subcommunity import chemostat_groups
    curves = {(1, "a"): _startup(0.5, 0.04, 4.0, UNIT), (2, "a"): _startup(0.7, 0.04, 4.0, UNIT)}
    for order in ((1, 2), (2, 1)):
        exps = [_chemostat(f"E{i}", f"a alone {i}", ["a"], [(i, "V1")], description=RUN) for i in order]
        (group,) = chemostat_groups(_client(curves), exps)
        assert group["scales"]["a"]["scale"] == pytest.approx(0.56, abs=2e-3)

def test_a_row_counts_once_in_the_rate_however_many_partners_it_has():
    """The steady-state derivation writes a row's scale on every arc of the row: a row with three partners
    at 0.46 and two rows at 0.32 and 0.30 gave 0.46 (or 0.39 with two partners), where the three rows' median
    is 0.32 (found in a fourth review)."""
    from grownet import integrated
    from grownet.subcommunity import METRIC

    def arc(partner, study, scale):
        return {"target": "a", "target_name": "a", "source": partner, "fitted_rate": scale,
                "fitted_rate_unit": "1/h", "fitted_rate_dilution": 0.04, "fitted_self": -scale * 1e-8,
                "study_id": study, "condition": "chemostat, D 0.04 per h, M, Cells/mL", "medium": "M"}
    records = [arc(p, "S1", 0.46) for p in ("x", "y", "z")] + [arc("x", "S2", 0.32), arc("x", "S3", 0.30)]
    got = integrated.fitted_rates(records, METRIC)["a"]
    assert got["rate"] == pytest.approx(0.32) and got["n"] == 3


def test_an_empty_result_after_a_filter_keeps_the_filter_s_reason():
    """Rows were determined and arcs derived, then a filter removed them: the steady lead said no chemostat
    design determines a row beside "2 of 2 rows determined" and sent the user to batch cultures (found in a
    fourth review). The general reasons speak then."""
    from grownet.gui import _empty_reason
    from grownet.subcommunity import determined_any
    skipped = [("chemostat group at D 0.04 per h, M, Cells/mL", "3 communities at an unperturbed steady state "
                "(a alone, b alone, a with b), 2 organism(s) present; 2 of 2 rows determined.")]
    assert determined_any(skipped)
    result = {"settings": {**gui.DEFAULTS, "derivation": "steady", "absence_threshold": 100.0},
              "studies": ["S1"], "resolved": [("x", {})], "errors": [], "network": None, "hidden": {},
              "skipped": skipped}
    assert "No chemostat design here determines a row" not in _empty_reason(result)


def test_a_row_without_a_scale_at_the_package_rate_keeps_its_own_reason():
    """b's row at D 0.04 has no scale, and b also has a scaled row at D 0.2: the package is at 0.04 (a, c and
    d have rows there), and b's reason is that its row there is in units of r_b - D, not that its rows were
    fitted at 0.2, which hid the row at the package's rate (found in a fourth review)."""
    import copy

    from grownet import integrated, matrix
    from grownet.subcommunity import METRIC
    client, exps = _runs()
    exps = copy.deepcopy(exps)
    exps[1]["description"] = "No perturbations."                          # b alone: no batch period stated
    unscaled, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    records = (unscaled + _at_dilution(0.2, "S2")
               + _renamed(_at_dilution(0.04, "S3"), {"a": "c", "b": "d"}))
    net = records_to_network(records, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}})
    rates = matrix.for_nodes(net, integrated.fitted_rates(records, METRIC), {})
    left = dict(matrix.coefficients(net, rates)["left_out"])
    assert "fitted in units of its own r_i - D" in left["b"], left["b"]


def test_report_notes_are_only_the_steady_derivation_s():
    from grownet import __main__ as cli
    plain = cli.build_parser().parse_args(["derive", "S1", "--live", "--report-rates", "--steady-check"])
    assert cli._report_notes(plain, {}) == []
    bare = cli.build_parser().parse_args(["derive", "S1", "--live", "--derivation", "steady"])
    assert cli._report_notes(bare, {}) == []


def test_a_run_still_changing_in_its_window_is_not_a_steady_state():
    """b rises at r - D = 0.1 per h at D 0.2: by 48 h it is still rising inside the last quarter of the run,
    which was averaged as its steady state and fitted, giving B_bb -0.67 where it is -0.5, with nothing
    flagged (found in a fourth review). Such a run is left out and named."""
    from test_growth_rates import _client
    curves = {(1, "a"): _startup(0.5, 0.2, 4.0, UNIT), (3, "b"): _startup(0.3, 0.2, 4.0, 2 * UNIT)}
    exps = [_chemostat("E1", "a alone", ["a"], [(1, "V1")], dilution="0.2", description=RUN),
            _chemostat("E2", "b alone", ["b"], [(3, "V1")], dilution="0.2", description=RUN)]
    from grownet.subcommunity import chemostat_groups
    groups = chemostat_groups(_client(curves), exps)
    names = [c["name"] for g in groups for c in g["communities"]]
    assert names == ["a alone"]
    said = " ".join(why for g in groups for _, why in g["left_out"])
    assert "not at a steady state: b changes by" in said


def test_a_split_by_technique_gives_an_arc_between_organisms_read_one_way_once():
    """b is read by fc in a second pair run, so the runs are split by how b is read; a and c are read one way
    throughout, and c's effect on a is the same measurement in both parts. Given once per part, it counted
    twice in the cells, the rates and the capacities (found in a fifth review)."""
    from test_growth_rates import _client
    from test_subcommunity_inputs import _retag
    curves = {(1, "a"): _startup(0.5, 0.04, 4.0, UNIT), (2, "a"): _startup(0.5, 0.04, 4.0, UNIT),
              (3, "b"): _startup(0.3, 0.04, 4.0, 2 * UNIT), (4, "b"): _startup(0.3, 0.04, 4.0, 2 * UNIT),
              (9, "c"): _startup(0.4, 0.04, 4.0, 1.5 * UNIT), (10, "c"): _startup(0.4, 0.04, 4.0, 1.5 * UNIT)}
    for i in (5, 6, 7, 8):
        curves[(i, "a")] = _startup(0.5, 0.04, 4.0, PAIR_A)
        curves[(i, "b")] = _startup(0.3, 0.04, 4.0, PAIR_B if i < 7 else 2 * PAIR_B)
    for i in (11, 12):
        curves[(i, "a")] = _startup(0.5, 0.04, 4.0, 0.7 * UNIT)
        curves[(i, "c")] = _startup(0.4, 0.04, 4.0, 1.0 * UNIT)
    exps = [_chemostat("E1", "a alone", ["a"], [(1, "V1"), (2, "V2")], description=RUN),
            _chemostat("E2", "b alone", ["b"], [(3, "V1"), (4, "V2")], description=RUN),
            _chemostat("E3", "a with b", ["a", "b"], [(5, "V1"), (6, "V2")], description=RUN),
            _chemostat("E4", "a with b again", ["a", "b"], [(7, "V1"), (8, "V2")], description=RUN),
            _chemostat("E5", "c alone", ["c"], [(9, "V1"), (10, "V2")], description=RUN),
            _chemostat("E6", "a with c", ["a", "c"], [(11, "V1"), (12, "V2")], description=RUN)]
    client = _client(curves)
    _retag(client, "b", "fc", bioreplicates={7, 8})
    records, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    assert len([r for r in records if (r["source_name"], r["target_name"]) == ("c", "a")]) == 1
    from grownet import integrated
    from grownet.subcommunity import METRIC
    assert integrated.fitted_rates(records, METRIC)
    a_rows = {(r["study_id"], r["fitted_rate_dilution"], r["medium"]) for r in records if r["target_name"] == "a"}
    assert len(a_rows) == 1                                     # one row of a, however many parts


def test_an_arc_merged_across_dilution_rates_still_counts_in_the_pair_s_sign():
    """Merged to genus: Prevotella helps Bacteroides alpha at D 0.04 and at D 0.2, and inhibits Bacteroides
    beta at 0.04. The facilitation arc of the genus spans both rates and stays out of the cell; its direction
    still counts, so the pair's arcs disagree and the cell is 0, named. Left out of the sign check, beta's
    inhibition alone filled the cell, and a study at another rate decided its sign by leaving (found in a
    fifth review)."""
    from grownet import integrated, matrix
    from grownet.derive import output_meta
    from grownet.subcommunity import METRIC

    def helped(records):
        return [{**r, "coefficient": -r["coefficient"], "strength": -r["strength"], "effect": "facilitation",
                 "metric_with": 2 * r["metric_without"] - r["metric_with"]}
                if (r["source_name"], r["target_name"]) == ("Prevotella copri", "Bacteroides alpha") else r
                for r in records]
    alpha = {"a": "Bacteroides alpha", "b": "Prevotella copri"}
    beta = {"a": "Bacteroides beta", "b": "Prevotella copri"}
    raw = (helped(_renamed(_at_dilution(0.04, "S1"), alpha)) + helped(_renamed(_at_dilution(0.2, "S3"), alpha))
           + _renamed(_at_dilution(0.04, "S2"), beta) + _renamed(_at_dilution(0.04, "F1"), {"a": "Clostridium c",
                                                                                              "b": "Dorea d"}))
    edges, meta = output_meta([dict(r) for r in raw], merge_genera=True)
    net = records_to_network(edges, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}, **meta})
    rates = matrix.for_nodes(net, integrated.fitted_rates(raw, METRIC), {})
    got = matrix.coefficients(net, rates)
    block = next(b for b in got["matrices"] if "Bacteroides" in b["organisms"])
    order = block["organisms"]
    assert block["matrix"][order.index("Bacteroides")][order.index("Prevotella")] == 0
    assert ("Bacteroides", "Prevotella") in [tuple(p) for p in block["conflicts"]]


def test_rows_record_their_own_technique_and_two_units_are_two_rows():
    """The capacity rule keys on the technique and unit of an organism's own term: steady rows never set the
    technique, so plateaus by two techniques were pooled, and the row key dropped the unit, so of two fits in
    two units the first read was kept and nothing named (found in a sixth review)."""
    from grownet import integrated
    from grownet.subcommunity import METRIC
    records, _ = _derive()
    assert {r["fitted_self_technique"] for r in records} == {"qpcr"}
    od = [{**r, "fitted_self_unit": "OD", "partner_abundance_unit": "OD", "condition": r["condition"] + " (OD)"}
          for r in records]
    a = next(r for r in integrated.fitted_rates(records + od, METRIC).values() if r["name"] == "a")
    assert a["n"] == 2


def test_a_row_without_a_scale_does_not_borrow_another_study_s():
    """b's row in S1 has no scale; S2 (same medium and dilution rate) gives b one. S1's arc on b is in units
    of r_b - D and stays out of the cell, named; it entered it through the log2 fallback multiplied by S2's
    rate, filed as a network saved before rates were recorded (found in a sixth review)."""
    import copy

    from grownet import integrated, matrix
    from grownet.subcommunity import METRIC
    client, exps = _runs()
    exps = copy.deepcopy(exps)
    exps[1]["description"] = "No perturbations."
    unscaled, _ = SteadyStateDeriver(client=client).derive({"id": "S1", "name": "x"}, exps)
    records = unscaled + _at_dilution(0.04, "S2")
    net = records_to_network(records, meta={"settings": {**gui.DEFAULTS, "derivation": "steady"}})
    rates = matrix.for_nodes(net, integrated.fitted_rates(records, METRIC), {})
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    order = block["organisms"]
    assert block["matrix"][order.index("b")][order.index("a")] == pytest.approx(0.26 * -0.1 / UNIT, rel=1e-6)
    named = " ".join(why for *_, why in got["arcs_left_out"])
    assert "in units of b's r_i - D" in named or "units of r_i - D" in named
    readme = matrix.readme_from(got, net, rates)
    assert "network derived before the two absolute rates" not in readme


def test_runs_of_two_studies_in_one_medium_are_fitted_together():
    """The pair a with b in study S1 and the monocultures in study S2, one medium composition and dilution
    rate: neither study alone determines a row, together they do (Karoline, 2026-11-06: "for the new chemostat
    inference mode, the medium composition has to match but other than that, I don't see why not"). Each arc
    names both studies, and the row counts once in the rates."""
    from test_subcommunity_inputs import _runs

    from grownet import integrated
    from grownet.subcommunity import METRIC
    client, exps = _runs()
    s1 = {"id": "S1", "name": "the pair"}, [exps[2]]
    s2 = {"id": "S2", "name": "the monocultures"}, [exps[0], exps[1]]
    alone = [SteadyStateDeriver(client=client).derive(*s) for s in (s1, s2)]
    assert not any(records for records, _ in alone)
    records, skipped = SteadyStateDeriver(client=client).derive_many([s1, s2])
    on_a = _arc(records, "b", "a")
    assert on_a["coefficient"] == pytest.approx(0.46 * -0.25 / UNIT, rel=1e-6)
    assert [s["id"] for s in on_a["studies"]] == ["S1", "S2"]
    assert any(what.endswith(" in S1, S2") for what, _ in skipped if what.startswith("chemostat group at"))
    a = next(r for r in integrated.fitted_rates(records, METRIC).values() if r["name"] == "a")
    assert a["n"] == 1


def test_runs_of_two_studies_in_different_media_are_not_fitted_together():
    """The same split, with the monocultures in another medium: the composition differs, so the runs are two
    fits and neither determines a row."""
    import copy

    from test_subcommunity_inputs import _runs
    client, exps = _runs()
    monos = copy.deepcopy([exps[0], exps[1]])
    for exp in monos:
        exp["compartments"][0]["mediumName"] = "Gifu Anaerobic Medium"
    records, _ = SteadyStateDeriver(client=client).derive_many([({"id": "S1", "name": "x"}, [exps[2]]),
                                                                ({"id": "S2", "name": "y"}, monos)])
    assert records == []


def test_the_page_hands_every_study_of_a_search_to_the_steady_derivation_at_once(monkeypatch):
    """A search reads its studies one by one; under the steady-state derivation it gives them all to one
    `derive_many`, so runs of several studies can be fitted together."""
    from test_gui import FakeClient

    calls = []

    class Recording(SteadyStateDeriver):
        def derive_many(self, studies):
            calls.append([study["id"] for study, _ in studies])
            return [], []
    class TwoStudies(FakeClient):
        """The fake study served under two ids, so a search finds two studies."""
        ids = ("SMGDB00000001", "SMGDB00000002")

        def study_experiments(self, study_id):
            return super().study_experiments(self.study_id)

        def get_study(self, study_id):
            return {**super().get_study(self.study_id), "id": study_id}

        def search(self, strain_ncbi_ids=None, metabolite_chebi_ids=None):
            return {"studies": list(self.ids)}
    monkeypatch.setattr(gui, "chosen_deriver", lambda settings, client=None: Recording(client=client))
    gui.run_query(TwoStudies(), ["Faecalibacterium prausnitzii"], {**gui.DEFAULTS, "derivation": "steady"},
                  published=False)
    # one call with both studies; given them one at a time, it fitted each study's runs apart
    assert calls == [list(TwoStudies.ids)]


# ---- one organism across studies: identity judged in each study, runs pooled by it --------------------

PRAUSNITZII = "Faecalibacterium prausnitzii A2-165"
DUNCANIAE = "Faecalibacterium duncaniae A2-165"
THETA = "Bacteroides thetaiotaomicron VPI-5482"


def _split(a_in_s2=PRAUSNITZII, taxa=True, s1_extra=(), s2_extra=()):
    """The invented design split over two studies: the pair in S1, the monocultures in S2, where the first
    organism may go by another name (`a_in_s2`). With `taxa`, every strain carries its NCBI taxon id."""
    from test_growth_rates import _client
    curves = {(1, a_in_s2): _startup(0.5, 0.04, 4.0, UNIT), (2, a_in_s2): _startup(0.5, 0.04, 4.0, UNIT),
              (3, THETA): _startup(0.3, 0.04, 4.0, 2 * UNIT), (4, THETA): _startup(0.3, 0.04, 4.0, 2 * UNIT),
              **{(i, PRAUSNITZII): _startup(0.5, 0.04, 4.0, PAIR_A) for i in (5, 6)},
              **{(i, THETA): _startup(0.3, 0.04, 4.0, PAIR_B) for i in (5, 6)}}
    exps = [_chemostat("E1", "a alone", [a_in_s2], [(1, "V1"), (2, "V2")], description=RUN),
            _chemostat("E2", "b alone", [THETA], [(3, "V1"), (4, "V2")], description=RUN),
            _chemostat("E3", "a with b", [PRAUSNITZII, THETA], [(5, "V1"), (6, "V2")], description=RUN)]
    if taxa:
        for exp in exps:
            for strain in exp["communityStrains"]:
                strain["NCBId"] = 226186 if strain["name"] == THETA else 411483
    return _client(curves), [({"id": "S1", "name": "the pair"}, [exps[2], *s1_extra]),
                             ({"id": "S2", "name": "the monocultures"}, [exps[0], exps[1], *s2_extra])]


def _sharing_411483(exp_id):
    """A batch experiment in which 411483 is also given to another strain, so the study refuses it."""
    return {"id": exp_id, "name": "another strain", "cultivationMode": "batch", "description": "",
            "communityStrains": [{"name": "Faecalibacterium prausnitzii M21-2", "NCBId": 411483}],
            "compartments": [{"mediumName": "Wilkins-Chalgren Anaerobe Broth"}], "bioreplicates": []}


def test_a_strain_renamed_between_studies_pools_by_its_taxon_id():
    """F. prausnitzii A2-165 in one study is F. duncaniae A2-165 in the other, taxon id 411483 in both: one
    organism, so the runs pool and determine the rows (Karoline, 2026-11-11: "if taxon ids agree and names
    differ, the studies can still be pooled"). Without the taxon ids the two names are two organisms, and
    a's row is not determined (b's is: the pair and b alone)."""
    client, studies = _split(a_in_s2=DUNCANIAE)
    records, _ = SteadyStateDeriver(client=client).derive_many(studies)
    on_a = next(r for r in records if r["source"] == "ncbi:226186" and r["target"] == "ncbi:411483")
    assert on_a["coefficient"] == pytest.approx(0.46 * -0.25 / UNIT, rel=1e-6)
    assert on_a["target_name"] == PRAUSNITZII and on_a["target_identity"] == "ncbi"
    assert [s["id"] for s in on_a["studies"]] == ["S1", "S2"]
    assert on_a["community"] == ["ncbi:226186", "ncbi:411483"]
    client, studies = _split(a_in_s2=DUNCANIAE, taxa=False)
    records, _ = SteadyStateDeriver(client=client).derive_many(studies)
    assert records and not [r for r in records if r["target_name"] in (PRAUSNITZII, DUNCANIAE)]


def test_a_strain_whose_taxon_id_one_study_refuses_is_not_pooled_across_them():
    """S2 gives 411483 to a second strain too, so there A2-165 is identified by genus and species, and in S1
    by its taxon id: two identities, so its runs are not pooled, and the reason is given once. Judged over
    both studies at once, the conflict in S2 demoted it in S1 too. Its row is not determined; b's is, and
    its arc from A2-165 is from S1's identity, the pair's."""
    client, studies = _split(s2_extra=[_sharing_411483("E9")])
    records, skipped = SteadyStateDeriver(client=client).derive_many(studies)
    assert not [r for r in records if r["target_name"] == PRAUSNITZII]
    assert {r["source"] for r in records if r["target_name"] == THETA} == {"ncbi:411483"}
    (why,) = [why for what, why in skipped if what == PRAUSNITZII]
    assert "identified differently" in why and "ncbi:411483" in why and "faecalibacterium prausnitzii" in why


def test_a_steady_arc_says_why_its_strain_lost_its_taxon_id():
    """Refused in both studies, A2-165 is one organism by genus and species, so the runs pool; its arcs say
    why its taxon id was refused, as the other derivations' do."""
    client, studies = _split(s1_extra=[_sharing_411483("E8")], s2_extra=[_sharing_411483("E9")])
    records, _ = SteadyStateDeriver(client=client).derive_many(studies)
    on_a = next(r for r in records if r["target_name"] == PRAUSNITZII and r["source_name"] == THETA)
    assert on_a["target"] == "faecalibacterium prausnitzii" and on_a["target_identity"] == "name"
    assert "411483" in on_a["target_taxon_id_refused"] and on_a["source_taxon_id_refused"] == ""


def test_an_arc_merged_with_a_pooled_one_keeps_every_study():
    """A pooled arc rests on S1 and S2; merged with the same arc from S3, the merged arc names all three, and
    `min_studies` counts them (it named S1 and S3, found in review of the pooling)."""
    from grownet.derive import merge_parallel
    client, studies = _split()
    records, _ = SteadyStateDeriver(client=client).derive_many(studies)
    on_a = next(r for r in records if r["source_name"] == THETA and r["target_name"] == PRAUSNITZII)
    (merged,), info = merge_parallel([on_a, _as_study(on_a, "S3")], min_studies=3)
    assert info["merged"] == 1 and [s["id"] for s in merged["studies"]] == ["S1", "S2", "S3"]


def test_pooling_does_not_move_the_package_dilution_rate():
    """a fitted at D 0.1 from runs of S1 and S2 pooled is a row in each, as the two studies fitted apart are;
    x at D 0.05 is one row. D 0.1 is the package's either way (counted once, the pooled row tied with x's
    and the lower D won)."""
    from grownet import integrated
    from grownet.subcommunity import METRIC

    def row(target, d, studies):
        return {"target": target, "target_name": target, "source": "p", "fitted_rate": 0.4,
                "fitted_rate_unit": "1/h", "fitted_rate_dilution": d, "fitted_self": -0.4e-8,
                "study_id": studies[0], "fitted_group": f"D {d} in {', '.join(studies)}",
                "studies": [{"id": s} for s in studies]}
    pooled = [row("a", 0.1, ["S1", "S2"]), row("x", 0.05, ["S3"])]
    apart = [row("a", 0.1, ["S1"]), row("a", 0.1, ["S2"]), row("x", 0.05, ["S3"])]
    for records in (pooled, apart):
        rates = integrated.fitted_rates(records, METRIC)
        assert rates["a"]["dilution"] == 0.1 and "x" not in rates


def test_a_run_left_out_for_its_technique_names_the_studies_that_set_it():
    """b is read by fc in a second pair run in S2 and by qPCR in the other runs, which come from S1 and S2:
    the run is left out, and the reason says which studies' runs read b the way the fit keeps."""
    from test_growth_rates import _client
    from test_subcommunity_inputs import _retag
    curves = {(1, "a"): _startup(0.5, 0.04, 4.0, UNIT), (2, "a"): _startup(0.5, 0.04, 4.0, UNIT),
              (3, "b"): _startup(0.3, 0.04, 4.0, 2 * UNIT), (4, "b"): _startup(0.3, 0.04, 4.0, 2 * UNIT)}
    for i in (5, 6, 7):
        curves[(i, "a")] = _startup(0.5, 0.04, 4.0, PAIR_A)
        curves[(i, "b")] = _startup(0.3, 0.04, 4.0, PAIR_B)
    client = _client(curves)
    _retag(client, "b", "fc", bioreplicates={7})
    pair = _chemostat("E3", "a with b", ["a", "b"], [(5, "V1"), (6, "V2")], description=RUN)
    again = _chemostat("E4", "a with b again", ["a", "b"], [(7, "V1")], description=RUN)
    monos = [_chemostat("E1", "a alone", ["a"], [(1, "V1"), (2, "V2")], description=RUN),
             _chemostat("E2", "b alone", ["b"], [(3, "V1"), (4, "V2")], description=RUN)]
    _, skipped = SteadyStateDeriver(client=client).derive_many([({"id": "S1", "name": "x"}, [pair]),
                                                                ({"id": "S2", "name": "y"}, [*monos, again])])
    (why,) = [why for what, why in skipped if what.startswith("a with b again")]
    assert "b by fc" in why and "(in S1, S2)" in why
