"""Pairwise interaction strength from replicate growth curves.

For species A and B, the interaction strength is a value pair:

  A: log2(property of A in co-culture / property of A in monoculture)
  B: log2(property of B in co-culture / property of B in monoculture)

where the property is a growth curve feature chosen by the caller (`method`, default "auc", the area under
the curve; see crossfeed.growth.FEATURES). log2 reads directly: 1 means the property doubled in co-culture,
-1 means it halved, 0 means no change.

Each value is computed for every combination of a co-culture replicate with a monoculture replicate and
summarized as mean, sample standard deviation (n - 1), and n. The combinations share replicates, so they
are not independent observations: the standard deviation describes the spread across combinations, not a
standard error, and is not a basis for a significance test.

Metadata matching of the replicates (condition, medium, and so on) is assumed to have happened upstream.
"""
from __future__ import annotations

import math
import statistics

from .growth import FEATURES, check_replicate_sets, curve_features, shared_window

LOG = "log2"


def _summary(species: str, values: list) -> dict:
    return {
        "species": species,
        "mean": statistics.mean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else None,
        "n": len(values),
        "values": values,
    }


def interaction_strength(mono_a, mono_b, co, species_a: str, species_b: str, method: str = "auc") -> dict:
    """Interaction strength of a species pair from three replicate sets.

    mono_a, mono_b: Replicates of species_a and species_b grown alone. co: Replicates of the co-culture,
    each with a curve for species_a and species_b. method: a name in crossfeed.growth.FEATURES.

    Raises ValueError when the sets are not comparable (mixed units, missing species, different start
    times), for an unknown method, or when no replicate combination yields a positive property for a
    species. Combinations where either property is zero or negative are skipped and reported.

    Returns a dict with "method", "log", "window" (start, end), "species_a" and "species_b" (each with
    "species", "mean", "sd", "n", "values"), and "skipped" as a list of (label, reason).
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
        values = []
        for i, co_rep in enumerate(co):
            co_value = prop(co_rep, species)
            for j, mono_rep in enumerate(monos):
                mono_value = prop(mono_rep, species)
                if co_value <= 0 or mono_value <= 0:
                    label = f"{species}: co-culture {co_rep.name or i} / monoculture {mono_rep.name or j}"
                    reason = f"non-positive {method} (co-culture {co_value:g}, monoculture {mono_value:g})"
                    result["skipped"].append((label, reason))
                    continue
                values.append(math.log2(co_value / mono_value))
        if not values:
            raise ValueError(f"{species}: no replicate combination has a positive {method}")
        result[key] = _summary(species, values)
    return result
