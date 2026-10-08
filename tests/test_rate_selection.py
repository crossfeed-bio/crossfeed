"""The third component of an arc's error: which monoculture set stage 1 was given (#155 item 1).

`_choose_monocultures` resolves a monoculture set per co-culture experiment, so one organism in one study
can enter two arcs with two different stage-1 rates. On SMGDB00000007 *Roseburia* enters one arc at 0.5091
and another at 0.6521, 17 per cent apart, and today each arc takes its own as if the other did not exist.

Craig's agent's recommendation on #155 item 1, which Karoline took on 2026-10-08 ("option 3's mechanism
with option 2's data"): widen the stage variance by the within-organism, within-study spread of those
selected rates. It is measured, it needs no number from the reader, and it moves `se`, `sd`, `p_value` and
the degrees of freedom only. `strength`, the effect and the status stay as fitted.

Every number below is computed by hand or from the identity the code documents.
"""
import math
import statistics

import pytest
from test_integrated import _named, _simulate

from grownet import integrated


def _fit(rate, selfs=-5.0e-10, coefficient=2.0e-10):
    """A noiseless two-organism study: three monoculture replicates and three co-cultures of A with B."""
    r = [rate, 0.3]
    A = [[selfs, coefficient], [0.0, -2.0e-9]]
    mono_times, mono_series = _simulate([rate], [[selfs]], [1.0e7])
    monos = [_named(["A"], mono_times, mono_series, f"m{k}") for k in range(3)]
    cos = []
    for k, start in enumerate((1.0e7, 1.1e7, 0.9e7)):
        times, series = _simulate(r, A, [start, 5.0e8])
        cos.append(_named(["A", "B"], times, series, f"c{k}"))
    return integrated.two_stage("A", monos, cos, ["A", "B"]), cos


def test_the_mean_strength_at_another_rate_is_hand_computable():
    """`_strength_mean_at` moves each coefficient by its own exact derivative and recomputes the strength
    at the new rate, which also sits in its own denominator.

    One replicate, by hand: A = 2e-10, dA/dr = 1e-9, level = 5e8, rate 0.4, asked at 0.45.

        moved    = 2e-10 + 1e-9 * (0.45 - 0.40) = 2.5e-10
        effect   = 2.5e-10 * 5e8 / 0.45         = 0.277777...
        strength = log2(1.277777...)            = 0.35364
    """
    rows = [(2.0e-10, (1.0e-9, 0.0), 5.0e8, 0.0)]
    got = integrated._strength_mean_at(rows, 0.40, 0.45)
    assert got == pytest.approx(math.log2(1 + 2.5e-10 * 5.0e8 / 0.45), rel=1e-12)
    assert round(got, 5) == 0.35364
    # at its own rate it is the unmoved coefficient's strength: log2(1 + 2e-10 * 5e8 / 0.4) = 0.32193
    assert round(integrated._strength_mean_at(rows, 0.40, 0.40), 5) == 0.32193
    # a replicate with no derivative gives nothing rather than a number from an assumption
    assert integrated._strength_mean_at([(2.0e-10, None, 5.0e8, 0.0)], 0.4, 0.45) is None


def test_the_component_enters_se_and_sd_and_leaves_the_estimate_alone():
    """With a spread given, `se` is the square root of three variances added and `sd` carries the same
    third part. The strength, which is the estimate, does not move."""
    got, cos = _fit(0.5)
    plain = integrated._arc_statistics(got, cos, "B")
    assert plain["se_rate_selection"] is None and plain["rate_selection_spread"] is None

    wide = integrated._arc_statistics(got, cos, "B", {"spread": 0.05, "n": 2})
    assert wide["rate_selection_spread"] == 0.05
    assert wide["se_rate_selection"] is not None and wide["se_rate_selection"] > 0
    assert wide["se"] == pytest.approx(math.sqrt(wide["se_replicates"] ** 2
                                                 + wide["se_rate_stage"] ** 2
                                                 + wide["se_rate_selection"] ** 2), rel=1e-9)
    # sd gains exactly the same variance, since both carry the stage
    assert wide["sd"] ** 2 - plain["sd"] ** 2 == pytest.approx(wide["se_rate_selection"] ** 2, rel=1e-9)
    # and the estimate is untouched
    assert wide["strength"] == plain["strength"]
    assert wide["n"] == plain["n"]
    # a wider spread is a wider component: the arc that rests on a less stable selection is tested less
    # confidently, which is the whole point
    wider = integrated._arc_statistics(got, cos, "B", {"spread": 0.10, "n": 2})
    assert wider["se_rate_selection"] > wide["se_rate_selection"]
    assert wider["se"] > wide["se"]


def test_a_spread_wider_than_the_rate_keeps_the_arm_that_exists():
    """A rate minus a spread at or below zero is no growth and has no strength, so that arm is dropped
    rather than clamped to something invented. The component is then the one-sided move."""
    got, cos = _fit(0.5)
    one_sided = integrated._arc_statistics(got, cos, "B", {"spread": 0.6, "n": 2})
    assert one_sided["se_rate_selection"] is not None and one_sided["se_rate_selection"] > 0


def _pending(records, fits):
    out = []
    for record, (got, cos) in zip(records, fits, strict=True):
        out.append({"record": record, "got": got, "reps": cos, "partner": "B", "target": "A",
                    "label": f"B -> A [{got['rate']:.3g}]"})
    return out


def _record(mismatch=None):
    return {"strength": 0.5, "effect": "facilitation", "status": "present", "sd": 1.0, "se": 1.0,
            "p_value": 0.5, "effect_over_sd": 0.5, "notes": [], "rate_mismatch_to_zero": mismatch}


def test_two_matched_sets_widen_every_arc_of_that_organism_and_say_so():
    """Two co-culture experiments, two monoculture sets, two fitted rates. The spread is their sample
    standard deviation, which for two values is their difference over the square root of two."""
    fits = [_fit(0.50), _fit(0.60)]
    records = [_record(), _record()]
    before = [dict(r) for r in records]
    integrated._widen_by_rate_selection(_pending(records, fits))

    rates = sorted(got["rate"] for got, _cos in fits)
    spread = statistics.stdev(rates)
    assert spread == pytest.approx(abs(rates[1] - rates[0]) / math.sqrt(2), rel=1e-12)
    for record, was in zip(records, before, strict=True):
        assert record["rate_selection_spread"] == pytest.approx(round(spread, 4))
        assert record["se_rate_selection"] > 0
        assert record["se"] > was["se"] or record["se"] != was["se"]
        assert record["p_value"] != was["p_value"]
        # the estimate and what the thresholds say about it are untouched
        assert record["strength"] == was["strength"] and record["effect"] == was["effect"]
        assert record["status"] == was["status"]
        # and the arc says which rates, how far apart, and what the number does not cover
        note = next(n for n in record["notes"] if "different monoculture set" in n)
        assert f"{rates[0]:.4g}" in note and f"{rates[1]:.4g}" in note
        assert "lower bound" in note and "never grown in" in note


def test_one_matched_set_leaves_the_arc_exactly_as_it_was():
    fits = [_fit(0.50)]
    records = [_record()]
    integrated._widen_by_rate_selection(_pending(records, fits))
    assert records[0] == _record()                      # not one field touched


def test_contradicting_arcs_say_so_only_when_they_took_nearly_the_same_rate():
    """Craig's agent's argument: two arcs of one organism that share a stage-1 estimate and still imply
    opposite mismatches cannot both be the rate being wrong, so for at least one of them the implied
    mismatch is partner-dependent growth. His own correction the same day withdrew the case whose two
    selected rates were 42 per cent apart, since arcs that far apart can carry two different errors. So
    the note is tied to the rates being close, and `CONTRADICTION_SPREAD` is where that line sits."""
    close = [_fit(0.50), _fit(0.52)]                    # about 3 per cent apart
    records = [_record(mismatch=0.3), _record(mismatch=-0.4)]
    integrated._widen_by_rate_selection(_pending(records, close))
    assert all(any("opposite sign" in n for n in r["notes"]) for r in records)
    assert all("partner" in next(n for n in r["notes"] if "opposite sign" in n) for r in records)

    far = [_fit(0.50), _fit(0.90)]                      # about 55 per cent apart
    records = [_record(mismatch=0.3), _record(mismatch=-0.4)]
    integrated._widen_by_rate_selection(_pending(records, far))
    assert not any(any("opposite sign" in n for n in r["notes"]) for r in records)
    assert all(any("different monoculture set" in n for n in r["notes"]) for r in records)

    # and agreeing arcs say nothing about a contradiction, however close their rates
    records = [_record(mismatch=0.3), _record(mismatch=0.4)]
    integrated._widen_by_rate_selection(_pending(records, close))
    assert not any(any("opposite sign" in n for n in r["notes"]) for r in records)
