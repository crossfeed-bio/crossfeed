"""Tests for the interaction strength helper (synthetic replicate curves, hand-computed values)."""
import math

import pytest

from crossfeed.growth import GrowthCurve, Replicate
from crossfeed.interaction import interaction_strength

A = "Faecalibacterium prausnitzii"
B = "Blautia hydrogenotrophica"


def _curve(species, values, times=(0, 10)):
    return GrowthCurve(species, times, values, "h", "16S copies/mL")


def _example():
    # Two-point curves over 10 h, so the area under the curve is 5 * (v0 + v1).
    mono_a = [Replicate([_curve(A, (1, 1))], "a1"),              # auc 10, max 1
              Replicate([_curve(A, (1, 3))], "a2")]              # auc 20, max 3
    mono_b = [Replicate([_curve(B, (1, 1))], "b1"),              # auc 10, max 1
              Replicate([_curve(B, (3, 5))], "b2")]              # auc 40, max 5
    co = [Replicate([_curve(A, (1, 3)), _curve(B, (1, 1))], "c1"),      # A auc 20; B auc 10
          Replicate([_curve(A, (3, 5)), _curve(B, (1, 0))], "c2")]      # A auc 40; B auc 5
    return mono_a, mono_b, co


def test_auc_default_matches_hand_computed_values():
    r = interaction_strength(*_example(), A, B)
    assert r["method"] == "auc" and r["log"] == "log2" and r["window"] == (0.0, 10.0)
    # A: log2 co = log2 20, log2 40 (mean log2 20 + 0.5, sd sqrt(0.5));
    #    log2 mono = log2 10, log2 20 (mean log2 10 + 0.5, sd sqrt(0.5))
    #    strength = 1, sd = sqrt(0.5 + 0.5) = 1, se = sqrt(0.5 / 2 + 0.5 / 2) = sqrt(0.5)
    a = r["species_a"]
    assert a["species"] == A
    assert a["mean"] == pytest.approx(1.0)
    assert a["sd"] == pytest.approx(1.0)
    assert a["se"] == pytest.approx(math.sqrt(0.5))
    assert (a["n_co"], a["n_mono"]) == (2, 2)
    assert a["co_log2"] == pytest.approx([math.log2(20), math.log2(40)])
    assert a["mono_log2"] == pytest.approx([math.log2(10), math.log2(20)])
    # B: log2 co = log2 10, log2 5 (mean log2 10 - 0.5, sd sqrt(0.5));
    #    log2 mono = log2 10, log2 40 (mean log2 10 + 1, sd sqrt(2))
    #    strength = -1.5, sd = sqrt(0.5 + 2) = sqrt(2.5), se = sqrt(0.5 / 2 + 2 / 2) = sqrt(1.25)
    b = r["species_b"]
    assert b["mean"] == pytest.approx(-1.5)
    assert b["sd"] == pytest.approx(math.sqrt(2.5))
    assert b["se"] == pytest.approx(math.sqrt(1.25))
    assert r["skipped"] == []


def test_max_method():
    r = interaction_strength(*_example(), A, B, method="max")
    # A: co maxima 3 and 5, mono maxima 1 and 3 -> (log2 3 + log2 5) / 2 - (0 + log2 3) / 2 = log2(5) / 2
    assert r["species_a"]["mean"] == pytest.approx(math.log2(5) / 2)
    # B: co maxima 1 and 1, mono maxima 1 and 5 -> 0 - log2(5) / 2
    assert r["species_b"]["mean"] == pytest.approx(-math.log2(5) / 2)


def test_single_replicate_per_set_has_no_sd_or_se():
    mono_a, mono_b, co = _example()
    r = interaction_strength(mono_a[:1], mono_b[:1], co[:1], A, B)
    # A: log2(20) - log2(10) = 1
    assert r["species_a"]["mean"] == pytest.approx(1.0)
    assert r["species_a"]["sd"] is None and r["species_a"]["se"] is None


def test_one_replicate_in_a_set_still_gives_no_sd():
    mono_a, mono_b, co = _example()
    r = interaction_strength(mono_a, mono_b, co[:1], A, B)
    # A: log2(20) - mean(log2 10, log2 20) = 0.5; the co-culture set has no spread to estimate
    assert r["species_a"]["mean"] == pytest.approx(0.5)
    assert r["species_a"]["sd"] is None


def test_non_positive_replicate_is_skipped():
    mono_a, mono_b, co = _example()
    co = co + [Replicate([_curve(A, (1, 1)), _curve(B, (0, 0))], "c3")]
    r = interaction_strength(mono_a, mono_b, co, A, B)
    # B's c3 area is 0: dropped from B's co-culture set only; A keeps all three co-culture replicates
    assert r["species_b"]["n_co"] == 2
    assert r["species_b"]["mean"] == pytest.approx(-1.5)
    assert r["species_a"]["n_co"] == 3
    assert r["skipped"] == [(f"{B}: co-culture replicate c3", "non-positive auc (0)")]


def test_no_positive_replicate_in_a_set_raises():
    mono_a, _, co = _example()
    mono_b = [Replicate([_curve(B, (0, 0))], "b0")]
    with pytest.raises(ValueError, match=f"{B}: no monoculture replicate has a positive auc"):
        interaction_strength(mono_a, mono_b, co, A, B)


def test_curves_are_cut_to_the_shared_window():
    mono_a, mono_b, co = _example()
    # a longer co-culture curve for A: over 0 to 10 h it is identical to c1's (1, 3)
    co[0] = Replicate([_curve(A, (1, 3, 9), times=(0, 10, 20)), _curve(B, (1, 1))], "c1")
    r = interaction_strength(mono_a, mono_b, co, A, B)
    assert r["window"] == (0.0, 10.0)
    assert r["species_a"]["mean"] == pytest.approx(1.0)


def test_errors_for_method_start_time_and_units():
    mono_a, mono_b, co = _example()
    with pytest.raises(ValueError, match="unknown method 'rate'"):
        interaction_strength(mono_a, mono_b, co, A, B, method="rate")
    late = [Replicate([_curve(B, (1, 1), times=(2, 10))], "b1")]
    with pytest.raises(ValueError, match="start at different time points"):
        interaction_strength(mono_a, late, co, A, B)
    days = [Replicate([GrowthCurve(B, (0, 10), (1, 1), "d", "16S copies/mL")], "b1")]
    with pytest.raises(ValueError, match="mixed time units"):
        interaction_strength(mono_a, days, co, A, B)
