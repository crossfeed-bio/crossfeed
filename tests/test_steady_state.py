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


# the chemostat's medium and the package's below are the two live spellings of one medium that still
# match under the keyed rule of 2026-10-07: the same words, one of them with the parenthesized
# abbreviation mGrowthDB sometimes adds. The bare short name "Wilkins-Chalgren" no longer matches either,
# which is the measured cost of keying and is pinned in the medium test below.
def _chemostat(exp_id, name, members, replicates, dilution="0.040",
               medium="Wilkins-Chalgren Anaerobe Broth", description=""):
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
    # the medium is the strict label since 2026-10-07: the name with every alteration its description
    # stated, which is what an arc records too, so the two sides of the check are comparable
    assert seen["medium"] == "Wilkins-Chalgren Anaerobe Broth" and seen["vessels"] == 2
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


def test_two_media_are_one_when_their_identities_agree_and_not_when_they_differ():
    """Karoline, 2026-10-07: "foodnet's strict medium rule should be applied in general ... because such
    changes alter interactions". So two recorded media are one when `media.identity`'s key agrees, and
    the key normalizes case, punctuation and a parenthesized abbreviation and carries every alteration
    the description stated. The rule is an equality, so it is transitive, which the subset rule it
    replaced was not (#142 item 10).

    Each case below is a pair of names mGrowthDB actually serves."""
    # the same words, with and without the abbreviation: SMGDB00000009 and 16 against SMGDB00000002, 7
    # and 11, which is the comparison the chemostat validation rests on
    assert steady.same_medium("Wilkins-Chalgren Anaerobe Broth (WC)", "Wilkins-Chalgren Anaerobe Broth")
    assert steady.same_medium("Db-MM medium", "Db-MM medium ")       # a trailing space is one medium
    assert not steady.same_medium("mMCB", "Wilkins-Chalgren Anaerobe Broth")
    assert not steady.same_medium("", "Wilkins-Chalgren Anaerobe Broth")

    # spoke to spoke, which the old test never asked (Craig's agent, on #141): every assertion there put
    # the short name on one side, and the short name was a subset of all three long ones. Both of these
    # hold because the alias table says so, not because the rule does (Karoline, 2026-10-07: "yes, add
    # the alias table"); `tests/test_media.py` pins what the rule says without it
    assert steady.same_medium("Wilkins-Chalgren Anaerobe Broth", "Wilkins-Chalgren Anerobe Broth (WC)")
    assert steady.same_medium("Wilkins-Chalgren Anaerobe Broth (WC)", "Wilkins-Chalgren")
    # an alias reaches a name, never an environment: a sugar dropped still makes another medium
    assert not steady.same_medium("Wilkins-Chalgren", "Wilkins-Chalgren Anaerobe Broth (-glucose)")

    # a composite name is a design of two compartments, not a medium with something added, and matching
    # it to one of its own compartments loses which compartment the organism was in (#142 item 13)
    assert not steady.same_medium("Wilkins-Chalgren Anaerobe Broth (WC)",
                                  "Wilkins-Chalgren Anaerobe Broth (WC); Mucin")
    assert not steady.same_medium("MDb-MM basal medium mucin DoS ", "Mucin")
    assert not steady.same_medium("LB", "Albumin broth")

    # an alteration the description stated travels in the label, so two concentrations are two media
    assert steady.same_medium("Minimal medium (MM) (+0.05% linoleic acid)",
                              "Minimal medium (+0.05% linoleic acid)")
    assert not steady.same_medium("Minimal medium (MM) (+0.05% linoleic acid)",
                                  "Minimal medium (MM) (+0.75% linoleic acid)")
    assert not steady.same_medium("Wilkins-Chalgren Anaerobe Broth",
                                  "Wilkins-Chalgren Anaerobe Broth (-glucose, -pyruvate)")


def test_a_run_scored_across_an_alias_says_which_entry_made_it_one_medium():
    """An alias is the one place grownet calls two names that disagree one medium, so it is never silent:
    the run is scored and the block says which entry of the table did it (Karoline, 2026-10-07)."""
    client = _client({(1, A): _flat(9.0e8)})
    short = steady.observed(client, [_chemostat("E1", "no perturbations", [A], [(1, "V1")],
                                                medium="Wilkins-Chalgren")])
    (check,) = steady.check(_package(), RATES, short)
    assert check["used"] is True
    assert check["medium_aliases"] == [["wilkins chalgren", "wilkins chalgren anaerobe broth"]]
    assert 'scored across a medium alias: "wilkins chalgren" is read as' in steady.as_text([check])

    # the full name on both sides needs no alias, and says nothing
    (plain,) = steady.check(_package(), RATES, steady.observed(
        client, [_chemostat("E1", "no perturbations", [A], [(1, "V1")])]))
    assert plain["used"] is True and plain["medium_aliases"] == []
    assert "medium alias" not in steady.as_text([plain])


def test_a_run_not_scored_over_a_spelling_says_so_rather_than_blaming_the_environment():
    """Craig's agent, on #141: `why_not` gave a scientific reason, that a coefficient is specific to its
    environment, for what may be a typo in a third-party database. For a spelling nobody has put in the
    alias table, the message says the two names differ and names the one word they differ in."""
    from grownet.media import near_miss
    assert near_miss("Db-MM medium", "Db-MN medium") == ("mm", "mn")
    # something added or taken away is a real difference, not a spelling, and is not reported as one
    assert near_miss("Wilkins-Chalgren Anaerobe Broth",
                     "Wilkins-Chalgren Anaerobe Broth (-glucose)") is None

    client = _client({(1, A): _flat(3.0e8)})
    other = steady.observed(client, [_chemostat("E1", "x", [A], [(1, "V1")], medium="Db-MM medium")])
    (check,) = steady.check(_package(medium="Db-MN medium"), RATES, other)
    assert check["used"] is False
    assert "mGrowthDB names them as different media" in check["why_not"]
    assert "differs from this run's medium in one word only" in check["why_not"]
    assert '"mn" against "mm"' in check["why_not"]


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


def test_a_matrix_holding_no_cell_still_stands_for_its_arcs_medium():
    """Round 20 of the review: a matrix's media became those of the cells it holds, so a matrix whose only
    pair is a sign conflict (B on A, +1.0 and -1.0, in WC) recorded none, and a chemostat in mMCB was scored
    against it with a note that the package records no medium. The arcs between its organisms are in WC,
    so the run is refused as another environment, as it was before."""
    def arc(effect, strength):
        return {"source": _gs(B), "target": _gs(A), "source_name": B, "target_name": A,
                "effect": effect, "strength": strength, "status": "present", "outcome": "quantified",
                "study_id": "S1", "metric": "growth_rate:easylinear:5", "evidence": "biculture",
                "medium": "Wilkins-Chalgren Anaerobe Broth (WC)", "partner_abundance": 2.0e8,
                "partner_abundance_unit": "Cells/mL", "partner_abundance_n": 3}
    got = matrix.coefficients(records_to_network([arc("facilitation", 1.0), arc("inhibition", -1.0)]), RATES)
    (block,) = got["matrices"]
    assert block["cells"] == 0 and block["media"] == []
    assert block["arc_media"] == ["Wilkins-Chalgren Anaerobe Broth (WC)"]
    client = _client({(1, A): _flat(3.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "x", [A], [(1, "V1")], medium="mMCB")])
    (result,) = steady.check(got, RATES, seen)
    assert not result["used"] and "the package in Wilkins-Chalgren Anaerobe Broth (WC)" in result["why_not"]


def test_a_matrix_holding_cells_stands_for_their_medium_only():
    """Round 21 of the review: a matrix whose one cell, B on A, is in WC, beside an arc A on B in LB that is
    in no cell (its partner counted in CFUs/mL), was matched by an LB chemostat through that arc and scored
    with the WC cell. A matrix holding a cell stands for its cells' media."""
    WC = "Wilkins-Chalgren Anaerobe Broth (WC)"

    def arc(src, tgt, medium, unit="Cells/mL"):
        return {"source": _gs(src), "target": _gs(tgt), "source_name": src, "target_name": tgt,
                "effect": "facilitation", "strength": 0.5, "status": "present", "outcome": "quantified",
                "study_id": "S1", "metric": "growth_rate:easylinear:5", "evidence": "biculture",
                "medium": medium, "partner_abundance": 2.0e8, "metric_with": 0.6, "metric_without": 0.4,
                "partner_abundance_unit": unit, "partner_abundance_n": 3}
    got = matrix.coefficients(records_to_network([arc(B, A, WC), arc(A, B, "LB", unit="CFUs/mL")]), RATES)
    (block,) = got["matrices"]
    assert block["cells"] == 1 and block["media"] == [WC] and "LB" in block["arc_media"]
    client = _client({(1, A): _flat(3.0e8), (1, B): _flat(2.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "x", [A, B], [(1, "V1")], medium="LB")])
    (result,) = steady.check(got, RATES, seen)
    assert not result["used"] and f"the package in {WC}" in result["why_not"]


def test_arcs_that_join_a_matrix_and_record_no_medium_are_not_given_the_network_s():
    """Round 21 of the review: B on A records no medium and is the matrix's one cell; another organism's arc
    on A is in LB. The matrix's arcs were given the network's media (LB), so a chemostat in another medium
    was refused as LB; the arcs joining the matrix say none, so it is scored with the note that the package
    records no medium."""
    def arc(src, tgt, medium, unit="Cells/mL"):
        return {"source": _gs(src), "target": _gs(tgt), "source_name": src, "target_name": tgt,
                "effect": "facilitation", "strength": 0.5, "status": "present", "outcome": "quantified",
                "study_id": "S1", "metric": "growth_rate:easylinear:5", "evidence": "biculture",
                "medium": medium, "partner_abundance": 2.0e8, "metric_with": 0.6, "metric_without": 0.4,
                "partner_abundance_unit": unit, "partner_abundance_n": 3}
    other = "Some other organism"
    # and A on B, between the matrix's own organisms, in LB with B counted in CFUs/mL: in no cell, so it
    # does not decide the matrix's medium either (round 22)
    got = matrix.coefficients(records_to_network([arc(B, A, None), arc(other, A, "LB", unit="CFUs/mL"),
                                                  arc(A, B, "LB", unit="CFUs/mL")]), RATES)
    block = got["matrices"][0]
    assert block["media"] == [] and block["arc_media"] == ["LB"]
    client = _client({(1, A): _flat(3.0e8), (1, B): _flat(2.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "x", [A, B], [(1, "V1")])])
    (result,) = steady.check(got, RATES, seen)
    assert result["used"] and "the effects in this matrix record no medium" in result["note"]


def test_a_matrix_holding_no_cell_is_scored_by_its_arcs_medium_with_its_aliases():
    """Round 21 of the review: a matrix whose one pair is a sign conflict in "Wilkins-Chalgren" holds no
    cell, so it stands for its arcs' medium. A chemostat in the full name is scored across the alias, with
    the alias named and no note that the package records no medium; an absent arc between the two, in LB,
    is not part of that environment."""
    def arc(effect, strength, medium="Wilkins-Chalgren", status="present"):
        return {"source": _gs(B), "target": _gs(A), "source_name": B, "target_name": A,
                "effect": effect, "strength": strength, "status": status, "outcome": "quantified",
                "study_id": "S1", "metric": "growth_rate:easylinear:5", "evidence": "biculture",
                "medium": medium, "partner_abundance": 2.0e8, "partner_abundance_unit": "Cells/mL",
                "partner_abundance_n": 3}
    absent = {**arc("facilitation", 0.1, medium="LB", status="absent"), "condition": "x"}
    got = matrix.coefficients(records_to_network([arc("facilitation", 1.0), arc("inhibition", -1.0), absent]),
                              RATES)
    (block,) = got["matrices"]
    assert block["cells"] == 0 and block["arc_media"] == ["Wilkins-Chalgren"]
    client = _client({(1, A): _flat(3.0e8)})
    seen = steady.observed(client, [_chemostat("E1", "x", [A], [(1, "V1")])])
    (result,) = steady.check(got, RATES, seen)
    assert result["used"] and result.get("note") is None
    assert result["medium_aliases"] == [["wilkins chalgren", "wilkins chalgren anaerobe broth"]]


def test_a_check_that_could_not_look_chemostats_up_says_so():
    """Round 22 of the review: a genus package (genus nodes carry no taxon id) and a search that failed both
    read "mGrowthDB holds no continuous culture of these organisms", while the strain run of the same study
    scores two chemostats. The check now says it did not run, and why."""
    from grownet.model import InteractionNetwork, Node
    genus = InteractionNetwork()
    genus.nodes["genus:Bacteroides"] = Node(id="genus:Bacteroides", name="Bacteroides", taxon_id="")

    class Failing:
        def search(self, **_):
            raise OSError("connection refused")
    found = steady.find(Failing(), genus)
    assert found == [] and "no organism of this network has a taxon id" in found.why_not
    text = steady.as_text(steady.check({"matrices": []}, {}, found))
    assert text.startswith("steady-state check: not checked, because no organism of this network has a taxon id")
    assert "holds no continuous culture" not in text
    strains = records_to_network([{"source": "ncbi:1", "target": "ncbi:2", "source_name": B, "target_name": A,
                                   "source_taxon_id": "1", "target_taxon_id": "2",
                                   "effect": "facilitation", "strength": 1.0, "status": "present", "study_id": "S1"}])
    failed = steady.find(Failing(), strains)
    assert "the search for chemostats of these organisms failed (connection refused)" in steady.as_text(
        steady.check({"matrices": []}, {}, failed))
    # control: a search that ran and found none still says mGrowthDB holds none
    assert "holds no continuous culture" in steady.as_text(steady.check({"matrices": []}, {}, []))
