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

# Above this condition number the columns are too close to tell apart, and the split between an
# organism's own limitation and its partner's effect is not identified by this design. It is measured on
# the design with each column scaled to unit length, so it reports collinearity and not the scale
# difference between an elapsed time (tens) and an abundance integral (billions). Two columns correlating
# at the +0.977 measured on #116 give about 86, so this limit keeps such a fit and reports its number,
# and refuses only a design whose columns are near duplicates.
MAX_CONDITION = 1.0e4
MIN_ROWS = 3            # fewer rows than unknowns plus one, and nothing can be fitted


def _trapezoid(times: list, values: list) -> list:
    """The running integral of a curve by the trapezoid rule, one entry per measured point."""
    out = [0.0]
    for i in range(1, len(times)):
        out.append(out[-1] + 0.5 * (values[i] + values[i - 1]) * (times[i] - times[i - 1]))
    return out


def design(replicate, target: str, organisms: list) -> dict:
    """The rows of the regression for one organism in one replicate.

    {"partners": [names in column order], "rows": [{"y", "time", "integrals"}], "reason"}: `y` is
    `ln(x_i(t) / x_i(0))`, `time` is the elapsed time, and `integrals` holds the time integral of each
    organism present, in `partners` order. A partner with no curve in this replicate is left out of the
    columns and named in `reason`, since a column of zeros would claim it was absent rather than
    unmeasured.
    """
    own = replicate.curve(target)
    if own is None:
        return {"partners": [], "rows": [], "reason": f"{target} was not measured in this replicate"}
    times, values = list(own.times), list(own.values)
    if not values or values[0] <= 0 or max(values) <= 0:
        return {"partners": [], "rows": [],
                "reason": f"no positive abundance to start from for {target} in this replicate"}
    partners, integrals, missing = [], [], []
    for name in organisms:
        curve = replicate.curve(name)
        if curve is None:
            missing.append(name)
            continue
        if list(curve.times) != times:
            missing.append(name)
            continue
        partners.append(name)
        integrals.append(_trapezoid(times, list(curve.values)))
    rows = []
    for k in range(1, len(times)):
        if values[k] <= 0:
            continue
        rows.append({"y": math.log(values[k] / values[0]), "time": times[k] - times[0],
                     "integrals": [column[k] for column in integrals]})
    reason = ""
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


def fit_row(replicate, target: str, organisms: list, max_condition: float = MAX_CONDITION) -> dict:
    """One organism's whole row from one replicate's time course.

    {"rate", "coefficients": {organism: A_ij}, "r2", "condition", "points", "reason"}. `coefficients` is
    empty with a `reason` when the design cannot identify the row: too few points, no positive abundance,
    or a condition number above `max_condition`, which is the collinearity measured on #116.
    """
    built = design(replicate, target, organisms)
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
    rates, selfs = [], []
    for i, replicate in enumerate(monocultures):
        fit = fit_row(replicate, target, [target], max_condition)
        if fit["rate"] is None or target not in fit["coefficients"]:
            skipped.append((f"{target} monoculture replicate {replicate.name or i}", fit["reason"]))
            continue
        rates.append(fit["rate"])
        selfs.append(fit["coefficients"][target])
    if not rates:
        return {"rate": None, "coefficients": {}, "r2": float("nan"), "condition": float("inf"),
                "points": 0, "stages": [], "skipped": skipped,
                "reason": f"no monoculture replicate of {target} could be fitted"}
    rate = sorted(rates)[len(rates) // 2]
    own = sorted(selfs)[len(selfs) // 2]
    stages.append("monoculture")

    partners = [name for name in organisms if name != target]
    rows, points, r2s, conditions = [], 0, [], []
    for i, replicate in enumerate(cocultures):
        built = design(replicate, target, [target, *partners])
        here = built["partners"]
        if len(built["rows"]) < MIN_ROWS or target not in here:
            skipped.append((f"{target} co-culture replicate {replicate.name or i}",
                            built["reason"] or "too few usable time points"))
            continue
        own_index = here.index(target)
        for row in built["rows"]:
            # the monoculture's own numbers are known, so what is left to fit is the partners' effect
            left = row["y"] - rate * row["time"] - own * row["integrals"][own_index]
            rows.append({"y": left,
                         "columns": [row["integrals"][here.index(name)] for name in partners
                                     if name in here]})
        points += len(built["rows"])
    present = [name for name in partners
               if any(name in design(rep, target, [target, *partners])["partners"] for rep in cocultures)]
    coefficients = {target: own}
    if rows and present:
        got = _least_squares(rows, len(present))
        answer, condition = got["values"], got["condition"]
        if answer is None or condition > max_condition:
            skipped.append((f"{target} co-cultures",
                            "the partners' effects are not identified by these curves (condition "
                            f"{condition:.3g})"))
        else:
            # this stage has one column per partner: the rate and the own limitation are already in
            coefficients.update(dict(zip(present, answer, strict=True)))
            r2s.append(got["r2"])
            conditions.append(condition)
            stages.append("co-culture")
    return {"rate": rate, "coefficients": coefficients,
            "r2": r2s[0] if r2s else float("nan"),
            "condition": max(conditions) if conditions else float("inf"),
            "points": points, "stages": stages, "skipped": skipped, "reason": ""}
