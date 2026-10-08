"""The gLV payload as fitted coefficients (#120).

The zip has held coefficients since #119 and #123 while this route still carried the old effect-size
matrix with its -1 diagonal and its stated extremes, so a reader got one thing from the page and another
from R. This is the same numbers on both routes, which is what #120 is for.

The format moves to `grownet.glv/v1`, because the fields change meaning: `matrices` replaces
`interactions`, one per abundance unit, since nothing is converted between units.
"""
import pytest

from grownet import matrix
from grownet.mgrowthdb import records_to_network

METRIC = "growth_rate:easylinear:5"


def _arc(source, target, with_rate, without_rate, x_j=2.0e8, unit="Cells/mL", outcome="quantified",
         strength=1.0, **extra):
    return {"source": source, "target": target, "source_name": source.upper(),
            "target_name": target.upper(), "effect": "facilitation", "strength": strength,
            "status": "present", "outcome": outcome, "study_id": "S1", "metric": METRIC,
            "evidence": "biculture", "medium": "WC", "partner_abundance": x_j,
            "partner_abundance_unit": unit, "partner_abundance_n": 3, "metric_with": with_rate,
            "metric_without": without_rate, "target_capacity": 3.0e8, "target_capacity_unit": unit,
            "target_capacity_n": 3, **extra}


def _rate(name, rate, capacity, unit="Cells/mL"):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"], "method": METRIC,
            "lag": 0.5, "lag_method": "baranyi", "capacity": capacity, "capacity_unit": unit,
            "capacity_n": 3, "per_study": {"S1": rate}}


def _net(arcs):
    return records_to_network(arcs, meta={"tool_version": "9.9.9", "absence": {"k": 1.0},
                                          "source_db": "mGrowthDB (live)"})


PAIR = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8), _arc("a", "b", 0.1, 0.2, x_j=4.0e8, strength=-1.0)]
RATES = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}


def test_the_payload_carries_the_coefficients_the_zip_holds():
    """The same numbers as the package: A_AB = (0.8 - 0.4) / 2e8 = +2e-9 and the fitted diagonal
    -0.4 / 1e9 = -4e-10, in 1/(h x Cells/mL)."""
    payload = matrix.glv_payload(_net(PAIR), RATES)
    assert payload["format"] == "grownet.glv/v1"
    (block,) = payload["matrices"]
    assert block["organisms"] == ["A", "B"]
    assert block["abundance_unit"] == "Cells/mL" and block["unit"] == "1/(h x Cells/mL)"
    cell = {(i, j): block["interactions"][i][j] for i in range(2) for j in range(2)}
    assert cell[(0, 1)] == pytest.approx(2.0e-9)          # B on A, rows affected
    assert cell[(0, 0)] == pytest.approx(-4.0e-10)        # the fitted diagonal
    assert "media" in block and block["media"] == ["WC"]


def test_one_matrix_per_abundance_unit_travels_too():
    arcs = PAIR + [_arc("d", "c", 0.8, 0.4, x_j=1.0e7, unit="CFUs/mL")]
    rates = {**RATES, "c": _rate("C", 0.5, 1.0e8, "CFUs/mL"), "d": _rate("D", 0.5, 2.0e8, "CFUs/mL")}
    payload = matrix.glv_payload(_net(arcs), rates)
    assert sorted(b["abundance_unit"] for b in payload["matrices"]) == ["CFUs/mL", "Cells/mL"]
    assert payload["caveats"]["abundance_units"] == ["CFUs/mL", "Cells/mL"]
    assert "never converted" in payload["caveats"]["units"]


def test_the_rates_travel_with_what_a_coefficient_is_made_of():
    detail = matrix.glv_payload(_net(PAIR), RATES)["growth_rate_detail"]
    first = next(d for d in detail if d["organism"] == "A")
    assert first["rate"] == 0.4 and first["carrying_capacity"] == 1.0e9
    assert first["lag"] == 0.5 and first["lag_method"] == "baranyi"
    assert first["method"] == METRIC


def test_the_caveats_say_what_is_a_measurement_and_what_is_not():
    """No stated extreme and no conventional diagonal is left, so the caveats are about what could not be
    fitted and about the bounds a censored comparison gives."""
    censored = _arc("c", "a", 0.8, 0.0, outcome="obligate", strength=None)
    arcs = PAIR + [censored]
    rates = {**RATES, "c": _rate("C", 0.5, 1.0e8)}
    caveats = matrix.glv_payload(_net(arcs), rates)["caveats"]
    assert caveats["censored_cells"] == [{"affected": "A", "actor": "C"}]
    assert "grew only with the actor, or only without it" in caveats["censored"]
    assert caveats["diagonal"] == "fitted: -r_i / K_i" or "fitted" in caveats["diagonal"]
    assert "extreme" not in caveats
    assert caveats["absence_k"] == 1.0 and caveats["media"] == ["WC"]
    assert "A x = -r" in caveats["unbounded"]
    assert caveats["left_out"] == [] and caveats["pairs_left_out"] == []


def test_an_organism_that_could_not_be_fitted_is_named_in_the_payload():
    rates = {"a": _rate("A", 0.4, 1.0e9)}            # B has no rate at all
    bare = [dict(arc, target_capacity=None, target_capacity_unit="", target_capacity_n=0)
            for arc in PAIR]
    caveats = matrix.glv_payload(_net(bare), rates)["caveats"]
    assert [name for name, _ in caveats["left_out"]] == ["B"]
    assert caveats["without_a_rate"] == ["B"]


def test_the_readme_travels_so_neither_route_loses_what_the_other_carries():
    payload = matrix.glv_payload(_net(PAIR), RATES)
    assert "THE COEFFICIENTS" in payload["readme"]
    assert "(r_with - r_without) / x_j" in payload["readme"]
