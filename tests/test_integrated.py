"""Fitting a gLV row from the whole time course, the integrated form (#127).

Karoline, 2026-10-06, on the shortlist of #124: "OK for 3, as an advanced option", so this is a second
`Deriver` and the default derivation does not change.

Integrating dx_i/dt = x_i (r_i + sum_j A_ij x_j) over a replicate's measured span gives

    ln( x_i(T) / x_i(0) ) = r_i * T + sum_j A_ij * integral( x_j dt )

which is linear in r_i and in every A_ij, so one least-squares fit per organism gives its whole row: no
rate window, no log2 ratio and no certified plateau. The tests build curves from known coefficients and
ask the fit to recover them.
"""
import math

import pytest

from grownet import integrated
from grownet.growth import GrowthCurve, Replicate


def _simulate(r, A, x0, t_end=10.0, step=0.01):
    """A gLV community integrated with small Euler steps: the data a fit should recover r and A from."""
    n = len(r)
    x = list(x0)
    times, series = [0.0], [list(x)]
    steps = int(t_end / step)
    for k in range(1, steps + 1):
        rates = [x[i] * (r[i] + sum(A[i][j] * x[j] for j in range(n))) for i in range(n)]
        x = [max(1e-12, x[i] + step * rates[i]) for i in range(n)]
        if k % 20 == 0:                      # keep every twentieth point, as a measured curve would be
            times.append(k * step)
            series.append(list(x))
    return times, series


def _replicate(names, times, series, unit="Cells/mL"):
    curves = tuple(GrowthCurve(species=name, times=list(times),
                               values=[row[i] for row in series], time_unit="h", abundance_unit=unit)
                   for i, name in enumerate(names))
    return Replicate(curves=curves, name="r1")


# One organism limiting itself: r = 0.5 /h, K = 1e9, so A_11 = -5e-10.
SOLO = ([0.5], [[-5.0e-10]], [1.0e7])


def test_the_design_of_one_organism_is_its_log_change_against_time_and_the_integrals():
    """The row the regression reads: the left side is ln(x(T) / x(0)) at each measured time, the columns
    are the elapsed time and the trapezoidal integral of each organism present."""
    times, series = _simulate(*SOLO)
    rep = _replicate(["A"], times, series)
    design = integrated.design(rep, "A", ["A"])
    assert design["partners"] == ["A"]
    # every measured point after the first, minus any the lag of this curve puts before the start
    assert len(times) - 4 <= len(design["rows"]) <= len(times) - 1
    first = design["rows"][0]
    begin = len(times) - 1 - len(design["rows"])        # the index the rows start from
    assert first["y"] == pytest.approx(math.log(series[begin + 1][0] / series[begin][0]), rel=1e-9)
    assert first["time"] == pytest.approx(times[begin + 1] - times[begin])
    # the integral of its own curve over that step, by the trapezoid rule
    expected = 0.5 * (series[begin][0] + series[begin + 1][0]) * (times[begin + 1] - times[begin])
    assert first["integrals"][0] == pytest.approx(expected, rel=1e-9)


def test_one_organism_recovers_its_own_rate_and_self_limitation():
    """The simplest check the whole task rests on: a logistic curve from r = 0.5 /h and A = -5e-10 is
    fitted back to those numbers, with no window and no plateau needed."""
    times, series = _simulate(*SOLO)
    fit = integrated.fit_row(_replicate(["A"], times, series), "A", ["A"])
    assert fit["rate"] == pytest.approx(0.5, rel=0.02)
    assert fit["coefficients"]["A"] == pytest.approx(-5.0e-10, rel=0.05)
    assert fit["r2"] > 0.99 and fit["points"] >= len(times) - 4
    assert fit["condition"] < 1.0e4           # one partner, so the design is well conditioned


def test_a_pair_recovers_both_coefficients_when_the_partners_are_not_collinear():
    """Two organisms, A limiting itself and helped by B: r_A = 0.4, A_AA = -4e-10, A_AB = +2e-10. The fit
    of A's row returns all three, because the two integrals do not rise together."""
    r = [0.4, 0.3]
    A = [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]]
    times, series = _simulate(r, A, [1.0e7, 5.0e8])
    fit = integrated.fit_row(_replicate(["A", "B"], times, series), "A", ["A", "B"])
    assert fit["rate"] == pytest.approx(0.4, rel=0.05)
    assert fit["coefficients"]["A"] == pytest.approx(-4.0e-10, rel=0.1)
    assert fit["coefficients"]["B"] == pytest.approx(2.0e-10, rel=0.2)
    assert fit["r2"] > 0.99


def test_a_fit_that_is_not_identified_is_reported_rather_than_published():
    """Measured on #116: inside one experiment the two integrals can correlate at +0.977, and the fit then
    splits the organism's own limitation from its partner's effect badly. The condition number says so,
    and anything above the limit is named rather than returned as a number."""
    r = [0.4, 0.4]
    A = [[-4.0e-10, -4.0e-10], [-4.0e-10, -4.0e-10]]
    times, series = _simulate(r, A, [1.0e7, 1.0e7])        # identical curves: the columns are the same
    fit = integrated.fit_row(_replicate(["A", "B"], times, series), "A", ["A", "B"])
    assert fit["condition"] > integrated.MAX_CONDITION
    assert fit["coefficients"] == {} and "not identified" in fit["reason"]


def test_the_two_stage_fit_holds_the_monoculture_numbers_fixed():
    """What worked on SMGDB00000004: the monocultures give r_i and A_ii, then the co-cultures give the
    partners' coefficients with those held fixed, which the collinearity above makes necessary."""
    r = [0.4, 0.3]
    A = [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]]
    mono_times, mono_series = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    co_times, co_series = _simulate(r, A, [1.0e7, 5.0e8])
    got = integrated.two_stage("A", [_replicate(["A"], mono_times, mono_series)],
                               [_replicate(["A", "B"], co_times, co_series)], ["A", "B"])
    assert got["rate"] == pytest.approx(0.4, rel=0.02)
    assert got["coefficients"]["A"] == pytest.approx(-4.0e-10, rel=0.05)   # from the monoculture
    assert got["coefficients"]["B"] == pytest.approx(2.0e-10, rel=0.25)    # from the co-culture
    # the stages say how the monoculture numbers were obtained: the median of the replicates' own fits,
    # or, where none of them identifies the row, one regression over all their rows (2026-10-06)
    assert got["stages"] == ["monoculture", "co-culture"]


def test_a_curve_that_starts_at_zero_or_never_rises_gives_no_fit():
    times = [0.0, 1.0, 2.0, 3.0]
    flat = GrowthCurve(species="A", times=times, values=[0.0, 0.0, 0.0, 0.0], time_unit="h",
                       abundance_unit="Cells/mL")
    fit = integrated.fit_row(Replicate(curves=(flat,), name="r1"), "A", ["A"])
    assert fit["coefficients"] == {} and "no positive" in fit["reason"]


# ---- the Deriver ------------------------------------------------------------------------------------

def test_the_deriver_emits_arcs_whose_strength_is_the_effect_at_the_measured_abundance():
    """The two derivations have to be comparable, so an integrated arc carries the same kind of strength
    as a ratio arc: with r_with = r_i + A_ij x_j, the log2 ratio is log2(1 + A_ij x_j / r_i), which is
    what this arc records, with the fitted coefficient beside it. Hand computed from the simulation:
    the arc's own numbers have to satisfy it exactly, and B, which rises from 5e8 towards its own 1e9
    plateau during the run, puts it near log2(1.4)."""
    from test_growth_rates import _client, _co, _mono

    from grownet.integrated import IntegratedDeriver
    r = [0.4, 0.3]
    A = [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]]
    mono_a = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    mono_b = _simulate([0.3], [[-3.0e-10]], [5.0e8])
    co = _simulate(r, A, [1.0e7, 5.0e8])

    def series(times, values, which=0):
        return [(t, row[which], None) for t, row in zip(times, values, strict=True)]

    client = _client({(1, "A"): series(*mono_a), (2, "B"): series(*mono_b),
                      (3, "A"): series(*co, 0), (3, "B"): series(*co, 1)})
    exps = [_mono("E1", "A", [(1, "r1")]), _mono("E2", "B", [(2, "r1")]),
            _co("E3", "A", "B", [(3, "r1")])]
    records, skipped = IntegratedDeriver(client=client).derive({"id": "S1"}, exps)
    arc = next(r for r in records if r["target_name"] == "A" and r["source_name"] == "B")
    assert arc["coefficient"] == pytest.approx(2.0e-10, rel=0.3)
    assert arc["coefficient_unit"].startswith("1/(h x ")
    # the identity the arc rests on, exactly: log2(1 + A_ij x_j / r_i)
    assert arc["strength"] == pytest.approx(
        math.log2(1 + arc["coefficient"] * arc["partner_abundance"] / arc["fitted_rate"]), abs=5e-4)
    assert 0.2 < arc["strength"] < 0.8
    assert arc["effect"] == "facilitation" and arc["outcome"] == "quantified"
    assert arc["metric"].startswith("integrated")
    assert arc["fit_condition"] > 0 and arc["fit_r2"] > 0.9


def test_the_fitted_rates_of_a_run_carry_the_rate_and_the_capacity_the_fit_implies():
    """The package needs a rate and a self-limitation per organism, and the integrated fit gives both:
    r_i directly and K_i = -r_i / A_ii, which is the plateau that fit implies. Hand computed: 0.4 over
    4e-10 is 1e9."""
    from grownet.integrated import fitted_rates
    records = [{"target": "a", "target_name": "A", "fitted_rate": 0.4, "fitted_self": -4.0e-10,
                "fitted_self_unit": "Cells/mL", "study_id": "S1", "fit_r2": 0.99, "fit_condition": 12.0}]
    rates = fitted_rates(records)
    assert rates["a"]["rate"] == pytest.approx(0.4)
    assert rates["a"]["capacity"] == pytest.approx(1.0e9)
    assert rates["a"]["capacity_unit"] == "Cells/mL"
    assert "integrated" in rates["a"]["method"]


def test_an_organism_whose_row_is_not_identified_is_skipped_with_the_reason():
    """A flat curve carries no growth to fit, so A's own rate and limitation cannot be identified and its
    arc is reported rather than invented. B, which does grow, still gets its own arc."""
    from test_growth_rates import _client, _co, _mono

    from grownet.integrated import IntegratedDeriver
    flat = [(float(t), 1.0e7, None) for t in range(14)]
    mono_b = _simulate([0.3], [[-3.0e-10]], [5.0e8])
    co = _simulate([0.0, 0.3], [[-1.0e-12, 0.0], [0.0, -3.0e-10]], [1.0e7, 5.0e8])

    def series(times, values, which=0):
        return [(t, row[which], None) for t, row in zip(times, values, strict=True)]

    client = _client({(1, "A"): flat, (2, "B"): series(*mono_b),
                      (3, "A"): series(*co, 0), (3, "B"): series(*co, 1)})
    exps = [_mono("E1", "A", [(1, "r1")]), _mono("E2", "B", [(2, "r1")]),
            _co("E3", "A", "B", [(3, "r1")])]
    records, skipped = IntegratedDeriver(client=client).derive({"id": "S1"}, exps)
    assert [r["target_name"] for r in records] == ["B"]
    assert any("A" in label and ("fitted" in why or "identified" in why) for label, why in skipped)


def test_the_rows_start_where_growth_starts_so_a_lag_does_not_eat_the_rate():
    """Karoline, 2026-10-06: "so the integrated form depends on identifying lag phase. what if Baranyi is
    used to determine r?" The model has no lag term, so a culture that sits at its inoculum and then grows
    makes ln(x(T)/x(0)) smaller than the model expects and the fit pays for it in the rate: on
    SMGDB00000007 that gave a rate of -0.08 /h. Starting the rows at the end of the lag, which #118
    reports, recovers the rate instead."""
    times, series = _simulate(*SOLO)
    lagged_times = [0.0, *[t + 3.0 for t in times]]
    lagged_series = [[series[0][0]], *series]          # three hours at the inoculum, then the same growth
    rep = _replicate(["A"], lagged_times, lagged_series)

    whole = integrated.fit_row(rep, "A", ["A"], start=0.0)      # the lag included: the rate is eaten
    after = integrated.fit_row(rep, "A", ["A"])                 # the lag found and skipped
    assert after["rate"] == pytest.approx(0.5, rel=0.1)
    assert after["rate"] > whole["rate"]
    assert "where growth starts" in after["reason"]


def _named(names, times, series, name, unit="Cells/mL"):
    curves = tuple(GrowthCurve(species=n, times=list(times), values=[row[i] for row in series],
                               time_unit="h", abundance_unit=unit) for i, n in enumerate(names))
    return Replicate(curves=curves, name=name)


def test_the_fit_carries_its_own_spread_over_replicates_and_over_the_rate_stage():
    """Before 2026-10-06 an integrated arc carried no sd, no standard error and no p-value, so the
    absence threshold returned "undetermined" for every one of them and nothing could be tested or
    corrected for multiple testing. Stage 2 is now fitted once per co-culture replicate, and once per
    leave-one-out of the monoculture replicates, so the spread over that set carries both stages.

    Three monocultures and three co-cultures of the same noiseless system: every estimate is the same
    number, so the spread is zero and the fit recovers the truth. What this pins is that the spread
    exists, rests on the replicates, and names the part that comes from the rate stage.
    """
    r = [0.4, 0.3]
    A = [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]]
    mono_times, mono_series = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    monos = [_named(["A"], mono_times, mono_series, f"m{k}") for k in range(3)]
    cos = []
    for k, start in enumerate((1.0e7, 1.1e7, 0.9e7)):      # three replicates differing in inoculum
        times, series = _simulate(r, A, [start, 5.0e8])
        cos.append(_named(["A", "B"], times, series, f"c{k}"))
    got = integrated.two_stage("A", monos, cos, ["A", "B"])

    assert got["replicates"] == 3
    assert [entry["replicate"] for entry in got["per_replicate"]] == ["c0", "c1", "c2"]
    spread = got["spread"]["B"]
    assert spread["n"] == 12                 # three replicates times four stage-1 variants
    assert spread["median"] == pytest.approx(2.0e-10, rel=0.25)
    assert spread["sd"] is not None and spread["sd"] >= 0
    assert "B" in got["stage_one_spread"]

    # and the R2 is of the whole fit against the measured log change, about zero, since y is zero at the
    # start by construction and the model has no intercept
    assert got["r2"] == pytest.approx(1.0, abs=0.05)


def test_a_row_whose_fit_explains_less_than_nothing_is_refused_with_the_reason(monkeypatch):
    """The R2 the arcs used to carry was stage 2's against stage 1's residual, which cannot say whether
    the model describes the curve at all. With the honest R2 in hand, a row that explains less of the
    organism's own log change than predicting nothing does is not a measurement, and the line is zero
    rather than a tuned threshold. Live on the whole database this refuses six rows of twenty-nine
    (2026-10-06).

    The fit itself is exercised by the tests above; what this pins is the gate, so the fit is replaced by
    one that reports a negative R2 and the deriver is asked what it does with it.
    """
    from test_growth_rates import _client, _co, _mono

    from grownet.integrated import IntegratedDeriver
    mono_a = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    mono_b = _simulate([0.3], [[-3.0e-10]], [5.0e8])
    co = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])

    def series(times, values, which=0):
        return [(t, row[which], None) for t, row in zip(times, values, strict=True)]

    client = _client({(1, "A"): series(*mono_a), (2, "B"): series(*mono_b),
                      (3, "A"): series(*co, 0), (3, "B"): series(*co, 1)})
    exps = [_mono("E1", "A", [(1, "r1")]), _mono("E2", "B", [(2, "r1")]),
            _co("E3", "A", "B", [(3, "r1")])]

    # with the real fit, A has an arc
    records, _ = IntegratedDeriver(client=client).derive({"id": "S1"}, exps)
    assert [r for r in records if r["target_name"] == "A"]

    real = integrated.two_stage

    def worse(target, monocultures, cocultures, organisms, max_condition=integrated.MAX_CONDITION):
        got = real(target, monocultures, cocultures, organisms, max_condition)
        return {**got, "r2": -0.5} if target == "A" else got

    monkeypatch.setattr(integrated, "two_stage", worse)
    records, skipped = IntegratedDeriver(client=client).derive({"id": "S1"}, exps)
    assert not [r for r in records if r["target_name"] == "A"]
    assert any("explains less of A's log abundance change" in reason for _, reason in skipped), skipped
    assert any("R2 -0.5" in reason for _, reason in skipped)


def test_an_organism_whose_fit_implies_no_plateau_keeps_its_measured_one():
    """A fit whose A_ii is not negative implies no plateau, and such an organism used to leave every
    matrix although its monocultures had reached a certified one. The diagonal is -r_i / K_i either way,
    so the measured plateau is used and named. Live, this is what brought two of the eight organisms of
    the whole-database package back, with the four cells that go with them (2026-10-06).

    Hand computed: the fit gives A a rate of 0.4 and no usable self-limitation, the monocultures measured
    a plateau of 1e9, so the capacity is 1e9 and the entry says where it came from.
    """
    fitted = {"a": {"name": "A", "rate": 0.4, "capacity": None, "capacity_unit": "", "capacity_n": 0},
              "b": {"name": "B", "rate": 0.2, "capacity": 5.0e8, "capacity_unit": "Cells/mL",
                    "capacity_n": 3}}
    measured = {"a": {"name": "A", "rate": 0.38, "capacity": 1.0e9, "capacity_unit": "Cells/mL",
                      "capacity_n": 4, "capacity_media": ["WC"], "capacity_per_study": {"S1": 1.0e9}},
                "b": {"name": "B", "rate": 0.21, "capacity": 9.9e8, "capacity_unit": "Cells/mL",
                      "capacity_n": 4}}
    filled, named = integrated.fill_capacities(fitted, measured)

    assert filled["a"]["capacity"] == 1.0e9 and filled["a"]["capacity_unit"] == "Cells/mL"
    assert filled["a"]["capacity_n"] == 4 and filled["a"]["capacity_media"] == ["WC"]
    assert "implies none" in filled["a"]["capacity_source"]
    assert named == [("A", 1.0e9)]
    # the rate stays the fit's own, since that is the parameter the coefficients were fitted with
    assert filled["a"]["rate"] == 0.4
    # and an organism the fit did pin keeps the fit's plateau, untouched
    assert filled["b"]["capacity"] == 5.0e8 and "capacity_source" not in filled["b"]


def test_the_monoculture_stage_pools_the_replicates_only_when_none_of_them_fits_alone():
    """Measured on the whole database and decided on 2026-10-06 (register, "Two improvements to the
    integrated form"): pooling every replicate's rows into one regression halves the worst coefficient
    spread and adds arcs, and it also flips three signs, which is what one outlying replicate does to a
    regression and not to a median. So the median of the separate fits stays the estimate, and pooling is
    what happens when no replicate identifies the row by itself.

    Three replicates of the same noiseless monoculture: each fits alone, so the median is used and the
    stage says so. Truncating each one to two rows leaves none of them fittable, and their rows together
    then give the same parameters, with the stage naming that route.
    """
    mono_times, mono_series = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    monos = [_named(["A"], mono_times, mono_series, f"m{k}") for k in range(3)]
    co_times, co_series = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])
    cos = [_named(["A", "B"], co_times, co_series, "c0")]

    got = integrated.two_stage("A", monos, cos, ["A", "B"])
    assert got["stages"][0] == "monoculture"
    assert got["rate"] == pytest.approx(0.4, rel=0.02)

    # three replicates of the same organism at different inocula, each cut to three measurements: two
    # rows apiece, too few for any of them to be fitted alone, and six rows together
    short = []
    for k, start in enumerate((1.0e7, 3.0e7, 9.0e7)):
        times, series = _simulate([0.4], [[-4.0e-10]], [start])
        short.append(_named(["A"], times[:3], series[:3], f"s{k}"))
    assert all(integrated.fit_row(r, "A", ["A"])["rate"] is None for r in short)

    pooled = integrated.two_stage("A", short, cos, ["A", "B"])
    assert pooled["stages"][0] == "monoculture (replicates pooled)"
    assert pooled["rate"] == pytest.approx(0.4, rel=0.02)        # the same parameters, from the rows
    assert pooled["coefficients"]["A"] == pytest.approx(-4.0e-10, rel=0.05)


def test_stage_one_takes_the_monocultures_of_this_experiments_own_condition():
    """#142 item 1, Karoline's rule of #47 and #81: replicate sets pool only across experiments with
    identical conditions, since interactions are environmentally specific. Stage 1 used to be every
    monoculture replicate of the organism anywhere in the study, so an organism grown at two
    concentrations gave one rate and one self-limitation over both; on SMGDB00000014 that pooled ten
    chemically different experiments whose implied plateaus span a factor of 5,500.

    Here A is grown alone at two concentrations: at the low one it plateaus at 1e9 (A_ii = -4e-10) and at
    the high one at 1e8 (A_ii = -4e-9), ten times lower. The co-culture words its growth the way the high
    one does, so stage 1 has to come from that monoculture alone, which `_choose_monocultures` picks by
    wording as it does for the specified comparison.
    """
    from test_growth_rates import _client, _co, _mono

    from grownet.integrated import IntegratedDeriver
    low = _simulate([0.4], [[-4.0e-10]], [1.0e7])            # plateaus at 1e9
    high = _simulate([0.4], [[-4.0e-9]], [1.0e7])            # plateaus at 1e8
    co = _simulate([0.4, 0.3], [[-4.0e-9, 2.0e-9], [0.0, -3.0e-10]], [1.0e7, 5.0e7])
    mono_b = _simulate([0.3], [[-3.0e-10]], [5.0e7])

    def series(times, values, which=0):
        return [(t, row[which], None) for t, row in zip(times, values, strict=True)]

    client = _client({(1, "A"): series(*low), (2, "A"): series(*high), (3, "B"): series(*mono_b),
                      (4, "A"): series(*co, 0), (4, "B"): series(*co, 1)})
    low_exp = {**_mono("E1", "A", [(1, "r1")]),
               "description": "A monoculture grown on a minimal medium with 0.05% acid"}
    high_exp = {**_mono("E2", "A", [(2, "r1")]),
                "description": "A monoculture grown on a minimal medium with 0.75% acid"}
    mono_b_exp = {**_mono("E3", "B", [(3, "r1")]), "description": "B monoculture grown on a medium"}
    co_exp = {**_co("E4", "A", "B", [(4, "r1")]),
              "description": "A+B co-culture grown on a minimal medium with 0.75% acid"}
    records, skipped = IntegratedDeriver(client=client).derive(
        {"id": "S1"}, [low_exp, high_exp, mono_b_exp, co_exp])

    arc = next(r for r in records if r["target_name"] == "A" and r["source_name"] == "B")
    # the self-limitation of the condition this co-culture was grown in, not a median over both
    assert arc["fitted_self"] == pytest.approx(-4.0e-9, rel=0.2)
    assert arc["fitted_self"] < -2.0e-9                      # nowhere near the low condition's -4e-10
    # and the row says which monoculture experiment it rests on, as the specified comparison does
    assert "E2" in arc["experiments"] and "E1" not in arc["experiments"]
    assert "E4" in arc["experiments"]
    assert not [row for row in skipped if "could not be identified" in row[1]]
