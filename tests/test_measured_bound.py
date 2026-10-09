"""The censored cell of the plain adjacency matrix: `NA`, with the measured bound on the arc (#129).

Karoline, 2026-10-06: "what would be your suggestion to get rid of the ad-hoc value in the plain
adjacency matrix?", and then "go with the bound in #129 following your recommendation". Settled
2026-10-08, after the bounds were measured on the live corpus and 11 of 12 landed inside the range of the
quantified arcs: **"NA, bound on the arc"**. A matrix cell cannot say what kind of number it holds, so a
bound printed there is indistinguishable from a ratio, which is the objection that retired +/-10. The
bound travels on the arc, where it says it is a floor, and `bounded_cells` names the cells left `NA`.

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
    With `max`, the co-culture's maximum is 6.4e7 and the bound on the monoculture is 1.5e6, so the arc
    says at least log2(6.4e7 / 1.5e6) = 5.415 and its cell says `NA`, neither 5.415 nor +10."""
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

    # and the cell of the plain matrix holds no number: not the bound, and not the convention either
    net = records_to_network(records)
    values, _ = matrix.cells(net)
    assert values[(arc["target"], arc["source"])] is None
    assert matrix.bounded_cells(net) == [(A, B, pytest.approx(math.log2(6.4e7 / 1.5e6), abs=5e-4))]

    # what the CSV writes there, which is the file the decision is about: NA, which R reads as not a
    # number, and 0 nowhere on that row, since 0 would say no interaction
    csv = matrix.matrix_csv(net)
    header, *body = csv.splitlines()
    names = header.split(",")[1:]
    table = {line.split(",")[0]: line.split(",")[1:] for line in body}
    assert table[A][names.index(B)] == "NA"                       # the cell the decision is about
    assert table[B][names.index(A)] == "0"                        # and the other direction is still 0
    assert "10" not in table[A] and "5.415" not in table[A]       # neither the convention nor the bound


def test_a_bound_is_smaller_than_the_convention_it_replaces():
    """What was wrong with +/-10: as a log2 mean it is a thousandfold difference, past anything measured.
    The bound above is 5.4, and it is a statement about this comparison. It is also why the bound could
    not simply stay in the cell: at 5.4 it sorts among the quantified arcs instead of past all of them,
    so a reader cannot tell it from a ratio (#129, settled 2026-10-08)."""
    assert math.log2(6.4e7 / 1.5e6) < matrix.EXTREME


def test_an_older_network_without_a_bound_still_shows_its_censored_cells():
    """A file derived before this change carries no bound. Its cell is `NA` like every other censored
    cell, rather than 0, which would read as no interaction, or the old convention, which would read as a
    measurement. The listing names it with no bound to report."""
    arc = {"source": "b", "target": "a", "source_name": "B", "target_name": "A",
           "effect": "facilitation", "strength": None, "status": "present", "outcome": "obligate",
           "study_id": "S1", "metric": "max"}
    net = records_to_network([arc])
    values, _ = matrix.cells(net)
    assert values[("a", "b")] is None
    assert matrix.bounded_cells(net) == [("A", "B", None)]
    assert sorted(matrix.matrix_csv(net).splitlines()[1].split(",")[1:]) == ["0", "NA"]


def test_a_bound_without_an_outcome_that_produces_one_is_named_rather_than_counted():
    """The fifth shape (Craig's agent, #174). `interaction.py` attaches a bound only to an obligate or
    abolished comparison, so nothing derives this. Nothing refuses it either: `Edge.validate` checks the
    outcome against its vocabulary and never relates two fields, and both constructors that turn records
    into edges read `strength_bound` and `outcome` independently. So a supplied record or a loaded file
    can carry it.

    Before this, the two censorship predicates disagreed on it: the gLV path counted the arc and built a
    coefficient while the adjacency cell held a number instead of `NA`, so two outputs of one package
    disagreed about whether the pair was measured. Now both say no and the package says why.
    """
    arc = {"source": "b", "target": "a", "source_name": "B", "target_name": "A",
           "effect": "facilitation", "strength": None, "strength_bound": 5.415,
           "bound_rule": "no growth without B: at most 1.5 times its own start over 6 h",
           # the outcome a bound is never produced for, and one the vocabulary allows
           "status": "present", "outcome": "no_growth", "study_id": "S1", "metric": "max",
           "metric_with": 6.4e7, "metric_without": 0.0, "partner_abundance": 5.0e8,
           "partner_abundance_unit": "Cells/mL"}
    net = records_to_network([arc])
    assert net.edges[0].validate() == []                   # the format allows the shape
    assert matrix._censored(net.edges[0]) is False
    assert matrix._reports_an_extreme(net.edges[0]) is False
    # no cell and no NA: this arc says nothing about that pair
    values, _ = matrix.cells(net)
    assert values == {} and matrix.bounded_cells(net) == []

    # and the package names it rather than passing over it, which is the standard the capacity unit
    # invariant sets in the same file
    _, _, unfitted = matrix._pair_values(net)
    assert any("carries a bound" in why and "no_growth" in why for _pair, why in unfitted), unfitted


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
    assert "the cell is NA and the arc carries the bound: at least log2 +5.415" in text
    assert "no growth without B" in text


def test_a_bound_that_does_not_separate_the_effect_from_zero_leaves_the_cell_at_zero():
    """Measured on SMGDB00000013 with the area under the curve: a culture that did not grow still carries
    the area of its own inoculum, so the rule's bound on an area can exceed the growing side's own area.
    The arc then has no usable bound. Its cell is `NA`, where it used to fall through to 0, and the
    reason says which metric bounds it tightly. The stated extreme does not come back for it."""
    from grownet.derive import bounded_strength
    c = {"outcome": "obligate", "with_log2": [math.log2(1.0e9)], "without_log2": [],
         "bound": {"value": 2.0e9, "factor": 1.5, "rule": "no growth: at most 1.5 times its own start"}}
    size, rule = bounded_strength(c)
    assert size is None and "does not bound this effect away from zero" in rule
    assert "its cell is NA" in rule and "growth rate" in rule     # the rule says what the cell holds

    arc = {"source": "b", "target": "a", "source_name": "B", "target_name": "A",
           "effect": "facilitation", "strength": None, "strength_bound": None, "bound_rule": rule,
           "status": "present", "outcome": "obligate", "study_id": "S1", "metric": "auc"}
    net = records_to_network([arc])
    values, _ = matrix.cells(net)
    assert values == {("a", "b"): None}                    # NA, rather than +10 and rather than 0
    assert matrix.bounded_cells(net) == [("A", "B", None)]
    # and the report says why there is no number, which the cell cannot
    from grownet.report import report_text
    result = {"network": net, "entries": [], "resolved": [], "unresolved": [], "studies": ["S1"],
              "skipped": [], "errors": [], "rates": {}, "hidden": {}, "absence": {"k": 1.0, "absent": 0}}
    text = report_text(result)
    assert "the cell is NA" in text and "does not bound this effect away from zero" in text
