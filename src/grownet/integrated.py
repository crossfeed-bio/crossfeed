"""Fitting a gLV row from the whole time course: the integrated form (#127).

Karoline, 2026-10-06, on the shortlist of #124: "OK for 3, as an advanced option". So this is the
arithmetic of a second derivation, selected in Advanced settings, and the default one does not change.

Integrating `dx_i/dt = x_i (r_i + sum_j A_ij x_j)` over a replicate's measured span gives

    ln( x_i(T) / x_i(0) ) = r_i * T + sum_j A_ij * integral( x_j dt )

which is **linear in r_i and in every A_ij**, so one least-squares fit per organism returns its whole row:
no growth-rate window, no log2 ratio, no certified plateau, and no choice of `x_j_star`, since the
regressor is the time integral of the partner's own curve.

What the measurement on #116 showed, and why `two_stage` exists: inside one experiment the integrals of
two organisms that rise together correlate (at +0.977 on SMGDB00000004), and the fit then splits an
organism's own limitation from its partner's effect badly. The monocultures identify `r_i` and `A_ii`
cleanly, so those are fitted first and held fixed while the co-cultures give the partners' coefficients.
Every fit reports its condition number and its residual, and a fit that is not identified is named rather
than published as a number.

Standard library only: the normal equations of a design this small are solved by Gaussian elimination.
"""
from __future__ import annotations

import math
import random
import statistics

# Above this condition number the columns are too close to tell apart, and the split between an
# organism's own limitation and its partner's effect is not identified by this design. It is measured on
# the design with each column scaled to unit length, so it reports collinearity and not the scale
# difference between an elapsed time (tens) and an abundance integral (billions). Two columns correlating
# at the +0.977 measured on #116 give about 86, so this limit keeps such a fit and reports its number,
# and refuses only a design whose columns are near duplicates. The number is the condition number of the
# normal equations, the square of the design's own, so 1e4 here is a design conditioned at 100: it
# refuses a numerically degenerate design and does not judge whether the split between an organism's own
# limitation and its partner's effect is well determined. The reported condition is the largest over the
# stages, and a biculture's partner stage has one column, whose scaled normal matrix is [[1.0]], so the
# monoculture stage is what that number describes (stated 2026-10-06).
MAX_CONDITION = 1.0e4
MIN_ROWS = 3            # fewer rows than unknowns plus one, and nothing can be fitted
# A free constant in each fit, which would absorb an error in the first measurement, was measured on the
# whole database and left out: the constant it wants is a median factor of 7 on x(0), which is misfit on a
# short window rather than a measurement error, and it costs a parameter where the rows are fewest
# (2026-10-06; the numbers are in docs/METHOD_NOTES.md).


def _trapezoid(times: list, values: list) -> list:
    """The running integral of a curve by the trapezoid rule, one entry per measured point."""
    out = [0.0]
    for i in range(1, len(times)):
        out.append(out[-1] + 0.5 * (values[i] + values[i - 1]) * (times[i] - times[i - 1]))
    return out


def lag_of(curve) -> float:
    """Where growth starts on this curve, from the Baranyi fit, or 0.0 when it has none to give.

    The integrated form has no lag term: a culture that sits at its inoculum for an hour and then grows
    makes `ln(x(T)/x(0))` smaller than the model expects, and the fit pays for it by trading the rate
    against the self-limitation, which is how r came out negative on SMGDB00000007. So the integral starts
    where growth starts, which is the lag #118 reports (Karoline, 2026-10-06, asking for exactly that use:
    "so the integrated form depends on identifying lag phase. what if Baranyi is used to determine r?").
    """
    from . import rates as rate_fits

    try:
        fit = rate_fits.baranyi_fit(list(curve.times), list(curve.values))
    except Exception:          # noqa: BLE001 - a curve the model rejects simply has no lag to report
        return 0.0
    lag = fit.get("lag") or 0.0
    span = curve.times[-1] - curve.times[0]
    # a lag longer than half the run would leave too little to fit, so it is not used
    return lag if 0.0 < lag < 0.5 * span else 0.0


def growth_window(curve, start: float) -> float:
    """Where to stop integrating: the end of the plateau after the curve's maximum.

    The model has no death term either, so a curve that declines after its peak reads as a stronger
    self-limitation and a smaller rate, which is what left SMGDB00000007's rates near zero. The rule that
    says where growth ends is already agreed and used by the Baranyi fit (register item 29,
    `rates._until_decline`): the plateau goes on while the log abundance stays within a share of the rise
    below the maximum, and ends at the first point under that.
    """
    from .rates import _positive_logs, _until_decline

    xs, ys = _positive_logs(list(curve.times), list(curve.values))
    inside = [(x, y) for x, y in zip(xs, ys, strict=True) if x >= start - 1e-9]
    if len(inside) < 3:
        return curve.times[-1]
    cut_xs, _ = _until_decline([x for x, _ in inside], [y for _, y in inside])
    return cut_xs[-1] if cut_xs else curve.times[-1]


def design(replicate, target: str, organisms: list, start: float = None, end: float = None) -> dict:
    """The rows of the regression for one organism in one replicate.

    `start` is where the integration begins, which defaults to the end of the target's own lag: the model
    has no lag term, so the rows start where growth does (`lag_of`). Every curve is read from that time,
    the target's own first value is the one there, and the integrals start there too.

    {"partners": [names in column order], "rows": [{"y", "time", "integrals"}], "reason"}: `y` is
    `ln(x_i(t) / x_i(0))`, `time` is the elapsed time, and `integrals` holds the time integral of each
    organism present, in `partners` order. A partner with no curve in this replicate is left out of the
    columns and named in `reason`, since a column of zeros would claim it was absent rather than
    unmeasured.
    """
    own = replicate.curve(target)
    if own is None:
        return {"partners": [], "rows": [], "reason": f"{target} was not measured in this replicate"}
    begin = lag_of(own) if start is None else start
    stop = growth_window(own, begin) if end is None else end
    whole = list(own.times)
    keep = [k for k, t in enumerate(whole) if begin - 1e-9 <= t <= stop + 1e-9]
    times = [whole[k] for k in keep]
    values = [list(own.values)[k] for k in keep]
    if not values or values[0] <= 0 or max(values) <= 0:
        return {"partners": [], "rows": [],
                "reason": f"no positive abundance to start from for {target} in this replicate"}
    partners, integrals, missing = [], [], []
    for name in organisms:
        curve = replicate.curve(name)
        if curve is None:
            missing.append(name)
            continue
        if list(curve.times) != whole:
            missing.append(name)
            continue
        partners.append(name)
        integrals.append(_trapezoid(times, [list(curve.values)[k] for k in keep]))
    rows = []
    for k in range(1, len(times)):
        if values[k] <= 0:
            continue
        rows.append({"y": math.log(values[k] / values[0]), "time": times[k] - times[0],
                     "integrals": [column[k] for column in integrals]})
    reason = ""
    if begin > whole[0] or stop < whole[-1]:
        reason = (f"the rows cover {begin:g} to {stop:g}, where growth starts and where it ends "
                  "(the model has no lag and no death)")
    if missing:
        reason = (f"{', '.join(missing)} not measured on the same time points in this replicate, so "
                  "no column for it")
    return {"partners": partners, "rows": rows, "reason": reason}


def _solve(matrix: list, rhs: list):
    """Gaussian elimination with partial pivoting, or None when the system is singular."""
    n = len(rhs)
    work = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(work[r][col]))
        if abs(work[pivot][col]) < 1e-300:
            return None
        work[col], work[pivot] = work[pivot], work[col]
        for r in range(n):
            if r == col:
                continue
            factor = work[r][col] / work[col][col]
            for k in range(col, n + 1):
                work[r][k] -= factor * work[col][k]
    return [work[i][n] / work[i][i] for i in range(n)]


def _condition(normal: list) -> float:
    """A condition number of the normal equations: the ratio of the largest to the smallest eigenvalue of
    a symmetric positive matrix, found by power iteration on it and on its inverse, which needs no
    third-party linear algebra. Infinity when it is singular."""
    n = len(normal)
    if not n:
        return float("inf")

    def power(apply) -> float:
        vector = [1.0] * n
        value = 0.0
        for _ in range(200):
            nxt = apply(vector)
            if nxt is None:
                return float("inf")
            size = math.sqrt(sum(v * v for v in nxt))
            if size <= 0:
                return 0.0
            vector = [v / size for v in nxt]
            value = size
        return value

    biggest = power(lambda v: [sum(normal[i][j] * v[j] for j in range(n)) for i in range(n)])
    inverse_biggest = power(lambda v: _solve([row[:] for row in normal], v))
    if not biggest or inverse_biggest in (0.0, float("inf")):
        return float("inf")
    return biggest * inverse_biggest


def _least_squares(rows: list, columns: int) -> dict:
    """The least-squares solution of these rows, with its residual and the design's condition number.

    Each column is scaled to unit length before the normal equations are formed, so the condition number
    measures how close the columns are to each other rather than how different their units are, and the
    solution is scaled back afterwards.
    """
    design_rows = [list(row["columns"]) for row in rows]
    ys = [row["y"] for row in rows]
    width = columns
    sizes = [math.sqrt(sum(r[i] * r[i] for r in design_rows)) or 1.0 for i in range(width)]
    scaled = [[r[i] / sizes[i] for i in range(width)] for r in design_rows]
    normal = [[sum(r[i] * r[j] for r in scaled) for j in range(width)] for i in range(width)]
    rhs = [sum(r[i] * y for r, y in zip(scaled, ys, strict=True)) for i in range(width)]
    condition = _condition(normal)
    answer = _solve([row[:] for row in normal], rhs)
    if answer is None:
        return {"values": None, "condition": float("inf"), "r2": float("nan")}
    answer = [a / size for a, size in zip(answer, sizes, strict=True)]
    fitted = [sum(a * b for a, b in zip(row, answer, strict=True)) for row in design_rows]
    mean = sum(ys) / len(ys)
    total = sum((y - mean) ** 2 for y in ys)
    residual = sum((y - f) ** 2 for y, f in zip(ys, fitted, strict=True))
    r2 = 1 - residual / total if total > 0 else float("nan")
    return {"values": answer, "condition": condition, "r2": r2, "residual": residual}


def fit_row(replicate, target: str, organisms: list, max_condition: float = MAX_CONDITION,
            start: float = None, end: float = None) -> dict:
    """One organism's whole row from one replicate's time course.

    {"rate", "coefficients": {organism: A_ij}, "r2", "condition", "points", "reason"}. `coefficients` is
    empty with a `reason` when the design cannot identify the row: too few points, no positive abundance,
    or a condition number above `max_condition`, which is the collinearity measured on #116.
    """
    built = design(replicate, target, organisms, start, end)
    rows = built["rows"]
    if len(rows) < MIN_ROWS or not built["partners"]:
        return {"rate": None, "coefficients": {}, "r2": float("nan"), "condition": float("inf"),
                "points": len(rows),
                "reason": built["reason"] or f"{len(rows)} usable time point(s), too few to fit a row"}
    got = _least_squares([{"y": row["y"], "columns": [row["time"], *row["integrals"]]} for row in rows],
                         1 + len(built["partners"]))
    answer, condition = got["values"], got["condition"]
    if answer is None or condition > max_condition:
        return {"rate": None, "coefficients": {}, "r2": got["r2"], "condition": condition,
                "points": len(rows),
                "reason": ("the row is not identified by this design: the elapsed time and the partners' "
                           f"integrals rise too nearly together (condition {condition:.3g})")}
    return {"rate": answer[0],
            "coefficients": dict(zip(built["partners"], answer[1:], strict=True)),
            "r2": got["r2"], "condition": condition, "points": len(rows),
            "reason": built["reason"]}


def _spread(values: list) -> dict:
    """{"n", "median", "sd"} of a set of estimates of one coefficient, or n = 0 when there are none."""
    if not values:
        return {"n": 0, "median": None, "sd": None}
    return {"n": len(values), "median": statistics.median(values),
            "sd": statistics.stdev(values) if len(values) > 1 else None}


def _overall_r2(target: str, partners: list, cocultures: list, rate: float, own: float,
                coefficients: dict) -> float:
    """How much of the organism's own log abundance change the whole fit explains, over its co-cultures.

    `_least_squares` reports the R2 of the stage it ran, and stage 2 runs against stage 1's residual, so
    its number answers a smaller question than the help's words. This one compares the model's prediction,
    `r_i t + A_ii integral(x_i) + sum_j A_ij integral(x_j)`, with the measured `ln(x_i(t) / x_i(0))`.
    """
    ys, predicted = [], []
    for replicate in cocultures:
        built = design(replicate, target, [target, *partners])
        here = built["partners"]
        if target not in here:
            continue
        own_index = here.index(target)
        for row in built["rows"]:
            value = rate * row["time"] + own * row["integrals"][own_index]
            for name in partners:
                if name in here and name in coefficients:
                    value += coefficients[name] * row["integrals"][here.index(name)]
            ys.append(row["y"])
            predicted.append(value)
    if len(ys) < 2:
        return float("nan")
    # about zero rather than about the mean of y: the model has no intercept, because y is
    # ln(x_i(t) / x_i(0)) and is zero at the start by construction, so the fit is not allowed to move the
    # level and must not be scored as if it were (the uncentered R2 of a no-intercept regression)
    total = sum(y * y for y in ys)
    residual = sum((y - f) ** 2 for y, f in zip(ys, predicted, strict=True))
    return 1 - residual / total if total > 0 else float("nan")


def _pooled_stage_one(target: str, replicates: list, max_condition: float):
    """(r_i, A_ii, the condition number) from every replicate's rows at once, or None.

    Each replicate contributes its own rows, `ln(x(t) / x(0))` against elapsed time and the integral of
    its own abundance, from its own start: the replicates share the two parameters, so one regression over
    all the rows uses all the data. None when there are no rows, when the design is not identified, or
    when the pooled rate is not growth, and the caller then falls back to the median of the separate fits.
    """
    rows = []
    for replicate in replicates:
        built = design(replicate, target, [target])
        if target not in built["partners"]:
            continue
        own_index = built["partners"].index(target)
        rows += [{"y": row["y"], "columns": [row["time"], row["integrals"][own_index]]}
                 for row in built["rows"]]
    if len(rows) < MIN_ROWS:
        return None
    got = _least_squares(rows, 2)
    if got["values"] is None or got["condition"] > max_condition:
        return None
    rate, own = got["values"]
    if rate <= 0:
        return None
    return rate, own, got["condition"]


# How many times stage 1 is resampled when its estimate is a median of per-replicate fits. 200 is enough
# for a standard error at this precision, and the draws are medians of values already computed, so the
# cost is arithmetic rather than another fit. The seed is fixed because a published number has to be
# reproducible: the same curves give the same standard error on every machine and every run.
STAGE_ONE_DRAWS = 200
STAGE_ONE_SEED = 20261007


def _stage_one_draws(target: str, rates: list, selfs: list, usable: list, pooled_only: bool,
                     max_condition: float) -> dict:
    """{"values": [(rate, self), ...], "method", "n"}: stage 1 resampled over its monoculture replicates.

    Stage 1's error has to reach the statistics that decide an arc, and how it is estimated depends on
    how stage 1 was estimated.

    When stage 1 is the median of one fit per monoculture replicate, the replicates are **bootstrapped**:
    `STAGE_ONE_DRAWS` resamples with replacement, each giving the median of the resampled set. A
    delete-one jackknife is not used there, because the jackknife is not a consistent variance estimator
    for a median (Efron 1979, *Ann. Statist.* 7(1):1-26, section 3): with many replicates the
    leave-one-out medians take two distinct values and the number collapses, which is what #142 item 3
    measured.

    When stage 1 is one regression over every monoculture row (`_pooled_stage_one`, the fallback where no
    replicate identifies itself), the estimate is a least-squares solution and a **delete-one jackknife**
    is consistent for it, scaled by (n - 1) / n on the sum of squares as a jackknife must be.

    `values` is empty when stage 1 rests on too few replicates to resample at all, and the caller then
    publishes the replicate spread alone and says what it rests on.
    """
    if pooled_only:
        if len(usable) < 3:
            return {"values": [], "n": len(usable), "variance_scale": 1.0,
                    "method": "none: too few monoculture replicates to resample"}
        left_out = []
        for k in range(len(usable)):
            got = _pooled_stage_one(target, [r for j, r in enumerate(usable) if j != k], max_condition)
            if got is not None:
                left_out.append((got[0], got[1]))
        if len(left_out) < 3:
            return {"values": [], "n": len(left_out), "variance_scale": 1.0,
                    "method": "none: the pooled stage could not be refitted without a replicate"}
        # a jackknife variance is ((n - 1) / n) * sum of squared deviations, which is (n - 1)^2 / n times
        # the sample variance of the leave-one-out values. Without the scaling the number shrinks as
        # replicates are added, which is what #142 item 3 measured.
        scale = (len(left_out) - 1) ** 2 / len(left_out)
        return {"values": left_out, "n": len(usable), "variance_scale": scale,
                "method": "delete-one jackknife of the pooled monoculture regression"}
    if len(rates) < 3:
        return {"values": [], "n": len(rates), "variance_scale": 1.0,
                "method": "none: too few monoculture replicates to resample"}
    rng = random.Random(STAGE_ONE_SEED)
    n = len(rates)
    draws = []
    for _ in range(STAGE_ONE_DRAWS):
        picks = [rng.randrange(n) for _ in range(n)]
        draws.append((statistics.median([rates[k] for k in picks]),
                      statistics.median([selfs[k] for k in picks])))
    return {"values": draws, "n": n, "variance_scale": 1.0,
            "method": f"bootstrap of {n} monoculture replicate(s), {STAGE_ONE_DRAWS} resamples"}


def two_stage(target: str, monocultures: list, cocultures: list, organisms: list,
              max_condition: float = MAX_CONDITION) -> dict:
    """The organism's row from its monocultures first, then its partners from the co-cultures.

    The monocultures identify `r_i` and `A_ii` with one column each and no collinearity; those are held
    fixed and subtracted from the co-culture rows, which leaves the partners' coefficients to be fitted.
    This is what worked on SMGDB00000004 (#116), where a joint fit inside one experiment was not
    identified. Returns the same shape as `fit_row`, with `stages` naming what each stage gave and
    `skipped` holding every replicate that gave nothing, with its reason.
    """
    stages, skipped = [], []
    rates, selfs, conditions = [], [], []
    usable = []        # the monoculture replicates whose own fit describes them, pooled below
    for i, replicate in enumerate(monocultures):
        fit = fit_row(replicate, target, [target], max_condition)
        if fit["rate"] is not None and fit["rate"] <= 0:
            # a non-positive rate from a monoculture is the model failing on that curve, not a measurement
            skipped.append((f"{target} monoculture replicate {replicate.name or i}",
                            f"the fit gives a rate of {fit['rate']:.4g}, which is not growth: the "
                            "integrated model does not describe this curve"))
            continue
        if fit["rate"] is None or target not in fit["coefficients"]:
            skipped.append((f"{target} monoculture replicate {replicate.name or i}", fit["reason"]))
            continue
        rates.append(fit["rate"])
        selfs.append(fit["coefficients"][target])
        usable.append(replicate)
        # the monoculture stage's conditioning is the informative one for a biculture: its partner stage
        # has one column, whose scaled normal matrix is [[1.0]], so reporting that stage alone made
        # every fitted arc read as perfectly conditioned (found 2026-10-06)
        if fit.get("condition") is not None and math.isfinite(fit["condition"]):
            conditions.append(fit["condition"])
    if not rates:
        # no replicate's own rows identify the row, but their rows together may: the replicates share
        # r_i and A_ii, so one regression over all of them is the last thing to try before reporting
        # nothing. Measured on the whole database, this is where five more arcs come from (2026-10-06).
        pooled = _pooled_stage_one(target, monocultures, max_condition)
        if pooled is None:
            return {"rate": None, "coefficients": {}, "r2": float("nan"), "condition": float("inf"),
                    "points": 0, "stages": [], "skipped": skipped,
                    "reason": f"no monoculture replicate of {target} could be fitted"}
        rates, selfs = [pooled[0]], [pooled[1]]
        usable = list(monocultures)
        conditions.append(pooled[2])
        pooled_only = True
    else:
        pooled_only = False
    # One regression over every usable monoculture replicate's rows, rather than the median of their
    # separate fits: the replicates share r_i and A_ii, so pooling their rows estimates both from all the
    # data at once, and the measured uncertainty of this stage was what dominated a partner coefficient's
    # spread (2026-10-06, Karoline: "please do both"). The per-replicate fits above still decide which
    # replicates the model describes and report the ones it does not, and the median of those fits is the
    # fallback when the pooled design is not identified.
    # the median of the separate fits, which is the project's merge rule for replicates and is robust to
    # one replicate whose curve the model does not describe. Pooling every replicate's rows into one
    # regression was measured against it on the whole database (2026-10-06): it halves the worst
    # coefficient spread but leaves the median spread unchanged, fits the co-culture rows slightly worse,
    # and flips the sign of three cells, which is what a single outlying replicate does to a regression
    # and not to a median. So pooling is the fallback above, where the separate fits give nothing at all,
    # rather than the estimate here.
    rate = statistics.median(rates)
    own = statistics.median(selfs)
    stages.append("monoculture (replicates pooled)" if pooled_only else "monoculture")

    partners = [name for name in organisms if name != target]
    # Stage 1 gives one (r, A_ii) per monoculture replicate, and stage 2 used to treat their median as
    # exact, so a partner coefficient carried no uncertainty at all and an error in stage 1 reached it
    # unannounced. Both are fixed by fitting stage 2 once per co-culture replicate and once per
    # leave-one-out of the monoculture replicates: the spread over that set carries the co-culture
    # replicate spread and stage 1's together, and the median over it is the estimate (2026-10-06).
    draws = _stage_one_draws(target, rates, selfs, usable, pooled_only, max_condition)

    per_replicate: list = []          # one {partner: value} per co-culture replicate, at (rate, own)
    sensitivity: list = []            # one {partner: (d/d rate, d/d own)} per co-culture replicate
    spread_values: dict = {}          # partner -> one value per co-culture replicate
    pooled_rows, points, present = [], 0, []
    for i, replicate in enumerate(cocultures):
        built = design(replicate, target, [target, *partners])
        here = built["partners"]
        if len(built["rows"]) < MIN_ROWS or target not in here:
            skipped.append((f"{target} co-culture replicate {replicate.name or i}",
                            built["reason"] or "too few usable time points"))
            continue
        own_index = here.index(target)
        mine = [name for name in partners if name in here]
        for name in mine:
            if name not in present:
                present.append(name)
        points += len(built["rows"])

        def rows_at(a_rate, a_self, built=built, here=here, mine=mine, own_index=own_index):
            # the monoculture's own numbers are known, so what is left to fit is the partners' effect
            return [{"y": row["y"] - a_rate * row["time"] - a_self * row["integrals"][own_index],
                     "columns": [row["integrals"][here.index(name)] for name in mine]}
                    for row in built["rows"]]

        rows = rows_at(rate, own)
        pooled_rows += rows
        got = _least_squares(rows, len(mine))
        if got["values"] is None or got["condition"] > max_condition:
            continue
        conditions.append(got["condition"])
        central = dict(zip(mine, got["values"], strict=True))
        # Stage 2 solves a least squares whose right-hand side is affine in (rate, own) and whose design
        # does not depend on them, so each coefficient is an affine function of the two and a single step
        # gives the exact derivative, whatever the step is. Two more solves per replicate therefore carry
        # stage 1's error into stage 2 exactly, where leaving it out made a partner coefficient read as
        # though the monoculture stage were known (#142 item 2).
        step_rate = 0.1 * abs(rate) or 1.0
        step_own = 0.1 * abs(own) or 1e-12
        by_rate = _least_squares(rows_at(rate + step_rate, own), len(mine))
        by_own = _least_squares(rows_at(rate, own + step_own), len(mine))
        slopes = {}
        if by_rate["values"] is not None and by_own["values"] is not None:
            for k, name in enumerate(mine):
                slopes[name] = ((by_rate["values"][k] - got["values"][k]) / step_rate,
                                (by_own["values"][k] - got["values"][k]) / step_own)
        for name, value in central.items():
            spread_values.setdefault(name, []).append(value)
        per_replicate.append({"replicate": replicate.name or str(i), **central})
        sensitivity.append({"replicate": replicate.name or str(i), **slopes})

    coefficients = {target: own}
    fitted = {name: statistics.median(values) for name, values in spread_values.items() if values}
    if fitted:
        coefficients.update(fitted)
        stages.append("co-culture")
    elif pooled_rows and present:
        # no single replicate identifies the partners on its own: fall back to all their rows together,
        # which is what this stage did before. The arc then carries no spread, and the rest of the tool
        # already reads a comparison with no spread as undetermined rather than as a measurement.
        got = _least_squares(pooled_rows, len(present))
        if got["values"] is None or got["condition"] > max_condition:
            skipped.append((f"{target} co-cultures",
                            "the partners' effects are not identified by these curves (condition "
                            f"{got['condition']:.3g})"))
        else:
            coefficients.update(dict(zip(present, got["values"], strict=True)))
            conditions.append(got["condition"])
            stages.append("co-culture (replicates pooled)")

    return {"rate": rate, "coefficients": coefficients,
            # how well the whole fit describes the organism's own log abundance change, which is what the
            # help says this number is. It used to be stage 2's own R2 against stage 1's residual, a
            # different and smaller question (2026-10-06).
            "r2": _overall_r2(target, partners, cocultures, rate, own, coefficients),
            "condition": max(conditions) if conditions else float("inf"),
            "points": points, "stages": stages, "skipped": skipped, "reason": "",
            # What the uncertainty rests on, as three disjoint things rather than one mixed set.
            # `per_replicate` is one coefficient per co-culture replicate at the stage-1 estimate;
            # `sensitivity` is each one's exact derivative with respect to (rate, own); `stage_one_draws`
            # is stage 1 resampled over its own monoculture replicates. The caller combines them, since
            # what it publishes is a log2 strength and not the coefficient (#142 item 2).
            "per_replicate": per_replicate,
            "sensitivity": sensitivity,
            "stage_one_draws": draws["values"],
            "stage_one_method": draws["method"],
            "stage_one_n": draws["n"],
            "stage_one_variance_scale": draws["variance_scale"],
            "self_limitation": own,
            "spread": {name: _spread(values) for name, values in spread_values.items()},
            "replicates": len(per_replicate)}


# ---- the Deriver -----------------------------------------------------------------------------------
#
# An integrated arc has to be comparable with a ratio arc, so it records the same kind of strength: with
# `r_with = r_i + A_ij x_j`, the log2 ratio the other derivation measures is `log2(1 + A_ij x_j / r_i)`,
# which is what goes into `strength`, with the fitted coefficient itself beside it. The fit's own numbers,
# `r_i` and `A_ii`, travel on every arc of that organism, so a package takes its rate and the plateau the
# fit implies, `K_i = -r_i / A_ii`, from the same fit rather than from a separate monoculture pass.

METHOD = ("integrated v1: ln(x_i(T) / x_i(0)) = r_i T + sum_j A_ij integral(x_j dt), two-stage least "
          "squares (monocultures for r_i and A_ii, then co-cultures for the partners)")
METRIC = "integrated:two_stage"


def rate_unit_of(curve) -> str:
    return f"1/{curve.time_unit}" if curve is not None and curve.time_unit else "1/h"


def fitted_rates(records: list) -> dict:
    """{node id: the rate entry a package takes} from the arcs of an integrated run.

    The fit gives `r_i` and `A_ii`, so the plateau it implies is `K_i = -r_i / A_ii`: an organism on its
    own settles there, which is what the carrying capacity means. A fit whose `A_ii` is not negative
    implies no plateau and gives no capacity, so such an organism is left without one, as the rest of the
    tool leaves what it cannot measure.
    """
    out: dict = {}
    for record in records:
        nid, rate = record.get("target"), record.get("fitted_rate")
        own = record.get("fitted_self")
        if nid is None or rate is None or nid in out:
            continue
        capacity = -rate / own if own and own < 0 and rate > 0 else None
        out[nid] = {"name": record.get("target_name", nid), "rate": rate,
                    "unit": record.get("fitted_rate_unit", "1/h"), "n": record.get("fit_points", 0),
                    "studies": [record.get("study_id", "")], "per_study": {}, "other_units": [],
                    "method": METRIC, "lag": None, "lag_method": "",
                    "capacity": capacity,
                    "capacity_unit": record.get("fitted_self_unit", "") if capacity else "",
                    "capacity_n": record.get("fit_points", 0) if capacity else 0,
                    "capacity_per_study": {}, "other_capacity_units": [], "capacity_left_out": [],
                    "fit_r2": record.get("fit_r2"), "fit_condition": record.get("fit_condition")}
    return out


def fill_capacities(fitted: dict, measured: dict) -> tuple:
    """(the fitted rates with a measured plateau where the fit implies none, what was filled).

    The fit implies `K_i = -r_i / A_ii`, and a fit whose `A_ii` is not negative implies no plateau, which
    used to leave that organism out of every matrix although its monocultures had reached a certified
    plateau. The diagonal is `-r_i / K_i` either way, so the measured plateau is used there and named.
    This is the same pairing the specified comparison makes, a fitted rate beside a measured plateau, and
    it keeps an organism whose own limitation the time course did not pin (2026-10-06).
    """
    filled = []
    for nid, entry in fitted.items():
        if entry.get("capacity") is not None:
            continue
        other = measured.get(nid) or {}
        if other.get("capacity") is None:
            continue
        entry["capacity"] = other["capacity"]
        entry["capacity_unit"] = other.get("capacity_unit", "")
        entry["capacity_n"] = other.get("capacity_n", 0)
        entry["capacity_per_study"] = dict(other.get("capacity_per_study") or {})
        entry["capacity_media"] = list(other.get("capacity_media") or ())
        entry["capacity_fall"] = other.get("capacity_fall")
        entry["capacity_left_out"] = list(other.get("capacity_left_out") or ())
        entry["capacity_source"] = "the monoculture plateau: this fit implies none"
        filled.append((entry.get("name", nid), entry["capacity"]))
    return fitted, filled


class IntegratedDeriver:
    """Derive a network by fitting each organism's row from the whole time course (#127).

    One fit per organism, over its monocultures and then its co-cultures (`two_stage`), and one arc per
    partner it was grown with. Every arc carries the fitted coefficient, the condition number and the
    residual of the fit behind it, and the rate and self-limitation of that organism, so a package takes
    its parameters from the same fit. An organism whose row the design cannot identify gives no arc and is
    reported, as everything else unmeasurable is.

    This is the advanced option Karoline approved on 2026-10-06 ("OK for 3, as an advanced option"): the
    default derivation, `ReplicateDeriver`, is untouched, and the two can be compared on the same data,
    including against the chemostat steady states of #125.
    """

    name = "integrated-v1"
    method = METHOD
    needs_client = True

    def __init__(self, client=None, spike_factor: float = None, max_condition: float = MAX_CONDITION,
                 include_non_batch: bool = False, **_ignored):
        self.client = client
        self.spike_factor = spike_factor
        self.max_condition = max_condition
        self.include_non_batch = include_non_batch

    def derive(self, study: dict, exps: list):
        from .adapter import replicates_for_experiment
        from .derive import (
            BATCH,
            CONDITIONS_UNVERIFIED,
            SINGLE_REPLICATE,
            TWO_REPLICATES,
            _choose_monocultures,
            _exp_id,
            _identity,
            _members,
            conditions,
            cultivation,
            media_identity,
            run_group,
            strain_identities,
        )
        from .growth import SPIKE_FACTOR

        if self.client is None:
            raise ValueError("IntegratedDeriver needs a client: it reads each replicate's measured series")
        spike = SPIKE_FACTOR if self.spike_factor is None else self.spike_factor
        records, skipped = [], []
        identities = strain_identities(exps, [])
        # the replicates of every experiment, split into monocultures of one organism and communities
        monocultures: dict = {}
        communities = []
        for exp in exps:
            mode = cultivation(exp)
            if mode != BATCH and not self.include_non_batch:
                skipped.append((exp.get("name") or _exp_id(exp),
                                f"{mode}: the integrated form needs batch growth, where the only losses "
                                "are the ones the model has"))
                continue
            members = _members(exp)
            if not members:
                continue
            reps, skips = replicates_for_experiment(self.client, exp, spike)
            skipped += skips
            if not reps:
                continue
            if len(members) == 1:
                # keyed and grouped exactly as `derive._mono_index` keys and groups them, so stage 1
                # pools only what the specified comparison would pool: identical recorded conditions and
                # the same description apart from a run number. The shape is what `_choose_monocultures`
                # reads: (replicates, strains, experiment ids, descriptions, names).
                here = monocultures.setdefault((members[0], conditions(exp)), {}).setdefault(
                    run_group(exp), ([], set(), [], [], []))
                here[0].extend(reps)
                here[1].add(members[0])
                here[2].append(_exp_id(exp))
                here[3].append(exp.get("description") or "")
                here[4].append(exp.get("name") or "")
            elif len(members) == 2:
                communities.append((exp, members, reps))
            else:
                # This form can fit a row from a community of any size, since every partner is a column
                # of its own, and that is a new capability rather than a port of the current method: the
                # existing evidence values are biculture and dropout, and an arc from a whole community
                # is neither. It needs a decision before it is emitted, so it is reported here.
                skipped.append((exp.get("name") or _exp_id(exp),
                                f"{len(members)} members: the integrated form can fit a row from a whole "
                                "community, which is a new kind of evidence and needs a decision first "
                                "(see the open decisions in docs/METHOD_NOTES.md)"))

        study_id = study.get("id")
        study_meta = {"study_citation": study.get("citation", ""), "study_license": study.get("license", ""),
                      "study_url": study.get("url", "")}
        for exp, members, reps in communities:
            # the strict label, so an arc says which altered medium it was measured in and the capacity
            # beside it can be matched to the same one (Karoline, 2026-10-07)
            medium = media_identity(exp)["label"]
            for target in members:
                partners = [m for m in members if m != target]
                # Stage 1 used to be every monoculture replicate of this organism anywhere in the
                # study, which pooled across chemically different experiments: on SMGDB00000014 that
                # made one rate out of ten conditions whose implied plateaus span a factor of 5,500.
                # It now follows the rule settled on #47 and recorded on #81, through the same two
                # functions the specified comparison uses, so both derivations compare like with like
                # (#142 item 1).
                groups = monocultures.get((target, conditions(exp))) or {}
                if not groups:
                    skipped.append((f"{target} in {exp.get('name') or _exp_id(exp)}",
                                    "no monoculture of it under this experiment's recorded conditions, so "
                                    "its own rate and limitation cannot be identified for this condition"))
                    continue
                chosen, how = _choose_monocultures(groups, exp)
                if chosen is None:
                    skipped.append((f"{target} in {exp.get('name') or _exp_id(exp)}", how))
                    continue
                monos, mono_experiments = chosen[0], list(chosen[2])
                # several sets under these conditions, told apart only by their descriptions, and nothing
                # recorded says which one this co-culture matches: the same caution the specified
                # comparison carries there
                unverified = len(groups) > 1 and how not in ("named", "qualifier", "wording")
                got = two_stage(target, monos, reps, [target, *partners], self.max_condition)
                skipped += got["skipped"]
                if got["rate"] is None or not got["coefficients"]:
                    skipped.append((f"{target} in {exp.get('name') or _exp_id(exp)}",
                                    got["reason"] or "its row could not be identified by this design"))
                    continue
                # a fit that explains less of the organism's own log abundance change than predicting
                # nothing does is not a measurement of anything. The line is zero, not a tuned
                # threshold: it is where the model stops describing the curve (2026-10-06)
                if got["r2"] is not None and got["r2"] == got["r2"] and got["r2"] < 0:
                    skipped.append((f"{target} in {exp.get('name') or _exp_id(exp)}",
                                    f"the fitted row explains less of {target}'s log abundance change "
                                    f"than predicting nothing does (R2 {got['r2']:.3g} about zero), so "
                                    "the integrated model does not describe these curves"))
                    continue
                own = got["coefficients"].get(target)
                curve = reps[0].curve(target)
                unit = curve.abundance_unit if curve is not None else ""
                for partner in partners:
                    coefficient = got["coefficients"].get(partner)
                    if coefficient is None:
                        skipped.append((f"{partner} -> {target} [{exp.get('name') or _exp_id(exp)}]",
                                        "the fit of this row did not identify this partner's effect"))
                        continue
                    here = reps[0].curve(partner)
                    # the partner's abundance is measured on the partner's own curve, so its unit is that
                    # curve's. It was labeled with the target's unit, and `matrix` keys a coefficient's
                    # matrix on this label, so a cross-unit effect entered the target's matrix instead of
                    # being named and left out (found 2026-10-06).
                    partner_unit = here.abundance_unit if here is not None else ""
                    if unit and partner_unit and partner_unit != unit:
                        skipped.append((f"{partner} -> {target} [{exp.get('name') or _exp_id(exp)}]",
                                        f"{partner} is counted in {partner_unit} and {target} in {unit}; "
                                        "abundances are never converted, so this effect is left out"))
                        continue
                    abundance = _mean_level(reps, partner)
                    effect = (coefficient * abundance / got["rate"]) if (abundance and got["rate"]) else 0.0
                    strength = math.log2(1 + effect) if effect > -1 else None
                    # the spread the fit itself gives: one strength per co-culture replicate, so this arc
                    # carries a mean, an sd, a standard error and a t-test against no effect, and the
                    # absence threshold and the multiple-testing correction act on it as they do on the
                    # specified comparison. Before this an integrated arc carried none of them and came
                    # out "undetermined" under every threshold (2026-10-06).
                    stats_here = _arc_statistics(got, reps, partner)
                    n_reps = stats_here["n"]
                    if stats_here["strength"] is not None:
                        strength = stats_here["strength"]
                    sd, se = stats_here["sd"], stats_here["se"]
                    quality = [SINGLE_REPLICATE] if n_reps < 2 else []
                    cautions = [TWO_REPLICATES] if n_reps == 2 else []
                    if unverified:
                        cautions.append(CONDITIONS_UNVERIFIED)
                    src, tgt = _identity(identities, partner), _identity(identities, target)
                    records.append({
                        "source": src["id"], "source_name": partner,
                        "target": tgt["id"], "target_name": target,
                        "source_taxon_id": src["taxon_id"], "source_species": src["species"],
                        "source_identity": src["identity"],
                        "target_taxon_id": tgt["taxon_id"], "target_species": tgt["species"],
                        "target_identity": tgt["identity"],
                        "effect": ("facilitation" if coefficient > 0 else
                                   "inhibition" if coefficient < 0 else "neutral"),
                        "strength": None if strength is None else round(strength, 4),
                        "weight": None if strength is None else round(abs(strength), 4),
                        # the status is left to the output, where the absence threshold decides it from
                        # the mean and the spread, as it does for every other derivation
                        "status": None, "outcome": "quantified", "metric": METRIC,
                        "method": METHOD, "evidence": "biculture",
                        "quality": quality, "cautions": cautions, "notes": [],
                        "cultivation_mode": cultivation(exp),
                        "medium": medium, "condition": exp.get("name", ""),
                        "community": sorted(_identity(identities, m)["id"] for m in members),
                        # the co-culture and the monoculture experiments the row rests on, as the
                        # specified comparison records them
                        "experiments": [_exp_id(exp), *mono_experiments],
                        "n_with": len(reps), "n_without": len(monos),
                        "sd": None if sd is None else round(sd, 4),
                        "se": None if se is None else round(se, 4),
                        "p_value": stats_here["p_value"],
                        "q_value": None, "significance": None,
                        "effect_over_sd": (None if (sd is None or not sd or strength is None)
                                           else round(abs(strength) / sd, 4)),
                        # the coefficient's own spread, in the coefficient's units: over co-culture
                        # replicates and over leave-one-out of the monoculture replicates together, with
                        # the part that comes from the monoculture stage alone beside it
                        "coefficient_sd": stats_here["coefficient_sd"],
                        "coefficient_n": n_reps,
                        "coefficient_sd_from_rate_stage": stats_here["coefficient_sd_from_rate_stage"],
                        # the two halves of `se`, on their own designs, and how stage 1 was resampled
                        "se_replicates": stats_here["se_replicates"],
                        "se_rate_stage": stats_here["se_rate_stage"],
                        "rate_stage_method": got.get("stage_one_method", ""),
                        "rate_stage_n": got.get("stage_one_n"),
                        # what this derivation adds: the coefficient itself and the fit behind it
                        "coefficient": coefficient,
                        "coefficient_unit": (f"1/({rate_unit_of(here)[2:]} x {partner_unit or unit})"
                                             if (partner_unit or unit) else ""),
                        "fitted_rate": got["rate"], "fitted_rate_unit": rate_unit_of(curve),
                        "fitted_self": own, "fitted_self_unit": unit,
                        "metric_with": got["rate"] + coefficient * (abundance or 0.0),
                        "metric_without": got["rate"],
                        "fit_r2": got["r2"], "fit_condition": got["condition"],
                        "fit_points": got["points"], "fit_stages": list(got["stages"]),
                        "partner_abundance": abundance, "partner_abundance_unit": partner_unit or unit,
                        "partner_abundance_n": len(reps),
                        "study_id": study_id, **study_meta,
                    })
        return records, skipped


def _level_of(replicate, species: str):
    """The partner's mean abundance over one replicate's measured span, or None."""
    from .growth import mean_over

    curve = replicate.curve(species)
    if curve is None:
        return None
    return mean_over(curve, curve.times[0], curve.times[-1])


def _log2_effect(coefficient: float, level: float, rate: float):
    """The comparable log2 strength of a fitted coefficient: log2(1 + A_ij x_j / r_i), or None where the
    fitted effect at least cancels the organism's own rate and no ratio exists."""
    effect = coefficient * level / rate
    return math.log2(1 + effect) if effect > -1 else None


def _arc_statistics(got: dict, cocultures: list, partner: str) -> dict:
    """What an arc publishes about one partner's effect, with both sources of error in it.

    {"n", "strength", "sd", "se", "se_replicates", "se_rate_stage", "p_value", "df",
     "coefficient_sd", "coefficient_sd_from_rate_stage", "per_replicate"}.

    Two things vary and they are measured on disjoint designs, which is why they are kept apart and then
    added (#142 items 2 and 3):

      * the **co-culture replicates**: one coefficient per replicate at stage 1's estimate, each turned
        into a strength at that replicate's own partner level. Their spread over the mean is the part a
        reader sees as `sd`, and `se_replicates` is that over the square root of their number.
      * **stage 1 itself**: the monoculture replicates resampled (`_stage_one_draws`), each resample
        giving another (rate, self-limitation). Stage 2's coefficient is affine in those two, so
        `sensitivity` carries each replicate's exact derivative and no refit is needed; the strength is
        recomputed at every draw, including the rate in its own denominator, and the spread of the mean
        over draws is `se_rate_stage`.

    `se` is the square root of the two variances added, and the t statistic that gives `p_value` uses it
    with a Satterthwaite degrees of freedom, so an arc whose monoculture stage is poorly determined is no
    longer tested as though that stage were exact. Before this, every one of these came from the
    co-culture replicates alone (2026-10-07).
    """
    from .stats import t_cdf
    rate, own = got.get("rate"), got.get("self_limitation")
    by_name = {replicate.name or str(i): replicate for i, replicate in enumerate(cocultures)}
    slopes = {entry["replicate"]: entry for entry in got.get("sensitivity") or ()}
    rows = []                       # (coefficient, (d/d rate, d/d own), partner level, central strength)
    for entry in got.get("per_replicate") or ():
        if partner not in entry or not rate:
            continue
        replicate = by_name.get(entry["replicate"])
        level = _level_of(replicate, partner) if replicate is not None else None
        if not level:
            continue
        central = _log2_effect(entry[partner], level, rate)
        if central is None:
            continue
        rows.append((entry[partner], (slopes.get(entry["replicate"]) or {}).get(partner), level, central))

    out = {"n": len(rows), "strength": None, "sd": None, "se": None, "se_replicates": None,
           "se_rate_stage": None, "p_value": None, "df": None, "coefficient_sd": None,
           "coefficient_sd_from_rate_stage": None, "per_replicate": [row[3] for row in rows]}
    if not rows:
        return out
    out["strength"] = statistics.mean(row[3] for row in rows)
    if len(rows) < 2:
        return out
    sd = statistics.stdev(row[3] for row in rows)
    out["coefficient_sd"] = statistics.stdev(row[0] for row in rows)
    var_replicates = sd * sd / len(rows)
    out["se_replicates"] = math.sqrt(var_replicates)

    draws = got.get("stage_one_draws") or ()
    scale = got.get("stage_one_variance_scale") or 1.0
    strength_means, coefficient_means = [], []
    if draws and own is not None and all(row[1] is not None for row in rows):
        for draw_rate, draw_own in draws:
            if not draw_rate:
                continue
            strengths, coefficients = [], []
            for coefficient, (by_rate, by_own), level, _central in rows:
                moved = coefficient + by_rate * (draw_rate - rate) + by_own * (draw_own - own)
                here = _log2_effect(moved, level, draw_rate)
                if here is None:
                    strengths = []
                    break
                strengths.append(here)
                coefficients.append(moved)
            if len(strengths) == len(rows):
                strength_means.append(statistics.mean(strengths))
                coefficient_means.append(statistics.mean(coefficients))
    var_stage = statistics.variance(strength_means) * scale if len(strength_means) >= 2 else 0.0
    if len(coefficient_means) >= 2:
        out["coefficient_sd_from_rate_stage"] = math.sqrt(statistics.variance(coefficient_means) * scale)
    out["se_rate_stage"] = math.sqrt(var_stage)
    out["se"] = math.sqrt(var_replicates + var_stage)
    # `sd` is the dispersion of one estimate and `se` the dispersion of their mean, and the tool's own
    # relation between them is se = sd / sqrt(n). Keeping that relation is what carries the rate stage
    # into the absence threshold, which compares the effect with k * sd, and into effect_over_sd: the
    # rate stage's error belongs to every replicate alike, so at replicate scale it is n times its
    # contribution to the variance of the mean. The two halves stay published beside it, so the
    # replicates' own scatter is still readable as se_replicates * sqrt(n) (#142 item 2).
    out["sd"] = out["se"] * math.sqrt(len(rows))

    df_replicates = len(rows) - 1
    df_stage = max(1, (got.get("stage_one_n") or 1) - 1)
    if var_stage > 0 and var_replicates > 0:
        df = ((var_replicates + var_stage) ** 2
              / (var_replicates ** 2 / df_replicates + var_stage ** 2 / df_stage))
    else:
        df = df_replicates if var_replicates > 0 else df_stage
    out["df"] = df
    if out["se"] > 0:
        t = out["strength"] / out["se"]
        out["p_value"] = min(1.0, 2.0 * (1.0 - t_cdf(abs(t), df)))
    else:
        out["p_value"] = 0.0 if out["strength"] else 1.0
    return out


def _mean_level(replicates: list, species: str):
    """The partner's mean abundance over the whole measured span, median over the replicates.

    The integrated fit needs no `x_j_star` of its own: this is only for the comparable `strength` an arc
    records, so it is the plainest average the curves give.
    """
    from .growth import mean_over

    values = []
    for replicate in replicates:
        curve = replicate.curve(species)
        if curve is None:
            continue
        value = mean_over(curve, curve.times[0], curve.times[-1])
        if value is not None:
            values.append(value)
    if not values:
        return None
    return statistics.median(values)
