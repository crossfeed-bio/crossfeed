"""Chemostat runs into the steady-state estimator, and each row's scale from the run's own start-up (#312).

Karoline's decisions on #310: chemostat steady states only ("Yes on 1"); the row scale r_i - D from the
chemostat itself, since "Mono-culture growth rates from batch are tricky, because they change in chemostat";
and "chemostat is not always switched on directly, so it would mean checking experiment description for a
batch period". Every number here is invented.
"""
import math

import pytest
from test_growth_rates import _client
from test_steady_state import _chemostat

from grownet.growth import GrowthCurve
from grownet.subcommunity import batch_period, chemostat_groups, fit, row_scale

LIVE = "Six species grown in a chemostat, maintained at 37°C. Chemostat mode started 4 hours after inoculation."
# a run is used only when it is known to be unperturbed (decision 1 of #310); the live run says so in its name,
# "No perturbations", which the chemostat check reads from the name and the description alike
RUN = LIVE + " No perturbations."


@pytest.mark.parametrize("text, kind, hours", [
    (LIVE, "batch", 4.0),                                                   # the one live run that says it
    ("Chemostat mode started 90 min after inoculation.", "batch", 1.5),
    ("A batch phase of 24 h preceded continuous feeding.", "batch", 24.0),
    ("Pumps were switched on after 6 h.", "batch", 6.0),
    ("After 12 hours of batch growth the dilution was started.", "batch", 12.0),
    ("Dilution from inoculation.", "from inoculation", 0.0),
    ("Chemostat mode was started directly after inoculation.", "from inoculation", 0.0),
    ("Control vessels with the same inoculum as experiment A8, but no perturbations.", "unknown", None),
    ("", "unknown", None),
])
def test_the_description_says_when_the_dilution_started(text, kind, hours):
    got = batch_period({"description": text})
    assert (got["kind"], got["hours"]) == (kind, hours)
    if kind != "unknown":
        assert got["said"] and got["said"].lower() in text.lower()      # the words it read, for the report


def _startup(r, D, batch, K, x0=1.0e6, step=1.0, end=48.0):
    """A chemostat trace: growth at r for `batch` hours, then at r - D (the pump on), until the steady state K.
    With batch 0 the pump runs from inoculation."""
    out, t = [], 0.0
    while t <= end + 1e-9:
        if t <= batch:
            x = x0 * math.exp(r * t)
        else:
            x = x0 * math.exp(r * batch) * math.exp((r - D) * (t - batch))
        out.append((t, min(x, K), None))              # as mGrowthDB serves a series
        t += step
    return out


def _curve(points, unit="h"):
    return GrowthCurve("a", tuple(p[0] for p in points), tuple(p[1] for p in points), unit, "Cells/mL", "qpcr")


def test_a_batch_period_gives_r_and_the_scale_is_r_less_d():
    """0.5 /h for the first 4 h (five points, 0 to 4), the pump on at D = 0.04: the scale is 0.5 - 0.04 = 0.46."""
    got = row_scale(_curve(_startup(0.5, 0.04, 4.0, 1.0e9)), 0.04, {"kind": "batch", "hours": 4.0, "said": "x"})
    assert got["scale"] == pytest.approx(0.46, abs=1e-9)
    assert "batch period" in got["how"] and "0.04" in got["how"]


def test_dilution_from_inoculation_gives_r_less_d_directly():
    """From inoculation the rise is at r - D = 0.46 already, so nothing is subtracted."""
    got = row_scale(_curve(_startup(0.5, 0.04, 0.0, 1.0e9)), 0.04, {"kind": "from inoculation", "hours": 0.0,
                                                                     "said": "x"})
    assert got["scale"] == pytest.approx(0.46, abs=1e-9)


def test_an_unstated_start_leaves_the_row_scaled_and_says_why():
    got = row_scale(_curve(_startup(0.5, 0.04, 4.0, 1.0e9)), 0.04, {"kind": "unknown", "hours": None, "said": ""})
    assert got["scale"] is None and "does not say when the dilution started" in got["how"]


def test_a_batch_period_too_short_to_fit_is_read_after_the_pump_and_a_washing_out_rate_gives_no_scale():
    """A 1 h batch period holds two points, too few for a rate; the rise after the pump started is r - D = 0.46
    itself, which is the other reading of the scale."""
    short = row_scale(_curve(_startup(0.5, 0.04, 1.0, 1.0e9)), 0.04, {"kind": "batch", "hours": 1.0, "said": "x"})
    # (easylinear refits over every window within its quota of the steepest, one of which reaches the plateau,
    # so 0.4592 rather than 0.46: growthrates' rule, kept so rates agree with mGrowthDB's)
    assert short["scale"] == pytest.approx(0.46, abs=2e-3) and "after the pump started" in short["how"]
    # and with no point after the pump either, no scale
    cut = [p for p in _startup(0.5, 0.04, 1.0, 1.0e9) if p[0] <= 1.0]
    none = row_scale(_curve(cut), 0.04, {"kind": "batch", "hours": 1.0, "said": "x"})
    assert none["scale"] is None and "points" in none["how"]
    # r 0.03 below D 0.04: no positive scale, so the organism could not hold a steady state at all
    slow = row_scale(_curve(_startup(0.03, 0.04, 6.0, 1.0e9)), 0.04, {"kind": "batch", "hours": 6.0, "said": "x"})
    assert slow["scale"] is None and "not above the dilution rate" in slow["how"]


def test_a_curve_in_minutes_or_days_gives_the_scale_per_hour_as_the_dilution_rate_is():
    """The dilution rate is recorded per hour (the chemostat check's /h), so the curve's rate is converted
    before D is taken off: a curve timed in days gave 11.7 per day less 0.1 per hour, labelled 1/h (found in
    review). The same run timed in minutes or in days gives the same 0.46 per hour."""
    hours = _startup(0.5, 0.04, 4.0, 1.0e9, step=0.5)
    period = {"kind": "batch", "hours": 4.0, "said": "x"}
    got = row_scale(_curve(hours), 0.04, period)
    minutes = row_scale(_curve([(t * 60, v, None) for t, v, _ in hours], unit="min"), 0.04, period)
    days = row_scale(_curve([(t / 24, v, None) for t, v, _ in hours], unit="d"), 0.04, period)
    assert got["scale"] == pytest.approx(0.46, abs=1e-9)
    assert minutes["scale"] == pytest.approx(0.46, rel=1e-9) and days["scale"] == pytest.approx(0.46, rel=1e-9)


def test_a_lag_inside_the_batch_period_is_overcome_by_the_rise_after_the_pump():
    """Flat for 3 h of a 4 h batch period, then 0.5 /h: the batch period alone gives no rate, or one far too
    low. After the pump starts the culture rises at r - D = 0.46 until it nears its plateau, and that reading is
    kept: each is a lower bound, and the larger is the closer."""
    lagged = []
    for t in [i * 1.0 for i in range(49)]:
        x = 1.0e6 if t <= 3 else 1.0e6 * math.exp(0.5 * (min(t, 4) - 3)) * math.exp(0.46 * max(t - 4, 0))
        lagged.append((t, min(x, 1.0e9), None))
    got = row_scale(_curve(lagged), 0.04, {"kind": "batch", "hours": 4.0, "said": "x"})
    assert got["scale"] == pytest.approx(0.46, abs=2e-3) and "after the pump started" in got["how"]
    # the batch period alone, the same run cut where the pump started: its one window easylinear tries (0 to
    # 3 h, as growthrates tries them) is flat, so it gives no scale at all
    alone = row_scale(_curve([p for p in lagged if p[0] <= 4]), 0.04, {"kind": "batch", "hours": 4.0, "said": "x"})
    assert alone["scale"] is None and "no window rises" in alone["how"]


# ---- whole runs into communities ------------------------------------------------------------------------

# the two-species system of tests/test_subcommunity.py, in Cells/mL: B = [[-1, -0.25], [-0.1, -0.5]] per 1e8
# Cells/mL, so a alone holds 1e8, b alone 2e8, and the pair 0.526316e8 and 1.894737e8
UNIT = 1.0e8
PAIR_A, PAIR_B = (1 - 0.25 * 0.9 / 0.475) * UNIT, 0.9 / 0.475 * UNIT


def _runs(extra_runs=(), extra_curves=None):
    curves = {(1, "a"): _startup(0.5, 0.04, 4.0, 1.0 * UNIT), (2, "a"): _startup(0.5, 0.04, 4.0, 1.0 * UNIT),
              (3, "b"): _startup(0.3, 0.04, 4.0, 2.0 * UNIT), (4, "b"): _startup(0.3, 0.04, 4.0, 2.0 * UNIT),
              (5, "a"): _startup(0.5, 0.04, 4.0, PAIR_A), (5, "b"): _startup(0.3, 0.04, 4.0, PAIR_B),
              (6, "a"): _startup(0.5, 0.04, 4.0, PAIR_A), (6, "b"): _startup(0.3, 0.04, 4.0, PAIR_B),
              **(extra_curves or {})}
    exps = [_chemostat("E1", "a alone", ["a"], [(1, "V1"), (2, "V2")], description=RUN),
            _chemostat("E2", "b alone", ["b"], [(3, "V1"), (4, "V2")], description=RUN),
            _chemostat("E3", "a with b", ["a", "b"], [(5, "V1"), (6, "V2")], description=RUN), *extra_runs]
    return _client(curves), exps


def test_chemostat_runs_become_communities_and_give_the_rows():
    client, exps = _runs()
    (group,) = chemostat_groups(client, exps)
    assert (group["dilution"], group["unit"]) == (0.04, "Cells/mL")
    by_name = {c["name"]: c for c in group["communities"]}
    assert by_name["a with b"]["abundance"] == pytest.approx({"a": PAIR_A, "b": PAIR_B}, rel=1e-9)
    assert len(by_name["a with b"]["vessels"]) == 2                      # per vessel, for the bootstrap
    rows = fit(group["communities"], draws=0)["rows"]
    assert rows["a"]["values"] == pytest.approx({"a": -1.0 / UNIT, "b": -0.25 / UNIT}, rel=1e-9)
    assert rows["b"]["values"] == pytest.approx({"a": -0.1 / UNIT, "b": -0.5 / UNIT}, rel=1e-9)
    # the row scales from the monocultures' own start-up: 0.5 - 0.04 and 0.3 - 0.04
    assert group["scales"]["a"]["scale"] == pytest.approx(0.46, abs=1e-9)
    assert group["scales"]["b"]["scale"] == pytest.approx(0.26, abs=1e-9)


def test_a_washed_out_member_counts_as_zero():
    """b inoculated with a and held at 0.5% of a, under the chemostat check's 1% wash-out rule."""
    washed = _chemostat("E4", "a with b, b lost", ["a", "b"], [(7, "V1")], description=RUN)
    client, exps = _runs([washed], {(7, "a"): _startup(0.5, 0.04, 4.0, UNIT),
                                    (7, "b"): _startup(0.3, 0.04, 4.0, 0.005 * UNIT)})
    (group,) = chemostat_groups(client, exps)
    lost = next(c for c in group["communities"] if c["name"] == "a with b, b lost")
    assert lost["abundance"]["b"] == 0.0


def test_a_perturbed_or_unknown_run_and_another_dilution_rate_are_kept_apart():
    perturbed = _chemostat("E5", "a with b", ["a", "b"], [(8, "V1")],
                           description="The pH of the feed was changed from 6.4 to 3.7.")
    unknown = _chemostat("E6", "a with b again", ["a", "b"], [(9, "V1")], description="Six vessels.")
    faster = _chemostat("E7", "a alone, faster", ["a"], [(10, "V1")], dilution="0.1", description=RUN)
    pair = {"a": _startup(0.5, 0.04, 4.0, PAIR_A), "b": _startup(0.3, 0.04, 4.0, PAIR_B)}
    client, exps = _runs([perturbed, unknown, faster],
                         {(8, "a"): pair["a"], (8, "b"): pair["b"], (9, "a"): pair["a"], (9, "b"): pair["b"],
                          (10, "a"): _startup(0.5, 0.1, 4.0, 0.8 * UNIT)})
    groups = chemostat_groups(client, exps)
    assert sorted(g["dilution"] for g in groups) == [0.04, 0.1]        # one fit per dilution rate
    slow = next(g for g in groups if g["dilution"] == 0.04)
    names = {c["name"] for c in slow["communities"]}
    assert "a with b" in names and "a with b again" not in names
    # the perturbed run is in no community, by its own reason: "unperturbed" alone is in the unknown run's
    # reason too, so a perturbed run let through passed the old check (found in review)
    assert not any(c.get("experiment") == "E5" for c in slow["communities"])
    left = " ".join(why for _, why in slow["left_out"])
    assert "the run carries perturbations" in left and "does not say it is unperturbed" in left


def _retag(client, species, technique, bioreplicates=None):
    for bid, rep in client.bioreplicates.items():
        if bioreplicates is not None and bid not in bioreplicates:
            continue
        for c in rep["measurementContexts"]:
            if c["subject"]["name"] == species:
                c["techniqueType"] = technique


def test_each_organism_keeps_its_own_technique_and_the_design_stays_one_group():
    """a read by qPCR in every run and b by flow cytometry in every run: each organism is one quantity
    throughout, so the design is one group and determines both rows. Grouping by the run's set of techniques
    made three groups ("qpcr", "fc", "fc; qpcr") that determined nothing (found in a second review)."""
    client, exps = _runs()
    _retag(client, "b", "fc")
    (group,) = chemostat_groups(client, exps)
    assert group["techniques"] == {"a": "qpcr", "b": "fc"}
    assert fit(group["communities"], draws=0)["rows"]["a"]["status"] == "identified"


def test_an_organism_read_by_two_techniques_splits_the_runs_and_says_why():
    """b by flow cytometry in its monoculture and by qPCR in the pair: b's abundance is not one quantity
    across them, so the runs are fitted apart by technique, and the reason names b and both techniques."""
    client, exps = _runs()
    _retag(client, "b", "fc", bioreplicates={3, 4})
    groups = chemostat_groups(client, exps)
    assert len(groups) == 2
    said = " ".join(why for g in groups for _, why in g["left_out"])
    assert "b by fc and qpcr" in said


def test_runs_reading_the_same_organisms_by_swapped_techniques_are_fitted_apart():
    """One run of a with b reads a by fc and b by qPCR, a second the other way round: splitting by the run's
    set of techniques put both in one fit, where a and b were each read two ways (found in a third review).
    Within every fit each organism has one technique."""
    second = _chemostat("E4", "a with b again", ["a", "b"], [(7, "V1"), (8, "V2")], description=RUN)
    client, exps = _runs([second], {(i, s): _startup(0.5 if s == "a" else 0.3, 0.04, 4.0,
                                                      PAIR_A if s == "a" else PAIR_B)
                                    for i in (7, 8) for s in ("a", "b")})
    _retag(client, "a", "fc", bioreplicates={5, 6})
    _retag(client, "b", "fc", bioreplicates={7, 8})
    for group in chemostat_groups(client, exps):
        for m in group["techniques"]:
            read = {c["techniques"][m] for c in group["communities"] if m in c["techniques"]}
            assert len(read) == 1, (group["technique"], m, read)
