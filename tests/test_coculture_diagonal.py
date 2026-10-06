"""The diagonal from a co-culture plateau, and the media each matrix came from (#124 items 2 and 5).

Karoline, 2026-10-06: "complete #124". Item 2 asked whether a carrying capacity can come from somewhere
other than that study's own monoculture; item 5 asked whether to write one matrix per medium.

What this implements, with the reasons in the issue comment: the plateau balance already used for an
organism that grows only with a partner (#123) works for any organism, so an organism with a rate but no
certified monoculture plateau is fitted at its plateau beside its partners instead of being dropped; and
media stay together in one matrix per unit, with each matrix naming the media its own arcs came from,
since partitioning by medium would fragment the corpus into singletons while the second box already holds
a search to one environment.
"""
import pytest

from grownet import matrix
from grownet.mgrowthdb import records_to_network

METRIC = "growth_rate:easylinear:5"


def _arc(source, target, with_rate, without_rate, x_j=2.0e8, capacity=None, medium="WC", unit="Cells/mL"):
    return {"source": source, "target": target, "source_name": source.upper(),
            "target_name": target.upper(), "effect": "facilitation", "strength": 1.0, "status": "present",
            "outcome": "quantified", "study_id": "S1", "metric": METRIC, "evidence": "biculture",
            "medium": medium, "partner_abundance": x_j, "partner_abundance_unit": unit,
            "partner_abundance_n": 3, "metric_with": with_rate, "metric_without": without_rate,
            "target_capacity": capacity, "target_capacity_unit": unit if capacity else "",
            "target_capacity_n": 3 if capacity else 0}


def _rate(name, rate, capacity, unit="Cells/mL"):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"], "method": METRIC,
            "lag": 0.0, "lag_method": "baranyi", "capacity": capacity,
            "capacity_unit": unit if capacity else "", "capacity_n": 3 if capacity else 0}


def _cell(block, affected, actor):
    i, j = block["organisms"].index(affected), block["organisms"].index(actor)
    return block["matrix"][i][j]


def test_an_organism_with_no_monoculture_plateau_is_fitted_at_its_co_culture_plateau():
    """SMGDB00000004's B. hydrogenotrophica reaches no certified plateau alone, so #119 dropped it from
    the matrix. Its plateau beside its partner fits the same balance: with r_A = 0.4 /h, A_AB = (0.8 -
    0.4) / 2e8 = +2e-9, B at its own co-culture plateau of 4e8 and A at 3e8,
    A_AA = -(0.4 + 2e-9 * 4e8) / 3e8 = -(0.4 + 0.8) / 3e8 = -4e-9."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8)]
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(records_to_network(arcs), rates)
    (block,) = got["matrices"]
    assert block["organisms"] == ["A", "B"]
    assert _cell(block, "A", "B") == pytest.approx(2.0e-9)
    assert _cell(block, "A", "A") == pytest.approx(-4.0e-9)
    assert got["plateau_rows"] == [("A", "its co-culture plateau")]
    assert got["left_out"] == []
    text = matrix.readme_from(got, records_to_network(arcs), rates)
    assert "co-culture plateau" in text and "A" in text


def test_a_monoculture_plateau_is_still_preferred_when_there_is_one():
    """Nothing changes for an organism that settled alone: -r/K from its own monoculture."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(records_to_network(arcs), rates)
    (block,) = got["matrices"]
    assert _cell(block, "A", "A") == pytest.approx(-4.0e-10)      # -0.4 / 1e9
    assert got["plateau_rows"] == []


def test_a_plateau_fit_that_comes_out_positive_is_named_not_published():
    """A self-limitation at or above zero is not a limitation. It happens when the partners suppress the
    organism harder than its own rate at the plateau: A_AB = (0.05 - 0.4) / 2e8 = -1.75e-9, so with B at
    4e8 the balance gives -(0.4 - 0.7) / 3e8 = +1e-9, which is not a limitation, and A is named."""
    arcs = [_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),   # a strong inhibition
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8)]
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(records_to_network(arcs), rates)
    assert got["matrices"][0]["organisms"] == ["B"]
    assert any(name == "A" and "above zero" in why for name, why in got["left_out"])


def test_each_matrix_names_the_media_its_own_arcs_came_from():
    """Item 5: media stay in one matrix per unit, and the README says which media each matrix holds, so a
    reader sees the mixture without the package fragmenting into one matrix per medium."""
    arcs = [_arc("b", "a", 0.8, 0.4, medium="WC"),
            _arc("d", "c", 0.8, 0.4, medium="mMCB", unit="CFUs/mL")]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8),
             "c": _rate("C", 0.5, 1.0e8, "CFUs/mL"), "d": _rate("D", 0.5, 2.0e8, "CFUs/mL")}
    got = matrix.coefficients(records_to_network(arcs), rates)
    by_unit = {b["abundance_unit"]: b for b in got["matrices"]}
    assert by_unit["Cells/mL"]["media"] == ["WC"]
    assert by_unit["CFUs/mL"]["media"] == ["mMCB"]
    text = matrix.readme_from(got, records_to_network(arcs), rates)
    assert "in WC" in text and "in mMCB" in text
