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
    mono_b = [Replicate([_curve(B, (1, 1))], "b1")]              # auc 10, max 1
    co = [Replicate([_curve(A, (1, 3)), _curve(B, (1, 1))], "c1"),      # A auc 20; B auc 10
          Replicate([_curve(A, (3, 5)), _curve(B, (1, 0))], "c2")]      # A auc 40; B auc 5
    return mono_a, mono_b, co


def test_auc_default_matches_hand_computed_values():
    r = interaction_strength(*_example(), A, B)
    assert r["method"] == "auc" and r["log"] == "log2" and r["window"] == (0.0, 10.0)
    # A: c1/a1 = 2, c1/a2 = 1, c2/a1 = 4, c2/a2 = 2 -> log2: 1, 0, 2, 1
    assert r["species_a"]["values"] == pytest.approx([1, 0, 2, 1])
    assert r["species_a"]["mean"] == pytest.approx(1.0)
    assert r["species_a"]["sd"] == pytest.approx(math.sqrt(2 / 3))
    assert r["species_a"]["n"] == 4
    # B: c1/b1 = 1, c2/b1 = 0.5 -> log2: 0, -1
    assert r["species_b"]["mean"] == pytest.approx(-0.5)
    assert r["species_b"]["sd"] == pytest.approx(math.sqrt(0.5))
    assert r["species_b"]["n"] == 2
    assert r["skipped"] == []


def test_max_method():
    r = interaction_strength(*_example(), A, B, method="max")
    # A: c1 max 3, c2 max 5 against a1 max 1, a2 max 3
    expected = [math.log2(3), 0.0, math.log2(5), math.log2(5 / 3)]
    assert r["species_a"]["values"] == pytest.approx(expected)
    assert r["species_a"]["mean"] == pytest.approx(sum(expected) / 4)
    # B: co max 1 in both replicates against b1 max 1
    assert r["species_b"]["values"] == pytest.approx([0.0, 0.0])


def test_single_combination_has_no_sd():
    mono_a, mono_b, co = _example()
    r = interaction_strength(mono_a[:1], mono_b, co[:1], A, B)
    assert r["species_a"]["n"] == 1 and r["species_a"]["sd"] is None


def test_non_positive_property_is_skipped():
    mono_a, mono_b, co = _example()
    co = co + [Replicate([_curve(A, (1, 1)), _curve(B, (0, 0))], "c3")]
    r = interaction_strength(mono_a, mono_b, co, A, B)
    assert r["species_b"]["n"] == 2
    assert r["skipped"] == [(f"{B}: co-culture c3 / monoculture b1", "non-positive auc (co-culture 0, monoculture 10)")]


def test_no_positive_combination_raises():
    mono_a, _, co = _example()
    mono_b = [Replicate([_curve(B, (0, 0))], "b0")]
    with pytest.raises(ValueError, match="no replicate combination has a positive auc"):
        interaction_strength(mono_a, mono_b, co, A, B)


def test_curves_are_cut_to_the_shared_window():
    mono_a, mono_b, co = _example()
    # a longer co-culture curve for A: over 0 to 10 h it is identical to c1's (1, 3)
    co[0] = Replicate([_curve(A, (1, 3, 9), times=(0, 10, 20)), _curve(B, (1, 1))], "c1")
    r = interaction_strength(mono_a, mono_b, co, A, B)
    assert r["window"] == (0.0, 10.0)
    assert r["species_a"]["values"] == pytest.approx([1, 0, 2, 1])


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
