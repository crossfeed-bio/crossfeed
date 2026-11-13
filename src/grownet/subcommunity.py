"""gLV rows from the steady states of sub-communities (#310, task #311).

Karoline, 2026-11-06: "can we have a third inference method just for gLV mode and chemostat, off by
default ... The idea here is to parameterize the gLV from steady-state abundances of sub-communities." The
idea is EPICS (Ansari et al. 2021, Nature Computational Science 1:619), which reads the monocultures and
the leave-one-out communities only; asked for "something more flexible that would try parameterisation on
all available sub-communities", this reads every community whose steady state was observed.

At a steady state every member i that is present satisfies

    1 + sum_j B_ij N_j = 0,        B_ij = A_ij / s_i

with N the steady-state abundances and s_i the row's scale, which in a chemostat is r_i - D (the growth rate
less the dilution rate; Karoline: "Mono-culture growth rates from batch are tricky, because they change in
chemostat"). So each community gives one equation per member present, linear in that member's row of B,
and each row is solved by least squares over all of its equations, its diagonal with the rest. On the
monocultures plus the leave-one-out communities this is exactly EPICS. The coefficients are EFFECTIVE
pairwise ones: an effect that needs a third species is folded into whichever pairs carry it, and a design
that pools very different communities assumes one effective coefficient holds across them, which
`leave_one_out_predictions` exists to test.

The rules, stated once:
  * a member at 0 **washed out**: it is not at an interior steady state, so it gives no equation, and it
    adds nothing to the others' (the caller decides what counts as 0; `steady.WASHED_OUT` is the chemostat
    check's rule);
  * a row is reported only where its equations **determine** it: the same least squares and the same
    condition limit as the integrated form (`integrated.MAX_CONDITION`), so "identified" means one thing
    across the tool. Fewer independent equations than unknowns is underdetermined, and the row is named
    rather than filled;
  * a coefficient B_ij is only ever an unknown where i and j were present together in some community; one
    whose pair never met is named as such;
  * the **spread** is a bootstrap over vessels, and a row has one only where every community it rests on has
    two vessels or more (decision 5 of #310); otherwise it has none, and its arcs are undetermined;
  * runs that end with the **same members present are one community** (`pool`): one set of members has one
    steady state, so they are one equation, their vessels pooled;
  * a row whose own term B_ii is **not negative** is not reported: B_ii = A_ii / (r_i - D) with A_ii < 0 for
    a self-limited organism, so B_ii >= 0 means either no self-limitation or r_i < D, and the sign of every
    effect on it depends on which.

Nothing here reads mGrowthDB; `#312` turns chemostat runs into these communities.
"""
from __future__ import annotations

import random
import re
import statistics

from .integrated import MAX_CONDITION, _least_squares, _solve

UNIT_ROW = "1/abundance, in units of the row scale s_i (r_i - D in a chemostat)"
DRAWS = 200


def _present(community: dict) -> dict:
    return {k: v for k, v in (community.get("abundance") or {}).items() if v is not None and v > 0}


def _equations(communities: list) -> dict:
    """species -> [(community name, {member: abundance})] for every community where it is present."""
    out: dict = {}
    for c in communities:
        here = _present(c)
        for i in here:
            out.setdefault(i, []).append((c["name"], here))
    return out


def _fit_row(i: str, equations: list) -> dict:
    columns = sorted({j for _, here in equations for j in here}, key=lambda j: (j != i, j))
    rows = [{"columns": [here.get(j, 0.0) for j in columns], "y": -1.0} for _, here in equations]
    got = _least_squares(rows, len(columns))
    if got["values"] is None or not got["condition"] <= MAX_CONDITION:
        return {"status": "underdetermined", "values": {}, "columns": columns, "equations": len(equations),
                "condition": got["condition"]}
    values = dict(zip(columns, got["values"], strict=True))
    if not values[i] < 0:
        # B_ii = A_ii / (r_i - D). A self-limited organism has A_ii < 0, so B_ii >= 0 means either no
        # self-limitation or r_i < D: an organism that cannot hold alone at this dilution rate and lives on
        # its partners. The sign of every effect on it is the sign of (r_i - D) B_ij, so which of the two
        # holds decides whether a partner helps or harms it, and the row cannot say. Reported, it called an
        # obligate cross-feeder's feeders inhibitors (found in review); the integrated form refuses a
        # non-negative self-limitation for the same reason.
        return {"status": "no self-limitation", "values": {}, "columns": columns, "equations": len(equations),
                "condition": got["condition"], "own": values[i]}
    return {"status": "identified", "values": values,
            "columns": columns, "equations": len(equations), "condition": got["condition"]}


def _resample(communities: list, rng: random.Random) -> list:
    """The communities with each one's replicates drawn with replacement, where it has two or more.

    A community's replicates are its vessels, or, for runs pooled by `pool`, its runs: vessels of one run
    share that run's inoculum and history, so drawing them as independent made the spread of a pooled
    community too narrow (found in a second review). The draw is the mean over the drawn replicates, of
    those that hold a value, the statistic the point estimate is. The bootstrap of a mean of n draws
    spreads sqrt((n - 1) / n) as far as the mean does, which with three vessels made the spread 18% too
    narrow and called arcs present too readily (found in review), so each draw's departure from the mean is
    widened by sqrt(n / (n - 1)). A member that washed out stays washed out."""
    import math
    out = []
    for c in communities:
        runs = c.get("run_means")
        units = runs if runs and len(runs) >= 2 else (c.get("vessels") or [])
        n = len(units)
        if n < 2:
            out.append(c)
            continue
        drawn = [rng.choice(units) for _ in units]
        widen = math.sqrt(n / (n - 1))
        abundance = {}
        for k, centre in c["abundance"].items():
            held = [v[k] for v in drawn if v.get(k) is not None]
            if centre is None or centre <= 0 or not held:
                abundance[k] = centre
                continue
            # a draw that the widening carries to 0 or below stays present, at a sliver of its mean
            abundance[k] = max(centre + widen * (statistics.fmean(held) - centre), 1e-9 * centre)
        out.append({**c, "abundance": abundance})
    return out


def pool(communities: list) -> list:
    """Communities with the same members present, as one community whose replicates are its runs.

    Under a gLV one set of members has one interior steady state, so two runs of it are replicates of one
    equation, not two equations. Kept apart, their noise alone told a row's unknowns apart: two runs of one
    pair, with no monoculture, were "identified" in 136 of 300 trials at 5% noise and more often the
    noisier the runs (found in review). And a leave-one-out prediction left one run out and kept its twin.
    The pooled abundance is the mean over runs of each run's mean, its replicates for the bootstrap are the
    runs (`run_means`), and it holds the members present only: a member one run inoculated and lost is that
    run's wash-out, which `fit` reports under the run's own name. Its name is its members', with the count,
    and `runs` names them all."""
    def by_values(v: dict) -> tuple:
        return tuple(sorted((k, x if x is not None else -1.0) for k, x in v.items()))

    groups: dict = {}
    for c in communities:
        groups.setdefault(frozenset(_present(c)), []).append(c)
    out = []
    # in an order set by what the communities hold, never by their names or the order they were read in: the
    # bootstrap draws in this order, and reordering the runs moved an arc's spread across the absence
    # threshold (found in a sixth review)
    for present in sorted(groups, key=lambda p: (len(p), tuple(sorted(p)))):
        runs = sorted(groups[present], key=lambda c: by_values(c["abundance"]))
        if len(runs) == 1:
            out.append({**runs[0], "vessels": sorted(runs[0].get("vessels") or [], key=by_values)}
                       if runs[0].get("vessels") else runs[0])
            continue
        means = []
        for c in runs:
            vessels = c.get("vessels") or [c["abundance"]]
            means.append({k: statistics.fmean(v[k] for v in vessels if (v.get(k) or 0) > 0) for k in present
                          if any((v.get(k) or 0) > 0 for v in vessels)})
        abundance = {k: statistics.fmean(m[k] for m in means if k in m) for k in sorted(present)}
        experiments = sorted({e for c in runs for e in (c.get("experiments") or [c.get("experiment", "")]) if e})
        # named by the organisms present, not by the first run read: "a with c (2 runs)" named a monoculture
        # pool after a run whose c washed out (found in a third review); `runs` names the runs
        out.append({"name": f"{'+'.join(sorted(present))} ({len(runs)} runs)", "abundance": abundance,
                    "vessels": sorted((v for c in runs for v in (c.get("vessels") or [c["abundance"]])), key=by_values),
                    "run_means": means, "experiments": experiments, "runs": [c["name"] for c in runs]})
    return out


def fit(communities: list, draws: int = DRAWS, seed: int = 0) -> dict:
    """Every row of B the communities determine.

    {"rows": {species: {"status", "values": {j: B_ij}, "sd": {j: sd} or None, "equations", "condition",
                        "columns"}},
     "washed_out": [(community, species)], "unidentified": [(i, j)], "why": {(i, j): reason}}
    """
    # a wash-out is a run's own, reported under its name before the runs are pooled
    species = sorted({k for c in communities for k in (c.get("abundance") or {})})
    washed_out = [(c["name"], k) for c in communities for k, v in (c.get("abundance") or {}).items()
                  if v is None or v <= 0]
    communities = pool(communities)
    by_species = _equations(communities)
    rows, unidentified, why = {}, [], {}
    for i in species:
        equations = by_species.get(i, [])
        if not equations:
            rows[i] = {"status": "no equation", "values": {}, "sd": None, "equations": 0,
                       "condition": float("inf"), "columns": []}
            why_none = f"{i} washed out of every community it was inoculated into"
        else:
            rows[i] = {**_fit_row(i, equations), "sd": None}
            why_none = ""
        for j in species:
            if j in rows[i]["values"]:
                continue
            unidentified.append((i, j))
            if why_none:
                why[(i, j)] = why_none
            elif rows[i]["status"] == "no self-limitation":
                why[(i, j)] = (f"the row of {i} has no self-limitation (its own term {rows[i]['own']:.3g} is not "
                               "negative): either it has none, or it cannot hold alone at this dilution rate, "
                               "and which one decides the sign of every effect on it")
            elif j not in rows[i]["columns"]:
                why[(i, j)] = f"no community holds both {i} and {j} at a steady state"
            else:
                why[(i, j)] = (f"the row of {i} is underdetermined: {rows[i]['equations']} equation(s) for "
                               f"{len(rows[i]['columns'])} unknowns, or too close to tell apart")
    # the spread: only for a row every one of whose communities was measured in two vessels or more
    replicated = {c["name"] for c in communities if len(c.get("vessels") or []) >= 2}
    rng = random.Random(seed)
    samples = [_resample(communities, rng) for _ in range(draws)] if draws else []
    for i, row in rows.items():
        if row["status"] != "identified" or not samples:
            continue
        if any(name not in replicated for name, _ in by_species[i]):
            continue
        values = {j: [] for j in row["values"]}
        for sample in samples:
            again = _fit_row(i, _equations(sample).get(i, []))
            if again["status"] == "identified" and all(j in again["values"] for j in values):
                for j in values:
                    values[j].append(again["values"][j])
        # how many draws the spread rests on, and a spread only where at least half of them gave the row: a draw
        # that does not determine it is not an estimate of zero, and an sd from 2 of 200 draws read like one
        # from all of them (raised in review of the estimator)
        row["draws"] = min((len(v) for v in values.values()), default=0)
        if row["draws"] >= max(2, len(samples) // 2):
            row["sd"] = {j: statistics.stdev(v) for j, v in values.items()}
    return {"rows": rows, "washed_out": washed_out, "unidentified": unidentified, "why": why}


def leave_one_out_predictions(communities: list) -> list:
    """Each community predicted by a fit made without it: the check against context dependence.

    [{"community", "status": "predicted" or why not, "predicted": {species: N}, "observed": {species: N}}]
    The prediction is the solution of B[present] x = -1 over the members observed present.
    """
    communities = pool(communities)
    out = []
    for k, c in enumerate(communities):
        here = _present(c)
        others = communities[:k] + communities[k + 1:]
        got = fit(others, draws=0)["rows"]
        members = sorted(here)
        missing = [(i, j) for i in members for j in members if j not in got.get(i, {}).get("values", {})]
        if missing:
            out.append({"community": c["name"], "status": "not predicted: without it, "
                        + ", ".join(f"{i} on {j}" for i, j in missing[:3]) + (" and more" if len(missing) > 3
                                                                              else "") + " is not determined",
                        "predicted": {}, "observed": here})
            continue
        solved = _solve([[got[i]["values"][j] for j in members] for i in members], [-1.0] * len(members))
        if solved is None:
            out.append({"community": c["name"], "status": "not predicted: the fitted rows are singular there",
                        "predicted": {}, "observed": here})
            continue
        out.append({"community": c["name"], "status": "predicted",
                    "predicted": dict(zip(members, solved, strict=True)), "observed": here})
    return out


# ---- chemostat runs into communities, and each row's scale from the run's own start-up (#312) ----------
#
# Karoline, on #310: chemostat steady states only; the row scale s_i = r_i - D "from the chemostat itself",
# since "Mono-culture growth rates from batch are tricky, because they change in chemostat"; and "chemostat
# is not always switched on directly, so it would mean checking experiment description for a batch period".
# mGrowthDB records no such period in a field, so it is read from the description, as the chemostat check
# reads perturbations; one live run says "Chemostat mode started 4 hours after inoculation".

_NUMBER = r"(\d+(?:\.\d+)?)\s*-?\s*(h|hrs?|hours?|min|mins|minutes?|d|days?)\b"
_BATCH = [re.compile(p, re.I) for p in (
    rf"(?:chemostat|continuous)\s+(?:mode|operation|feeding|culture)?\s*(?:was\s+|were\s+)?"
    rf"(?:started|switched on|turned on|began|initiated)\s+{_NUMBER}\s+after\s+inoculation",
    rf"batch\s+(?:phase|period|growth|mode|stage)\s+(?:of|for|lasting)\s+{_NUMBER}",
    rf"(?:pumps?|feed(?:ing)?|dilution|medium flow|inflow)\s+(?:was\s+|were\s+)?"
    rf"(?:started|switched on|turned on|initiated|began)\s+(?:after|at)\s+{_NUMBER}",
    rf"after\s+{_NUMBER}\s+(?:of\s+)?batch",
)]
_FROM_START = re.compile(
    r"(?:chemostat\s+mode|dilution|pumps?|feed(?:ing)?|continuous\s+(?:mode|feeding))\s+(?:was\s+|were\s+)?"
    r"(?:started\s+|switched on\s+|run\s+|applied\s+)?(?:from|at|upon|(?:directly|immediately)\s+(?:after|at|upon))"
    r"\s+inoculation", re.I)
_HOURS = {"h": 1.0, "hr": 1.0, "hrs": 1.0, "hour": 1.0, "hours": 1.0, "min": 1 / 60, "mins": 1 / 60,
          "minute": 1 / 60, "minutes": 1 / 60, "d": 24.0, "day": 24.0, "days": 24.0}
# a curve's time unit, in hours
_PER_HOUR = {"h": 1.0, "hours": 1.0, "hour": 1.0, "min": 1 / 60, "minutes": 1 / 60, "d": 24.0, "days": 24.0}
MIN_STARTUP_POINTS = 3


def batch_period(exp: dict) -> dict:
    """When the dilution started, as the description says: {"kind", "hours", "said"}, where kind is "batch"
    (a batch period of `hours` before the pump), "from inoculation", or "unknown" (it does not say)."""
    text = " ".join(str(exp.get(k) or "") for k in ("description", "name"))
    for pattern in _BATCH:
        m = pattern.search(text)
        if m:
            return {"kind": "batch", "hours": float(m.group(1)) * _HOURS[m.group(2).lower()], "said": m.group(0)}
    m = _FROM_START.search(text)
    if m:
        return {"kind": "from inoculation", "hours": 0.0, "said": m.group(0)}
    return {"kind": "unknown", "hours": None, "said": ""}


def row_scale(curve, dilution: float, period: dict) -> dict:
    """The row scale s_i = r_i - D from a monoculture chemostat's own start-up: {"scale", "how"}.

    Inside a stated batch period the steepest rise is at most r_i, so that rate less D is one reading; after
    the pump starts the steepest rise is at most r_i - D, which is another; the larger is kept. With the
    pump on from inoculation the steepest rise is r_i - D already. Each rate is easylinear's, per hour, its
    window shortened to the points there. Neither reading is a bound once the curve is noisy: a lag, or an
    inoculum near the plateau, keeps a short start-up from its maximum rate and pulls a reading low, while
    noise pulls it high, since the steepest window is kept, and keeping the larger of two pulls it higher
    (METHOD_NOTES has the measured sizes). An error in the scale scales the row's coefficients in proportion
    and changes no sign. Where the description does not say
    when the dilution started, there is no scale and the row stays in units of r_i - D (decision 3 of
    #310)."""
    from .rates import DEFAULT_WINDOW, RateUnavailable, easylinear_fit
    if period["kind"] == "unknown":
        return {"scale": None, "how": "the description does not say when the dilution started, so the start-up "
                                      "cannot be told from batch growth; the row stays in units of r_i - D"}
    per_hour = _PER_HOUR.get((curve.time_unit or "").lower())
    if per_hour is None:
        return {"scale": None, "how": f"the curve's time unit {curve.time_unit!r} is not one this reads"}
    times, values = list(curve.times), list(curve.values)
    end = period["hours"] / per_hour if period["kind"] == "batch" else None

    def steepest(points):
        if len(points) < MIN_STARTUP_POINTS:
            return None, f"{len(points)} measured points; a rate needs {MIN_STARTUP_POINTS}"
        try:
            got = easylinear_fit([t for t, _ in points], [v for _, v in points],
                                 window=min(DEFAULT_WINDOW, len(points) - 1))
        except RateUnavailable as e:
            return None, str(e)
        # per hour, the unit the dilution rate is recorded in: a curve timed in days gave its rate per day
        # less D per hour, labelled 1/h (found in review)
        return got["rate"] / per_hour, ""

    points = list(zip(times, values, strict=True))
    if end is None:
        rate, why = steepest(points)
        if rate is None:
            return {"scale": None, "how": f"no rate in the start-up ({period['said']}): {why}"}
        scale = rate
        how = f"pump on from inoculation ({period['said']}): the steepest rise is r_i - D, {rate:.4g} per h"
    else:
        # Two readings of the same scale, and the larger is kept. Inside the batch period the steepest rise
        # is r_i at most, on a noiseless curve; after the pump starts, while the organism is still far from
        # its steady state, it is r_i - D at most. A lag or an inoculum near the plateau pulls each below the
        # truth (a 2 h lag in a 4 h batch period took 57% off r_i - D read from the batch alone, found in
        # review), which the larger of the two mostly recovers. Noise pushes the other way: with 5% noise on
        # each point the kept scale is high more often than not (found in a second review), so neither is
        # called a bound.
        batch_rate, batch_why = steepest([(t, v) for t, v in points if t <= end + 1e-9])
        pumped, pumped_why = steepest([(t, v) for t, v in points if t >= end - 1e-9])
        readings = []
        if batch_rate is not None:
            readings.append((batch_rate - dilution, f"the batch period's steepest rise r_i {batch_rate:.4g} "
                                                    f"per h less the dilution rate {dilution:.4g}"))
        if pumped is not None:
            readings.append((pumped, f"the steepest rise after the pump started, {pumped:.4g} per h"))
        if not readings:
            return {"scale": None, "how": f"no rate in the start-up ({period['said']}): {batch_why}; after the "
                                          f"pump started, {pumped_why}"}
        # the batch reading unless the other is larger by more than rounding: an exact exponential gives both
        scale, said = readings[0]
        for value, words in readings[1:]:
            if value > scale + 1e-9 * abs(scale):
                scale, said = value, words
        how = (f"batch period ({period['said']}): {said}, the larger of the two readings of r_i - D"
               if len(readings) == 2 else f"batch period ({period['said']}): {said}, the one reading of r_i - D")
    # `not scale > 0`, not `scale <= 0`: a NaN scale fails it too, and is refused with the rest
    if not scale > 0:
        return {"scale": None, "how": how + f"; {scale:.4g} is not above the dilution rate, so the organism "
                                            "could not hold a steady state at it"}
    return {"scale": scale, "how": how}


SETTLED = 0.10    # the most an organism may change between the two halves of the window a steady state is read in


def _still_changing(reps, washed) -> list:
    """What in a run is not settled: an organism present whose mean over the second half of the window the
    steady state is averaged over (`steady._tail_mean`) differs from the first half's by more than `SETTLED`,
    in any vessel. A window of fewer than four points cannot be split and is not judged."""
    from .steady import _tail_mean
    out = []
    for rep in reps:
        for curve in rep.curves:
            if curve.species in washed:
                continue
            _, (start, end), _ = _tail_mean(curve)
            inside = [(t, v) for t, v in zip(curve.times, curve.values, strict=True)
                      if start - 1e-9 <= t <= end + 1e-9 and v is not None]
            if len(inside) < 4:
                continue
            half = len(inside) // 2
            first = statistics.fmean(v for _, v in inside[:half])
            second = statistics.fmean(v for _, v in inside[half:])
            change = abs(second - first) / abs(second) if second else float("inf")
            if change > SETTLED:
                said = (f"{curve.species} changes by {change:.0%} between the two halves of the window averaged "
                        f"({start:g} to {end:g} {curve.time_unit}), more than {SETTLED:.0%}")
                if said not in out:
                    out.append(said)
    return out


def chemostat_groups(client, exps: list, spike_factor: float = None, key_of=None, study_of=None) -> list:
    """The continuous cultures among `exps` as estimator input, one group per medium, abundance unit and
    dilution rate (decision 1 of #310): {"medium", "unit", "dilution", "communities", "scales", "left_out"}.

    The steady states are the chemostat check's (`steady.observed`: the mean over the last quarter of each
    vessel, every run and organism it could not read named). A run is used only when it is known to be
    unperturbed and records its dilution rate; a member below the check's wash-out share is 0; a run with an
    inoculated member that could not be read is left out, since its effect on the others is unknown. The
    scales come from the monoculture runs' start-up (`row_scale`), the median over their vessels.

    `key_of(exp, name)` is what an organism is keyed by in the communities and the scales, its name unless
    given: the derivation keys it by its identity in its own study, so runs of several studies pool by
    identity (Karoline, 2026-11-11). `study_of(exp)` names each community's study, for the reasons.
    """
    from .adapter import replicates_for_experiment
    from .derive import media_identity
    from .growth import SPIKE_FACTOR
    from .steady import _washed_out, observed
    spike = SPIKE_FACTOR if spike_factor is None else spike_factor
    by_id = {exp.get("id"): exp for exp in exps}
    groups: dict = {}
    for entry in observed(client, exps, spike):
        name = entry["name"]
        exp = by_id.get(entry["experiment"]) or {}
        # the medium by the tool's one rule, so "Wilkins-Chalgren" and "Wilkins-Chalgren Anaerobe Broth (WC)"
        # are one medium here as everywhere else (Karoline, 2026-10-07)
        # how each organism of the run was measured: one organism's abundance read by qPCR in one community
        # and by flow cytometry in another is not one quantity (found in review), checked per group below
        reps, _ = replicates_for_experiment(client, exp, spike) if exp else ([], None)
        techniques = {}
        for rep in reps:
            for c in rep.curves:
                techniques.setdefault(c.species, set()).add(c.technique or "unrecorded")
        # the dilution rate to the six digits a condition writes it with, so 0.04 and 0.0400000001 are one
        # group rather than two too small to determine anything (raised in review of the inputs)
        key = (media_identity(exp)["key"] if exp else (entry["medium"] or "").lower(), entry["unit"],
               float(f"{entry['dilution']:.6g}"))
        group = groups.setdefault(key, {"medium": entry["medium"], "unit": entry["unit"],
                                        "dilution": entry["dilution"], "communities": [], "scales": {},
                                        "left_out": []})
        group["left_out"] += entry["left_out"]
        if entry["why_not"]:
            group["left_out"].append((name, entry["why_not"]))
            continue
        if entry["perturbed"] is None:
            group["left_out"].append((name, "not used: its description does not say it is unperturbed, and "
                                            "a fit takes only runs known to be at an unperturbed steady state"))
            continue
        members = [s.get("name") for s in exp.get("communityStrains") or []]
        unread = [m for m in members if m not in entry["organisms"]]
        if unread:
            group["left_out"].append((name, f"no steady state read for {', '.join(unread)}, so its effect on "
                                            "the others is unknown"))
            continue
        biggest = max(o["value"] for o in entry["organisms"].values())
        washed = {m for m, o in entry["organisms"].items() if _washed_out(o["value"], biggest)}
        moving = _still_changing(reps, washed)
        if moving:
            # the mean over the last quarter of a run that is still rising is not a steady state, and fitted as
            # one it gave wrong coefficients with nothing flagged (found in a fourth review)
            group["left_out"].append((name, "not at a steady state: " + "; ".join(moving)))
            continue
        def k(m, exp=exp):
            return key_of(exp, m) if key_of else m
        indices = sorted({i for o in entry["organisms"].values() for i in o.get("per_vessel", {})})
        vessels = [{k(m): (0.0 if m in washed else o["per_vessel"][i])
                    for m, o in entry["organisms"].items() if i in o.get("per_vessel", {})} for i in indices]
        # the mean over vessels, the statistic the bootstrap over vessels draws (`_resample`); the chemostat
        # check's median is the same for two vessels and near it for three
        abundance = {k(m): (0.0 if m in washed else
                         statistics.fmean(o["per_vessel"].values()) if o.get("per_vessel") else o["value"])
                     for m, o in entry["organisms"].items()}
        taken = {c["name"] for c in group["communities"]}
        group["communities"].append({"name": name if name not in taken else f"{name} ({entry['experiment']})",
                                     "abundance": abundance, "vessels": vessels,
                                     "experiment": entry["experiment"],
                                     "study": study_of(exp) if study_of else "",
                                     "techniques": {k(m): "; ".join(sorted(t)) for m, t in techniques.items()}})
        if len(members) == 1:
            period = batch_period(exp)
            # every monoculture run's vessels are gathered first: the scale was set from each run in turn, so
            # with two runs of one organism it was the last one read (found in a fifth review)
            group.setdefault("readings", {}).setdefault(k(members[0]), []).extend(
                row_scale(c, entry["dilution"], period) for rep in reps if (c := rep.curve(members[0])) is not None)
    for group in groups.values():
        for organism, got in (group.pop("readings", None) or {}).items():
            scales = [g["scale"] for g in got if g["scale"] is not None]
            # the median over the vessels, said as such: the first vessel's own reading was quoted beside a
            # scale that was not its (found in a fifth review)
            median_how = (got[0]["how"] if len(scales) <= 1 else
                          f"the median over {len(scales)} vessels' start-ups, {statistics.median(scales):.4g} per h; "
                          f"the first: {got[0]['how']}")
            group["scales"][organism] = ({"scale": statistics.median(scales), "how": median_how
                                          if len(scales) == len(got) else median_how + " (some vessels "
                                          "gave none)", "vessels": len(scales)} if scales else
                                         {"scale": None, "how": got[0]["how"] if got else "no curve read",
                                          "vessels": 0})
    settled = _by_technique(groups.values())
    for group in settled:
        for species in sorted({k for c in group["communities"] for k in c["abundance"]}):
            group["scales"].setdefault(species, {"scale": None, "vessels": 0,
                                                 "how": "no monoculture chemostat of it in this group, so its "
                                                        "row stays in units of r_i - D"})
    # a group with no usable run is kept for its reasons: dropped, a lone still-rising or perturbed run was
    # named nowhere (found in a sixth review); the derivation reports it and fits nothing
    return sorted((g for g in settled if g["communities"] or g["left_out"]),
                  key=lambda g: (g["dilution"], g["medium"], g["technique"]))


def _by_technique(groups) -> list:
    """Each group with every organism read by ONE technique throughout it: `techniques` {organism: technique}
    and `technique` the set. A run whose vessels read one organism by two techniques is left out and named;
    where an organism is read by one technique in some runs and another in others, the runs reading it by
    its more common technique (most runs, then most vessels, then the first by name) are kept and the others
    left out and named.

    One technique per organism per fit, never parts: splitting the runs into parts by technique and fitting
    each was put back together downstream, where only the abundance unit is known, so a cell took the median
    of a qPCR and a flow-cytometry coefficient and the package settled where nothing was observed (found in a
    sixth review, after the split had been rebuilt in the third, fourth and fifth)."""
    out = []
    for g in groups:
        left = list(g["left_out"])
        kept = []
        for c in g["communities"]:
            two = sorted(m for m, t in c.get("techniques", {}).items() if "; " in t)
            if two:
                left.append((c["name"], "left out: its vessels read " + ", ".join(
                    f"{m} by {c['techniques'][m]}" for m in two) + ", and one organism's abundance by two "
                    "techniques is not one quantity"))
            else:
                kept.append(c)
        runs: dict = {}
        for c in kept:
            for m, t in c.get("techniques", {}).items():
                tally = runs.setdefault(m, {}).setdefault(t, [0, 0])
                tally[0] += 1
                tally[1] += len(c.get("vessels") or [None])
        chosen = {m: min(ts, key=lambda t: (-ts[t][0], -ts[t][1], t)) for m, ts in runs.items()}
        final = []

        def where(m, c, kept=kept, chosen=chosen):
            # the studies whose runs set the technique kept, where they are not only this run's own: the fit
            # spans the studies of a search, and the reason did not say a run was left out because of another
            # study's (raised in review of the pooling)
            studies = sorted({d.get("study") for d in kept if d.get("techniques", {}).get(m) == chosen[m]
                              and d.get("study")})
            return f" (in {', '.join(studies)})" if studies and studies != [c.get("study")] else ""

        for c in kept:
            other = sorted(m for m, t in c.get("techniques", {}).items() if t != chosen[m])
            if other:
                left.append((c["name"], "left out: it reads " + ", ".join(
                    f"{m} by {c['techniques'][m]}, where the other runs of this medium and dilution rate read it "
                    f"by {chosen[m]}{where(m, c)}" for m in other) + "; one technique per organism in a fit, the "
                    "one most runs use"))
            else:
                final.append(c)
        techniques = {m: chosen[m] for m in sorted({m for c in final for m in c.get("techniques", {})})}
        out.append({**g, "communities": final, "left_out": left, "techniques": techniques,
                    "technique": "; ".join(sorted(set(techniques.values())))})
    return out


# ---- what a design determines, in words (#310) ---------------------------------------------------------

def _communities(k: int) -> str:
    return f"{k} community" if k == 1 else f"{k} communities"


NEEDS = ("An organism's row has one unknown for its own limitation and one per partner it met at a steady "
         "state, so it needs at least that many communities holding it: its monoculture and a pair with each "
         "partner, or the monocultures and every community missing one member, at one medium and dilution rate, "
         "in any of the studies searched.")


def _group_summary(communities: list, got: dict) -> str:
    """One sentence for a chemostat group: what it held, how many rows that determines, and what a row needs."""
    names = [c["name"] for c in communities]
    present = sorted({k for c in communities for k, v in c["abundance"].items() if v > 0})
    rows = [r for r in got["rows"].values() if r["status"] == "identified" and len(r["values"]) > 1]
    shown = ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
    held = (f"{_communities(len(names))} at an unperturbed steady state ({shown}), "
            f"{len(present)} organism(s) present; ")
    if not rows:
        return held + "no row is determined. " + NEEDS
    return held + f"{len(rows)} of {len(present)} rows determined."


def _row_reasons(got: dict) -> list:
    """(organism, why) for every row the design leaves undetermined or incomplete, one line each."""
    out = []
    for i, row in got["rows"].items():
        if row["status"] == "no equation":
            out.append((i, "washed out of every community it was inoculated into: no steady-state equation"))
            continue
        if row["status"] == "no self-limitation":
            out.append((i, f"its row is not reported: its own term {row['own']:.3g} is not negative, so either "
                           "it has no self-limitation or it cannot hold alone at this dilution rate (living on "
                           "its partners), and which one decides whether each partner helps or harms it"))
            continue
        if row["status"] == "underdetermined":
            e, u = row["equations"], len(row["columns"])
            holds = f"{_communities(e)} hold{'s' if e == 1 else ''} it at a steady state, for {u} unknowns"
            out.append((i, f"its row is not determined: {holds} (its own limitation and {u - 1} partner(s))"
                        + ("" if e < u else ", and they are too alike to tell apart: the partners stand in "
                                            "the same proportions in each")))
            continue
        never = [j for (r, j), why in got["why"].items() if r == i and j != i and "no community holds both" in why]
        if never:
            out.append((i, f"no community holds it at a steady state with {', '.join(never)}, so their effects "
                           "on it are not derived"))
    return out


def determined_any(skipped: list) -> bool:
    """Whether some chemostat group determined a row with a partner: then arcs were derived, and an empty
    result is a filter's doing (the partner filter, the absence threshold), which the general reasons name.
    The steady lead said "no chemostat design here determines a row" beside "3 of 3 rows determined"
    (found in a fourth review)."""
    return any(what.startswith("chemostat group at ") and "rows determined" in str(why)
               and "no row is determined" not in str(why) for what, why in skipped)


def empty_reason(skipped: list, command_line: bool = False) -> str:
    """Why the steady-state derivation gave nothing, from what the groups held: the lead the page and the
    command line give instead of the replicate comparison's own sentences. Each surface names its own
    control for going back to batch cultures."""
    switch = ("Derive without --derivation steady to read batch cultures instead." if command_line else
              "Set Derivation in Advanced settings to derive from batch cultures instead.")
    groups = [(what[len("chemostat group at "):], why) for what, why in skipped
              if what.startswith("chemostat group at ")]
    if not groups:
        # "these studies hold no continuous culture" was false where the second box or the Technique setting
        # had removed the one a study holds (found in a second review): say what was read, not what is held
        box = any("matches the media, experiments or studies entered" in str(why) for _, why in skipped)
        return ("No chemostat design here determines a row: of the experiments read"
                + (", after the second box left some out," if box else
                   " (the second box and the Technique setting narrow them)")
                + " none is a continuous culture at an unperturbed steady state with its dilution rate recorded, "
                "which is all this derivation reads. "
                # only where a reason says what a study held, not where every one is the second box's (found
                # in a third review)
                + ("The reasons say what each study held. "
                   if any("matches the media, experiments or studies entered" not in str(why) for _, why in skipped)
                   else "") + switch)
    said = " ".join(f"At {setting}: {why}" for setting, why in groups[:3])
    more = f" ({len(groups) - 3} more groups among the reasons.)" if len(groups) > 3 else ""
    return f"No chemostat design here determines a row. {said}{more} The reasons say what each organism lacks. {switch}"


# ---- the derivation (#313) ------------------------------------------------------------------------------

METHOD = ("steady state v1: at a chemostat steady state every member present satisfies 1 + sum_j B_ij N_j = 0 "
          "with B = A / (r_i - D); each row solved by least squares over every unperturbed sub-community of "
          "one medium composition, abundance unit and dilution rate across the studies searched, each organism "
          "read by one technique (EPICS, Ansari "
          "et al. 2021, generalized)")
METRIC = "steady_state:subcommunities"


class SteadyStateDeriver:
    """The third derivation: gLV rows from the chemostat steady states of sub-communities (#310).

    Off by default and chosen with Derivation in Advanced settings or `--derivation steady`. It reads
    continuous cultures only (`chemostat_groups`), fits each group's rows (`fit`), and turns every
    identified off-diagonal coefficient into an arc:

      * strength log2(1 + B_ij x_j*), x_j* the partner's abundance in the largest community of the group
        holding both, the scale the other derivations report on; where 1 + B_ij x_j* is not positive the
        partner would stop i's net growth, and the arc is abolished with no ratio, as the integrated form's;
      * its sd from the row's bootstrap over vessels, through d strength / d B = x / ((1 + B x) ln 2), and
        none where a community of the row has a single vessel, so presence is then undetermined;
      * the coefficient s_i B_ij in 1/(time x abundance) where the row's scale s_i = r_i - D was read from
        the chemostat's own start-up, and B_ij itself, in units of r_i - D, where it was not.

    What the design leaves undetermined, what washed out, and how each community is predicted by a fit
    made without it are in the skipped reasons and the arcs' notes.
    """

    name = "steady-v1"
    method = METHOD
    no_growth_rule = False
    # it reads chemostat steady states only, so none of the comparison's settings reaches it
    ignores = ("metric", "rate_method", "rate_window", "include_dropout", "include_non_batch",
               "no_growth_alpha", "no_growth_factor", "capacity_max_fall")
    needs_client = True
    statistics = {
        "test": "none: the spread of each coefficient is a bootstrap over the vessels (or pooled runs) of every "
                "community its row rests on, and there is no test statistic",
        "correction": "{name} over every comparison tested in this derivation (none here)",
        "role": "presence is decided by the absence threshold on the bootstrap spread",
    }
    provisional = (
        "Each interaction is an effective generalized Lotka-Volterra coefficient fitted from chemostat steady "
        "states: at a steady state every organism present satisfies 1 + sum_j B_ij N_j = 0 with B = A / (r_i "
        "- D), and each organism's row is the least-squares solution over every unperturbed community of one "
        "medium composition, abundance unit and dilution rate it was present in, across the studies "
        "searched, each organism read by one technique there. Effective means that an effect needing "
        "a third organism is folded into the pairs that carry it, so a coefficient describes the communities "
        "it was fitted from. The strength beside it is log2(1 + B_ij x_j) at the partner's abundance in the "
        "largest community holding both. An interaction is reported when |strength| is at least k standard "
        "deviations, the spread being a bootstrap over vessels (over runs where runs were pooled, and within "
        "one run otherwise, so narrower than run-to-run differences); a row with any community read in a single "
        "vessel has none. Runs that end with the same organisms are one community, and a row whose own term is "
        "not negative is not reported, since the sign of every effect on it would depend on whether r_i is "
        "below D (see docs/METHOD_NOTES.md in the grownet repository)."
    )

    # the second box (media, experiments, studies) is applied here, as the other derivations apply it: it
    # was read by the default derivation only, so naming one medium changed nothing under the others (found
    # in review). `derive_interactions` hands the selection to a deriver that says it applies it.
    applies_selection = True

    def __init__(self, client=None, spike_factor: float = None, draws: int = DRAWS, selection=None,
                 **_ignored):
        self.client = client
        self.spike_factor = spike_factor
        self.draws = draws
        self.selection = selection

    # A search hands every study to `derive_many` at once, so runs of several studies in one medium are fitted
    # together (Karoline, 2026-11-06: "for the new chemostat inference mode, the medium composition has to
    # match but other than that, I don't see why not"); `derive` is one study, for the command line's study
    # path and `derive_interactions`.
    pools_studies = True

    def derive(self, study: dict, exps: list):
        return self.derive_many([(study, exps)])

    def derive_many(self, studies: list):
        """(records, skipped) from the chemostat runs of every study given, [(study, experiments)], fitted
        together where the medium composition (`media_identity`), the abundance unit and the dilution rate
        match. An arc names every study its communities come from."""
        import math

        from .derive import _identity, select_experiments, strain_identities
        from .integrated import _log2_effect
        if self.client is None:
            raise ValueError("SteadyStateDeriver needs a client: it reads each vessel's measured series")
        metas, of_exp, by_study, published, records, skipped = {}, {}, {}, {}, [], []
        for study, exps in sorted(studies, key=lambda s: s[0].get("id", "")):
            study_id = study.get("id", "")
            metas[study_id] = {"id": study_id, "citation": study.get("name") or study_id, "license": "",
                               "url": study.get("url", "")}
            published[study_id] = study.get("publishedAt") or study.get("uploadedAt") or ""
            # a strain's identity is judged within its own study, as every derivation judges it, over the whole
            # study (a taxon id given to two strain names there is refused as before); then the experiments the
            # second box asks for, with the monocultures under the same conditions. Runs of several studies are
            # pooled by that identity, so a strain whose trusted taxon id agrees pools under two names (Karoline,
            # 2026-11-11: "option A, but if taxon ids agree and names differ, the studies can still be pooled
            # (since a taxon name may change, as in the case of F. prausnitzii A2-165 and F. duncaniae A2-165).
            # Name conflicts within a study can be treated as before."). Judged over every study of the search,
            # one unrelated study could demote a strain everywhere (raised in review of the pooling).
            by_study[study_id] = strain_identities(exps, [])
            for exp in select_experiments(exps, self.selection, skipped, study_id=study_id):
                of_exp[exp.get("id")] = (study_id, exp)

        def study_of(exp):
            return of_exp.get(exp.get("id"), ("", None))[0]

        # each organism key's identity as each study gives it, with the name it goes by there
        identity_of: dict = {}
        names_of: dict = {}

        def key_of(exp, name):
            got = _identity(by_study.get(study_of(exp), {}), name)
            identity_of.setdefault(got["id"], {}).setdefault(study_of(exp), {**got, "name": name})
            names_of.setdefault(name, set()).add(got["id"])
            return got["id"]

        def shown(key, arc_studies):
            # an arc names its organism as one of the studies the arc rests on does, the most recently
            # published, so a renamed strain goes by its later name; the first study of the whole search named
            # it, which could be a study the arc does not rest on and, for A2-165, the superseded name
            # (raised in review of the pooling)
            per_study = identity_of[key]
            # an arc rests on studies holding each of its organisms, so `ours` is empty only where there is no
            # arc (a group whose runs were all left out, `say(..., [])`): there the whole search names it
            ours = [s for s in arc_studies if s in per_study] or sorted(per_study)
            return per_study[max(ours, key=lambda s: (published.get(s, ""), s))]

        def other_names(key, arc_studies):
            # the latest study's name is a guess at the current one, so where the arc's studies name the
            # organism differently the others are said, and so is a choice no date could make (Karoline,
            # 2026-11-12, on the review's point that undated studies were named by study id)
            per_study = identity_of[key]
            ours = [s for s in arc_studies if s in per_study]
            chosen = shown(key, arc_studies)
            others = {}
            for s in ours:
                if per_study[s]["name"] != chosen["name"]:
                    others.setdefault(per_study[s]["name"], []).append(s)
            if not others:
                return None
            picked = max(ours, key=lambda s: (published.get(s, ""), s))
            rivals = [s for s in ours if per_study[s]["name"] != chosen["name"]]
            undated = [s for s in rivals if not published.get(s)]
            # a date chose only where the shown study has one and every dated rival is earlier; an undated
            # rival is said, since "most recently published" overclaims about a study with no date (raised in
            # review of the pooling)
            if published.get(picked) and all(published.get(s, "") < published[picked] for s in rivals):
                how = "the name in the most recently published of them" + (
                    f", as {', '.join(undated)} carries no publication date" if undated else "")
            else:
                how = "the name in the study whose id sorts last, as no publication date tells them apart"
            # no "; " inside: notes are written joined by "; ", and a note holding it splits into fragments
            # (raised in review of the pooling). It opens with the key, which `say` turns into the name shown,
            # with the key where two identities share that name, as every other line of the arc
            return (f"{key} is named differently in studies this arc rests on, "
                    + ", ".join(f"{n} (in {', '.join(ss)})" for n, ss in sorted(others.items()))
                    + f", and is shown by {how}")

        exps = [exp for _, exp in of_exp.values()]
        groups = chemostat_groups(self.client, exps, self.spike_factor, key_of=key_of, study_of=study_of)
        # one name that stands for two identities in two studies (its taxon id trusted in one and refused in the
        # other, say) is two organisms here, so its runs are not pooled; said once
        skipped += [(name, f"identified differently in the studies searched ({', '.join(sorted(ids))}), so its "
                           "runs are fitted as different organisms rather than pooled")
                    for name, ids in sorted(names_of.items()) if len(ids) > 1]
        def say(lines, in_studies):
            # the fit is keyed by identity, so its reasons name "ncbi:226186" where a reader wants the strain:
            # each key is put back as the name it goes by in the group's studies (with the key where two
            # identities share a name), in one pass so a name put in is not read again
            keys = sorted(identity_of, key=len, reverse=True)
            if not keys:
                return list(lines)
            names = {k: shown(k, in_studies)["name"] for k in keys}
            twice = {n for n in names.values() if list(names.values()).count(n) > 1}
            names = {k: (f"{n} ({k})" if n in twice else n) for k, n in names.items()}
            pattern = re.compile(r"(?<![\w:])(" + "|".join(map(re.escape, keys)) + r")(?![\w:])")
            return [tuple(pattern.sub(lambda m: names[m.group(1)], part) for part in line) for line in lines]

        for group in groups:
            label = (f"chemostat, D {group['dilution']:g} per h, {group['medium']}, {group['unit']}"
                     + (f", {group['technique']}" if group.get("technique") else ""))
            if not group["communities"]:
                skipped += say([(f"{what} [{label}]", why) for what, why in group["left_out"]], [])
                continue
            # runs of the same members are one equation (`pool`), here as in the fit, so an arc's community,
            # its experiments and its leave-one-out note name what the fit used
            communities = pool(group["communities"])
            # the fit takes the runs as they are and pools them itself, so a run's wash-out is reported under
            # its own name: pooled first, it was lost (found in a third review)
            got = fit(group["communities"], draws=self.draws)
            # what the design can and cannot determine, said once for the group and once per organism rather
            # than once per coefficient, which was n^2 lines of the same sentence (Karoline, 2026-11-06: "Is
            # the error message in this case informative?")
            setting = label[len("chemostat, "):]
            # the studies the group's runs come from, named, since one fit may span several
            in_studies = sorted({of_exp[e][0] for c in group["communities"]
                                 for e in (c.get("experiments") or [c.get("experiment", "")]) if e in of_exp})
            skipped += say([(f"chemostat group at {setting} in {', '.join(in_studies)}",
                             _group_summary(communities, got))]
                           + [(f"{what} [{label}]", why) for what, why in group["left_out"]]
                           + [(f"{species} in {community} [{label}]", "washed out: no steady-state equation")
                              for community, species in got["washed_out"]]
                           + [(f"{i} [{label}]", why) for i, why in _row_reasons(got)], in_studies)
            predictions = {p["community"]: p for p in leave_one_out_predictions(communities)}
            for i, row in got["rows"].items():
                if row["status"] != "identified":
                    continue
                scale = group["scales"].get(i, {"scale": None, "how": "no scale"})
                s_i = scale["scale"]
                unit_coefficient = (f"1/(h x {group['unit']})" if s_i is not None
                                    else f"1/{group['unit']}, in units of r_i - D")
                # every study the row was fitted from: the coefficient rests on all of the row's equations, not
                # only on the communities holding the pair
                row_experiments = {e for c in communities if (c["abundance"].get(i) or 0) > 0
                                   for e in (c.get("experiments") or [c.get("experiment", "")])}
                untraced = sorted(e or "(no id)" for e in row_experiments if e not in of_exp)
                if untraced:
                    # a row that cannot name every study it rests on is not reported: it was credited to the
                    # first study of the search, a plausible citation and a wrong one (raised in review of the
                    # pooling). Not reached today, since every run is read from a study; said if it ever is
                    skipped.append((f"{shown(i, in_studies)['name']} [{label}]",
                                    f"its row rests on runs not traced to a study ({', '.join(untraced)}), so the "
                                    "study it would cite is unknown and its arcs are not reported"))
                    continue
                arc_studies = sorted({of_exp[e][0] for e in row_experiments})
                for j, b in row["values"].items():
                    if j == i:
                        continue
                    holding = [c for c in communities if (c["abundance"].get(i) or 0) > 0
                               and (c["abundance"].get(j) or 0) > 0]
                    # a tie between communities of one size is broken by their members, not their names (by
                    # name, renaming two runs changed an arc's strength, found in a sixth review)
                    largest = max(holding, key=lambda c: (len(_present(c)), tuple(sorted(_present(c)))))
                    x = largest["abundance"][j]
                    strength = _log2_effect(b, x, 1.0)
                    sd_b = (row["sd"] or {}).get(j) if row["sd"] is not None else None
                    sd = (None if sd_b is None or strength is None
                          else abs(x / ((1 + b * x) * math.log(2))) * sd_b)
                    arc_experiments = sorted({e for c in holding
                                              for e in (c.get("experiments") or [c.get("experiment", "")])} - {""})
                    check = predictions.get(largest["name"], {})
                    notes = [f"row scale: {scale['how']}"]
                    if check.get("status") == "predicted" and i in check["predicted"]:
                        notes.append(f"{largest['name']} predicted without it: {i} at "
                                     f"{check['predicted'][i]:.3g}, observed {check['observed'][i]:.3g}")
                    elif check.get("status"):
                        notes.append(f"{largest['name']} {check['status']}")
                    notes += [n for n in (other_names(j, arc_studies), other_names(i, arc_studies)) if n]
                    notes = [line for (line,) in say([(n,) for n in notes], arc_studies)]
                    # the communities are keyed by identity (`key_of`); each is shown as one of the arc's studies
                    # gives it (`shown`)
                    source, target = shown(j, arc_studies), shown(i, arc_studies)
                    records.append({
                        "source": source["id"], "target": target["id"],
                        "source_name": source["name"], "target_name": target["name"],
                        "source_taxon_id": source["taxon_id"], "target_taxon_id": target["taxon_id"],
                        "source_species": source["species"], "target_species": target["species"],
                        "source_identity": source["identity"], "target_identity": target["identity"],
                        # why a strain lost its taxon id, where it did, as the other derivations write it
                        "source_taxon_id_refused": source.get("taxon_id_refused", ""),
                        "target_taxon_id_refused": target.get("taxon_id_refused", ""),
                        "effect": "facilitation" if b > 0 else "inhibition",
                        "strength": None if strength is None else round(strength, 4),
                        # |strength|, as every derivation's arcs carry it for widths and layouts (it was null
                        # on every steady arc, found in a third review)
                        "weight": None if strength is None else round(abs(strength), 4),
                        "outcome": "abolished" if strength is None else "quantified",
                        "strength_bound": None,
                        "bound_rule": ("no ratio: at this partner level the fitted row puts the organism's "
                                       "net growth at or below zero" if strength is None else ""),
                        "metric": METRIC, "method": METHOD, "evidence": "steady_state",
                        "quality": [], "cautions": [], "notes": notes,
                        "cultivation_mode": "chemostat", "medium": group["medium"], "condition": label,
                        # how the target was measured: one technique per organism within a fit (`_by_technique`)
                        "technique": group.get("techniques", {}).get(i) or "unrecorded",
                        # the members present: one inoculated and washed out is not in the community
                        "community": sorted(_present(largest)),
                        "experiments": arc_experiments,
                        "n_with": len(largest.get("vessels") or []) or None, "n_without": None,
                        "sd": None if sd is None else round(sd, 4), "se": None,
                        "p_value": None, "q_value": None, "significance": None,
                        "effect_over_sd": (None if not sd or strength is None else round(abs(strength) / sd, 4)),
                        # i's net growth rate its row implies with the partner at x and without it, as the
                        # integrated form records them, so the package takes the coefficient from their
                        # difference over x like any fitted arc; a row with no scale has no rate to give
                        "metric_with": None if s_i is None else s_i * (1 + b * x),
                        "metric_without": s_i, "metric_unit": "1/h" if s_i is not None else "",
                        "coefficient": (s_i * b) if s_i is not None else b,
                        "coefficient_unit": unit_coefficient,
                        "coefficient_sd": (None if sd_b is None else (s_i or 1.0) * sd_b),
                        "fitted_rate": s_i, "fitted_rate_unit": "1/h",
                        "fitted_rate_dilution": group["dilution"],
                        "fitted_self": (s_i * row["values"][i]) if s_i is not None else row["values"][i],
                        "fitted_self_unit": group["unit"],
                        # the technique the organism's own abundance was read by, which the capacity rule keys on
                        # (it was never set, so plateaus by two techniques were pooled, found in a sixth review)
                        "fitted_self_technique": group["techniques"].get(i, ""),
                        "partner_abundance": x, "partner_abundance_unit": group["unit"],
                        "partner_abundance_n": len(largest.get("vessels") or []),
                        # every study the communities behind the arc come from, as a merged arc names them
                        # the fit the row comes from, which may span studies: a row counts once in the rates
                        "fitted_group": f"{label} in {', '.join(in_studies)}",
                        "study_id": arc_studies[0], "study_citation": metas[arc_studies[0]]["citation"],
                        "study_license": "", "study_url": metas[arc_studies[0]]["url"],
                        "studies": [metas[s] for s in arc_studies],
                    })
        return records, skipped
