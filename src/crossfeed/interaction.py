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

A set that did not grow is decided by the no-growth rule before any ratio: `grew` tests each replicate's
maximum against its abundance at the first time point (Karoline, register item 5). Zero growth is a
result, not an error. When the target has a positive property only with the source present
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

from . import rates
from .growth import (
    FEATURES,
    SPIKE_FACTOR,
    check_replicate_sets,
    check_sets,
    cut,
    reached_stationary,
    shared_window,
    spike,
)
from .stats import paired

LOG = "log2"
BICULTURE = "biculture"
DROPOUT = "dropout"
QUANTIFIED, OBLIGATE, ABOLISHED, NO_GROWTH = "quantified", "obligate", "abolished", "no_growth"
# a set left empty by exclusions (for example every replicate spiked): not a growth result, never exported
UNUSABLE = "unusable"

# The no-growth rule (Karoline, register item 5, settled on #68): a species has not grown in a set when
# its maximum is not significantly above its abundance at the first time point, across the replicates of
# that set, and it did not rise by NO_GROWTH_FACTOR either. Each replicate is paired with itself: its own
# maximum, at whatever time that replicate peaks, against its own start, on a log2 scale. It is applied
# before any ratio, so a set that only drifts never produces a log ratio of two near-zero quantities
# (register item 11). Both numbers are settings, and `rule_meta` records them in every network.
NO_GROWTH_ALPHA = 0.05
# With two or three replicates a real rise often fails significance, and reading that as "no growth" turns
# an ordinary comparison into an obligate or abolished claim (measured on live studies, #37). So a set also
# counts as grown when the geometric mean of its rises, max / start per replicate, reaches this factor.
# The factor defines growth. Karoline set a medium default of 1.5, which a user can make more stringent
# (for example 2, one doubling) as an advanced setting (on #68).
NO_GROWTH_FACTOR = 1.5
NO_GROWTH_TEST = ("paired two-sided t-test of log2(maximum / first time point) per replicate against 0; "
                  "each replicate's maximum is taken at its own time")


def _feature(method: str):
    """The (times, values) -> number function behind a metric name: auc, max, or a growth rate
    ("growth_rate:easylinear:5", "growth_rate:baranyi"; crossfeed.rates)."""
    if method in FEATURES:
        return FEATURES[method]
    rate = rates.feature(method)
    if rate is None:
        raise ValueError(f"unknown method {method!r}; choose one of {sorted(FEATURES)} or a growth rate")
    return rate


def _check_method(method: str) -> None:
    _feature(method)


def _property(end: float, method: str):
    fn = _feature(method)

    def prop(rep, species):
        # only the metric asked for is computed: a Baranyi fit costs milliseconds per curve
        return fn(*cut(rep.curve(species), end))
    return prop


def _spike_reason(rep, species, found: dict, factor: float) -> str:
    curve = rep.curve(species)
    times = ", ".join(f"{t:g}" for t in found["times"])
    reason = (f"implausible spike: {found['ratio']:.0f} times both neighboring points (limit {factor:g}), "
              f"at {times} {curve.time_unit}; left out for this species only")
    note = rep.notes.get(species)
    return f"{reason}; {note}" if note else reason


def _log_values(reps, species, role, prop, method, skipped, spike_factor=SPIKE_FACTOR, flagged=None,
                no_growth=None) -> list:
    """log2 of the property for each replicate in a set.

    A replicate whose curve for `species` carries an implausible spike (`crossfeed.growth.spike`) is left
    out for that species and reported, never dropped silently; its other species still take part. A
    non-positive property is left out and reported as before.
    """
    values = []
    for i, rep in enumerate(reps):
        label = f"{species}: {role} replicate {rep.name or i}"
        found = spike(rep.curve(species), spike_factor)
        if found:
            skipped.append((label, _spike_reason(rep, species, found, spike_factor)))
            if flagged is not None:
                flagged.append({"species": species, "role": role, "replicate": rep.name or str(i),
                                "ratio": found["ratio"], "times": found["times"]})
            continue
        try:
            value = prop(rep, species)
        except rates.RateUnavailable as e:
            # no growth rate for this curve (too few points, a rejected fit): left out and reported, never
            # replaced by another number, and not read as no growth (#41)
            skipped.append((label, f"no growth rate: {e}"))
            continue
        if value <= 0:
            skipped.append((label, f"non-positive {method} ({value:g})"))
            if no_growth is not None:
                no_growth.append(label)
            continue
        values.append(math.log2(value))
    return values


def grew(reps, species: str, end: float, alpha: float = None, factor: float = None) -> dict:
    """Whether `species` grew in a replicate set: {"grew", "n", "p", "log2_rise", "reason"}.

    Each replicate gives one rise, log2(maximum / abundance at the first time point) within the shared
    window, with the maximum taken wherever that replicate peaks (the time of maximum abundance varies
    across replicates; Karoline, on #68). The set has grown when the mean rise is above 0 and a paired
    t-test finds it different from 0 at `alpha`, or when the mean rise reaches log2(`factor`), which is
    the geometric mean of the ratios reaching the factor. One replicate cannot be tested, so it counts as
    grown when its maximum exceeds its start; such an edge is flagged `single_replicate` anyway. A
    replicate whose start is not positive has no ratio and is left out of the rule, and a set with no
    replicate left falls back to the property itself, as before this rule existed. `alpha` of 0 switches
    the rule off; `factor` of 0 leaves the test alone.
    """
    alpha = NO_GROWTH_ALPHA if alpha is None else alpha
    factor = NO_GROWTH_FACTOR if factor is None else factor
    starts, maxima, found = [], [], 0
    for rep_ in reps:
        curve = rep_.curve(species)
        if curve is None:
            continue
        times, values = cut(curve, end)
        if not values:
            continue
        found += 1
        if values[0] > 0:
            starts.append(values[0])
            maxima.append(max(values))
    if not found:
        return {"grew": False, "n": 0, "p": None, "log2_rise": None, "reason": "no usable curve for this species"}
    if not alpha or not starts:
        return {"grew": True, "n": len(starts), "p": None, "log2_rise": None, "reason": ""}
    rises = [math.log2(m / s) for m, s in zip(maxima, starts, strict=True)]
    rise = statistics.mean(rises)
    verdict = {"n": len(rises), "log2_rise": rise, "p": None, "reason": ""}
    if len(rises) < 2:
        grew_ = rise > 0
        return {**verdict, "grew": grew_,
                "reason": "" if grew_ else "the maximum does not exceed the abundance at the first time point"}
    test = paired(rises, [0.0] * len(rises))
    verdict["p"] = test["p"]
    if rise > 0 and test["p"] < alpha:
        return {**verdict, "grew": True}
    if factor and rise >= math.log2(factor):
        return {**verdict, "grew": True}
    also = f" and did not reach {factor:g} times it" if factor else ""
    return {**verdict, "grew": False,
            "reason": f"the maximum is not significantly above the abundance at the first time point{also} "
                      f"(mean log2 rise {rise:.3g}, paired t-test p = {test['p']:.3g}, alpha {alpha:g}, "
                      f"{len(rises)} replicates)"}


def rule_meta(alpha: float = None, factor: float = None) -> dict:
    """The no-growth rule as it ran, for a network's `meta`: a reader of any obligate or abolished edge
    can see which rule produced it (Craig's agent, on #68)."""
    alpha = NO_GROWTH_ALPHA if alpha is None else alpha
    factor = NO_GROWTH_FACTOR if factor is None else factor
    return {"rule": "grown when the mean log2 rise is significantly above 0, or reaches log2(factor)",
            "test": NO_GROWTH_TEST, "alpha": alpha, "factor": factor, "applied": bool(alpha)}


def _grown_values(reps, species, role, prop, method, skipped, spike_factor, flagged, no_growth, end,
                  alpha, factor) -> list:
    """The log2 values of a set, or none when the set did not grow (the no-growth rule, #37)."""
    verdict = grew(reps, species, end, alpha, factor)
    if not verdict["grew"]:
        skipped.append((f"{species}: {role}", verdict["reason"] or "no growth"))
        if no_growth is not None:
            no_growth.extend(f"{species}: {role} replicate {r.name or i}" for i, r in enumerate(reps))
        return []
    return _log_values(reps, species, role, prop, method, skipped, spike_factor, flagged, no_growth)


def _compare(with_log2: list, without_log2: list, zero_with: int = 0, zero_without: int = 0) -> dict:
    """The log2 set comparison shared by both designs, including the outcomes where one set has no growth.

    n_with and n_without count the replicates behind the result: the growing ones, or for the set that
    shows no growth in an obligate or abolished comparison, the replicates without growth (`zero_with`,
    `zero_without`). That set has no log2 values by definition, so counting its log2 values would call
    every such edge a single replicate (Karoline, on #47).
    """
    n_with, n_without = len(with_log2), len(without_log2)
    result = {"outcome": QUANTIFIED, "mean": None, "sd": None, "se": None, "n_with": n_with,
              "n_without": n_without, "with_log2": with_log2, "without_log2": without_log2}
    if (not with_log2 and not zero_with) or (not without_log2 and not zero_without):
        # every replicate of a set was left out (a spike, for example): absence of data, not of growth
        result["outcome"] = UNUSABLE
        return result
    if not with_log2 or not without_log2:
        result["outcome"] = OBLIGATE if with_log2 else ABOLISHED if without_log2 else NO_GROWTH
        if result["outcome"] == OBLIGATE:
            result["n_without"] = zero_without
        elif result["outcome"] == ABOLISHED:
            result["n_with"] = zero_with
        return result
    result["mean"] = statistics.mean(with_log2) - statistics.mean(without_log2)
    if n_with > 1 and n_without > 1:   # a set with one replicate has no spread to estimate
        var_with, var_without = statistics.variance(with_log2), statistics.variance(without_log2)
        result["sd"] = math.sqrt(var_with + var_without)
        result["se"] = math.sqrt(var_with / n_with + var_without / n_without)
    return result


def stationary_verdict(reps, species: str, end: float):
    """Whether a replicate set reached stationary phase by `end`: True or False by the majority of its
    replicates (Karoline, 2026-09-28), or None when most of them cannot be judged (too few points)."""
    calls = [reached_stationary(c, end) for c in (rep.curve(species) for rep in reps) if c is not None]
    judged = [c for c in calls if c is not None]
    if not calls or len(judged) * 2 <= len(calls):
        return None
    return sum(judged) * 2 > len(judged)


def interaction_strength(mono_a, mono_b, co, species_a: str, species_b: str, method: str = "auc",
                         spike_factor: float = SPIKE_FACTOR, no_growth_alpha: float = None,
                         no_growth_factor: float = None) -> dict:
    """Interaction strength of a species pair from mono versus bi-culture replicate sets.

    mono_a, mono_b: Replicates of species_a and species_b grown alone. co: Replicates of the co-culture,
    each with a curve for species_a and species_b. method: a name in crossfeed.growth.FEATURES.

    Raises ValueError when the sets are not comparable (mixed units, missing species, different start
    times) or for an unknown method. Replicates with a zero or negative property are left out of that
    species' set and reported; a set left without growth gives the outcome "obligate", "abolished", or
    "no_growth" (see the module docstring).

    Each species is compared over its own window: from the common start to the earliest last time point
    of its own curves in the co-culture and alone, so the partner's monoculture, which is not part of the
    comparison, does not shorten it (Karoline, 2026-09-28, register item 26: as for drop-outs; the area
    needs an equal window on both sides, which this is).

    Returns a dict with "method", "log", "window" (start, end) over the whole design, "species_a" and
    "species_b" (each with "species", "window", "outcome", "mean", "sd", "se", "n_co", "n_mono", "co_log2",
    "mono_log2"; "mean", "sd", and
    "se" are None unless the outcome is "quantified", and "sd" and "se" are None when a set has a single
    replicate), and "skipped" as a list of (label, reason).
    """
    _check_method(method)
    check_replicate_sets(mono_a, mono_b, co, species_a, species_b)
    start, end = shared_window(c for rep in [*mono_a, *mono_b, *co] for c in rep.curves)

    result = {"method": method, "log": LOG, "window": (start, end), "skipped": [], "flagged": []}
    for key, species, monos in (("species_a", species_a, mono_a), ("species_b", species_b, mono_b)):
        window = shared_window(rep.curve(species) for rep in [*co, *monos])
        end = window[1]
        prop = _property(end, method)
        zero_co, zero_mono = [], []
        co_log2 = _grown_values(co, species, "co-culture", prop, method, result["skipped"],
                                spike_factor, result["flagged"], zero_co, end, no_growth_alpha,
                                no_growth_factor)
        mono_log2 = _grown_values(monos, species, "monoculture", prop, method, result["skipped"],
                                  spike_factor, result["flagged"], zero_mono, end, no_growth_alpha,
                                  no_growth_factor)
        c = _compare(co_log2, mono_log2, len(zero_co), len(zero_mono))
        stationary = {"with": stationary_verdict(co, species, end),
                      "without": stationary_verdict(monos, species, end)}
        result[key] = {"species": species, "window": window, "stationary": stationary,
                       "outcome": c["outcome"], "mean": c["mean"],
                       "sd": c["sd"], "se": c["se"],
                       "n_co": c["n_with"], "n_mono": c["n_without"],
                       "co_log2": c["with_log2"], "mono_log2": c["without_log2"]}
    return result


def dropout_interaction_strengths(full, dropouts: dict, method: str = "auc",
                                  spike_factor: float = SPIKE_FACTOR,
                                  no_growth_alpha: float = None, no_growth_factor: float = None) -> dict:
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

    Each arc is compared over its own window: from the common start to the earliest last time point of
    the target's curves in the two sets, so one short curve elsewhere in the design does not shorten it.

    Returns a dict with "method", "log", "window" (start, end) over the whole design, "arcs" (each with
    "source", "target", "evidence", "community", "window", "outcome", "mean", "sd", "se", "n_with",
    "n_without", "with_log2", "without_log2"), "skipped" as a list of (label, reason), and "flagged" as
    in `interaction_strength`. `spike_factor` works as there.
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

    evidence = BICULTURE if len(members) == 2 else DROPOUT
    community = sorted(members)
    result = {"method": method, "log": LOG, "window": (start, end), "arcs": [], "skipped": [], "flagged": []}

    def once(found: list, into: list) -> None:
        # the full community set takes part in several arcs; report each of its skips once
        into.extend(x for x in found if x not in into)

    for removed, reps in dropouts.items():
        without_role = f"community without {removed}"
        for target in (m for m in members if m != removed):
            # each arc has its own window: the target's curves in the two sets (Karoline, on #47)
            window = shared_window(rep.curve(target) for rep in [*full, *reps])
            prop = _property(window[1], method)
            skips, flags, zero_full, zero_without = [], [], [], []
            full_log2 = _grown_values(full, target, "full community", prop, method, skips, spike_factor,
                                      flags, zero_full, window[1], no_growth_alpha, no_growth_factor)
            without_log2 = _grown_values(reps, target, without_role, prop, method, skips, spike_factor,
                                         flags, zero_without, window[1], no_growth_alpha,
                                         no_growth_factor)
            once(skips, result["skipped"])
            once(flags, result["flagged"])
            c = _compare(full_log2, without_log2, len(zero_full), len(zero_without))
            if c["outcome"] == NO_GROWTH:
                result["skipped"].append((f"arc {removed} -> {target}",
                                          f"no growth ({method}) in the full community or the {without_role}"))
                continue
            if c["outcome"] == UNUSABLE:
                result["skipped"].append((f"arc {removed} -> {target}", "every replicate of a set was left out"))
                continue
            result["arcs"].append({"source": removed, "target": target, "evidence": evidence,
                                   "community": community, "window": window,
                                   "stationary": {"with": stationary_verdict(full, target, window[1]),
                                                  "without": stationary_verdict(reps, target, window[1])},
                                   **c})
    return result
