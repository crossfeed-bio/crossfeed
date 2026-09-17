"""Pairwise interaction strength from replicate growth curves.

For species A and B, the interaction strength is a value pair, one per species, comparing the species'
growth in co-culture with its growth alone. The growth property is a growth curve feature chosen by the
caller (`method`, default "auc", the area under the curve; see crossfeed.growth.FEATURES).

Each replicate set is summarized on the log2 scale first, so no replicate is used twice:

  strength = mean(log2 property over co-culture replicates) - mean(log2 property over monoculture replicates)
  sd       = sqrt(sd_co^2 + sd_mono^2)                (spread of a single co versus mono comparison)
  se       = sqrt(sd_co^2 / n_co + sd_mono^2 / n_mono) (standard error of the strength)

where sd_co and sd_mono are sample standard deviations (n - 1) of the log2 values. The co-culture and the
monoculture sets are independent replicates, so these are exact for the difference of the two means, and
the per-replicate log2 values are returned for follow-up tests (for example a Welch t-test). The strength
is the log2 ratio of geometric means: 1 means the property doubled in co-culture, -1 means it halved.

The two values of the pair are not independent of each other: A and B are measured in the same co-culture
replicates.

Metadata matching of the replicates (condition, medium, and so on) is assumed to have happened upstream.
"""
from __future__ import annotations

import math
import statistics

from .growth import FEATURES, check_replicate_sets, curve_features, shared_window

LOG = "log2"


def _log_values(reps, species, role, prop, method, skipped) -> list:
    """log2 of the property for each replicate in a set; non-positive replicates are skipped and reported."""
    values = []
    for i, rep in enumerate(reps):
        value = prop(rep, species)
        if value <= 0:
            skipped.append((f"{species}: {role} replicate {rep.name or i}", f"non-positive {method} ({value:g})"))
            continue
        values.append(math.log2(value))
    if not values:
        raise ValueError(f"{species}: no {role} replicate has a positive {method}")
    return values


def _strength(species: str, co_log2: list, mono_log2: list) -> dict:
    n_co, n_mono = len(co_log2), len(mono_log2)
    if n_co > 1 and n_mono > 1:
        var_co, var_mono = statistics.variance(co_log2), statistics.variance(mono_log2)
        sd = math.sqrt(var_co + var_mono)
        se = math.sqrt(var_co / n_co + var_mono / n_mono)
    else:
        sd = se = None   # a set with one replicate has no spread to estimate
    return {
        "species": species,
        "mean": statistics.mean(co_log2) - statistics.mean(mono_log2),
        "sd": sd,
        "se": se,
        "n_co": n_co,
        "n_mono": n_mono,
        "co_log2": co_log2,
        "mono_log2": mono_log2,
    }


def interaction_strength(mono_a, mono_b, co, species_a: str, species_b: str, method: str = "auc") -> dict:
    """Interaction strength of a species pair from three replicate sets.

    mono_a, mono_b: Replicates of species_a and species_b grown alone. co: Replicates of the co-culture,
    each with a curve for species_a and species_b. method: a name in crossfeed.growth.FEATURES.

    Raises ValueError when the sets are not comparable (mixed units, missing species, different start
    times), for an unknown method, or when a set has no replicate with a positive property for a species.
    Replicates with a zero or negative property are left out of that species' set and reported.

    Returns a dict with "method", "log", "window" (start, end), "species_a" and "species_b" (each with
    "species", "mean", "sd", "se", "n_co", "n_mono", "co_log2", "mono_log2"; "sd" and "se" are None when a
    set has a single replicate), and "skipped" as a list of (label, reason).
    """
    if method not in FEATURES:
        raise ValueError(f"unknown method {method!r}; choose one of {sorted(FEATURES)}")
    check_replicate_sets(mono_a, mono_b, co, species_a, species_b)
    all_reps = [*mono_a, *mono_b, *co]
    start, end = shared_window(c for rep in all_reps for c in rep.curves)

    def prop(rep, species):
        return curve_features(rep.curve(species), end)[method]

    result = {"method": method, "log": LOG, "window": (start, end), "skipped": []}
    for key, species, monos in (("species_a", species_a, mono_a), ("species_b", species_b, mono_b)):
        co_log2 = _log_values(co, species, "co-culture", prop, method, result["skipped"])
        mono_log2 = _log_values(monos, species, "monoculture", prop, method, result["skipped"])
        result[key] = _strength(species, co_log2, mono_log2)
    return result
