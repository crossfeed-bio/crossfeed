"""Coefficients from absolute rates, which is what keeps an obligate pair (#123).

Karoline, 2026-10-06, asked: "Do we keep obligates despite the lack of a floor? If not, how can we keep
them?", and then "yes, please go ahead with #123". The answer in the issue: the formula she settled,

    A_ij = r_i (2^L - 1) / x_j_star      with 2^L = (i's rate with j) / (i's rate without j)

is algebraically `(r_with - r_without) / x_j_star`, and that form is defined where the ratio is not. An
obligate pair has `r_without = 0`, an abolished one `r_with = 0`, and an obligate organism's own row
becomes `r_i = 0` with its diagonal from the co-culture plateau.

Every number here is hand computed in the test that uses it.
"""
import csv
import io
import zipfile

import pytest

from grownet import matrix
from grownet.mgrowthdb import records_to_network

RATE_METRIC = "growth_rate:easylinear:5"


def _arc(source, target, with_rate, without_rate, x_j=2.0e8, outcome="quantified", strength=0.0,
         unit="Cells/mL", capacity=None, **extra):
    """One biculture arc carrying what #123 adds: the target's own rate in each set, and its plateau in
    the co-culture."""
    record = {"source": source, "target": target, "source_name": source.upper(),
              "target_name": target.upper(), "effect": "facilitation" if with_rate >= without_rate
              else "inhibition", "strength": strength, "status": "present", "outcome": outcome,
              "study_id": "S1", "metric": RATE_METRIC, "evidence": "biculture", "medium": "WC",
              "partner_abundance": x_j, "partner_abundance_unit": unit, "partner_abundance_n": 3,
              "metric_with": with_rate, "metric_without": without_rate, "metric_unit": "1/h",
              "target_capacity": capacity, "target_capacity_unit": unit if capacity else "",
              "target_capacity_n": 3 if capacity else 0}
    return {**record, **extra}


def _rate(name, rate, capacity, unit="Cells/mL"):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"], "method": RATE_METRIC,
            "lag": 0.0, "lag_method": "baranyi", "capacity": capacity, "capacity_unit": unit,
            "capacity_n": 3}


def _net(arcs):
    return records_to_network(arcs, meta={"tool_version": "9.9.9", "absence": {"k": 1.0}})


def _cell(block, affected, actor):
    i, j = block["organisms"].index(affected), block["organisms"].index(actor)
    return block["matrix"][i][j]


# ---- the difference form ---------------------------------------------------------------------------

def test_an_off_diagonal_cell_is_the_difference_of_the_two_rates_over_the_partners_abundance():
    """A grows at 0.8 /h with B and 0.4 /h without it, and B averages 2e8 over A's window, so
    A_AB = (0.8 - 0.4) / 2e8 = +2e-9. The same number the ratio form gave when r_i was this arc's own
    without-set rate, and now it always is."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(_net(arcs), rates)
    (block,) = got["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(2.0e-9)
    assert _cell(block, "A", "A") == pytest.approx(-4.0e-10)      # -r_i / K_i, unchanged
    assert got["from_absolute_rates"] is True


def test_an_inhibiting_partner_gives_a_negative_cell():
    """A grows at 0.1 /h with B and 0.4 /h without, so A_AB = (0.1 - 0.4) / 2e8 = -1.5e-9."""
    arcs = [_arc("b", "a", 0.1, 0.4, x_j=2.0e8, strength=-2.0)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    (block,) = matrix.coefficients(_net(arcs), rates)["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(-1.5e-9)


def test_the_arcs_own_rates_are_used_not_a_median_over_studies():
    """What the difference form fixes: the cell no longer mixes this experiment's ratio with a rate
    averaged over every study. A's reported rate is 0.2 /h here while this comparison measured 0.4
    without B, and the cell uses 0.4: (0.8 - 0.4) / 2e8 = 2e-9, not (0.8 - 0.2) / 2e8."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0)]
    rates = {"a": _rate("A", 0.2, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    (block,) = matrix.coefficients(_net(arcs), rates)["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(2.0e-9)
    assert _cell(block, "A", "A") == pytest.approx(-0.2 / 1.0e9)   # the diagonal still uses the median


def test_arcs_of_one_pair_merge_by_the_median_of_their_coefficients():
    """Karoline's merge rule (register item 14) on the converted numbers: two conditions give +2e-9 and
    +4e-9, so the cell is their median, +3e-9."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0, condition="one"),
            _arc("b", "a", 1.2, 0.4, x_j=2.0e8, strength=1.6, condition="two")]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    (block,) = matrix.coefficients(_net(arcs), rates)["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(3.0e-9)


def test_arcs_that_disagree_in_sign_are_still_left_at_zero_and_named():
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0, condition="one"),
            _arc("b", "a", 0.1, 0.4, x_j=2.0e8, strength=-2.0, condition="two")]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(_net(arcs), rates)
    (block,) = got["matrices"]
    assert _cell(block, "A", "B") == 0.0
    assert block["conflicts"] == [("A", "B")]


# ---- the censored pairs stop being censored --------------------------------------------------------

def test_an_obligate_pair_is_a_measurement_not_a_floor():
    """A does not grow without B, so r_without = 0 and A_AB = 0.8 / 2e8 = +4e-9. No floor, no stated
    extreme, and nothing taken from another pair of the run."""
    arcs = [_arc("b", "a", 0.8, 0.0, x_j=2.0e8, outcome="obligate", strength=None, capacity=3.0e8)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(_net(arcs), rates)
    (block,) = got["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(4.0e-9)
    assert got["floors"] == []                     # the floor of #119 is gone from the package
    text = matrix.readme_from(got, _net(arcs), rates)
    assert "FLOORS, NOT MEASUREMENTS" not in text         # the section of #119 is gone
    assert "no floor and no stated extreme enters this package" in text
    assert "B on A" in text.split("CELLS FROM A COMPARISON WHERE ONE SIDE DID NOT GROW")[1]


def test_an_abolished_pair_is_the_negative_of_the_rate_it_lost():
    """A grows only without B, so r_with = 0 and A_AB = (0 - 0.4) / 2e8 = -2e-9."""
    arcs = [_arc("b", "a", 0.0, 0.4, x_j=2.0e8, outcome="abolished", strength=None, capacity=3.0e8)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    (block,) = matrix.coefficients(_net(arcs), rates)["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(-2.0e-9)


def test_an_obligate_organism_gets_a_whole_row_from_the_co_culture():
    """What a gLV model means by obligate: the organism cannot grow alone, so r_i = 0, and it is held up
    by its partner. A has no monoculture rate at all. Hand computed: A_AB = 0.8 / 2e8 = +4e-9, and at the
    co-culture plateau 0 = 0 + A_AA x_A* + A_AB x_B*, with A at 3e8 and B at 4e8 (its own plateau there),
    so A_AA = -4e-9 * 4e8 / 3e8 = -5.333e-9."""
    arcs = [_arc("b", "a", 0.8, 0.0, x_j=2.0e8, outcome="obligate", strength=None, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, strength=0.585, capacity=4.0e8)]
    rates = {"b": _rate("B", 0.2, 5.0e8)}          # A has no monoculture rate and no capacity
    got = matrix.coefficients(_net(arcs), rates)
    (block,) = got["matrices"]
    assert "A" in block["organisms"] and "B" in block["organisms"]
    assert _cell(block, "A", "B") == pytest.approx(4.0e-9)
    assert _cell(block, "A", "A") == pytest.approx(-5.333e-9, rel=1e-3)
    assert got["obligate_rows"] == [("A", "B")]
    assert got["left_out"] == []
    # the rate of such an organism is zero by measurement, and the rates file says so
    text = matrix.readme_from(got, _net(arcs), rates)
    assert "grows only with" in text and "A" in text


def test_an_obligate_organism_without_a_co_culture_plateau_is_still_named():
    """No plateau, no diagonal: the organism leaves the matrix with the reason, as before."""
    arcs = [_arc("b", "a", 0.8, 0.0, x_j=2.0e8, outcome="obligate", strength=None, capacity=None),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, strength=0.585, capacity=4.0e8)]
    rates = {"b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(_net(arcs), rates)
    assert got["matrices"][0]["organisms"] == ["B"]
    assert any(name == "A" and "plateau" in why for name, why in got["left_out"])


def test_the_plain_adjacency_matrix_still_holds_the_log2_means_and_the_extremes():
    """What stays as it is: only the package converts (#119, #123)."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0),
            _arc("b", "c", 0.8, 0.0, x_j=2.0e8, outcome="obligate", strength=None)]
    table = list(csv.reader(io.StringIO(matrix.matrix_csv(_net(arcs)))))
    names = table[0][1:]
    assert float(table[1 + names.index("A")][1 + names.index("B")]) == pytest.approx(1.0)
    assert float(table[1 + names.index("C")][1 + names.index("B")]) == matrix.EXTREME


def test_the_package_says_which_rates_each_cell_came_from():
    """A reader has to be able to rebuild a cell: the README names the form and the report carries both
    rates behind every arc."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    net = _net(arcs)
    with zipfile.ZipFile(io.BytesIO(matrix.glv_package(net, rates))) as archive:
        readme = archive.read("README.txt").decode()
    assert "(r_with - r_without) / x_j" in readme
    assert "behind every arc are in the report" in readme and "rebuilt by hand" in readme


def test_a_network_saved_before_this_change_still_converts_through_the_ratio():
    """A file derived by 0.2.0 carries the log2 ratio and no absolute rates. Rather than refusing it, the
    package falls back to r_i (2^L - 1) / x_j with the reported rate, 0.4 * (2 - 1) / 2e8 = +2e-9 here,
    and the README names the cells that came that way."""
    old = _arc("b", "a", 0.8, 0.4, x_j=2.0e8, strength=1.0)
    for field in ("metric_with", "metric_without", "target_capacity", "target_capacity_unit",
                  "target_capacity_n"):
        old.pop(field)
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(_net([old]), rates)
    (block,) = got["matrices"]
    assert _cell(block, "A", "B") == pytest.approx(2.0e-9)
    assert got["from_absolute_rates"] is False and got["from_the_ratio"] == [("A", "B")]
    assert "CELLS TAKEN FROM THE LOG2 RATIO" in matrix.readme_from(got, _net([old]), rates)
