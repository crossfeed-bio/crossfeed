"""Interaction strength from replicate growth curves.

An interaction strength compares a target species' growth with a source species present against its
growth with the source absent. The growth property is a growth curve feature chosen by the caller
(`method`, default "auc", the area under the curve; see crossfeed.growth.FEATURES).

Each replicate set is summarized on the log2 scale first, so no replicate is used twice:

  strength = mean(log2 property with the source) - mean(log2 property without the source)
  sd       = sqrt(sd_with^2 + sd_without^2)                     (spread of a single comparison)
  se       = sqrt(sd_with^2 / n_with + sd_without^2 / n_without) (standard error of the strength)

where sd_with and sd_without are sample standard deviations (n - 1) of the log2 values. The two sets are
independent replicates, so these are exact for the difference of the two means, and the per-replicate log2
values are returned for follow-up tests (for example a Welch t-test). The strength is the log2 ratio of
geometric means: 1 means the property doubled with the source present, -1 means it halved.

Two designs share this comparison:

  * mono versus bi-culture (`interaction_strength`): the target alone against the target with one partner.
    The arc is a direct interaction (evidence "biculture").
  * drop-out communities (`dropout_interaction_strengths`): the full community against the community
    without the source. The source can act on the target through a third species, so the arc is not
    necessarily direct (evidence "dropout"); strictly it is a hyper-arc, kept as an arc with the community
    recorded. A two-member community is the bi-culture design.

Zero growth is a result, not an error. When the target has a positive property only with the source present
(for example it grows in bi-culture but not in monoculture), the source is required for its growth: an
obligate commensal or mutualist relationship, outcome "obligate". When it has a positive property only
without the source, the source abolishes its growth, outcome "abolished". A log2 ratio is undefined in both
cases, so mean, sd, and se are None and the outcome carries the information. Without growth in either set
the outcome is "no_growth". A comparison with a log2 value is "quantified". Individual replicates with a zero
or negative property within a set that also has positive replicates are left out and reported.

Comparisons that share replicates are not independent: the two values of a bi-culture pair share the
co-culture replicates, and drop-out arcs to the same target share the full community replicates.

Metadata matching of the replicates (condition, medium, and so on) is assumed to have happened upstream.
"""
from __future__ import annotations

import math
import statistics

from .growth import FEATURES, check_replicate_sets, check_sets, curve_features, shared_window

LOG = "log2"
BICULTURE = "biculture"
DROPOUT = "dropout"
QUANTIFIED, OBLIGATE, ABOLISHED, NO_GROWTH = "quantified", "obligate", "abolished", "no_growth"


def _check_method(method: str) -> None:
    if method not in FEATURES:
        raise ValueError(f"unknown method {method!r}; choose one of {sorted(FEATURES)}")


def _property(end: float, method: str):
    def prop(rep, species):
        return curve_features(rep.curve(species), end)[method]
    return prop


def _log_values(reps, species, role, prop, method, skipped) -> list:
    """log2 of the property for each replicate in a set; non-positive replicates are skipped and reported."""
    values = []
    for i, rep in enumerate(reps):
        value = prop(rep, species)
        if value <= 0:
            skipped.append((f"{species}: {role} replicate {rep.name or i}", f"non-positive {method} ({value:g})"))
            continue
        values.append(math.log2(value))
    return values


def _compare(with_log2: list, without_log2: list) -> dict:
    """The log2 set comparison shared by both designs, including the outcomes where one set has no growth."""
    n_with, n_without = len(with_log2), len(without_log2)
    result = {"outcome": QUANTIFIED, "mean": None, "sd": None, "se": None, "n_with": n_with,
              "n_without": n_without, "with_log2": with_log2, "without_log2": without_log2}
    if not with_log2 or not without_log2:
        result["outcome"] = OBLIGATE if with_log2 else ABOLISHED if without_log2 else NO_GROWTH
        return result
    result["mean"] = statistics.mean(with_log2) - statistics.mean(without_log2)
    if n_with > 1 and n_without > 1:   # a set with one replicate has no spread to estimate
        var_with, var_without = statistics.variance(with_log2), statistics.variance(without_log2)
        result["sd"] = math.sqrt(var_with + var_without)
        result["se"] = math.sqrt(var_with / n_with + var_without / n_without)
    return result


def interaction_strength(mono_a, mono_b, co, species_a: str, species_b: str, method: str = "auc") -> dict:
    """Interaction strength of a species pair from mono versus bi-culture replicate sets.

    mono_a, mono_b: Replicates of species_a and species_b grown alone. co: Replicates of the co-culture,
    each with a curve for species_a and species_b. method: a name in crossfeed.growth.FEATURES.

    Raises ValueError when the sets are not comparable (mixed units, missing species, different start
    times) or for an unknown method. Replicates with a zero or negative property are left out of that
    species' set and reported; a set left without growth gives the outcome "obligate", "abolished", or
    "no_growth" (see the module docstring).

    Returns a dict with "method", "log", "window" (start, end), "species_a" and "species_b" (each with
    "species", "outcome", "mean", "sd", "se", "n_co", "n_mono", "co_log2", "mono_log2"; "mean", "sd", and
    "se" are None unless the outcome is "quantified", and "sd" and "se" are None when a set has a single
    replicate), and "skipped" as a list of (label, reason).
    """
    _check_method(method)
    check_replicate_sets(mono_a, mono_b, co, species_a, species_b)
    start, end = shared_window(c for rep in [*mono_a, *mono_b, *co] for c in rep.curves)
    prop = _property(end, method)

    result = {"method": method, "log": LOG, "window": (start, end), "skipped": []}
    for key, species, monos in (("species_a", species_a, mono_a), ("species_b", species_b, mono_b)):
        co_log2 = _log_values(co, species, "co-culture", prop, method, result["skipped"])
        mono_log2 = _log_values(monos, species, "monoculture", prop, method, result["skipped"])
        c = _compare(co_log2, mono_log2)
        result[key] = {"species": species, "outcome": c["outcome"], "mean": c["mean"], "sd": c["sd"], "se": c["se"],
                       "n_co": c["n_with"], "n_mono": c["n_without"],
                       "co_log2": c["with_log2"], "mono_log2": c["without_log2"]}
    return result


def dropout_interaction_strengths(full, dropouts: dict, method: str = "auc") -> dict:
    """Interaction strengths from a full community and drop-out communities.

    full: Replicates of the full community, each with a curve for every member (the same members in every
    replicate). dropouts: a mapping from a removed species R to the Replicates of the community without R,
    each with a curve for every member except R. Not every member needs a drop-out set.

    For every removed species R and every remaining member X, the arc R -> X compares X in the full
    community (with R) against X in the community without R; a positive mean means R affects X positively,
    directly or indirectly. Arcs carry evidence "dropout", or "biculture" for a two-member community, and
    the sorted community members.

    Raises ValueError for an unknown method, empty or inconsistent sets (a drop-out set that still holds R
    or lacks a member, a removed species outside the community), mixed units, or different start times. A
    replicate with a zero or negative property is left out of its set and reported. An arc whose target
    grows in only one of the two sets is kept with the outcome "obligate" or "abolished"; an arc whose
    target grows in neither is skipped and reported.

    Returns a dict with "method", "log", "window" (start, end), "arcs" (each with "source", "target",
    "evidence", "community", "outcome", "mean", "sd", "se", "n_with", "n_without", "with_log2",
    "without_log2"), and "skipped" as a list of (label, reason).
    """
    _check_method(method)
    if not full:
        raise ValueError("no full community replicates")
    if not dropouts:
        raise ValueError("no drop-out sets")
    members = full[0].species
    outside = [r for r in dropouts if r not in members]
    if outside:
        raise ValueError(f"drop-out species {outside} not a member of the full community {sorted(members)}")
    check_sets([("full community", full, members)]
               + [(f"community without {r}", reps, [m for m in members if m != r]) for r, reps in dropouts.items()])
    start, end = shared_window(c for rep in [*full, *(r for reps in dropouts.values() for r in reps)]
                               for c in rep.curves)
    prop = _property(end, method)

    evidence = BICULTURE if len(members) == 2 else DROPOUT
    community = sorted(members)
    result = {"method": method, "log": LOG, "window": (start, end), "arcs": [], "skipped": []}
    full_log2 = {m: _log_values(full, m, "full community", prop, method, result["skipped"]) for m in members}
    for removed, reps in dropouts.items():
        without_role = f"community without {removed}"
        for target in (m for m in members if m != removed):
            c = _compare(full_log2[target], _log_values(reps, target, without_role, prop, method, result["skipped"]))
            if c["outcome"] == NO_GROWTH:
                result["skipped"].append((f"arc {removed} -> {target}",
                                          f"no growth ({method}) in the full community or the {without_role}"))
                continue
            result["arcs"].append({"source": removed, "target": target, "evidence": evidence,
                                   "community": community, **c})
    return result
