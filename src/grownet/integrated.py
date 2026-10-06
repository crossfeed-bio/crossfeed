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
        from .derive import BATCH, _exp_id, _identity, _members, cultivation, strain_identities
        from .growth import SPIKE_FACTOR
        from .selection import medium_of

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
                    abundance = _mean_level(reps, partner)
                    effect = (coefficient * abundance / got["rate"]) if (abundance and got["rate"]) else 0.0
                    strength = math.log2(1 + effect) if effect > -1 else None
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
                        "status": "present", "outcome": "quantified", "metric": METRIC,
                        "method": METHOD, "evidence": "biculture",
                        "quality": [], "cautions": [], "notes": [], "cultivation_mode": cultivation(exp),
                        "medium": medium, "condition": exp.get("name", ""),
                        "community": sorted(_identity(identities, m)["id"] for m in members),
                        "experiments": [_exp_id(exp)],
                        "n_with": len(reps), "n_without": len(monos),
                        "sd": None, "se": None, "p_value": None, "q_value": None, "significance": None,
                        "effect_over_sd": None,
                        # what this derivation adds: the coefficient itself and the fit behind it
                        "coefficient": coefficient, "coefficient_unit": f"1/({rate_unit_of(here)[2:]} x "
                                                                        f"{unit})" if unit else "",
                        "fitted_rate": got["rate"], "fitted_rate_unit": rate_unit_of(curve),
                        "fitted_self": own, "fitted_self_unit": unit,
                        "metric_with": got["rate"] + coefficient * (abundance or 0.0),
                        "metric_without": got["rate"],
                        "fit_r2": got["r2"], "fit_condition": got["condition"],
                        "fit_points": got["points"], "fit_stages": list(got["stages"]),
                        "partner_abundance": abundance, "partner_abundance_unit": unit,
                        "partner_abundance_n": len(reps),
                        "study_id": study_id, **study_meta,
                    })
        return records, skipped


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
    return sorted(values)[len(values) // 2]
