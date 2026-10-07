"""The quantities a gLV coefficient is made of (#118), on hand-built curves.

Karoline's decision on #116: the gLV matrix stops using conventions, so `A_ii = -r_i / K_i` needs the
monoculture carrying capacity, and `A_ij = r_i (2^L - 1) / x_j_star` needs the partner's abundance over
the window the target's rate was fitted in ("the mean over the target's rate window"). Baranyi's lag comes
with them, since the integrated form starts there and the rate estimators disagree without it.

This task only adds fields: nothing an arc already said changes.
"""
import math

import pytest
from test_growth_rates import A, _client, _mono  # the fake mGrowthDB API of the rate tests

from grownet import rates
from grownet.derive import merge_rates, monoculture_rates, partner_abundance
from grownet.growth import GrowthCurve, Replicate, mean_over

START = math.log(1.0e6)      # the Baranyi model's y0: a culture starting at 1e6
RISE = math.log(1.0e3)       # its d: a thousandfold rise to the plateau


def _exponential(doubling=2.0, points=12, start=1.0e6, step=1.0, lag=0.0):
    """A curve that sits at `start` through `lag` hours, then doubles every `doubling` hours."""
    out = []
    for k in range(points):
        t = k * step
        value = start if t <= lag else start * 2 ** ((t - lag) / doubling)
        out.append((t, value))
    return [t for t, _ in out], [v for _, v in out]


def _curve(times, values, species="A", unit="Cells/mL"):
    return GrowthCurve(species=species, times=times, values=values, time_unit="h", abundance_unit=unit)


# ---- the fits expose what they already computed ----------------------------------------------------

def test_the_rate_fit_says_which_window_it_used():
    """`x_j_star` is an average over that window, so the window has to leave the fit."""
    times, values = _exponential(doubling=2.0, points=14)
    fit = rates.easylinear_fit(times, values)
    assert fit["rate"] == pytest.approx(rates.easylinear(times, values))   # the old call is unchanged
    assert fit["rate"] == pytest.approx(math.log(2) / 2, rel=1e-9)
    assert fit["start"] < fit["end"]
    assert fit["start"] >= times[0] and fit["end"] <= times[-1]
    assert fit["points"] >= rates.DEFAULT_WINDOW


def test_a_flat_curve_has_no_window_to_report():
    times, values = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [1e6] * 7
    fit = rates.easylinear_fit(times, values)
    assert fit["rate"] <= 0 and fit["start"] is None and fit["end"] is None


def _baranyi_curve(mu, lag, points=24, step=0.5, y0=START, d=RISE):
    """A curve the Baranyi model itself generates, so the fit can be asked to recover known parameters."""
    times = [k * step for k in range(points)]
    return times, [math.exp(rates._baranyi(t, y0, mu, d, mu * lag)) for t in times]


def test_the_baranyi_fit_reports_the_lag_it_fitted():
    """Karoline, 2026-10-06: "what if Baranyi is used to determine r? It accounts for lag phase." The fit
    already estimates h0 = mu * lag and threw the lag away; asked for known parameters, it returns them."""
    times, values = _baranyi_curve(mu=0.35, lag=3.0)
    fit = rates.baranyi_fit(times, values)
    assert fit["rate"] == pytest.approx(rates.baranyi(times, values))      # the old call is unchanged
    assert fit["rate"] == pytest.approx(0.35, rel=0.15)
    assert fit["lag"] == pytest.approx(3.0, abs=0.75)                      # the lag is recovered
    assert fit["r2"] > 0.95 and fit["start"] <= times[0] + 1e-9

    no_lag = rates.baranyi_fit(*_baranyi_curve(mu=0.35, lag=0.0))
    assert no_lag["lag"] == pytest.approx(0.0, abs=0.5)                    # and not invented


# ---- the partner's abundance over a window ---------------------------------------------------------

def test_the_mean_over_a_window_is_the_area_divided_by_its_length():
    # a straight line from 2 to 6 over 4 hours has mean 4; taken over its middle two hours, mean 4 again
    curve = _curve([0.0, 1.0, 2.0, 3.0, 4.0], [2.0, 3.0, 4.0, 5.0, 6.0])
    assert mean_over(curve, 0.0, 4.0) == pytest.approx(4.0)
    assert mean_over(curve, 1.0, 3.0) == pytest.approx(4.0)
    # a window inside one interval interpolates rather than snapping to a measured point
    assert mean_over(curve, 0.0, 1.0) == pytest.approx(2.5)
    assert mean_over(curve, 3.5, 4.0) == pytest.approx(5.75)


def test_a_window_outside_the_curve_has_no_mean():
    curve = _curve([0.0, 1.0, 2.0], [2.0, 3.0, 4.0])
    assert mean_over(curve, 5.0, 6.0) is None
    assert mean_over(curve, 1.0, 1.0) is None            # no width, no average


def test_the_partner_abundance_of_a_replicate_is_its_mean_over_the_targets_window():
    """The number Karoline chose: the partner's average across the interval the target's rate came from."""
    times, values = _exponential(doubling=2.0, points=14)
    target = _curve(times, values, species="target")
    partner = _curve(times, [5.0e8] * len(times), species="partner")     # flat, so its mean is 5e8 anywhere
    rep = Replicate(curves=(target, partner))
    got = partner_abundance(rep, "target", "partner")
    assert got["value"] == pytest.approx(5.0e8)
    assert got["unit"] == "Cells/mL"
    assert got["window"][0] < got["window"][1]


def test_a_partner_that_was_not_measured_gives_a_reason_not_a_number():
    times, values = _exponential(points=14)
    rep = Replicate(curves=(_curve(times, values, species="target"),))
    got = partner_abundance(rep, "target", "partner")
    assert got["value"] is None and "partner" in got["reason"]


# ---- the carrying capacity, the lag and the method travel with the rate ----------------------------


def _settles(plateau=1.0e8, start=1.0e6, points=12):
    """A curve that doubles every hour up to `plateau` and then stays there, so stationary phase is
    certified and the plateau is the carrying capacity. Hand computed: 1e6 doubling hourly reaches 1e8
    after 6.64 h, and every later point repeats 1e8."""
    out = []
    for t in range(points):
        out.append((float(t), min(plateau, start * 2 ** t), None))
    return out


def test_the_carrying_capacity_is_the_plateau_of_a_monoculture_that_reached_one():
    """#116: "A_ii = -r_i / K_i", so K_i is the monoculture plateau, in the abundance unit it was
    measured in. Two replicates plateau at 1e8 and 3e8, so the median of the two is 2e8."""
    client = _client({(1, A): _settles(plateau=1.0e8), (2, A): _settles(plateau=3.0e8)})
    found, skipped = monoculture_rates(client, [_mono("E1", A, [(1, "r1"), (2, "r2")])])
    (entry,) = found.values()
    (here,) = entry["capacity_by_medium"].values()        # one medium: these fixtures name none
    assert here["values"] == pytest.approx([1.0e8, 3.0e8])
    assert here["unit"] == "Cells/mL"                 # the abundance unit, not the rate's 1/h
    assert entry["method"] == "growth_rate:easylinear:5"
    assert entry["capacity_left_out"] == [] and skipped == []
    merged = merge_rates([("S1", found)])[next(iter(found))]
    assert merged["capacity"] == pytest.approx(2.0e8) and merged["capacity_n"] == 2
    assert merged["capacity_unit"] == "Cells/mL"
    assert merged["capacity_per_study"]["S1"] == pytest.approx(2.0e8)


def test_a_curve_still_growing_gives_a_rate_and_no_capacity_and_says_so():
    """A plateau that was never measured is not a carrying capacity, and the rate is still good: the
    exclusion is reported beside the capacity, not as a rate that was left out."""
    times, values = _exponential(doubling=1.0, points=12)
    client = _client({(1, A): [(t, v, None) for t, v in zip(times, values, strict=True)]})
    found, skipped = monoculture_rates(client, [_mono("E1", A, [(1, "r1")])])
    (entry,) = found.values()
    assert entry["values"] and entry["capacity_by_medium"] == {}    # a rate, no capacity
    assert skipped == []                                            # nothing about the rate was left out
    (label, reason) = entry["capacity_left_out"][0]
    assert "r1" in label and "had not reached stationary phase" in reason
    merged = merge_rates([("S1", found)])[next(iter(found))]
    assert merged["capacity"] is None and merged["capacity_n"] == 0
    assert merged["capacity_left_out"] == entry["capacity_left_out"]


def test_the_lag_always_comes_from_the_baranyi_fit_whichever_rate_was_asked_for():
    """Karoline, 2026-10-06, settling it after the live check: "use the lag from Baranyi and easylinear
    since it works better (users can always enforce Baranyi in the advanced options)". So the rate is the
    estimator the reader chose and the lag is Baranyi's either way, named as such. The curve lags 2 h and
    then doubles hourly."""
    times, values = _baranyi_curve(mu=math.log(2), lag=2.0, points=20, step=0.5)
    curve = [(t, v, None) for t, v in zip(times, values, strict=True)]
    for method, named in (("easylinear", "growth_rate:easylinear:5"), ("baranyi", "growth_rate:baranyi")):
        found, _ = monoculture_rates(_client({(1, A): curve}), [_mono("E1", A, [(1, "r1")])],
                                     rate_method=method)
        entry = next(iter(found.values()))
        assert entry["method"] == named
        assert entry["lag_method"] == "baranyi"
        assert entry["lags"][0] == pytest.approx(2.0, abs=0.5)
        merged = merge_rates([("S1", found)])[next(iter(found))]
        assert merged["lag"] == pytest.approx(2.0, abs=0.5) and merged["lag_n"] == 1
        assert merged["method"] == named and merged["lag_method"] == "baranyi"


def test_capacities_in_another_abundance_unit_are_named_not_converted():
    """The same rule the rates follow across time units, Karoline's "left out rather than converted"."""
    def one(value, unit):
        return {"ncbi:1": {"name": A, "unit": "1/h", "values": [0.4], "replicates": ["r1"], "lags": [],
                           "capacity_left_out": [], "method": "growth_rate:easylinear:5",
                           "capacity_by_medium": {"wc": {"label": "WC", "unit": unit, "values": [value],
                                                         "falls": [1.0], "curves": ["r1"]}}}}
    cells, grams = one(1.0e8, "Cells/mL"), one(0.9, "g/L")
    merged = merge_rates([("S1", cells), ("S2", grams)])["ncbi:1"]
    assert merged["capacity"] == pytest.approx(1.0e8) and merged["capacity_unit"] == "Cells/mL"
    assert merged["other_capacity_units"] == ["S2 (g/L)"]
    assert merged["n"] == 2                       # the rates themselves are in one unit, so both count


# ---- a plateau the culture did not hold -----------------------------------------------------------

def _peaks_then_falls(peak=1.0e8, fall=10.0, start=1.0e6, points=12):
    """A curve that rises geometrically to `peak` and then declines geometrically, so its last point is
    exactly `peak / fall`. It has stopped growing, so `reached_stationary` certifies it, and the plateau
    recorded for it is the peak."""
    half = points // 2
    rise = [start * (peak / start) ** (k / (half - 1)) for k in range(half)]
    tail = [peak * (1.0 / fall) ** ((k + 1) / (points - half)) for k in range(points - half)]
    return [(float(i), v, None) for i, v in enumerate(rise + tail)]


def test_the_fall_from_the_peak_is_one_for_a_plateau_and_the_ratio_for_a_decline():
    """`fall_from_peak` is the window maximum over the last measured value: 1 where the curve ends at its
    peak, and the ratio where it declined after peaking. A curve that falls from its first point has no
    rise, so `reached_stationary` returns None and nothing asks this question of it."""
    from grownet.growth import fall_from_peak, reached_stationary

    def curve(values):
        return GrowthCurve("A", [2.0 * i for i in range(len(values))], values, "h", "OD600")

    plateau = curve([1.0, 3.0, 6.0, 8.4, 8.55, 8.6])
    peaked = curve([1.0, 3.0, 6.0, 8.6, 6.5, 4.5])
    falling = curve([8.6, 7.9, 7.1, 6.3, 5.4, 4.5])
    assert reached_stationary(plateau, plateau.times[-1]) is True
    assert fall_from_peak(plateau, plateau.times[-1]) == pytest.approx(1.0)
    assert reached_stationary(peaked, peaked.times[-1]) is True
    assert fall_from_peak(peaked, peaked.times[-1]) == pytest.approx(8.6 / 4.5)
    # the shape Craig's agent's note was about is this one, not the next: it certifies and hands over a
    # peak 1.91 times what it held
    assert reached_stationary(falling, falling.times[-1]) is None


def test_a_curve_that_fell_too_far_from_its_peak_gives_no_capacity_and_is_named():
    """Karoline, 2026-10-07, closing open decision 4 of #141: the plateau stays the peak, the fall is
    published beside it, and a curve that fell further than the limit gives nothing and says so. One
    replicate falls a hundredfold and one tenfold, and the default limit of 10 keeps the second."""
    client = _client({(1, A): _peaks_then_falls(peak=1.0e8, fall=100.0),
                      (2, A): _peaks_then_falls(peak=1.0e8, fall=10.0)})
    found, skipped = monoculture_rates(client, [_mono("E1", A, [(1, "r1"), (2, "r2")])])
    (entry,) = found.values()
    (here,) = entry["capacity_by_medium"].values()
    assert here["values"] == pytest.approx([1.0e8])               # only the replicate within the limit
    assert here["falls"] == pytest.approx([10.0])
    assert skipped == []                                          # the rate itself was not left out
    (label, reason) = entry["capacity_left_out"][0]
    assert "r1" in label and "1/100 of its peak" in reason and "10 times allowed" in reason
    merged = merge_rates([("S1", found)])[next(iter(found))]
    assert merged["capacity"] == pytest.approx(1.0e8) and merged["capacity_n"] == 1
    assert merged["capacity_fall"] == pytest.approx(10.0)


def test_the_limit_is_a_setting_and_zero_keeps_every_certified_plateau():
    """"the factor ... should go in the advanced settings" (Karoline, 2026-10-07). 0 is the behaviour
    before 0.3.0: every certified plateau counts, however far the culture fell afterwards."""
    curves = {(1, A): _peaks_then_falls(peak=1.0e8, fall=100.0),
              (2, A): _peaks_then_falls(peak=1.0e8, fall=10.0)}
    off, _ = monoculture_rates(_client(curves), [_mono("E1", A, [(1, "r1"), (2, "r2")])],
                               capacity_max_fall=0)
    entry = next(iter(off.values()))
    (here,) = entry["capacity_by_medium"].values()
    assert len(here["values"]) == 2 and entry["capacity_left_out"] == []
    assert merge_rates([("S1", off)])[next(iter(off))]["capacity_fall"] == pytest.approx(55.0)

    strict, _ = monoculture_rates(_client(curves), [_mono("E1", A, [(1, "r1"), (2, "r2")])],
                                  capacity_max_fall=2.0)
    entry = next(iter(strict.values()))
    assert entry["capacity_by_medium"] == {} and len(entry["capacity_left_out"]) == 2


def test_the_fall_travels_into_the_report_and_the_rates_csv():
    """A plateau that is the peak of a declining curve is published with what those curves held at their
    last measurement, in the report's growth-rates section and as a column of the rates CSV."""
    import csv as csv_module
    import io as io_module

    from grownet import matrix
    rates_found = {"ncbi:1": {"name": A, "rate": 0.4, "unit": "1/h", "n": 2, "studies": ["S1"],
                              "per_study": {}, "method": "growth_rate:easylinear:5", "lag": None,
                              "lag_method": "", "capacity": 1.0e8, "capacity_unit": "Cells/mL",
                              "capacity_n": 2, "capacity_fall": 4.0, "capacity_left_out": [],
                              "capacity_medium": "WC"}}
    row = list(csv_module.reader(io_module.StringIO(matrix.rates_csv(rates_found))))[1]
    assert row[-2] == "4" and row[-1] == "WC"

    from grownet.model import InteractionNetwork
    from grownet.report import report_text
    net = InteractionNetwork()
    net.meta["growth_rates"] = {"rule": "r", "organisms": {"ncbi:1": rates_found["ncbi:1"]}}
    text = report_text({"network": net, "resolved": [], "unresolved": [], "studies": [], "errors": [],
                        "skipped": [], "entries": []})
    assert "those curves ended at 1/4 of their peak (median)" in text


# ---- a capacity comes from one medium -------------------------------------------------------------

def _mono_in(exp_id, name, replicates, medium, description=""):
    """A monoculture experiment that names its medium and states its alterations, as mGrowthDB does."""
    exp = _mono(exp_id, name, replicates)
    exp["compartments"] = [{"mediumName": medium}]
    exp["description"] = description
    return exp


def test_a_capacity_is_taken_from_one_medium_and_the_others_are_named():
    """Karoline, 2026-10-07: "capacity merge by medium is a good idea. in addition, we can do the stricter
    test that foodnet does; medium matches but contradicting extras, such as acetic acid or mucin, do not
    count as matching medium." Plateaus are collected per medium and never pooled: the medium with the
    most certified curves is published, and the other is named rather than averaged in. Two replicates
    plateau at 1e8 in the base medium, one at 3e8 with acetate added."""
    client = _client({(1, A): _settles(plateau=1.0e8), (2, A): _settles(plateau=1.0e8),
                      (3, A): _settles(plateau=3.0e8)})
    exps = [_mono_in("E1", A, [(1, "r1"), (2, "r2")], "mMCB"),
            _mono_in("E2", A, [(3, "r3")], "mMCB", "mMCB with initial acetate")]
    found, _ = monoculture_rates(client, exps)
    (entry,) = found.values()
    assert sorted(entry["capacity_by_medium"]) == ["mmcb", "mmcb | +acetate"]

    merged = merge_rates([("S1", found)])[next(iter(found))]
    assert merged["capacity"] == pytest.approx(1.0e8)          # the base medium's, not of all three
    assert merged["capacity_medium"] == "mMCB"
    assert merged["capacity_media"] == ["mMCB"]                # one medium, so nothing is pooled
    assert merged["capacity_other_media"] == ["mMCB (+acetate)"]
    assert merged["capacity_n"] == 2
    (what, why) = merged["capacity_left_out"][-1]
    assert what == "1 curve(s) in mMCB (+acetate)"
    assert "not pooled across media" in why and "taken from mMCB" in why


def test_the_medium_with_the_most_curves_wins_whatever_order_the_studies_came_in():
    """A tie goes to the first label, so the published capacity does not depend on the order the studies
    were read in, which is the failure register item 14 is about in another place."""
    curves = {(1, A): _settles(plateau=1.0e8), (2, A): _settles(plateau=3.0e8),
              (3, A): _settles(plateau=3.0e8)}
    base = _mono_in("E1", A, [(1, "r1")], "mMCB")
    added = _mono_in("E2", A, [(2, "r2"), (3, "r3")], "mMCB", "mMCB with initial acetate")
    for order in ([base, added], [added, base]):
        found, _ = monoculture_rates(_client(curves), order)
        merged = merge_rates([("S1", found)])[next(iter(found))]
        assert merged["capacity_medium"] == "mMCB (+acetate)"   # two curves against one
        assert merged["capacity"] == pytest.approx(3.0e8)


def test_the_second_box_says_how_many_media_one_word_reached():
    """Karoline, 2026-10-07: the strict rule applies to the second box too, "because such changes alter
    interactions". A reader who types one word is told how many environments came back, so a search over
    a study that varies one medium does not read as a search of one medium."""
    from grownet.derive import select_experiments
    from grownet.selection import parse
    exps = [_mono_in("E1", A, [(1, "r1")], "Minimal medium (MM)",
                     "Growth of At on minimal medium with 0.05% linoleic acid"),
            _mono_in("E2", A, [(2, "r2")], "Minimal medium (MM)",
                     "Growth of At on minimal medium with 0.75% linoleic acid")]
    notes: list = []
    kept = select_experiments(exps, parse(["linoleic"]), notes)
    assert len(kept) == 2                                  # both are read, as the text match asks
    (what, why) = next((row for row in notes if row[0].startswith("media matched by")), (None, None))
    assert what == "media matched by linoleic"
    assert "2 different media" in why and "never one pooled set" in why
    assert "Minimal medium (MM) (+0.05% linoleic acid)" in why
    assert "Name an experiment id" in why

    # one medium, one note fewer: nothing is said where there is nothing to warn about
    quiet: list = []
    select_experiments(exps[:1], parse(["linoleic"]), quiet)
    assert not [row for row in quiet if row[0].startswith("media matched by")]


# ---- the partner's abundance reaches the arc ------------------------------------------------------

def test_an_arc_carries_the_partners_abundance_over_the_targets_window():
    """End to end: the number lands on the record, so a gLV coefficient can be built from a network.
    The partner is flat at 5e8 cells/mL in both co-culture replicates, so its mean over any window is
    5e8, and the median over the two replicates is 5e8 too."""
    from test_growth_rates import B, _co
    from test_growth_rates import _mono as _mono_exp

    from grownet.derive import interactions_from_replicates

    def curve(doubling, points=12, start=1.0e6):
        return [(float(t), start * 2 ** (t / doubling), None) for t in range(points)]

    flat = [(float(t), 5.0e8, None) for t in range(12)]
    client = _client({(1, A): curve(2.0), (2, A): curve(2.0),          # A alone, two replicates
                      (3, B): curve(2.0), (4, B): curve(2.0),          # B alone, two replicates
                      (5, A): curve(1.0), (5, B): flat,                # A with B, faster with B
                      (6, A): curve(1.0), (6, B): flat})
    exps = [_mono_exp("E1", A, [(1, "r1"), (2, "r2")]), _mono_exp("E2", B, [(3, "r1"), (4, "r2")]),
            _co("E3", A, B, [(5, "r1"), (6, "r2")])]
    records, _ = interactions_from_replicates(client, {"id": "S1"}, exps, "S1", method="auc")
    arc = next(r for r in records if r["target_name"] == A and r["source_name"] == B)
    assert arc["partner_abundance"] == pytest.approx(5.0e8)
    assert arc["partner_abundance_unit"] == "Cells/mL" and arc["partner_abundance_n"] == 2
    assert arc["partner_abundance_left_out"] == []

    # and through the network, so a saved file carries it (#119 reads it from there)
    from grownet.mgrowthdb import records_to_network
    edge = next(e for e in records_to_network(records).edges if e.target.startswith("faecalibacterium"))
    assert edge.partner_abundance == pytest.approx(5.0e8) and edge.partner_abundance_unit == "Cells/mL"


def test_the_glv_payload_and_the_package_carry_the_quantities_beside_each_rate():
    """What travels to R and into the zip: the rate as before, and the three numbers beside it, so
    nothing a reader would have seen in the report is missing on those routes (#118)."""
    import csv
    import io
    import zipfile

    from grownet import matrix
    from grownet.mgrowthdb import records_to_network

    net = records_to_network(
        [{"source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
          "strength": 1.5, "status": "present", "outcome": "quantified", "study_id": "S1",
          "metric": "growth_rate:baranyi", "partner_abundance": 2.0e8,
          "partner_abundance_unit": "Cells/mL", "partner_abundance_n": 3}],
        meta={"tool_version": "9.9.9", "absence": {"k": 1.0}})
    rates_found = {"a": {"name": "A", "rate": 0.4, "unit": "1/h", "n": 3, "studies": ["S1"],
                         "per_study": {"S1": 0.4}, "method": "growth_rate:baranyi", "lag": 1.5,
                         "capacity": 2.5e8, "capacity_unit": "Cells/mL", "capacity_n": 3}}
    detail, = matrix.glv_payload(net, rates_found)["growth_rate_detail"]
    assert detail["rate"] == 0.4 and detail["method"] == "growth_rate:baranyi" and detail["lag"] == 1.5
    assert detail["carrying_capacity"] == 2.5e8 and detail["carrying_capacity_unit"] == "Cells/mL"
    assert detail["carrying_capacity_curves"] == 3

    with zipfile.ZipFile(io.BytesIO(matrix.glv_package(net, rates_found))) as archive:
        row, = list(csv.DictReader(io.StringIO(archive.read("growth_rates.csv").decode())))
        assert row["carrying_capacity"] == "2.5e+08" and row["lag"] == "1.5"
        assert row["method"] == "growth_rate:baranyi" and row["capacity_unit"] == "Cells/mL"
        readme = archive.read("README.txt").decode()
        assert "carrying capacity" in readme and "growth_rate:baranyi" in readme
