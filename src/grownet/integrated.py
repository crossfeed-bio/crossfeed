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
        # the monoculture stage's conditioning is the informative one for a biculture: its partner stage
        # has one column, whose scaled normal matrix is [[1.0]], so reporting that stage alone made
        # every fitted arc read as perfectly conditioned (found 2026-10-06)
        if fit.get("condition") is not None and math.isfinite(fit["condition"]):
            conditions.append(fit["condition"])
    if not rates:
        return {"rate": None, "coefficients": {}, "r2": float("nan"), "condition": float("inf"),
                "points": 0, "stages": [], "skipped": skipped,
                "reason": f"no monoculture replicate of {target} could be fitted"}
    # a real median: sorted(x)[len(x) // 2] takes the upper middle value when the count is even,
    # and two replicates is the common case here, while every other module uses statistics.median
    rate = statistics.median(rates)
    own = statistics.median(selfs)
    stages.append("monoculture")

    partners = [name for name in organisms if name != target]
    # Stage 1 gives one (r, A_ii) per monoculture replicate, and stage 2 used to treat their median as
    # exact, so a partner coefficient carried no uncertainty at all and an error in stage 1 reached it
    # unannounced. Both are fixed by fitting stage 2 once per co-culture replicate and once per
    # leave-one-out of the monoculture replicates: the spread over that set carries the co-culture
    # replicate spread and stage 1's together, and the median over it is the estimate (2026-10-06).
    variants = [(rate, own)]
    if len(rates) >= 3:
        for k in range(len(rates)):
            kept_rates = [v for j, v in enumerate(rates) if j != k]
            kept_selfs = [v for j, v in enumerate(selfs) if j != k]
            variants.append((statistics.median(kept_rates), statistics.median(kept_selfs)))

    per_replicate: list = []          # one {partner: value} per co-culture replicate, central variant
    spread_values: dict = {}          # partner -> every value over replicates and stage-1 variants
    stage_one_values: dict = {}       # partner -> values at a fixed replicate, varying stage 1 only
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
        central = {}
        for which, (a_rate, a_self) in enumerate(variants):
            rows = []
            for row in built["rows"]:
                # the monoculture's own numbers are known, so what is left to fit is the partners' effect
                left = row["y"] - a_rate * row["time"] - a_self * row["integrals"][own_index]
                rows.append({"y": left,
                             "columns": [row["integrals"][here.index(name)] for name in mine]})
            pooled_rows += rows if which == 0 else []
            got = _least_squares(rows, len(mine))
            if got["values"] is None or got["condition"] > max_condition:
                continue
            conditions.append(got["condition"])
            for name, value in zip(mine, got["values"], strict=True):
                spread_values.setdefault(name, []).append(value)
                if which == 0:
                    central[name] = value
                else:
                    stage_one_values.setdefault(name, []).append(value)
        if central:
            per_replicate.append({"replicate": replicate.name or str(i), **central})

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
            # what the spread rests on: one value per co-culture replicate (central stage 1), every value
            # over replicates and stage-1 variants, and the part of it that comes from stage 1 alone
            "per_replicate": per_replicate,
            "spread": {name: _spread(values) for name, values in spread_values.items()},
            "stage_one_spread": {name: _spread(values) for name, values in stage_one_values.items()},
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
            SINGLE_REPLICATE,
            TWO_REPLICATES,
            _exp_id,
            _identity,
            _members,
            cultivation,
            strain_identities,
        )
        from .growth import SPIKE_FACTOR
        from .selection import medium_of
        from .stats import paired

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
                monocultures.setdefault(members[0], []).append((exp, reps))
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
            medium = medium_of(exp)
            for target in members:
                partners = [m for m in members if m != target]
                monos = [rep for _, found in monocultures.get(target, []) for rep in found]
                if not monos:
                    skipped.append((f"{target} in {exp.get('name') or _exp_id(exp)}",
                                    "no monoculture of it to identify its own rate and limitation from"))
                    continue
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
                    per_rep = _strengths(got, reps, partner, got["rate"])
                    spread = (got.get("spread") or {}).get(partner) or {}
                    stage_one = (got.get("stage_one_spread") or {}).get(partner) or {}
                    n_reps = len(per_rep)
                    if n_reps >= 2:
                        strength = statistics.mean(per_rep)
                        sd = statistics.stdev(per_rep)
                        se = sd / math.sqrt(n_reps)
                        test = paired(per_rep, [0.0] * n_reps)
                    else:
                        sd = se = None
                        test = None
                    quality = [SINGLE_REPLICATE] if n_reps < 2 else []
                    cautions = [TWO_REPLICATES] if n_reps == 2 else []
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
                        "experiments": [_exp_id(exp)],
                        "n_with": len(reps), "n_without": len(monos),
                        "sd": None if sd is None else round(sd, 4),
                        "se": None if se is None else round(se, 4),
                        "p_value": None if test is None else test["p"],
                        "q_value": None, "significance": None,
                        "effect_over_sd": (None if (sd is None or not sd or strength is None)
                                           else round(abs(strength) / sd, 4)),
                        # the coefficient's own spread, in the coefficient's units: over co-culture
                        # replicates and over leave-one-out of the monoculture replicates together, with
                        # the part that comes from the monoculture stage alone beside it
                        "coefficient_sd": spread.get("sd"),
                        "coefficient_n": spread.get("n"),
                        "coefficient_sd_from_rate_stage": stage_one.get("sd"),
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


def _strengths(got: dict, cocultures: list, partner: str, rate: float) -> list:
    """The comparable log2 strength this fit gives per co-culture replicate.

    One per replicate that identified the partner's effect, each from that replicate's own coefficient
    and its own partner level, so the spread over them is a spread over replicates and the rest of the
    tool can test it as it tests the specified comparison.
    """
    by_name = {replicate.name or str(i): replicate for i, replicate in enumerate(cocultures)}
    out = []
    for entry in got.get("per_replicate") or ():
        if partner not in entry:
            continue
        replicate = by_name.get(entry["replicate"])
        level = _level_of(replicate, partner) if replicate is not None else None
        if not level or not rate:
            continue
        effect = entry[partner] * level / rate
        if effect > -1:
            out.append(math.log2(1 + effect))
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
