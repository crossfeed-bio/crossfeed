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
    run's wash-out, which `fit` reports under the run's own name. Its name is the first run's, with the count,
    and `runs` names them all."""
    groups: dict = {}
    for c in communities:
        groups.setdefault(frozenset(_present(c)), []).append(c)
    out = []
    for present, runs in groups.items():
        if len(runs) == 1:
            out.append(runs[0])
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
                    "vessels": [v for c in runs for v in (c.get("vessels") or [c["abundance"]])],
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
            if again["status"] == "identified":
                for j in values:
                    values[j].append(again["values"].get(j, 0.0))
        if all(len(v) >= 2 for v in values.values()):
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
    if not scale > 0:
        return {"scale": None, "how": how + f"; {scale:.4g} is not above the dilution rate, so the organism "
                                            "could not hold a steady state at it"}
    return {"scale": scale, "how": how}


def chemostat_groups(client, exps: list, spike_factor: float = None) -> list:
    """The continuous cultures among `exps` as estimator input, one group per medium, abundance unit and
    dilution rate (decision 1 of #310): {"medium", "unit", "dilution", "communities", "scales", "left_out"}.

    The steady states are the chemostat check's (`steady.observed`: the mean over the last quarter of each
    vessel, every run and organism it could not read named). A run is used only when it is known to be
    unperturbed and records its dilution rate; a member below the check's wash-out share is 0; a run with an
    inoculated member that could not be read is left out, since its effect on the others is unknown. The
    scales come from the monoculture runs' start-up (`row_scale`), the median over their vessels.
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
        key = (media_identity(exp)["key"] if exp else (entry["medium"] or "").lower(), entry["unit"],
               entry["dilution"])
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
        indices = sorted({i for o in entry["organisms"].values() for i in o.get("per_vessel", {})})
        vessels = [{m: (0.0 if m in washed else o["per_vessel"][i])
                    for m, o in entry["organisms"].items() if i in o.get("per_vessel", {})} for i in indices]
        # the mean over vessels, the statistic the bootstrap over vessels draws (`_resample`); the chemostat
        # check's median is the same for two vessels and near it for three
        abundance = {m: (0.0 if m in washed else
                         statistics.fmean(o["per_vessel"].values()) if o.get("per_vessel") else o["value"])
                     for m, o in entry["organisms"].items()}
        taken = {c["name"] for c in group["communities"]}
        group["communities"].append({"name": name if name not in taken else f"{name} ({entry['experiment']})",
                                     "abundance": abundance, "vessels": vessels,
                                     "experiment": entry["experiment"],
                                     "techniques": {m: "; ".join(sorted(t)) for m, t in techniques.items()}})
        if len(members) == 1:
            period = batch_period(exp)
            got = [row_scale(c, entry["dilution"], period) for rep in reps
                   if (c := rep.curve(members[0])) is not None]
            scales = [g["scale"] for g in got if g["scale"] is not None]
            group["scales"][members[0]] = ({"scale": statistics.median(scales), "how": got[0]["how"]
                                            if len(scales) == len(got) else got[0]["how"] + " (some vessels "
                                            "gave none)", "vessels": len(scales)} if scales else
                                           {"scale": None, "how": got[0]["how"] if got else "no curve read",
                                            "vessels": 0})
    settled = _by_technique(groups.values())
    for group in settled:
        for species in sorted({k for c in group["communities"] for k in c["abundance"]}):
            group["scales"].setdefault(species, {"scale": None, "vessels": 0,
                                                 "how": "no monoculture chemostat of it in this group, so its "
                                                        "row stays in units of r_i - D"})
    return sorted((g for g in settled if g["communities"]),
                  key=lambda g: (g["dilution"], g["medium"], g["technique"]))


def _by_technique(groups) -> list:
    """Each group as it is where every organism was read by one technique throughout it, with `techniques`
    {organism: technique} and `technique` the set; otherwise split into one group per run-level technique,
    named. Grouping every run by its run-level technique split a design where each organism keeps its own
    technique (a by qPCR, b by flow cytometry) into three groups that determined nothing (found in a second
    review)."""
    out = []
    for g in groups:
        per: dict = {}
        for c in g["communities"]:
            for m, t in c.get("techniques", {}).items():
                per.setdefault(m, set()).add(t)
        mixed = {m: ts for m, ts in per.items() if len(ts) > 1}
        if not mixed:
            g["techniques"] = {m: next(iter(ts)) for m, ts in per.items()}
            g["technique"] = "; ".join(sorted({t for ts in per.values() for t in ts}))
            out.append(g)
            continue
        said = "; ".join(f"{m} by {' and '.join(sorted(ts))}" for m, ts in sorted(mixed.items()))
        # each run joins the first part whose organisms it reads the same way, so within a part every organism
        # has one technique: splitting by the run's set of techniques put a run reading a by fc and b by qpcr
        # beside one reading them the other way round (found in a third review)
        parts: list = []
        for c in sorted(g["communities"], key=lambda c: c["name"]):
            own = c.get("techniques", {})
            for part in parts:
                if all(part["techniques"].get(m, t) == t for m, t in own.items()):
                    part["techniques"].update(own)
                    part["communities"].append(c)
                    break
            else:
                parts.append({"techniques": dict(own), "communities": [c]})
        for k, part in enumerate(parts):
            techniques, communities = part["techniques"], part["communities"]
            t = ", ".join(f"{m} by {tech}" for m, tech in sorted(techniques.items()))
            out.append({**g, "communities": communities, "technique": t, "techniques": techniques,
                        "scales": dict(g["scales"]),
                        "left_out": (list(g["left_out"]) if k == 0 else []) + [
                            (f"runs measured by {t}", f"fitted apart from the runs measured otherwise, since in "
                                                      f"this medium and dilution rate {said}, and one organism's "
                                                      "abundance by two techniques is not one quantity")]})
    return out


# ---- what a design determines, in words (#310) ---------------------------------------------------------

def _communities(k: int) -> str:
    return f"{k} community" if k == 1 else f"{k} communities"


NEEDS = ("An organism's row has one unknown for its own limitation and one per partner it met at a steady "
         "state, so it needs at least that many communities holding it: its monoculture and a pair with each "
         "partner, or the monocultures and every community missing one member, at one medium and dilution rate.")


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
                + ("The reasons say what each study held. " if skipped else "") + switch)
    said = " ".join(f"At {setting}: {why}" for setting, why in groups[:3])
    more = f" ({len(groups) - 3} more groups among the reasons.)" if len(groups) > 3 else ""
    return f"No chemostat design here determines a row. {said}{more} The reasons say what each organism lacks. {switch}"


# ---- the derivation (#313) ------------------------------------------------------------------------------

METHOD = ("steady state v1: at a chemostat steady state every member present satisfies 1 + sum_j B_ij N_j = 0 "
          "with B = A / (r_i - D); each row solved by least squares over every unperturbed sub-community of "
          "one medium, abundance unit and dilution rate, each organism read by one technique (EPICS, Ansari "
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
        "medium, abundance unit and dilution rate it was present in, each organism read by one technique "
        "there. Effective means that an effect needing "
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

    def derive(self, study: dict, exps: list):
        import math

        from .derive import _identity, select_experiments, strain_identities
        from .integrated import _log2_effect
        if self.client is None:
            raise ValueError("SteadyStateDeriver needs a client: it reads each vessel's measured series")
        study_id = study.get("id", "")
        study_meta = {"study_citation": study.get("name") or study_id, "study_license": "",
                      "study_url": study.get("url", "")}
        # identities over the whole study, as the other derivations judge an ambiguous taxon id, then the
        # experiments the second box asks for, with the monocultures under the same conditions
        identities = strain_identities(exps, [])
        records, skipped = [], []
        exps = select_experiments(exps, self.selection, skipped, study_id=study_id)
        for group in chemostat_groups(self.client, exps, self.spike_factor):
            label = (f"chemostat, D {group['dilution']:g} per h, {group['medium']}, {group['unit']}"
                     + (f", {group['technique']}" if group.get("technique") else ""))
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
            skipped += [(f"chemostat group at {setting}", _group_summary(communities, got))]
            skipped += [(f"{what} [{label}]", why) for what, why in group["left_out"]]
            skipped += [(f"{species} in {community} [{label}]", "washed out: no steady-state equation")
                        for community, species in got["washed_out"]]
            skipped += [(f"{i} [{label}]", why) for i, why in _row_reasons(got)]
            predictions = {p["community"]: p for p in leave_one_out_predictions(communities)}
            for i, row in got["rows"].items():
                if row["status"] != "identified":
                    continue
                scale = group["scales"].get(i, {"scale": None, "how": "no scale"})
                s_i = scale["scale"]
                unit_coefficient = (f"1/(h x {group['unit']})" if s_i is not None
                                    else f"1/{group['unit']}, in units of r_i - D")
                for j, b in row["values"].items():
                    if j == i:
                        continue
                    holding = [c for c in communities if (c["abundance"].get(i) or 0) > 0
                               and (c["abundance"].get(j) or 0) > 0]
                    largest = max(holding, key=lambda c: (len([v for v in c["abundance"].values() if v > 0]),
                                                          c["name"]))
                    x = largest["abundance"][j]
                    strength = _log2_effect(b, x, 1.0)
                    sd_b = (row["sd"] or {}).get(j) if row["sd"] is not None else None
                    sd = (None if sd_b is None or strength is None
                          else abs(x / ((1 + b * x) * math.log(2))) * sd_b)
                    check = predictions.get(largest["name"], {})
                    notes = [f"row scale: {scale['how']}"]
                    if check.get("status") == "predicted" and i in check["predicted"]:
                        notes.append(f"{largest['name']} predicted without it: {i} at "
                                     f"{check['predicted'][i]:.3g}, observed {check['observed'][i]:.3g}")
                    elif check.get("status"):
                        notes.append(f"{largest['name']} {check['status']}")
                    source, target = _identity(identities, j), _identity(identities, i)
                    records.append({
                        "source": source["id"], "target": target["id"], "source_name": j, "target_name": i,
                        "source_taxon_id": source["taxon_id"], "target_taxon_id": target["taxon_id"],
                        "source_species": source["species"], "target_species": target["species"],
                        "source_identity": source["identity"], "target_identity": target["identity"],
                        "effect": "facilitation" if b > 0 else "inhibition",
                        "strength": None if strength is None else round(strength, 4),
                        "outcome": "abolished" if strength is None else "quantified",
                        "strength_bound": None,
                        "bound_rule": ("no ratio: at this partner level the fitted row puts the organism's "
                                       "net growth at or below zero" if strength is None else ""),
                        "metric": METRIC, "method": METHOD, "evidence": "steady_state",
                        "quality": [], "cautions": [], "notes": notes,
                        "cultivation_mode": "chemostat", "medium": group["medium"], "condition": label,
                        # the members present: one inoculated and washed out is not in the community
                        "community": sorted(_identity(identities, m)["id"] for m in _present(largest)),
                        "experiments": sorted({e for c in holding
                                               for e in (c.get("experiments") or [c.get("experiment", "")])} - {""}),
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
                        "partner_abundance": x, "partner_abundance_unit": group["unit"],
                        "partner_abundance_n": len(largest.get("vessels") or []),
                        "study_id": study_id, **study_meta,
                    })
        return records, skipped
