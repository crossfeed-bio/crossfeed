"""The gLV package as fitted coefficients, in 1/(time x abundance), one matrix per unit (#119).

Karoline settled the entries on #116 ("let's use the mixture of growth curve features that fits the
equation best; following Craig's recommendation and the math"):

    A_ii = -r_i / K_i
    A_ij = r_i * (2^L - 1) / x_j_star          L = log2 ratio of the target's growth RATE

Every number below is hand computed in the test that uses it. An organism doubling every hour has
r = ln 2 = 0.693 /h; the rates here are round numbers instead, so the arithmetic stays checkable.
"""
import csv
import io
import math
import zipfile

import pytest

from grownet import matrix
from grownet.mgrowthdb import records_to_network

RATE_METRIC = "growth_rate:baranyi"


# each organism's own rate, so an arc can carry the absolute numbers its strength is the ratio of (#123)
RATE_OF = {"a": 0.4, "b": 0.2, "c": 0.5, "d": 0.5}


def _arc(source, target, strength, x_j=2.0e8, unit="Cells/mL", **extra):
    """One biculture arc with the partner's abundance #118 measures beside it, and the two absolute rates
    #123 fits from: the target's own rate without the source, and that rate times 2^strength with it, so
    (r_with - r_without) / x_j is the same number the ratio form gave."""
    without = RATE_OF.get(target, 0.4)
    with_source = None if strength is None else without * 2 ** strength
    record = {"source": source, "target": target, "source_name": source.upper(),
              "target_name": target.upper(),
              "effect": "facilitation" if (strength or 1) > 0 else "inhibition", "strength": strength,
              "status": "present", "outcome": "quantified", "study_id": "S1", "metric": RATE_METRIC,
              "evidence": "biculture", "medium": "WC", "partner_abundance": x_j,
              "partner_abundance_unit": unit, "partner_abundance_n": 3,
              "metric_with": with_source, "metric_without": without,
              "target_capacity": 3.0e8, "target_capacity_unit": unit, "target_capacity_n": 3}
    record.update(extra)
    if record["outcome"] == "obligate":
        record.update(metric_with=without * 2, metric_without=0.0)       # grew only with the source
    elif record["outcome"] == "abolished":
        record.update(metric_with=0.0, metric_without=without)           # grew only without it
    return record


def _rate(name, rate, capacity, unit="Cells/mL", method=RATE_METRIC, **extra):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"], "per_study": {"S1": rate},
            "method": method, "lag": 0.5, "lag_method": "baranyi", "capacity": capacity,
            "capacity_unit": unit, "capacity_n": 3,
            **extra}


def _net(arcs):
    return records_to_network(arcs, meta={"tool_version": "9.9.9", "absence": {"k": 1.0},
                                          "source_db": "mGrowthDB (live)"})


# A pair with everything: A doubles its rate with B (L = 1), B's rate halves with A (L = -1).
PAIR = [_arc("b", "a", 1.0, x_j=2.0e8), _arc("a", "b", -1.0, x_j=4.0e8)]
RATES = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}


def _one(net, rates):
    """The single matrix of a network whose abundances are all in one unit."""
    got = matrix.coefficients(net, rates)
    assert len(got["matrices"]) == 1, got["matrices"]
    return got, got["matrices"][0]


def _cell(block, affected, actor):
    i, j = block["organisms"].index(affected), block["organisms"].index(actor)
    return block["matrix"][i][j]


def test_a_diagonal_cell_is_minus_the_rate_over_the_carrying_capacity():
    """-r_i / K_i: A is 0.4 /h over 1e9 cells/mL = -4e-10, B is 0.2 over 5e8 = -4e-10. The gLV diagonal
    is now fitted, so the -1 convention is gone from the package."""
    _, block = _one(_net(PAIR), RATES)
    assert _cell(block, "A", "A") == pytest.approx(-4.0e-10)
    assert _cell(block, "B", "B") == pytest.approx(-4.0e-10)
    assert block["abundance_unit"] == "Cells/mL" and block["unit"] == "1/(h x Cells/mL)"


def test_an_off_diagonal_cell_is_the_rate_times_the_ratio_over_the_partners_abundance():
    """r_i (2^L - 1) / x_j*: B on A is 0.4 * (2 - 1) / 2e8 = +2e-9; A on B is 0.2 * (0.5 - 1) / 4e8 =
    -2.5e-10. Rows are affected and columns are the actor, as before."""
    _, block = _one(_net(PAIR), RATES)
    assert _cell(block, "A", "B") == pytest.approx(2.0e-9)
    assert _cell(block, "B", "A") == pytest.approx(-2.5e-10)
    assert block["cells"] == 2 and block["conflicts"] == []


def test_one_matrix_per_abundance_unit_each_declaring_its_own():
    """Craig's partition, which Karoline took: a cell mass conversion would have to be invented, and the
    dynamics are invariant to the unit, so units are kept apart rather than converted. C is measured in
    CFUs/mL, so it gets its own matrix and does not appear in the other."""
    arcs = PAIR + [_arc("d", "c", 1.0, x_j=1.0e7, unit="CFUs/mL")]
    rates = {**RATES, "c": _rate("C", 0.5, 1.0e8, unit="CFUs/mL"),
             "d": _rate("D", 0.5, 2.0e8, unit="CFUs/mL")}
    got = matrix.coefficients(_net(arcs), rates)
    by_unit = {block["abundance_unit"]: block for block in got["matrices"]}
    assert sorted(by_unit) == ["CFUs/mL", "Cells/mL"]
    assert by_unit["Cells/mL"]["organisms"] == ["A", "B"]
    assert by_unit["CFUs/mL"]["organisms"] == ["C", "D"]
    assert by_unit["CFUs/mL"]["unit"] == "1/(h x CFUs/mL)"
    # D on C: 0.5 * (2 - 1) / 1e7 = +5e-8, in its own unit and nowhere near the other matrix
    assert _cell(by_unit["CFUs/mL"], "C", "D") == pytest.approx(5.0e-8)
    assert all(abs(v) < 1.0e-8 for row in by_unit["Cells/mL"]["matrix"] for v in row)


def test_an_obligate_pair_needs_no_floor_at_all():
    """The floor this task gave a censored pair was replaced on #123, which Karoline settled the same
    day: the formula is a difference of rates, and an obligate pair measured 0 without the actor, so
    0.8 / 2e8 = +4e-9 is a measurement. tests/test_absolute_rates.py checks that form; here only that
    no floor and no stated extreme is left."""
    arcs = PAIR + [_arc("c", "a", None, x_j=2.0e8, outcome="obligate", effect="facilitation")]
    rates = {**RATES, "c": _rate("C", 0.5, 1.0e8)}
    got, block = _one(_net(arcs), rates)
    assert _cell(block, "A", "C") == pytest.approx(4.0e-9)
    assert got["floors"] == []
    text = matrix.readme_from(got, _net(arcs), rates)
    assert "FLOORS, NOT MEASUREMENTS" not in text and "by convention" not in text
    assert all(abs(v) != 10.0 for row in block["matrix"] for v in row)


def test_no_convention_is_left_in_the_package():
    """The acceptance of #119: no -1 diagonal, no +/-10, and nothing to scale."""
    arcs = PAIR + [_arc("b", "c", None, x_j=2.0e8, outcome="abolished", effect="inhibition")]
    rates = {**RATES, "c": _rate("C", 0.5, 1.0e8)}
    with zipfile.ZipFile(io.BytesIO(matrix.glv_package(_net(arcs), rates))) as archive:
        names = sorted(archive.namelist())
        assert names == ["README.txt", "growth_rates.csv", "interaction_matrix.Cells_per_mL.csv"]
        table = list(csv.reader(io.StringIO(archive.read(names[2]).decode())))
        numbers = [float(v) for row in table[1:] for v in row[1:]]
        assert all(abs(v) < 1.0e-6 for v in numbers)      # per-capita coefficients, not log2 means
        assert not any(v in (-1.0, 10.0, -10.0) for v in numbers)
        readme = archive.read("README.txt").decode()
        assert "-1 by convention" not in readme and "glv_scale" not in readme
        assert "1/(h x Cells/mL)" in readme


def test_an_organism_without_any_certified_plateau_is_named_not_given_a_number():
    """A self-limitation of 0 is a number no one stands behind. #118 only certifies a monoculture K from a
    curve that reached stationary phase, and #124 item 2 then allows the organism's own plateau beside its
    partners instead; with neither, it leaves the matrix and the README says why."""
    bare = [dict(arc, target_capacity=None, target_capacity_unit="", target_capacity_n=0) for arc in PAIR]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, None, unit="")}
    got, block = _one(_net(bare), rates)
    assert block["organisms"] == ["A"]
    assert got["left_out"] == [("B", "no carrying capacity from a curve that reached stationary phase, "
                                "so its self-limitation is not fitted")]
    text = matrix.readme_from(got, _net(bare), rates)
    assert "B" in text and "stationary" in text

    # with a plateau beside its partner, the same organism is fitted there instead (#124 item 2)
    got, block = _one(_net(PAIR), rates)
    assert block["organisms"] == ["A", "B"]
    assert got["plateau_rows"] == [("B", "its co-culture plateau")]


def test_an_organism_without_a_rate_is_named_too():
    """The Baranyi guards reject a curve rather than borrow easylinear's rate (#119), so an organism can
    reach the package with no rate at all. It leaves the matrix and is named."""
    got, block = _one(_net(PAIR), {"a": _rate("A", 0.4, 1.0e9)})
    assert block["organisms"] == ["A"]
    assert got["left_out"] == [("B", "no growth rate, and no arc saying it grows only with a partner, so "
                                "neither its own limitation nor the effect of anything on it can be "
                                "fitted")]


def test_a_pair_without_the_partners_abundance_stays_at_zero_and_is_named():
    """x_j* is the number the formula divides by: without it there is no coefficient. The cell is 0, as a
    sign conflict is, and the README names the pair with the reason."""
    arcs = [dict(PAIR[0], partner_abundance=None, partner_abundance_unit="", partner_abundance_n=0),
            PAIR[1]]
    got, block = _one(_net(arcs), RATES)
    assert _cell(block, "A", "B") == 0.0
    assert got["pairs_left_out"] == [("A", "B", "no abundance for B over A's growth window, so the "
                                      "per-capita effect cannot be fitted")]


def test_a_pair_measured_in_another_unit_than_the_affected_organism_is_named():
    """The matrix of a unit holds only the cells measured in it: a cell whose partner was counted another
    way would make the row inconsistent."""
    arcs = [dict(PAIR[0], partner_abundance=1.0e7, partner_abundance_unit="CFUs/mL"), PAIR[1]]
    got, block = _one(_net(arcs), RATES)
    assert _cell(block, "A", "B") == 0.0
    assert got["pairs_left_out"] == [("A", "B", "B's abundance beside A is in CFUs/mL, and this matrix is "
                                      "in Cells/mL; left out rather than converted")]


def test_a_network_derived_from_areas_cannot_be_converted():
    """L is a ratio of growth rates, so auc and max cannot produce it (#119). The package says which
    setting to change rather than converting the wrong quantity."""
    arcs = [dict(a, metric="auc") for a in PAIR]
    with pytest.raises(matrix.CannotConvert) as raised:
        matrix.coefficients(_net(arcs), RATES)
    assert "growth_rate" in str(raised.value) and "auc" in str(raised.value)


def test_the_readme_states_the_estimators_and_what_the_choice_moves():
    """#119: "The README states the rate method beside the growth rates". Karoline, 2026-10-06, then
    settled which: the rate is the reader's own estimator, the lag is always Baranyi's, and the README
    says what choosing another rate estimator would move.

    What it moves was corrected on 2026-10-06 (register item 34's amendment). This test asserted the
    earlier claim, that the estimator sets the timescale and not the equilibrium. That claim is wrong:
    the diagonal's r_i is a median over studies while each off-diagonal uses its own comparison's rates,
    x_j_star is the window the estimator fitted in, and the guards reject different curves, so the
    equilibrium belongs to the estimator. The requirement is unchanged and the sentence that meets it is
    not."""
    got, _ = _one(_net(PAIR), RATES)
    text = matrix.readme_from(got, _net(PAIR), RATES)
    assert "Growth rates: growth_rate:baranyi" in text
    assert "Lag: baranyi" in text
    assert "sets where this matrix settles as well as how fast a simulation" in text
    assert "nothing about where it settles" not in text

    easylinear = {k: {**v, "method": "growth_rate:easylinear:5"} for k, v in RATES.items()}
    other = matrix.readme_from(matrix.coefficients(_net(PAIR), easylinear), _net(PAIR), easylinear)
    assert "Growth rates: growth_rate:easylinear:5" in other and "Lag: baranyi" in other


def test_the_plain_adjacency_matrix_still_holds_the_log2_means():
    """What stays as it is (#119): only the package converts."""
    table = list(csv.reader(io.StringIO(matrix.matrix_csv(_net(PAIR)))))
    names = table[0][1:]
    row = table[1 + names.index("A")]
    assert float(row[1 + names.index("B")]) == pytest.approx(1.0)       # the log2 mean, unconverted
    assert float(row[1 + names.index("A")]) == 0.0                      # and the 0 diagonal
    obligate = _net(PAIR + [dict(_arc("c", "a", None), outcome="obligate", effect="facilitation")])
    # and a censored cell is NA there, not the stated extreme (#129, settled 2026-10-08)
    assert "NA" in matrix.matrix_csv(obligate)
    assert not any(cell in ("10", "-10") for row in matrix.matrix_csv(obligate).splitlines()[1:]
                   for cell in row.split(",")[1:])


def test_the_coefficients_reproduce_a_known_equilibrium():
    """A check a reader can repeat: with A_ii = -r_i/K_i, an organism on its own settles at K_i, since
    r_i + A_ii K_i = 0. Hand computed: A at 1e9 and B at 5e8 cells/mL, their own plateaus."""
    _, block = _one(_net(PAIR), RATES)
    for name, rate, capacity in (("A", 0.4, 1.0e9), ("B", 0.2, 5.0e8)):
        a_ii = _cell(block, name, name)
        assert -rate / a_ii == pytest.approx(capacity)
    assert math.isclose(_cell(block, "A", "A"), -4.0e-10, rel_tol=1e-12)


def test_the_readme_says_what_a_diverging_simulation_means_now():
    """Measured on study 7 while building this: with Baranyi rates, BH and RI are fitted as facilitating
    each other more than each limits itself, and miaSim returns NA. That is now a statement of the
    measurements, not a unit mismatch, so the README says so and does not offer scaling as the cure."""
    mutual = [_arc("b", "a", 3.0, x_j=1.0e8), _arc("a", "b", 3.0, x_j=1.0e8)]
    got, block = _one(_net(mutual), RATES)
    # each off-diagonal (0.4 * 7 / 1e8 = 2.8e-8) outweighs its own diagonal (-4e-10)
    assert _cell(block, "A", "B") > abs(_cell(block, "A", "A"))
    text = matrix.readme_from(got, _net(mutual), RATES)
    assert "can still grow without bound" in text and "A x = -r" in text
    assert "glv_scale" not in text


def test_the_readme_says_where_each_matrix_settles():
    """The package defines its own meaning as the solution of A x = -r and left the reader to solve it,
    so a matrix with no positive equilibrium shipped looking like any other (found 2026-10-06).

    PAIR gives A_AA = -0.4/1e9 = -4e-10, A_AB = (0.8 - 0.4)/2e8 = +2e-9, A_BB = -0.2/5e8 = -4e-10 and
    A_BA = (0.1 - 0.2)/4e8 = -2.5e-10. By hand, B's row gives x_A = 8e8 - 1.6 x_B, and A's row then gives
    2.64e-9 x_B = -0.08, so x_B = -3.03e7: B sits below zero, because A inhibits B just hard enough at
    A's own plateau to cancel B's rate. So this matrix settles nowhere with every organism above zero,
    and the README has to say so.
    """
    got, block = _one(_net(PAIR), RATES)
    assert block["not_above_zero"] == ["B"]
    assert block["equilibrium"][1] == pytest.approx(-3.0303e7, rel=1e-3)
    assert "NOWHERE WITH EVERY ORGANISM ABOVE ZERO" in matrix.readme_from(got, _net(PAIR), RATES)

    # a weaker inhibition of B by A does have a positive equilibrium, and then the README prints it:
    # A_BA = (0.15 - 0.2)/4e8 = -1.25e-10 gives x_A = 1.6e9 - 3.2 x_B, then 3.28e-9 x_B = 0.24, so
    # x_B = 7.317e7 and x_A = 1.366e9
    softer = [PAIR[0], {**PAIR[1], "metric_with": 0.15, "metric_without": 0.2}]
    other, block2 = _one(_net(softer), RATES)
    assert block2["not_above_zero"] == []
    assert block2["equilibrium"][0] == pytest.approx(1.3659e9, rel=1e-3)
    assert block2["equilibrium"][1] == pytest.approx(7.317e7, rel=1e-3)
    text = matrix.readme_from(other, _net(softer), RATES)
    assert "where it settles (the solution of A x = -r" in text
    assert "A 1.366e+09" in text and "B 7.317e+07" in text
