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
    two vessels or more (decision 5 of #310); otherwise it has none, and its arcs are undetermined.

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
    return {"status": "identified", "values": dict(zip(columns, got["values"], strict=True)),
            "columns": columns, "equations": len(equations), "condition": got["condition"]}


def _resample(communities: list, rng: random.Random) -> list:
    """The communities with each one's vessels drawn with replacement, where it has two or more."""
    out = []
    for c in communities:
        vessels = c.get("vessels") or []
        if len(vessels) < 2:
            out.append(c)
            continue
        drawn = [rng.choice(vessels) for _ in vessels]
        keys = set().union(*drawn)
        out.append({**c, "abundance": {k: statistics.fmean(v.get(k, 0.0) for v in drawn) for k in keys}})
    return out


def fit(communities: list, draws: int = DRAWS, seed: int = 0) -> dict:
    """Every row of B the communities determine.

    {"rows": {species: {"status", "values": {j: B_ij}, "sd": {j: sd} or None, "equations", "condition",
                        "columns"}},
     "washed_out": [(community, species)], "unidentified": [(i, j)], "why": {(i, j): reason}}
    """
    species = sorted({k for c in communities for k in (c.get("abundance") or {})})
    washed_out = [(c["name"], k) for c in communities for k, v in (c.get("abundance") or {}).items()
                  if v is None or v <= 0]
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

    Inside a stated batch period the rise is r_i, so the scale is that rate less D; with the pump on from
    inoculation the rise is r_i - D already. The rate is easylinear's, over the start-up only, with its
    window shortened to the points there. Where the description does not say when the dilution started,
    there is no scale and the row stays in units of r_i - D (decision 3 of #310)."""
    from .rates import DEFAULT_WINDOW, RateUnavailable, easylinear_fit
    if period["kind"] == "unknown":
        return {"scale": None, "how": "the description does not say when the dilution started, so the start-up "
                                      "cannot be told from batch growth; the row stays in units of r_i - D"}
    per_hour = _PER_HOUR.get((curve.time_unit or "").lower())
    if per_hour is None:
        return {"scale": None, "how": f"the curve's time unit {curve.time_unit!r} is not one this reads"}
    times, values = list(curve.times), list(curve.values)
    if period["kind"] == "batch":
        end = period["hours"] / per_hour
        keep = [(t, v) for t, v in zip(times, values, strict=True) if t <= end + 1e-9]
        times, values = [t for t, _ in keep], [v for _, v in keep]
    if len(times) < MIN_STARTUP_POINTS:
        return {"scale": None, "how": f"{len(times)} measured points in the start-up "
                                      f"({period['said']}); a rate needs {MIN_STARTUP_POINTS}"}
    try:
        got = easylinear_fit(times, values, window=min(DEFAULT_WINDOW, len(times) - 1))
    except RateUnavailable as e:
        return {"scale": None, "how": f"no rate in the start-up ({period['said']}): {e}"}
    if period["kind"] == "batch":
        scale = got["rate"] - dilution
        how = (f"batch period ({period['said']}): r_i {got['rate']:.4g} less the dilution rate {dilution:.4g}")
    else:
        scale = got["rate"]
        how = f"pump on from inoculation ({period['said']}): the rise is r_i - D, {got['rate']:.4g}"
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
    from .growth import SPIKE_FACTOR
    from .steady import _washed_out, observed
    spike = SPIKE_FACTOR if spike_factor is None else spike_factor
    by_id = {exp.get("id"): exp for exp in exps}
    groups: dict = {}
    for entry in observed(client, exps, spike):
        name = entry["name"]
        key = ((entry["medium"] or "").lower(), entry["unit"], entry["dilution"])
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
        exp = by_id.get(entry["experiment"]) or {}
        members = [s.get("name") for s in exp.get("communityStrains") or []]
        unread = [m for m in members if m not in entry["organisms"]]
        if unread:
            group["left_out"].append((name, f"no steady state read for {', '.join(unread)}, so its effect on "
                                            "the others is unknown"))
            continue
        biggest = max(o["value"] for o in entry["organisms"].values())
        abundance = {m: (0.0 if _washed_out(o["value"], biggest) else o["value"])
                     for m, o in entry["organisms"].items()}
        indices = sorted({i for o in entry["organisms"].values() for i in o.get("per_vessel", {})})
        vessels = [{m: (0.0 if abundance[m] == 0.0 else o["per_vessel"][i])
                    for m, o in entry["organisms"].items() if i in o.get("per_vessel", {})} for i in indices]
        taken = {c["name"] for c in group["communities"]}
        group["communities"].append({"name": name if name not in taken else f"{name} ({entry['experiment']})",
                                     "abundance": abundance, "vessels": vessels,
                                     "experiment": entry["experiment"]})
        if len(members) == 1:
            period = batch_period(exp)
            reps, _ = replicates_for_experiment(client, exp, spike)
            got = [row_scale(c, entry["dilution"], period) for rep in reps
                   if (c := rep.curve(members[0])) is not None]
            scales = [g["scale"] for g in got if g["scale"] is not None]
            group["scales"][members[0]] = ({"scale": statistics.median(scales), "how": got[0]["how"]
                                            if len(scales) == len(got) else got[0]["how"] + " (some vessels "
                                            "gave none)", "vessels": len(scales)} if scales else
                                           {"scale": None, "how": got[0]["how"] if got else "no curve read",
                                            "vessels": 0})
    for group in groups.values():
        for species in sorted({k for c in group["communities"] for k in c["abundance"]}):
            group["scales"].setdefault(species, {"scale": None, "vessels": 0,
                                                 "how": "no monoculture chemostat of it in this group, so its "
                                                        "row stays in units of r_i - D"})
    return sorted((g for g in groups.values() if g["communities"]), key=lambda g: (g["dilution"], g["medium"]))
