"""Scoring a gLV package against a chemostat steady state (#125, from #124 item 4a).

Karoline, 2026-10-06: "you can check accuracy of fit using study 7 for mono-cultures and pairs with study
5's controls, which are steady state community abundances (without perturbation, ignoring the extra
species, which are at small abundance)", and then "go ahead with ... the chemostat validation".

A chemostat holds dx_i/dt = x_i (r_i + sum_j A_ij x_j) - D x_i, so at steady state A x* = -(r - D). The
package is built from batch cultures and never sees these numbers, which is what makes them a score.
Every expected value below is hand computed in the test that uses it.
"""
import math

import pytest
from test_growth_rates import A, B, _client

from grownet import matrix, steady
from grownet.derive import _gs
from grownet.mgrowthdb import records_to_network


def _chemostat(exp_id, name, members, replicates, dilution="0.040", medium="Wilkins-Chalgren",
               description=""):
    return {"id": exp_id, "name": name, "cultivationMode": "chemostat", "description": description,
            "communityStrains": [{"name": m} for m in members],
            "compartments": [{"mediumName": medium, "dilutionRate": dilution}],
            "bioreplicates": [{"id": bid, "name": rname} for bid, rname in replicates]}


def _flat(value, points=12, step=10.0, start=None):
    """A chemostat trace that rises from `start` and then holds `value`: the steady state is `value`."""
    first = value / 10 if start is None else start
    return [(i * step, first if i < points // 2 else value, None) for i in range(points)]


# ---- what the chemostat says ----------------------------------------------------------------------

def test_the_steady_state_of_a_vessel_is_the_mean_over_the_end_of_the_run():
    """The rule, stated once: the mean over the last quarter of the run in each vessel, then the median
    over the vessels. Vessel 1 holds A at 2e8 and vessel 2 at 4e8, so the median is 3e8."""
    client = _client({(1, A): _flat(2.0e8), (2, A): _flat(4.0e8)})
    exp = _chemostat("E1", "no perturbations", [A], [(1, "V1"), (2, "V2")])
    (seen,) = steady.observed(client, [exp])
    assert seen["dilution"] == pytest.approx(0.040) and seen["unit"] == "Cells/mL"
    assert seen["medium"] == "Wilkins-Chalgren" and seen["vessels"] == 2
    assert seen["organisms"][A]["value"] == pytest.approx(3.0e8)
    assert seen["organisms"][A]["vessels"] == 2
    assert seen["window"][0] < seen["window"][1] and seen["perturbed"] is False
    assert seen["left_out"] == []


def test_an_organism_without_a_curve_in_the_chemostat_is_named_not_given_a_number():
    client = _client({(1, A): _flat(2.0e8)})
    exp = _chemostat("E1", "no perturbations", [A, B], [(1, "V1")])
    (seen,) = steady.observed(client, [exp])
    assert A in seen["organisms"] and B not in seen["organisms"]
    assert any(B in who and "no curve" in why for who, why in seen["left_out"])


def test_a_chemostat_without_a_recorded_dilution_rate_says_so():
    """SMGDB00000001's chemostat records none, and a steady state cannot be scored without it."""
    client = _client({(1, A): _flat(2.0e8)})
    exp = _chemostat("E1", "community", [A], [(1, "V1")], dilution=None)
    (seen,) = steady.observed(client, [exp])
    assert seen["dilution"] is None
    assert "no dilution rate" in seen["why_not"]


def test_a_perturbed_chemostat_is_named_as_perturbed():
    """Karoline asked for the steady states "without perturbation", so a perturbed run is marked rather
    than used silently."""
    client = _client({(1, A): _flat(2.0e8)})
    exp = _chemostat("E1", "A6", [A], [(1, "V1")],
                     description="Perturbations: a pulse of mucin at 100 h.")
    (seen,) = steady.observed(client, [exp])
    assert seen["perturbed"] is True and "perturbation" in seen["why_not"]


# ---- what the package predicts --------------------------------------------------------------------

def _rate(name, rate, capacity):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"],
            "method": "growth_rate:easylinear:5", "lag": 0.0, "lag_method": "baranyi",
            "capacity": capacity, "capacity_unit": "Cells/mL", "capacity_n": 3}


RATES = {_gs(A): _rate(A, 0.4, 1.0e9), _gs(B): _rate(B, 0.2, 5.0e8)}


def _package(medium="Wilkins-Chalgren Anaerobe Broth (WC)"):
    """A package of the two organisms of the rate tests, from one arc so that it records a medium.
    A's diagonal is -0.4 / 1e9 = -4e-10, so A alone settles at 1e9 and at 9e8 under a dilution of
    0.04 /h: (0.4 - 0.04) / 4e-10."""
    arc = {"source": _gs(B), "target": _gs(A), "source_name": B, "target_name": A,
           "effect": "facilitation", "strength": 1.0, "status": "present", "outcome": "quantified",
           "study_id": "S1", "metric": "growth_rate:easylinear:5", "evidence": "biculture",
           "medium": medium, "partner_abundance": 2.0e8, "partner_abundance_unit": "Cells/mL",
           "partner_abundance_n": 3}
    return matrix.coefficients(records_to_network([arc]), RATES)


def test_the_prediction_is_the_solution_of_a_x_equals_minus_r_minus_d():
    """Hand computed: with A_ii = -4e-10 and r = 0.4 /h, a batch equilibrium is 1e9, and under a dilution
    rate of 0.04 /h it is (0.4 - 0.04) / 4e-10 = 9e8."""
    block = _package()["matrices"][0]
    # A on its own: the sub-community of one organism the chemostat would hold
    assert steady.predicted(block, RATES, 0.0, [A])["values"][A] == pytest.approx(1.0e9)
    assert steady.predicted(block, RATES, 0.040, [A])["values"][A] == pytest.approx(9.0e8)
    # and a dilution rate above the growth rate washes the organism out, which is not a positive state
    washed = steady.predicted(block, RATES, 0.5, [A])
    assert washed["values"][A] < 0 and "not positive" in washed["notes"][A]


def test_the_check_reports_the_ratio_per_organism():
    """The number a reader wants: predicted over observed. The package says 9e8 under D = 0.04 and the
    chemostat holds 3e8, so the ratio is 3."""
    client = _client({(1, A): _flat(3.0e8)})
    exp = _chemostat("E1", "no perturbations", [A], [(1, "V1")])
    seen = steady.observed(client, [exp])
    (check,) = steady.check(_package(), RATES, seen)
    assert check["used"] is True
    row = check["rows"][0]
    assert row["organism"] == A and row["predicted"] == pytest.approx(9.0e8)
    assert row["observed"] == pytest.approx(3.0e8) and row["ratio"] == pytest.approx(3.0)
    text = steady.as_text([check])
    assert "no perturbations" in text and "3.0x" in text.replace("3x", "3.0x")


def test_an_organism_the_fit_washes_out_and_the_chemostat_lost_too_agrees():
    """SMGDB00000011's Faecalibacterium duncaniae sits at 0 in every vessel. A fit that sends it to zero
    or below agrees in direction, and the check says so rather than printing a ratio of infinity."""
    client = _client({(1, A): _flat(1.0, start=1.0e7),      # A fell to about nothing
                      (1, B): _flat(3.0e8)})                # while B held 3e8, so A is 3e-9 of the run
    exp = _chemostat("E1", "no perturbations", [A, B], [(1, "V1")])
    seen = steady.observed(client, [exp])
    got = _package()
    block = got["matrices"][0]
    here = block["organisms"].index(A)
    block["matrix"][here][here] = 4.0e-10                   # a positive diagonal: no bounded state
    (check,) = steady.check(got, RATES, seen)
    row = next(r for r in check["rows"] if r["organism"] == A)
    assert row["ratio"] is None and "washes this organism out and the chemostat did too" in row["note"]


def test_nothing_is_scored_across_abundance_units_or_media():
    client = _client({(1, A): _flat(3.0e8)})
    other_unit = steady.observed(client, [_chemostat("E1", "no perturbations", [A], [(1, "V1")])])
    other_unit[0]["unit"] = "CFUs/mL"
    (check,) = steady.check(_package(), RATES, other_unit)
    assert check["used"] is False and "CFUs/mL" in check["why_not"]

    other_medium = steady.observed(client, [_chemostat("E1", "x", [A], [(1, "V1")], medium="mMCB")])
    (check,) = steady.check(_package(), RATES, other_medium)
    assert check["used"] is False and "mMCB" in check["why_not"]


def test_the_two_names_of_wilkins_chalgren_are_one_medium():
    """The batch study writes "Wilkins-Chalgren Anaerobe Broth (WC)" and the chemostat "Wilkins-Chalgren",
    and they are the same medium, so a check is not refused over the spelling."""
    assert steady.same_medium("Wilkins-Chalgren Anaerobe Broth (WC)", "Wilkins-Chalgren")
    assert steady.same_medium("wilkins chalgren", "Wilkins-Chalgren Anaerobe Brot")
    assert not steady.same_medium("mMCB", "Wilkins-Chalgren")
    assert not steady.same_medium("", "Wilkins-Chalgren")

    # the rule compared raw substrings until 2026-10-06, which called a defined medium with mucin added
    # the same medium as mucin alone: the one false positive mGrowthDB's own names produce. A short name
    # now needs two words of the longer one, and a word that states an omission or an addition separates
    # two names however much else they share.
    assert not steady.same_medium("MDb-MM basal medium mucin DoS ", "Mucin")
    assert not steady.same_medium("LB", "Albumin broth")
    assert not steady.same_medium("WC", "Nutrient broth WC-free")
    assert not steady.same_medium("Wilkins-Chalgren", "Wilkins-Chalgren without glucose")
    assert steady.same_medium("Db-MM medium", "Db-MM medium ")       # a trailing space is one medium


OTHER = "Escherichia coli LF82"


def test_a_matrix_sharing_no_organism_with_the_chemostat_is_not_scored():
    client = _client({(1, OTHER): _flat(3.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "no perturbations", [OTHER], [(1, "V1")])])
    (check,) = steady.check(_package(), RATES, seen)
    assert check["used"] is False and "no organism" in check["why_not"]


def test_the_check_only_reports_and_never_changes_a_coefficient():
    got = _package()
    before = [row[:] for row in got["matrices"][0]["matrix"]]
    client = _client({(1, A): _flat(3.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "no perturbations", [A], [(1, "V1")])])
    steady.check(got, RATES, seen)
    assert got["matrices"][0]["matrix"] == before
    assert math.isclose(before[0][0], -4.0e-10, rel_tol=1e-12)


# ---- the routes that carry it ----------------------------------------------------------------------

def test_the_check_travels_in_the_package_and_in_the_report():
    """One computation, both routes: the zip carries steady_state_check.txt and the report the same
    block, so a reader of either sees what the package was scored against (#125)."""
    import io
    import zipfile

    from grownet.model import InteractionNetwork

    client = _client({(1, A): _flat(3.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "no perturbations", [A], [(1, "V1")])])
    checks = steady.check(_package(), RATES, seen)
    text = steady.as_text(checks)

    arc = {"source": _gs(B), "target": _gs(A), "source_name": B, "target_name": A,
           "effect": "facilitation", "strength": 1.0, "status": "present", "outcome": "quantified",
           "study_id": "S1", "metric": "growth_rate:easylinear:5", "evidence": "biculture",
           "medium": "Wilkins-Chalgren Anaerobe Broth (WC)", "partner_abundance": 2.0e8,
           "partner_abundance_unit": "Cells/mL", "partner_abundance_n": 3}
    net = records_to_network([arc])
    net.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    with zipfile.ZipFile(io.BytesIO(matrix.glv_package(net, RATES,
                                                       {"steady_state_check.txt": text}))) as archive:
        assert "steady_state_check.txt" in archive.namelist()
        assert archive.read("steady_state_check.txt").decode() == text

    # and the report prints the same block when a run made one
    from grownet.report import report_text
    assert isinstance(net, InteractionNetwork)
    result = {"network": net, "entries": [], "resolved": [], "unresolved": [], "studies": ["S1"],
              "skipped": [], "errors": [], "rates": RATES, "steady": checks,
              "hidden": {}, "absence": {"k": 1.0, "absent": 0}}
    assert "steady-state check" in report_text(result)
    assert "no perturbations" in report_text(result)


def test_a_run_that_asked_for_no_check_says_nothing_about_one():
    """The check is off by default, so a report of a search without it carries no block about it."""
    from grownet.report import report_text
    net = records_to_network([{"source": "a", "target": "b", "source_name": "A", "target_name": "B",
                               "effect": "facilitation", "strength": 1.0, "status": "present",
                               "outcome": "quantified", "study_id": "S1"}])
    result = {"network": net, "entries": [], "resolved": [], "unresolved": [], "studies": ["S1"],
              "skipped": [], "errors": [], "rates": {}, "hidden": {}, "absence": {"k": 1.0, "absent": 0}}
    assert "steady-state check" not in report_text(result)


def test_the_page_setting_and_the_command_line_flag_are_one_setting():
    """Karoline's standing rule: anything the page does, the command line does (#72)."""
    from grownet.__main__ import build_parser
    from grownet.gui import DEFAULTS, parse_settings

    derive = next(a for a in build_parser()._actions if a.dest == "cmd").choices["derive"]
    assert "--steady-check" in {o for action in derive._actions for o in action.option_strings}
    assert DEFAULTS["steady_check"] is False                      # off by default on both
    assert parse_settings({"steady_check": ["1"]})["steady_check"] is True
