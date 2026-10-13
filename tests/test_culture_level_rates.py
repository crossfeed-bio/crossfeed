"""Rates from culture-level counts of a monoculture (#140) and no pooling across starting densities (#81 b).

Karoline: "yes to #140 with option 1" (2026-10-07), "Counts only" (2026-10-12), and on #81 "I'd also pick
b)" (2026-10-12): a monoculture measured only as a whole culture gives its rate and lag from a plate count
or flow cytometry, never from optical density and never a capacity; and a rate is not pooled across
measured starting densities more than 10 times apart.
"""
import math

from grownet import derive
from grownet.adapter import culture_trace_replicates
from grownet.rates import RateUnavailable, baranyi_fit

STRAIN = "Escherichia coli LF82"


def _logistic(start, rate=0.5, top=1e9, n=40):
    """A logistic curve sampled every hour: a rate, a lag-free start and a plateau."""
    return [(float(t), top / (1 + (top / start - 1) * math.exp(-rate * t)), None) for t in range(n)]


class CultureClient:
    """Monoculture experiments whose bioreplicates carry only culture-level contexts."""

    def __init__(self, techniques_by_rep, starts=None):
        self.techniques_by_rep, self.starts = techniques_by_rep, starts or {}

    def get_bioreplicate(self, rid):
        return {"id": rid, "name": rid, "isAverage": False, "measurementTimeUnits": "h",
                "measurementContexts": [
                    {"id": f"{rid}/{t}/{i}", "techniqueType": t,
                     "techniqueUnits": {"plates": "CFUs/mL", "fc": "Cells/mL"}.get(t, ""),
                     "subject": {"type": "bioreplicate"}}
                    for i, t in enumerate(self.techniques_by_rep[rid])]}

    def get_measurement_series(self, cid):
        rid, technique, _ = cid.split("/")
        return _logistic(self.starts.get(rid, 1e5)) if technique != "ph" else [(t, 7.0, None) for t in range(16)]


def _exp(reps, name="mono"):
    return {"id": name, "name": name, "cultivationMode": "batch", "communityStrains": [{"name": STRAIN, "NCBId": 1}],
            "bioreplicates": [{"id": r, "name": r} for r in reps]}


def test_a_count_is_taken_and_optical_density_never():
    client = CultureClient({"r1": ["od", "fc", "ph"], "r2": ["od", "ph"], "r3": ["plates", "fc"],
                            "r4": ["fc", "fc"]})
    reps, skipped = culture_trace_replicates(client, _exp(["r1", "r2", "r3", "r4"]), STRAIN)
    assert [(r.name, r.curve(STRAIN).technique) for r in reps] == \
        [("r1", "culture-level fc"), ("r3", "culture-level plates")]
    reasons = dict(skipped)
    assert "no single culture-level count" in reasons["mono: r2"], "OD alone gives nothing"
    assert "no single culture-level count" in reasons["mono: r4"], "two counts and nothing says which"


def test_the_rate_and_lag_come_from_the_count_and_the_capacity_never(monkeypatch):
    client = CultureClient({"r1": ["fc"], "r2": ["fc"], "r3": ["fc"]})
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], [("mono: r1", "no usable")]))
    found, _ = derive.monoculture_rates(client, [_exp(["r1", "r2", "r3"])], identities={})
    (entry,) = found.values()
    assert len(entry["values"]) == 3 and abs(entry["values"][0] - 0.5) < 0.1
    assert entry["sources"] == {"culture-level fc": 3}
    assert entry["capacity_by_medium"] == {}, "a plateau is never read from a culture-level trace"
    # the curve DOES reach a plateau, so the empty capacity is the guard and not the data (found in review:
    # a 16-point curve never reached stationary, so deleting the guard left this green)
    from grownet.growth import GrowthCurve, reached_stationary
    points = _logistic(1e5)
    curve = GrowthCurve(STRAIN, [t for t, _, _ in points], [v for _, v, _ in points], "h", "Cells/mL")
    assert reached_stationary(curve, curve.times[-1]) is True
    merged = derive.merge_rates([("S9", found)])
    (rate,) = merged.values()
    assert rate["rate_sources"] == {"culture-level fc": 3} and rate["capacity"] is None


def test_a_rate_is_not_pooled_across_starts_more_than_ten_times_apart(monkeypatch):
    """SMGDB00000014's Comamonas monocultures start from 1e4 to 1.01e6 CFU/mL, 101 times apart, live."""
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], []))
    wide = CultureClient({"a": ["plates"], "b": ["plates"]}, starts={"a": 1e4, "b": 1.01e6})
    found, skipped = derive.monoculture_rates(wide, [_exp(["a", "b"])], identities={})
    assert found == {} and any("101 times apart" in why for _, why in skipped), skipped
    near = CultureClient({"a": ["plates"], "b": ["plates"]}, starts={"a": 1e5, "b": 9e5})
    found, skipped = derive.monoculture_rates(near, [_exp(["a", "b"])], identities={})
    assert len(next(iter(found.values()))["values"]) == 2, "nine times apart is still one set"


def test_a_baranyi_start_that_runs_off_is_a_rejected_fit_not_a_crash():
    """First met on SMGDB00000025's optical densities: math.exp raised OverflowError on a start's log-rate."""
    import grownet.rates as rates
    original = rates._fit_once
    try:
        rates._fit_once = lambda xs, ys, start: ([start[0], 1e6, start[2], start[3]], 0.0)
        times = [float(t) for t in range(12)]
        values = [math.exp(0.3 * t) for t in times]
        import pytest
        with pytest.raises(RateUnavailable):
            baranyi_fit(times, values)
    finally:
        rates._fit_once = original
