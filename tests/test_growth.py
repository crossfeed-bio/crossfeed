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


# ---- implausible spikes (#39) --------------------------------------------------------------------

from crossfeed.growth import spike  # noqa: E402

BH14 = (8.5e6, 2.4e7, 5.1e7, 7.1e7, 1.06e8, 5.264e13, 5.264e13, 4.8e8, 1.1e9, 1.4e9, 2.1e9, 2.9e9, 2.8e9)


def _series(values, species=A):
    return GrowthCurve(species, range(len(values)), values, "h", "Cells/mL")


def test_the_bh14_shape_is_flagged_with_its_time_points():
    found = spike(_series(BH14))
    assert found and found["ratio"] > 1000
    assert found["times"] == [5, 6]          # both identical extreme points, not only the first


def test_a_decline_after_a_peak_is_not_a_spike():
    # rises tenfold, then falls tenfold: no point jumps above both of its neighbours
    assert spike(_series((1e7, 1e8, 1e9, 1e9, 5e8, 2e8, 1e8))) is None


def test_a_clean_growth_curve_is_not_flagged():
    assert spike(_series((1e6, 2e6, 8e6, 3e7, 9e7, 1e8, 1.1e8))) is None


def test_factor_zero_switches_the_check_off():
    assert spike(_series(BH14), factor=0) is None


def test_a_jump_from_zero_is_left_to_the_no_growth_rule():
    assert spike(_series((0.0, 0.0, 0.0, 5.0))) is None
    assert spike(_series((0.0, 5.0, 0.0, 0.0))) is None         # a zero neighbour gives no scale


# SMGDB00000013 (CFU/mL over 288 h), which the earlier max/median statistic flagged (Karoline, on #62)
DIE_OFF = (3.5e7, 2.1e6, 2.9e5, 3.7e5, 4.7e4, 3.6e4, 1.9e4, 3.0e2, 1.0)        # Microbacterium alone
LATE_GROWTH = (1.2e7, 8.1e5, 5.7e5, 5.3e5, 3.0e5, 2.9e5, 2.2e7, 1.3e8, 2.8e8)  # Ochrobactrum with Comamonas


def test_a_die_off_and_late_growth_are_not_spikes():
    assert spike(_series(DIE_OFF)) is None          # the maximum is the inoculum, the first point
    assert spike(_series(LATE_GROWTH)) is None      # the maximum is the last point


def test_a_single_point_spike_and_the_largest_run_are_reported():
    # 1e11 against neighbours 1e6 and 2e6: ratio 1e11 / 2e6 = 5e4
    found = spike(_series((1e6, 1e11, 2e6, 4e6, 8e6)))
    assert found["times"] == [1] and found["ratio"] == pytest.approx(5e4)
    # a jump of 50 is below the default factor of 100 and above a factor of 10
    assert spike(_series((1e6, 5e7, 1e6, 1e6))) is None
    assert spike(_series((1e6, 5e7, 1e6, 1e6)), factor=10)["ratio"] == pytest.approx(50)


def test_a_run_of_three_is_not_a_spike():
    # three consecutive high points are a phase of the curve, not a spike
    assert spike(_series((1e6, 1e11, 1e11, 1e11, 1e6))) is None
