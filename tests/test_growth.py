"""Tests for growth curves and the replicate set checks (synthetic curves, no network)."""
import pytest

from crossfeed.growth import GrowthCurve, Replicate, check_replicate_sets, curve_features, shared_window

A = "Faecalibacterium prausnitzii"
B = "Blautia hydrogenotrophica"


def _curve(species, values=(0.1, 0.4, 0.8), times=(0, 12, 24), time_unit="h", abundance_unit="OD600"):
    return GrowthCurve(species, times, values, time_unit, abundance_unit)


def _sets(**co_kwargs):
    mono_a = [Replicate([_curve(A)], "a1"), Replicate([_curve(A)], "a2")]
    mono_b = [Replicate([_curve(B)], "b1")]
    co = [Replicate([_curve(A), _curve(B, **co_kwargs)], "c1")]
    return mono_a, mono_b, co


def test_valid_sets_pass():
    check_replicate_sets(*_sets(), A, B)


@pytest.mark.parametrize("kwargs, message", [
    ({"times": (0, 12)}, "2 time points but 3 values"),
    ({"times": (0,), "values": (0.1,)}, "at least two time points"),
    ({"times": (0, 12, 12)}, "strictly increasing"),
    ({"time_unit": ""}, "abundance unit are required"),
])
def test_curve_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        _curve(A, **kwargs)


def test_replicate_rejects_duplicate_species():
    with pytest.raises(ValueError, match="more than one curve"):
        Replicate([_curve(A), _curve(A)], "dup")


def test_mixed_time_units_raise():
    with pytest.raises(ValueError, match=r"mixed time units.*'d': co-culture replicate c1, " + B):
        check_replicate_sets(*_sets(time_unit="d"), A, B)


def test_mixed_abundance_units_raise():
    with pytest.raises(ValueError, match="mixed abundance units"):
        check_replicate_sets(*_sets(abundance_unit="CFU/mL"), A, B)


def test_co_culture_missing_a_species_raises():
    mono_a, mono_b, _ = _sets()
    co = [Replicate([_curve(A)], "c1")]
    with pytest.raises(ValueError, match="co-culture replicate c1 holds species"):
        check_replicate_sets(mono_a, mono_b, co, A, B)


def test_wrong_species_in_mono_set_raises():
    mono_a, mono_b, co = _sets()
    with pytest.raises(ValueError, match="mono A replicate b1"):
        check_replicate_sets(mono_b, mono_b, co, A, B)


def test_empty_set_and_same_species_raise():
    mono_a, mono_b, co = _sets()
    with pytest.raises(ValueError, match="no mono B replicates"):
        check_replicate_sets(mono_a, [], co, A, B)
    with pytest.raises(ValueError, match="must differ"):
        check_replicate_sets(mono_a, mono_a, co, A, A)


def test_features_whole_curve():
    # trapezoids: 12 * (0.1 + 0.4) / 2 + 12 * (0.4 + 0.8) / 2 = 3.0 + 7.2
    f = curve_features(_curve(A))
    assert f["auc"] == pytest.approx(10.2)
    assert f["max"] == pytest.approx(0.8)


def test_features_cut_between_points_interpolates():
    # at t = 18 the interpolated abundance is 0.6: 3.0 + 6 * (0.4 + 0.6) / 2
    f = curve_features(_curve(A), end=18)
    assert f["auc"] == pytest.approx(6.0)
    assert f["max"] == pytest.approx(0.6)


def test_features_cut_on_a_point_and_peak_before_end():
    f = curve_features(_curve(A, values=(0.1, 0.9, 0.5)), end=12)
    assert f["auc"] == pytest.approx(6.0)
    assert f["max"] == pytest.approx(0.9)
    assert curve_features(_curve(A, values=(0.1, 0.9, 0.5)))["max"] == pytest.approx(0.9)


def test_features_window_outside_curve_raises():
    with pytest.raises(ValueError, match="outside the curve"):
        curve_features(_curve(A), end=30)


def test_shared_window_uses_earliest_end():
    assert shared_window([_curve(A), _curve(B, times=(0, 6, 18))]) == (0.0, 18.0)


def test_shared_window_different_starts_raise():
    with pytest.raises(ValueError, match="start at different time points"):
        shared_window([_curve(A), _curve(B, times=(1, 12, 24))])
