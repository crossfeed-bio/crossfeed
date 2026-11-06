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
