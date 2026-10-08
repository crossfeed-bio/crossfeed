"""The censored cell of the plain adjacency matrix, as a measured bound (#129).

Karoline, 2026-10-06: "what would be your suggestion to get rid of the ad-hoc value in the plain
adjacency matrix?", and then "go with the bound in #129 following your recommendation".

A pair is censored because the no-growth rule (#37) judged one side not to have grown: the geometric mean
of its rises, maximum over first point, stayed under `factor` (1.5 by default). That rule is a
measurement about that side, and it bounds the metric it could have had, so the cell holds a bound instead
of the stated +/-10:

    obligate   (the without-set did not grow):  at least  log2(metric_with)  - log2(factor * x0)
    abolished  (the with-set did not grow):     at most   log2(factor * x0)  - log2(metric_without)

Every number here is hand computed in the test that uses it.
"""
import math

import pytest
from test_growth_rates import A, B, _client, _co, _mono

from grownet import interaction, matrix
from grownet.derive import interactions_from_replicates
from grownet.mgrowthdb import records_to_network


def _flat(value, points=7, step=1.0):
    """A curve that never grows: the rule's rise is 0, far under the factor."""
    return [(i * step, value, None) for i in range(points)]


def _doubling(start=1.0e6, points=7, step=1.0):
    """A curve that doubles every hour, so its maximum is 64 times its start over six hours."""
    return [(i * step, start * 2 ** i, None) for i in range(points)]


def test_the_rule_bounds_the_metric_of_a_set_that_did_not_grow():
    """The number the bound rests on: a set whose rises stayed under the factor ended at most
    factor * x0. Flat at 1e6 with a factor of 1.5 gives a bound of 1.5e6 on `max`."""
    from grownet.growth import GrowthCurve, Replicate
    curve = GrowthCurve(species=A, times=[0.0, 1.0, 2.0, 3.0], values=[1.0e6] * 4, time_unit="h",
                        abundance_unit="Cells/mL")
    reps = [Replicate(curves=(curve,))]
    bound = interaction.no_growth_bound(reps, A, 3.0, "max", factor=1.5)
    assert bound["value"] == pytest.approx(1.5e6)
    assert bound["factor"] == 1.5 and "1.5" in bound["rule"]
    # the area under that bound over the window, for the metric that integrates
    area = interaction.no_growth_bound(reps, A, 3.0, "auc", factor=1.5)
    assert area["value"] == pytest.approx(1.5e6 * 3.0)
    # and a growth rate consistent with no growth over three hours: ln(1.5) / 3
    rate = interaction.no_growth_bound(reps, A, 3.0, "growth_rate:easylinear:5", factor=1.5)
    assert rate["value"] == pytest.approx(math.log(1.5) / 3.0)


def test_an_obligate_arc_carries_a_bound_instead_of_the_stated_extreme():
    """A grows only with B: its monoculture is flat at 1e6 and its co-culture doubles hourly to 6.4e7.
    With `max`, the co-culture's maximum is 6.4e7 and the bound on the monoculture is 1.5e6, so the cell
    is at least log2(6.4e7 / 1.5e6) = 5.415, not +10."""
    client = _client({(1, A): _flat(1.0e6), (2, A): _flat(1.0e6),
                      (3, A): _doubling(1.0e6), (3, B): _doubling(2.0e6),
                      (4, A): _doubling(1.0e6), (4, B): _doubling(2.0e6),
                      (5, B): _doubling(2.0e6), (6, B): _doubling(2.0e6)})
    exps = [_mono("E1", A, [(1, "r1"), (2, "r2")]), _mono("E2", B, [(5, "r1"), (6, "r2")]),
            _co("E3", A, B, [(3, "r1"), (4, "r2")])]
    records, _ = interactions_from_replicates(client, {"id": "S1"}, exps, "S1", method="max")
    arc = next(r for r in records if r["target_name"] == A and r["source_name"] == B)
    assert arc["outcome"] == "obligate" and arc["strength"] is None
    assert arc["strength_bound"] == pytest.approx(math.log2(6.4e7 / 1.5e6), abs=5e-4)   # rounded as
    # every strength is, to four decimals
    assert "no growth" in arc["bound_rule"] and "1.5" in arc["bound_rule"]

    # and the cell of the plain matrix is that bound, with nothing conventional left
    net = records_to_network(records)
    values, _ = matrix.cells(net)
    cell = values[(arc["target"], arc["source"])]
    assert cell == pytest.approx(math.log2(6.4e7 / 1.5e6), abs=5e-4)
    assert cell != matrix.EXTREME
    assert matrix.bounded_cells(net) == [(A, B, pytest.approx(cell))]


def test_a_bound_is_smaller_than_the_convention_it_replaces():
    """What was wrong with +/-10: as a log2 mean it is a thousandfold difference, past anything measured.
    The bound above is 5.4, and it is a statement about this comparison."""
    assert math.log2(6.4e7 / 1.5e6) < matrix.EXTREME


def test_an_older_network_without_a_bound_still_shows_its_censored_cells():
    """A file derived before this change carries no bound. Rather than dropping the arc to 0, which reads
    as no interaction, the cell falls back to the convention and the README names it."""
    arc = {"source": "b", "target": "a", "source_name": "B", "target_name": "A",
           "effect": "facilitation", "strength": None, "status": "present", "outcome": "obligate",
           "study_id": "S1", "metric": "max"}
    net = records_to_network([arc])
    values, _ = matrix.cells(net)
    assert values[("a", "b")] == matrix.EXTREME
    assert matrix.bounded_cells(net) == []
    assert matrix.by_convention(net) == [("A", "B", matrix.EXTREME)]


def test_the_report_says_the_number_is_a_bound_and_where_it_came_from():
    from grownet.report import report_text
    arc = {"source": "b", "target": "a", "source_name": "B", "target_name": "A",
           "effect": "facilitation", "strength": None, "strength_bound": 5.415,
           "bound_rule": "no growth without B: at most 1.5 times its own start over 6 h",
           "status": "present", "outcome": "obligate", "study_id": "S1", "metric": "max"}
    net = records_to_network([arc])
    result = {"network": net, "entries": [], "resolved": [], "unresolved": [], "studies": ["S1"],
              "skipped": [], "errors": [], "rates": {}, "hidden": {}, "absence": {"k": 1.0, "absent": 0}}
    text = report_text(result)
    assert "the cell is a bound: at least log2 +5.415" in text
    assert "no growth without B" in text


def test_a_bound_that_does_not_separate_the_effect_from_zero_leaves_the_cell_at_zero():
    """Measured on SMGDB00000013 with the area under the curve: a culture that did not grow still carries
    the area of its own inoculum, so the rule's bound on an area can exceed the growing side's own area.
    The arc then has no usable bound, its cell stays 0, and the reason says which metric bounds it
    tightly. The stated extreme does not come back for it."""
    from grownet.derive import bounded_strength
    c = {"outcome": "obligate", "with_log2": [math.log2(1.0e9)], "without_log2": [],
         "bound": {"value": 2.0e9, "factor": 1.5, "rule": "no growth: at most 1.5 times its own start"}}
    size, rule = bounded_strength(c)
    assert size is None and "does not bound this effect away from zero" in rule
    assert "growth rate" in rule

    arc = {"source": "b", "target": "a", "source_name": "B", "target_name": "A",
           "effect": "facilitation", "strength": None, "strength_bound": None, "bound_rule": rule,
           "status": "present", "outcome": "obligate", "study_id": "S1", "metric": "auc"}
    net = records_to_network([arc])
    values, _ = matrix.cells(net)
    assert values == {}                                    # no cell at all, rather than +10
    assert matrix.by_convention(net) == [] and matrix.bounded_cells(net) == []
