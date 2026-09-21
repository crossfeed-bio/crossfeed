"""The statistics crossfeed reports, in the standard library only.

Welch's t-test compares the per-replicate log2 values with and without a partner, and Benjamini-Hochberg
corrects the resulting p-values for the number of comparisons tested in one derivation. Neither decides
whether an edge exists (that is the mean plus or minus its standard deviation, see
`crossfeed.derive.classify`): a significant result supports an edge, and a non-significant one is not
informative (Karoline, on #40). They are reported on each edge so a reader can weigh the evidence.

The t distribution comes from the regularized incomplete beta function (continued fraction, as in
Numerical Recipes), since the standard library has no Student's t. It is checked against printed
critical values in the tests.
"""
from __future__ import annotations

import math
import statistics

_TINY = 1e-300


def _beta_fraction(a: float, b: float, x: float, eps: float = 3e-14, max_iter: int = 300) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                   -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > _TINY else _TINY)
            c = 1.0 + aa / c
            c = c if abs(c) > _TINY else _TINY
            h *= d * c
        if abs(d * c - 1.0) < eps:
            break
    return h


def incomplete_beta(a: float, b: float, x: float) -> float:
    """The regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """The cumulative distribution function of Student's t with `df` degrees of freedom."""
    tail = 0.5 * incomplete_beta(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t > 0 else tail


def welch(x, y) -> dict | None:
    """Welch's two-sided t-test of mean(x) against mean(y), or None with fewer than two values per side.

    Returns {"t", "df", "p"}. When neither side varies, the p-value is 0 if the means differ and 1 if not.
    """
    if len(x) < 2 or len(y) < 2:
        return None
    vx, vy = statistics.variance(x), statistics.variance(y)
    nx, ny = len(x), len(y)
    diff = statistics.mean(x) - statistics.mean(y)
    se2 = vx / nx + vy / ny
    if se2 == 0:
        return {"t": math.inf if diff else 0.0, "df": math.inf, "p": 0.0 if diff else 1.0}
    df = se2 ** 2 / ((vx / nx) ** 2 / (nx - 1) + (vy / ny) ** 2 / (ny - 1))
    t = diff / math.sqrt(se2)
    return {"t": t, "df": df, "p": min(1.0, 2.0 * (1.0 - t_cdf(abs(t), df)))}


def benjamini_hochberg(p_values) -> list:
    """Benjamini-Hochberg adjusted p-values, in the input order; None entries stay None and do not count."""
    indexed = [(p, i) for i, p in enumerate(p_values) if p is not None]
    m = len(indexed)
    adjusted = [None] * len(p_values)
    running = 1.0
    for rank, (p, i) in reversed(list(enumerate(sorted(indexed), start=1))):
        running = min(running, p * m / rank)
        adjusted[i] = running
    return adjusted
