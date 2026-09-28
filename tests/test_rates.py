"""Growth rates (#41): easylinear as mGrowthDB computes it, and a guarded Baranyi fit, on curves whose
answer is known by construction."""
import math

import pytest

from crossfeed import rates
from crossfeed.growth import GrowthCurve, Replicate
from crossfeed.interaction import interaction_strength
from crossfeed.rates import RateUnavailable, baranyi, easylinear, method_name

T = [float(t) for t in range(13)]


def test_easylinear_gives_the_rate_of_an_exponential():
    # ln y = 0.5 t exactly, so every window has slope 0.5
    assert easylinear(T, [math.exp(0.5 * t) for t in T]) == pytest.approx(0.5)


def test_easylinear_takes_the_steepest_phase_of_lag_growth_and_plateau():
    # flat until t = 3, ln y rising 0.8 per hour until t = 8, flat after: the rate is the exponential phase's
    logs = [0.0 if t <= 3 else min(0.8 * (t - 3), 4.0) for t in T]
    assert easylinear(T, [math.exp(y) for y in logs]) == pytest.approx(0.8)


def test_easylinear_needs_one_point_more_than_its_window():
    with pytest.raises(RateUnavailable, match="needs 6"):
        easylinear(T[:5], [1, 2, 4, 8, 16])
    assert easylinear(T[:6], [1, 2, 4, 8, 16, 32]) == pytest.approx(math.log(2))
    # zeros carry no log and are left out before counting
    with pytest.raises(RateUnavailable, match="3 positive"):
        easylinear(T[:6], [0, 0, 0, 1, 2, 4])


def test_baranyi_recovers_the_rate_of_a_baranyi_curve():
    # y0 = 0, mu = 0.6, d = 5 (ymax - y0), lag = 2 h (h0 = mu * lag = 1.2): the fit returns mu
    logs = [rates._baranyi(t, 0.0, 0.6, 5.0, 1.2) for t in T]
    assert baranyi(T, [math.exp(y) for y in logs]) == pytest.approx(0.6, rel=0.02)


def test_baranyi_rejects_a_curve_the_model_does_not_describe():
    # a rise then a fall back to the start: no sigmoid fits it, so no rate is given, and the reason says why
    logs = [0, 1, 2, 3, 4, 4, 3, 2, 1, 0, 0, 0, 0]
    with pytest.raises(RateUnavailable, match="Baranyi fit rejected"):
        baranyi(T, [math.exp(y) for y in logs])


def test_method_names_record_the_rule():
    assert method_name() == "growth_rate:easylinear:5"
    assert method_name("easylinear", 7) == "growth_rate:easylinear:7"
    assert method_name("baranyi") == "growth_rate:baranyi"
    assert rates.feature("auc") is None
    with pytest.raises(ValueError):
        method_name("logistic")


def _curve(species, rate):
    return GrowthCurve(species, tuple(T), tuple(math.exp(rate * t) for t in T), "h", "CFU/mL")


def test_an_interaction_on_growth_rate_is_the_log2_ratio_of_the_rates():
    # A grows at 0.25/h alone and 0.5/h with B in both replicates: log2(0.5 / 0.25) = +1 exactly, sd 0
    mono_a = [Replicate([_curve("A", 0.25)], f"a{i}") for i in range(2)]
    mono_b = [Replicate([_curve("B", 0.3)], f"b{i}") for i in range(2)]
    co = [Replicate([_curve("A", 0.5), _curve("B", 0.3)], f"c{i}") for i in range(2)]
    r = interaction_strength(mono_a, mono_b, co, "A", "B", method="growth_rate:easylinear:5")
    assert r["species_a"]["mean"] == pytest.approx(1.0) and r["species_a"]["sd"] == pytest.approx(0.0)
    assert r["species_b"]["mean"] == pytest.approx(0.0)
    assert r["method"] == "growth_rate:easylinear:5"


def test_a_curve_without_a_rate_is_left_out_and_reported_not_read_as_no_growth():
    # one monoculture replicate falls after its peak: Baranyi gives it no rate, so the set keeps the other,
    # and the reason is reported; nothing is called obligate or abolished
    fall = GrowthCurve("A", tuple(T), tuple(math.exp(y) for y in [0, 1, 2, 3, 4, 4, 3, 2, 1, 0, 0, 0, 0]),
                       "h", "CFU/mL")
    mono_a = [Replicate([fall], "a0"), Replicate([_curve("A", 0.25)], "a1")]
    mono_b = [Replicate([_curve("B", 0.3)], f"b{i}") for i in range(2)]
    co = [Replicate([_curve("A", 0.5), _curve("B", 0.3)], f"c{i}") for i in range(2)]
    r = interaction_strength(mono_a, mono_b, co, "A", "B", method="growth_rate:baranyi")
    assert r["species_a"]["outcome"] == "quantified" and r["species_a"]["n_mono"] == 1
    assert any("no growth rate: Baranyi fit rejected" in reason for _, reason in r["skipped"])
