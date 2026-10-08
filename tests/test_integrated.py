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
import statistics

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
    corrected for multiple testing. Stage 2 is now fitted once per co-culture replicate, with its exact
    derivative with respect to stage 1's two numbers beside it, and stage 1 is resampled over its own
    monoculture replicates, so the two sources of error are measured on disjoint designs and added
    (2026-10-07, #142 item 2; before that the spread mixed them in one set).

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
    assert spread["n"] == 3                  # one coefficient per co-culture replicate, nothing mixed in
    assert spread["median"] == pytest.approx(2.0e-10, rel=0.25)
    assert spread["sd"] is not None and spread["sd"] >= 0

    # stage 1's own error, on its own design: three monoculture replicates, bootstrapped
    assert got["stage_one_n"] == 3
    assert got["stage_one_method"].startswith("bootstrap of 3 monoculture replicate(s)")
    assert len(got["stage_one_draws"]) == integrated.STAGE_ONE_DRAWS
    # and every replicate carries the exact derivative of its coefficient with respect to (rate, self)
    assert [entry["replicate"] for entry in got["sensitivity"]] == ["c0", "c1", "c2"]
    assert all("B" in entry for entry in got["sensitivity"])

    # the arc statistics add the two: here the system is noiseless, so both parts are near zero
    stats_here = integrated._arc_statistics(got, cos, "B")
    assert stats_here["n"] == 3
    assert stats_here["se"] == pytest.approx(
        math.sqrt(stats_here["se_replicates"] ** 2 + stats_here["se_rate_stage"] ** 2), rel=1e-9)
    assert stats_here["strength"] == pytest.approx(statistics.mean(stats_here["per_replicate"]))

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


def test_a_fit_that_implies_no_plateau_takes_the_measured_one_before_its_partners_are_fitted(monkeypatch):
    """#142 item 7. A fit whose A_ii is not negative implies no plateau, and such an organism used to be
    given the measured one in `fill_capacities`, **after** its partners had been fitted against the fitted
    A_ii: the published row then satisfied no equation anyone had fitted, and its R2 and condition number
    described the row that was not published. On *S. thermophilus* the self term moved by 2.24 times the
    whole partner coefficient the row's claim rested on, and in the opposite direction.

    The substitution happens inside `two_stage` now, before stage 2.

    **Which route reaches it changed on 2026-10-08** (#160, Craig's agent's option 2). A single
    monoculture replicate whose fit implies no plateau is now refused outright, because a non-negative
    A_ii says the model does not describe that curve, so the per-replicate route to the substitution is
    gone. What remains, and what this test drives, is the pooled fallback: where no replicate's own rows
    identify the row, the rows are pooled, and if *that* fit implies no plateau the measured one is still
    the rescue. Refusing an individual bad curve and rescuing a stage where every curve together implies
    no plateau are different judgements, and both are kept.

    So the contrivance is on `_pooled_stage_one` rather than on `fit_row`, since a curve that plateaus
    will ordinarily fit a negative A_ii. The curves themselves do reach a certified plateau of 1e9, so
    the substitution has something to use.
    """
    # 40 h, long enough that the curve reaches its 1e9 plateau and holds it, so it certifies
    times, series = _simulate([0.4], [[-4.0e-10]], [1.0e7], t_end=40.0)
    monos = [_replicate(["A"], times, series) for _ in range(3)]
    co_times, co_series = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])
    cos = [_replicate(["A", "B"], co_times, co_series) for _ in range(2)]

    # no replicate's own fit is usable, so stage 1 falls to the pooled rows ...
    monkeypatch.setattr(integrated, "fit_row",
                        lambda *a, **k: {"rate": None, "coefficients": {}, "r2": float("nan"),
                                         "condition": float("inf"), "points": 0,
                                         "reason": "contrived: this replicate gives nothing"})
    # ... and the pooled fit implies no plateau, which is the case the substitution exists for
    real_pooled = integrated._pooled_stage_one

    def no_plateau(target, replicates, max_condition):
        got = real_pooled(target, replicates, max_condition)
        return None if got is None else (got[0], 0.0, got[2])

    monkeypatch.setattr(integrated, "_pooled_stage_one", no_plateau)
    got = integrated.two_stage("A", monos, cos, ["A", "B"])

    assert "measured plateau" in got["self_limitation_source"]
    assert "self-limitation from the measured plateau" in got["stages"]
    # the published self-limitation is -r/K at the measured plateau, exactly
    plateau = integrated._measured_plateau(monos, "A")
    assert plateau is not None and plateau[0] == pytest.approx(1.0e9, rel=0.01)
    assert got["coefficients"]["A"] == pytest.approx(-got["rate"] / plateau[0], rel=1e-9)
    # and the partner was fitted against that number, not against the one the fit implied: the row the
    # package publishes is the row that was fitted
    assert got["coefficients"].get("B") is not None


def test_the_retired_post_hoc_substitution_fills_nothing():
    """`fill_capacities` is a no-op for one release so that an outside caller does not break on an
    import. It published a row no fit had produced, which is why it is gone (#142 item 7)."""
    fitted = {"a": {"name": "A", "rate": 0.4, "capacity": None, "capacity_unit": "", "capacity_n": 0}}
    measured = {"a": {"name": "A", "rate": 0.38, "capacity": 1.0e9, "capacity_unit": "Cells/mL"}}
    out, named = integrated.fill_capacities(fitted, measured)
    assert named == [] and out["a"]["capacity"] is None


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


def test_disagreeing_monocultures_widen_the_arc_the_same_co_cultures_give():
    """#142 item 2: `sd`, `se`, `p_value` and therefore the absence threshold were computed from the
    co-culture replicates alone, so stage 1 was treated as exact in the one place that decides which arcs
    reach a file. The same co-cultures now give a wider arc when the monocultures they rest on disagree.

    Both runs use identical co-culture replicates. The first has three monocultures of one and the same
    organism; the second has three that imply plateaus a factor of three apart, so stage 1 is the same
    median with a real spread around it, and nothing about the co-cultures has changed.
    """
    r = [0.4, 0.3]
    A = [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]]
    cos = []
    for k, start in enumerate((1.0e7, 1.1e7, 0.9e7)):
        times, series = _simulate(r, A, [start, 5.0e8])
        cos.append(_named(["A", "B"], times, series, f"c{k}"))

    def monos_of(*selfs):
        out = []
        for k, own in enumerate(selfs):
            times, series = _simulate([0.4], [[own]], [1.0e7])
            out.append(_named(["A"], times, series, f"m{k}"))
        return out

    agreeing = integrated.two_stage("A", monos_of(-4.0e-10, -4.0e-10, -4.0e-10), cos, ["A", "B"])
    spread_out = integrated.two_stage("A", monos_of(-2.0e-10, -4.0e-10, -6.0e-10), cos, ["A", "B"])
    tight = integrated._arc_statistics(agreeing, cos, "B")
    wide = integrated._arc_statistics(spread_out, cos, "B")

    # the same co-culture replicates on both sides, so the replicate half is the same
    assert tight["n"] == wide["n"] == 3
    assert wide["se_replicates"] == pytest.approx(tight["se_replicates"], rel=0.3)
    # and the monoculture stage's half is what differs, which is the whole point
    assert tight["se_rate_stage"] == pytest.approx(0.0, abs=1e-9)
    assert wide["se_rate_stage"] > 10 * (tight["se_rate_stage"] or 1e-12)
    assert wide["se"] > tight["se"]
    # it reaches the test, which is what decides a q-value and a significance
    assert wide["p_value"] > tight["p_value"]
    # `sd` is the spread of one comparison, so it carries the stage too and widens with it: the absence
    # threshold reads it, and that is how the stage reaches the decision about presence.
    assert wide["sd"] > tight["sd"]
    # both components, and not `se * sqrt(n)`: a stage error shared by every replicate must not be
    # multiplied by their number, which made the threshold harder to pass the more replicates a row had
    for one in (tight, wide):
        replicate_spread = one["se_replicates"] * math.sqrt(one["n"])
        expected = math.sqrt((one["se_rate_stage"] or 0.0) ** 2 + replicate_spread ** 2)
        assert one["sd"] == pytest.approx(expected, rel=1e-9)
        assert one["sd"] != pytest.approx(one["se"] * math.sqrt(one["n"]), rel=1e-6) or not one["se_rate_stage"]


def test_the_fitted_parameters_do_not_depend_on_the_order_of_the_rows():
    """#142 item 4: `fitted_rates` kept the first row it met per organism (`nid in out: continue`), so an
    organism's rate, the plateau the fit implies, the diagonal -r/K, the printed equilibrium and the
    chemostat prediction were all "whichever arc the loop reached first". Every row is now merged by the
    median, which is the rule register item 14 sets for arcs and `derive.merge_rates` follows for the
    measured parameters.

    A is fitted in three rows, with rates 0.2, 0.4 and 0.9 and plateaus 1e9, 2e9 and 3e9. The median of
    each is what a package may publish, in any order the rows arrive.
    """
    rows = [
        {"target": "a", "target_name": "A", "fitted_rate": 0.2, "fitted_self": -2.0e-10,
         "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": "S1", "fit_points": 8,
         "fit_r2": 0.9, "fit_condition": 10.0},
        {"target": "a", "target_name": "A", "fitted_rate": 0.4, "fitted_self": -2.0e-10,
         "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": "S1", "fit_points": 9,
         "fit_r2": 0.8, "fit_condition": 40.0},
        {"target": "a", "target_name": "A", "fitted_rate": 0.9, "fitted_self": -3.0e-10,
         "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": "S2", "fit_points": 7,
         "fit_r2": 0.7, "fit_condition": 25.0},
    ]
    forward = integrated.fitted_rates(rows)["a"]
    backward = integrated.fitted_rates(list(reversed(rows)))["a"]
    assert forward == backward                       # the whole entry, not only the rate

    assert forward["rate"] == pytest.approx(0.4)     # the median of 0.2, 0.4 and 0.9
    assert forward["capacity"] == pytest.approx(2.0e9)   # of 1e9, 2e9 and 3e9
    assert forward["n"] == 3 and forward["capacity_n"] == 3
    assert forward["n_label"] == "fitted row(s)"      # not replicates: this path has no cultures of its own
    assert sorted(forward["studies"]) == ["S1", "S2"]
    assert forward["per_study"]["S1"] == pytest.approx(0.3)    # each study's own median
    assert forward["per_study"]["S2"] == pytest.approx(0.9)
    assert forward["capacity_per_study"]["S1"] == pytest.approx(1.5e9)
    assert forward["fit_r2"] == pytest.approx(0.8)             # the median R2 of the rows merged
    assert forward["fit_condition"] == pytest.approx(40.0)     # and the worst conditioning among them

    # keeping the first row would have given 0.2 and 1e9 one way and 0.9 and 3e9 the other
    assert forward["rate"] != pytest.approx(rows[0]["fitted_rate"])
    assert forward["rate"] != pytest.approx(rows[-1]["fitted_rate"])


def test_a_fitted_rate_in_another_unit_is_named_not_converted():
    """The rule the measured parameters follow across units, in the fitted ones too."""
    rows = [
        {"target": "a", "target_name": "A", "fitted_rate": 0.4, "fitted_self": -2.0e-10,
         "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": "S1", "fit_points": 8},
        {"target": "a", "target_name": "A", "fitted_rate": 9.6, "fitted_self": -2.0e-10,
         "fitted_rate_unit": "1/day", "fitted_self_unit": "Cells/mL", "study_id": "S2", "fit_points": 8},
        {"target": "a", "target_name": "A", "fitted_rate": 0.4, "fitted_self": -4.0e-10,
         "fitted_rate_unit": "1/h", "fitted_self_unit": "g/L", "study_id": "S3", "fit_points": 8},
    ]
    got = integrated.fitted_rates(rows)["a"]
    assert got["rate"] == pytest.approx(0.4) and got["unit"] == "1/h"
    assert got["other_units"] == ["S2 (1/day)"]
    assert got["capacity_unit"] == "Cells/mL" and got["capacity_n"] == 1
    assert got["other_capacity_units"] == ["S3 (g/L)"]


def test_replicates_that_measured_different_partners_are_not_pooled_into_one_design():
    """#142 item 12, found by Craig's agent on #134: `design` leaves a partner with no curve out of the
    columns, so a replicate's rows are as wide as that replicate's own partners, while the pooled
    fallback asked for the union. `_least_squares` then indexed past the short rows and raised
    `IndexError`, which no handler caught: the call sits inside the loop over every target in every
    experiment, so one organism in one experiment took out the whole run.

    The shape is ordinary: monocultures of A, co-cultures A+B and A+C, which is pairwise co-culture in a
    community of three. Here each partner is flat at zero throughout, so no single replicate identifies
    its own effect and the pooled fallback is the path taken.
    """
    times, series = _simulate([0.5], [[-5.0e-10]], [1.0e7])
    mono = _replicate(["A"], times, series)
    flat = [[row[0], 0.0] for row in series]
    with_b = _replicate(["A", "B"], times, flat)
    with_c = _replicate(["A", "C"], times, flat)

    got = integrated.two_stage("A", [mono, mono, mono], [with_b, with_c], ["A", "B", "C"])
    assert got["rate"] is not None                       # it returns rather than raising
    # neither partner's effect is identified by a column of zeros, and A's own row still is
    assert "A" in got["coefficients"]
    # and the set left out of the pooled design is named rather than mixed in
    left_out = [why for what, why in got["skipped"] if "left out of the pooled fit" in why]
    assert len(left_out) == 1
    assert "not a partner at zero" in left_out[0]


def test_the_pooled_fallback_uses_the_largest_set_of_replicates_sharing_their_partners():
    """Two replicates measured A with B and one measured A with B and C: the pair is the larger set, so
    the pooled fit is of B, and the row that also measured C is named. Whichever order they arrive in."""
    times, series = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])
    mono_times, mono_series = _simulate([0.4], [[-4.0e-10]], [1.0e7])
    mono = _replicate(["A"], mono_times, mono_series)
    flat_three = [[row[0], row[1], 0.0] for row in series]
    pair = [_replicate(["A", "B"], times, series), _replicate(["A", "B"], times, series)]
    trio = _replicate(["A", "B", "C"], times, flat_three)

    for order in ([*pair, trio], [trio, *pair]):
        got = integrated.two_stage("A", [mono, mono, mono], order, ["A", "B", "C"])
        pooled = [why for what, why in got["skipped"] if "left out of the pooled fit" in why]
        if pooled:                                        # only when the fallback was the path taken
            assert "A, B, C" in pooled[0] or "B, C" in pooled[0]
        assert "C" not in got["coefficients"] or got["coefficients"].get("C") is not None


def test_the_fit_is_scored_only_over_the_replicates_stage_two_used():
    """#142 item 9: `_overall_r2` scored every co-culture replicate, including ones stage 2 had refused,
    so a replicate the fit never saw could discard a whole organism through the R2 gate. It is now given
    the replicates stage 2 used, and it scores the interaction-free null beside the fit."""
    times, series = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])
    mono_times, mono_series = _simulate([0.4], [[-4.0e-10]], [1.0e7], t_end=40.0)
    monos = [_replicate(["A"], mono_times, mono_series) for _ in range(3)]
    good = _named(["A", "B"], times, series, "c0")
    # a replicate whose partner is flat at zero: stage 2 cannot identify it, so it is not used
    flat = _named(["A", "B"], times, [[row[0], 0.0] for row in series], "c1")

    got = integrated.two_stage("A", monos, [good, flat], ["A", "B"])
    assert [entry["replicate"] for entry in got["per_replicate"]] == ["c0"]
    only_good = integrated.two_stage("A", monos, [good], ["A", "B"])
    # the same rows are scored either way, since the refused replicate is not scored
    assert got["scored_rows"] == only_good["scored_rows"]
    assert got["r2"] == pytest.approx(only_good["r2"], rel=1e-9)
    # and the null is there to compare against: B does affect A, so the fit beats it
    assert got["null_r2"] == got["null_r2"]            # not nan
    assert got["r2"] > got["null_r2"]


def test_the_mismatch_that_would_zero_an_arc_is_minus_a_over_the_rate_times_the_derivative():
    """`rate_mismatch_to_zero` by hand, with no fitting in the way.

    A rate `r (1 + d)` moves a coefficient to `A + (dA/dr) r d`, exactly, because stage 2's solution is
    affine in the rate. Setting that to zero gives `d = -A / (r dA/dr)`. With r = 4, one replicate at
    A = 2 and dA/dr = 0.5, that is -2 / (0.5 * 4) = -1.0; a second at A = -3 and dA/dr = 0.5 gives
    3 / 2 = 1.5; the arc reports their median, which with a third replicate at -1.0 is -1.0.
    """
    rows = [(2.0, (0.5, 0.0), 1.0, 0.0), (-3.0, (0.5, 0.0), 1.0, 0.0), (1.0, (-0.25, 0.0), 1.0, 0.0)]
    assert integrated._mismatch_to_zero(rows[:1], 4.0) == pytest.approx(-1.0)
    assert integrated._mismatch_to_zero(rows[1:2], 4.0) == pytest.approx(1.5)
    assert integrated._mismatch_to_zero(rows[2:], 4.0) == pytest.approx(1.0)
    assert integrated._mismatch_to_zero(rows, 4.0) == pytest.approx(1.0)      # median of -1.0, 1.5, 1.0
    # a replicate whose derivative is zero contributes nothing: no change in the rate reaches that arc
    assert integrated._mismatch_to_zero([(2.0, (0.0, 0.0), 1.0, 0.0)], 4.0) is None
    assert integrated._mismatch_to_zero([(2.0, None, 1.0, 0.0)], 4.0) is None
    assert integrated._mismatch_to_zero(rows, 0.0) is None                    # no rate, no fraction of it


def test_the_mismatch_that_would_zero_an_arc_recovers_a_planted_rate_mismatch():
    """The truth: B has no effect on A, A_AB = 0 exactly. The only departure from the ideal is that A's
    monocultures were grown at 0.90 times the rate A had in the co-culture, which is the ordinary case
    where the recorded conditions match and the biology did not. Stage 1 is held fixed in stage 2, so the
    arc is the only parameter left to absorb the mismatch and a facilitation arc appears that is not
    there (#155 item 1).

    The rate the fit holds is 0.90 r, and the rate that would explain the arc away is r, which is higher
    by 1 / 0.90 - 1 = 0.1111. `rate_mismatch_to_zero` is that number, to three decimals.
    """
    rates, effects, start = [0.4, 0.3], [[-4.0e-10, 0.0], [0.0, -3.0e-10]], [1.0e7, 5.0e8]
    co_times, co_series = _simulate(rates, effects, start)
    cos = [_named(["A", "B"], co_times, co_series, f"c{k}") for k in range(3)]
    for bias, expected in ((1.00, 0.0), (0.90, 1.0 / 0.90 - 1.0), (1.20, 1.0 / 1.20 - 1.0)):
        mono_times, mono_series = _simulate([rates[0] * bias], [[effects[0][0]]], [start[0]], t_end=40.0)
        monos = [_named(["A"], mono_times, mono_series, f"m{k}") for k in range(3)]
        got = integrated.two_stage("A", monos, cos, ["A", "B"])
        stats = integrated._arc_statistics(got, cos, "B")
        assert stats["rate_mismatch_to_zero"] == pytest.approx(expected, abs=5e-4), bias


def test_the_fitted_window_is_measured_against_the_whole_course():
    """Karoline, 2026-10-07: "the effect 1 organism has on another can change along the growth curve.
    this is not something we treat here, but something we can warn about."

    The model has no death term, so the rows stop at the end of the plateau after the maximum. This curve
    rises for 10 h and then falls back for another 30, measured every 2 h: the fit covers 0 to 12 h of the
    40 measured, a share of 0.3, and the arc carries the window_partial caution below half.
    """
    times = [2.0 * k for k in range(21)]                       # 0 to 40 h
    rise = [1.0e7 * math.exp(0.4 * t) for t in times[:6]]      # 0 to 10 h, growing
    peak = rise[-1]
    fall = [peak * math.exp(-0.15 * (t - 10.0)) for t in times[6:]]
    series = [[v] for v in rise + fall]
    rep = _named(["A"], times, series, "r1")
    window = integrated.fitted_window([rep], "A")
    assert (window["span_start"], window["span_end"]) == (0.0, 40.0)
    assert window["start"] == 0.0 and window["end"] == pytest.approx(12.0)
    assert window["share"] == pytest.approx(12.0 / 40.0)
    assert window["unit"] == "h"
    assert window["share"] < integrated.WINDOW_SHARE_CAUTION
    # an organism this replicate does not hold has no window at all, rather than a window of zero
    assert integrated.fitted_window([rep], "B") == {}
    # a course fitted end to end covers all of itself
    growing = _named(["A"], times, [[1.0e7 * math.exp(0.08 * t)] for t in times], "r2")
    assert integrated.fitted_window([growing], "A")["share"] == pytest.approx(1.0)


def test_the_published_rate_says_how_many_cultures_it_rests_on_not_how_many_rows():
    """#155 item 13. `growth_rates.csv`'s `replicates` column has meant monoculture replicates since
    0.2.0, where it was right because the only derivation compared replicate sets. This derivation merges
    fitted rows, and writing that row count into the column made a rate from three monocultures read as
    resting on one culture, which is how the gLV example's thinness went unnoticed: the example's
    *S. thermophilus* rate really does rest on one replicate of three, and nothing distinguished it.

    Two arcs for one organism, both fitted from the same three monocultures: `n` is 2 rows, `replicates`
    is 3 cultures, and the capacity, which is -r/A_ii from that same stage, rests on those 3 too.
    """
    records = [{"target": "ncbi:1", "target_name": "A", "fitted_rate": 0.4, "fitted_self": -4.0e-10,
                "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": "S1",
                "rate_stage_n": 3, "fit_points": 7},
               {"target": "ncbi:1", "target_name": "A", "fitted_rate": 0.5, "fitted_self": -5.0e-10,
                "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": "S1",
                "rate_stage_n": 3, "fit_points": 7}]
    got = integrated.fitted_rates(records)["ncbi:1"]
    assert got["n"] == 2 and got["n_label"] == "fitted row(s)"      # what the median was taken over
    assert got["replicates"] == 3                                   # what the rate itself rests on
    assert got["capacity_curves"] == 3
    assert got["rate"] == pytest.approx(0.45)                       # the median of the two rows

    # a row whose stage was never resampled reports no replicate count rather than inventing one
    thin = integrated.fitted_rates([{**records[0], "rate_stage_n": None}])["ncbi:1"]
    assert thin["replicates"] is None and thin["n"] == 1


def test_the_rates_csv_writes_cultures_under_replicates_for_either_derivation():
    """The column means one thing whichever derivation filled it: the replicate path has no `replicates`
    key and its `n` already counts cultures, so it is written unchanged."""
    from grownet import matrix

    integrated_entry = {"name": "A", "rate": 0.45, "unit": "1/h", "n": 2, "n_label": "fitted row(s)",
                        "replicates": 3, "studies": ["S1"], "method": "integrated:two_stage",
                        "lag": None, "capacity": 9.0e8, "capacity_unit": "Cells/mL", "capacity_n": 2,
                        "capacity_curves": 3}
    replicate_entry = {"name": "B", "rate": 0.30, "unit": "1/h", "n": 4, "studies": ["S1"],
                       "method": "easylinear", "lag": None, "capacity": 7.0e8,
                       "capacity_unit": "Cells/mL", "capacity_n": 4}
    rows = [line.split(",") for line in
            matrix.rates_csv({"a": integrated_entry, "b": replicate_entry}).strip().splitlines()]
    head = rows[0]
    assert head[3] == "replicates" and head[10] == "capacity_curves"
    by = {r[0]: r for r in rows[1:]}                     # without a network the row is keyed by node id
    assert by["a"][3] == "3" and by["a"][10] == "3"      # the cultures, not the 2 rows
    assert by["b"][3] == "4" and by["b"][10] == "4"      # unchanged where n already counts cultures


def test_the_rate_rule_does_not_claim_one_merge_where_there_are_two():
    from grownet import matrix

    assert "median over the fitted rows" in matrix.rate_rule("integrated:two_stage")
    assert "monoculture replicates" in matrix.rate_rule("integrated:two_stage")
    assert matrix.rate_rule("easylinear").endswith("median over replicates and studies; "
                                                   "batch experiments only")


def _rate_record(medium, rate, own, study="S1", fall=None):
    return {"target": "ncbi:1", "target_name": "A", "fitted_rate": rate, "fitted_self": own,
            "fitted_rate_unit": "1/h", "fitted_self_unit": "Cells/mL", "study_id": study,
            "rate_stage_n": 3, "fit_points": 7, "medium": medium, "fitted_capacity_fall": fall}


def test_a_fitted_capacity_comes_from_one_medium_as_the_decision_says():
    """Karoline, 2026-10-07: a capacity comes from one medium, and plateaus are not pooled across media,
    since a capacity sits beside off-diagonals measured in one of them. `derive.merge_rates` did that for
    the specified comparison; this path took the median over every fitted row whatever the medium, so the
    decision held for one derivation and not for the default (#155 item 2).

    Three rows: two in minimal medium with linoleic acid, one in the same medium with an antioxidant as
    well. The plateaus a fit implies are -r/A_ii, so 0.4/4e-10 = 1e9 and 0.4/8e-10 = 5e8 in the first
    medium and 0.4/1e-10 = 4e9 in the second. The first medium has more rows, so the capacity is the
    median of its two, 7.5e8, and the other medium is named rather than pooled in. Pooling all three
    would give 1e9, the median of the three.
    """
    acid = "Minimal medium (MM) (+0.75% linoleic acid)"
    both = "Minimal medium (MM) (+0.0015mm tbhq antioxidant, +0.75% linoleic acid)"
    got = integrated.fitted_rates([_rate_record(acid, 0.4, -4.0e-10), _rate_record(acid, 0.4, -8.0e-10),
                                   _rate_record(both, 0.4, -1.0e-10)])["ncbi:1"]
    assert got["capacity"] == pytest.approx(7.5e8)       # not 1e9, which is the median of all three
    assert got["capacity_n"] == 2
    assert got["capacity_medium"] == acid
    assert got["capacity_media"] == [acid] and got["capacity_other_media"] == [both]
    left_out = got["capacity_left_out"]
    assert len(left_out) == 1 and "1 fitted row(s)" in left_out[0][0] and both in left_out[0][0]
    assert "not pooled across media" in left_out[0][1]
    # the rate itself is still the median over every row, whatever the medium: a rate is a property of
    # the organism in each medium it was measured in, and only the plateau is the one the matrix sits on
    assert got["rate"] == pytest.approx(0.4)


def test_the_fall_from_peak_is_published_where_a_curve_reached_the_plateau():
    """`capacity_fall_from_peak` is documented as published beside the capacity. On this path the fall
    was measured inside `_measured_plateau` and discarded, so the column was always empty; it is now
    carried where the capacity is a measured plateau, and stays empty where the fit implied one, since
    there no curve exists whose fall could be measured (#155 item 2)."""
    one = "Wilkins-Chalgren Anaerobe Broth"
    measured = integrated.fitted_rates([_rate_record(one, 0.4, -4.0e-10, fall=1.33),
                                        _rate_record(one, 0.4, -4.0e-10, fall=1.41)])["ncbi:1"]
    assert measured["capacity_fall"] == pytest.approx(1.37)        # the median of the two
    implied = integrated.fitted_rates([_rate_record(one, 0.4, -4.0e-10)])["ncbi:1"]
    assert implied["capacity"] == pytest.approx(1.0e9) and implied["capacity_fall"] is None


def test_the_measured_plateau_reports_how_far_its_curves_fell():
    """One curve that ended at its peak and one that ended a third below it: the plateau is the median of
    the two maxima and the fall is the median of the two falls."""
    times = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
    held = [1.0e7 * min(math.exp(0.6 * t), 50.0) for t in times]          # rises, then holds
    fell = [v for v in held[:-2]] + [held[-1] / 3.0, held[-1] / 3.0]      # rises, then falls to a third
    reps = [_named(["A"], times, [[v] for v in held], "r1"),
            _named(["A"], times, [[v] for v in fell], "r2")]
    got = integrated._measured_plateau(reps, "A")
    assert got is not None
    plateau, unit, curves, fall = got
    assert curves == 2 and unit == "Cells/mL"
    assert plateau == pytest.approx(5.0e8)          # both peak at the same ceiling
    assert fall == pytest.approx((1.0 + 3.0) / 2)   # one curve at its peak, one a third below it


def test_a_monoculture_fit_is_refused_for_model_failure_not_for_the_rates_sign():
    """#160, Karoline taking Craig's agent's option 2 on 2026-10-08.

    The guard used to refuse a monoculture replicate whose fitted RATE was not positive. His argument,
    which the live data bears out: that is selection rather than filtering, and it selects for noise. On
    SMGDB00000006's *S. thermophilus* the three replicates fitted rates -0.1121, -0.1051 and +0.0109
    with self-limitations +4.357, +4.276 and +1.595. The self-limitation agrees, all three failing the
    same way; only the rate's sign disagrees. So the old guard keyed on the unstable statistic and kept
    whichever replicate landed above zero, and because only a near-zero positive can survive that cut,
    the survivor is biased toward zero by construction. The output of a selection then published as a
    measurement, with `rate_stage_n` 1.

    A non-negative `A_ii` is no self-limitation, so the fit implies no plateau and an unbounded culture,
    and that is the direct answer to "does the model describe this curve". A non-positive rate is still
    refused, because the whole row divides by it.
    """
    times, series = _simulate([0.4], [[-4.0e-10]], [1.0e7], t_end=40.0)
    good = _named(["A"], times, series, "good")
    co_times, co_series = _simulate([0.4, 0.3], [[-4.0e-10, 2.0e-10], [0.0, -3.0e-10]], [1.0e7, 5.0e8])
    cos = [_named(["A", "B"], co_times, co_series, f"c{k}") for k in range(2)]

    # a replicate whose fit has failed in the way STpos's three did: a positive self-limitation, and a
    # small positive rate that the old guard would have waved through
    real = integrated.fit_row

    def failed(replicate, target, organisms, *args, **kwargs):
        got = real(replicate, target, organisms, *args, **kwargs)
        if replicate.name == "failed" and len(organisms) == 1:
            got["rate"], got["coefficients"][target] = 0.0109, 1.595
        return got

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as m:
        m.setattr(integrated, "fit_row", failed)
        failing = _named(["A"], times, series, "failed")
        got = integrated.two_stage("A", [good, failing], cos, ["A", "B"])
        why = dict(got["skipped"])
        key = next(k for k in why if "failed" in k)
        assert "self-limitation of 1.595" in why[key]
        assert "implies no plateau" in why[key] and "whatever its rate came out as" in why[key]
        # the good replicate alone carries the stage, so the failed one's near-zero rate is nowhere near
        assert got["rate"] == pytest.approx(0.4, rel=0.02)
        assert got["stage_one_n"] == 1

    # and a non-positive rate is still refused, on its own wording
    def no_growth(replicate, target, organisms, *args, **kwargs):
        got = real(replicate, target, organisms, *args, **kwargs)
        if replicate.name == "failed" and len(organisms) == 1:
            got["rate"], got["coefficients"][target] = -0.05, -4.0e-10
        return got

    with _pytest.MonkeyPatch.context() as m:
        m.setattr(integrated, "fit_row", no_growth)
        got = integrated.two_stage("A", [good, _named(["A"], times, series, "failed")], cos, ["A", "B"])
        why = dict(got["skipped"])
        key = next(k for k in why if "failed" in k)
        assert "rate of -0.05" in why[key] and "which is not growth" in why[key]
