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
    assert len(design["rows"]) == len(times) - 1
    first = design["rows"][0]
    assert first["y"] == pytest.approx(math.log(series[1][0] / series[0][0]), rel=1e-9)
    assert first["time"] == pytest.approx(times[1] - times[0])
    # the integral of its own curve over that step, by the trapezoid rule
    expected = 0.5 * (series[0][0] + series[1][0]) * (times[1] - times[0])
    assert first["integrals"][0] == pytest.approx(expected, rel=1e-9)


def test_one_organism_recovers_its_own_rate_and_self_limitation():
    """The simplest check the whole task rests on: a logistic curve from r = 0.5 /h and A = -5e-10 is
    fitted back to those numbers, with no window and no plateau needed."""
    times, series = _simulate(*SOLO)
    fit = integrated.fit_row(_replicate(["A"], times, series), "A", ["A"])
    assert fit["rate"] == pytest.approx(0.5, rel=0.02)
    assert fit["coefficients"]["A"] == pytest.approx(-5.0e-10, rel=0.05)
    assert fit["r2"] > 0.99 and fit["points"] == len(times) - 1
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
    assert got["stages"] == ["monoculture", "co-culture"]


def test_a_curve_that_starts_at_zero_or_never_rises_gives_no_fit():
    times = [0.0, 1.0, 2.0, 3.0]
    flat = GrowthCurve(species="A", times=times, values=[0.0, 0.0, 0.0, 0.0], time_unit="h",
                       abundance_unit="Cells/mL")
    fit = integrated.fit_row(Replicate(curves=(flat,), name="r1"), "A", ["A"])
    assert fit["coefficients"] == {} and "no positive" in fit["reason"]
