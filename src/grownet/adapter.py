"""mGrowthDB experiments to replicate growth curves.

`grownet.interaction` compares replicate sets of growth curves, which is the comparison the
collaboration specified. mGrowthDB serves its measurements as a time series per measurement context, one
context per strain per bioreplicate, so this module is the join between the two: it reads an experiment
and returns one `grownet.growth.Replicate` per bioreplicate, each holding a `GrowthCurve` per strain.

Two rules worth stating, because both are choices:

  * A bioreplicate flagged `isAverage` is the mean of the real replicates (mGrowthDB), so it is not an
    independent replicate and is left out, with a reason recorded. Including it would duplicate the data
    and shrink the spread the comparison measures.
  * Units come from the record: the time unit from the bioreplicate, the abundance unit from the
    context's technique units, falling back to the technique name when no unit string is reported (an OD
    reading and a qPCR count then still refuse to be compared, which is the point of the check).

When a strain's curve carries an implausible spike (`grownet.growth.spike`), the adapter looks for
other measurements of the same strain in the same replicate and says whether they are clean, because they
are evidence about the flag (in BH_14 the qPCR trace spikes while the flow cytometry trace does not). A
community-level trace counts as such an alternative only in a monoculture, where it measures that single
strain; in a co-culture it is the sum of the members. The alternative is named, never substituted: mixing
techniques between monoculture and co-culture is what register item 13 warns about.

Anything that cannot be built is reported with a reason rather than guessed at, as everywhere else in
grownet. Nothing pulled here is written into the repository.
"""
from __future__ import annotations

import contextlib
import contextvars

from .growth import SPIKE_FACTOR, GrowthCurve, Replicate, spike

AVERAGE = "average of the replicates, not an independent replicate"
# how a replicate or series that mGrowthDB failed to deliver is reported: a gap in the data read, not a
# property of the data (audit step 7)
UNREAD = "could not read"


def unread(skipped: list) -> list:
    """The skipped entries that are failed reads from mGrowthDB, not data that was read and refused."""
    return [(label, reason) for label, reason in skipped if reason.startswith(UNREAD)]


def condensed(skipped: list) -> list:
    """The skip list for reading: the average bioreplicates, left out as mGrowthDB marks them, become one
    line per experiment ("3 average replicate(s) left out"), in place of the first; the rest is unchanged
    (Karoline, 2026-09-28: a quarter of all of mGrowthDB's skip list was these lines)."""
    averages = {}
    for label, reason in skipped:
        if reason == AVERAGE:
            averages.setdefault(label.split(": ")[0], []).append(label)
    out, done = [], set()
    for label, reason in skipped:
        if reason != AVERAGE:
            out.append((label, reason))
            continue
        experiment = label.split(": ")[0]
        if experiment not in done:
            done.add(experiment)
            out.append((experiment, f"{len(averages[experiment])} average replicate(s) left out ({AVERAGE})"))
    return out


# The two separators a PAIR label is built with, declared here because `about_a_pair` reads them and the
# builders write them. They are written in nine places: derive.py's `{a} with {b} [{cond}]` for a pair
# whose sets could not be compared, its `{source} -> {target} [{cond}]` for the no-growth and unusable
# outcomes, and integrated.py's `{partner} -> {target} [...]`. This started as a bare `" with " in label`
# and the `" -> "` half was missed, so on SMGDB00000013 the report said "pairs the data did not support:
# none" while listing seven of them under a heading saying they are not pairs. Inferring the kind from
# the label's punctuation is only safe while the punctuation is a contract, which is what this is.
#
# NOT GUARDED, deliberately and worth knowing: a THIRD separator added somewhere would be filed as a
# note again, and no test catches that. A source scan cannot tell a pair label from an experiment label
# with a species appended (`{label}: {name}, {species}` interpolates three names and is not a pair), and
# the suite is offline so it cannot read the real corpus. The honest guard is to tag the entry at the
# `skipped.append` site, where the code knows which kind it is building; that is 61 sites and is the
# right fix when someone next touches them.
PAIR_SEPARATORS = (" with ", " -> ")


def about_a_pair(label: str, reason: str) -> bool:
    """Whether a condensed entry is about a PAIR that gave no edge, or a note about the input.

    The two were listed together under the heading "pairs the data did not support (N)", and on the live
    corpus 97 of those 186 entries were average-replicate notes keyed by experiment, 31 of them naming
    conditions that DID produce reported arcs: the report said a condition was a pair the data did not
    support 254 lines after reporting an interaction derived from it (#232). A pair entry names two
    organisms with one of `PAIR_SEPARATORS` between them; a note names an experiment or a study.
    """
    return AVERAGE not in reason and any(sep in label for sep in PAIR_SEPARATORS)


# The Technique setting of the run under way (Karoline, 2026-10-14, #292: "Curves of it only"): set once
# where a run starts (`only_technique`), read wherever curves are built, so the many readers of a study do
# not each carry it. The prefetch's worker threads only read records and never build a curve.
TECHNIQUE: contextvars.ContextVar = contextvars.ContextVar("grownet_technique", default=None)


@contextlib.contextmanager
def only_technique(technique):
    """Within this block, keep only curves measured by `technique` (None or "" keeps every technique)."""
    token = TECHNIQUE.set(technique or None)
    try:
        yield
    finally:
        TECHNIQUE.reset(token)

MIN_POINTS = 2


def _strain_contexts(bioreplicate: dict):
    """(subject name, context) for every per-strain measurement context of a bioreplicate."""
    for context in bioreplicate.get("measurementContexts", []):
        subject = context.get("subject") or {}
        if subject.get("type") == "strain" and subject.get("name"):
            yield subject["name"], context


def _alternatives(bioreplicate: dict, species: str, own_id, single_strain: bool):
    """(technique, context) for other measurements of `species` in this replicate."""
    for context in bioreplicate.get("measurementContexts", []):
        if context.get("id") == own_id:
            continue
        subject = context.get("subject") or {}
        technique = context.get("techniqueType") or "unknown technique"
        if subject.get("type") == "strain" and subject.get("name") == species:
            yield technique, context
        elif single_strain and subject.get("type") == "bioreplicate" and technique != "metabolite":
            yield f"community {technique}", context


def _alternatives_note(client, bioreplicate: dict, species: str, own_id, single_strain: bool,
                       spike_factor: float) -> str:
    """What the other measurements of a flagged strain say, for the report."""
    parts = []
    for technique, context in _alternatives(bioreplicate, species, own_id, single_strain):
        try:
            points = client.get_measurement_series(context["id"])
        except Exception:  # noqa: BLE001 - an unreadable alternative is reported, not fatal
            parts.append(f"{technique} unreadable")
            continue
        try:
            other = GrowthCurve(species, [t for t, _, _ in points], [v for _, v, _ in points], "time",
                                _abundance_unit(context) or technique)
        except ValueError:
            parts.append(f"{technique} not comparable")
            continue
        found = spike(other, spike_factor)
        parts.append(f"{technique} also spiked ({found['ratio']:.0f} times its neighbors)" if found
                     else f"{technique} clean")
    if parts:
        return "other measurements of this strain in this replicate, not substituted: " + ", ".join(parts)
    if not single_strain:
        return ("no other measurement of this strain in this replicate (the community traces measure all "
                "members together)")
    return "no other measurement of this strain in this replicate"


def _abundance_unit(context: dict) -> str:
    return (context.get("techniqueUnits") or context.get("techniqueOriginalUnits")
            or context.get("techniqueType") or "")


# The culture-level traces a monoculture's rate may come from, preferred in this order (#140, Karoline
# 2026-10-07: "yes to #140 with option 1", and 2026-10-12: "Counts only"). Plate counts and flow
# cytometry, never optical density: a rate is invariant to a proxy's scale but not to its linearity, and
# OD saturates where counts do not (Craig's agent, on #140). Built with OD first, SMGDB00000010's OD,
# six points over 168 h starting at the medium's own 0.6, gave rates of 0.0007 to 0.009 /h that entered
# published medians, and OD first readings near 0.001 tripped the starting-density rule on noise. pH and
# metabolites measure the medium, not the culture's size.
CULTURE_TECHNIQUES = ("plates", "fc")


def culture_trace_replicates(client, experiment: dict, species: str, technique: str | None = None) -> tuple:
    """(replicates, skipped) for a MONOCULTURE whose bioreplicates carry no per-strain series: the strain's
    curve taken from a culture-level trace, by `CULTURE_TECHNIQUES` order (#140).

    Only for a monoculture, where the whole culture is the one strain. The curve's `technique` says
    "culture-level <technique>", so whatever reads it can tell. What it may supply is decided by the
    caller: a growth rate and a lag, never a carrying capacity, since a plateau is read exactly where a
    culture-level proxy is least likely to be proportional to cell number.

    `technique`, the Technique setting, keeps only that technique among `CULTURE_TECHNIQUES`; #140 still
    decides which culture-level counts exist, so OD is never one (Karoline, 2026-10-14, #292).
    """
    technique = technique if technique is not None else TECHNIQUE.get()
    allowed = tuple(t for t in CULTURE_TECHNIQUES if technique in (None, "", t))
    replicates, skipped = [], []
    label = experiment.get("name") or experiment.get("id") or "experiment"
    for stub in experiment.get("bioreplicates", []):
        try:
            bioreplicate = client.get_bioreplicate(stub["id"])
        except Exception as e:  # noqa: BLE001 - one unreadable bioreplicate must not lose the others
            skipped.append((f"{label}: {stub.get('name', stub.get('id'))}", f"{UNREAD} it: {e}"))
            continue
        name = bioreplicate.get("name") or str(bioreplicate.get("id"))
        if bioreplicate.get("isAverage"):
            continue
        by_technique: dict = {}
        for context in bioreplicate.get("measurementContexts", []):
            if (context.get("subject") or {}).get("type") == "bioreplicate":
                by_technique.setdefault(context.get("techniqueType") or "", []).append(context)
        chosen = next((t for t in allowed if len(by_technique.get(t, ())) == 1), None)
        if chosen is None:
            skipped.append((f"{label}: {name}", "no per-strain series and no single culture-level count (plates or "
                                                 "flow cytometry) to take a growth rate from"
                            + (f" measured by {technique}, the Technique setting" if technique else "")))
            continue
        context = by_technique[chosen][0]
        technique_used = chosen
        try:
            points = client.get_measurement_series(context["id"])
        except Exception as e:  # noqa: BLE001 - report the context, keep the others
            skipped.append((f"{label}: {name}", f"{UNREAD} its culture-level {technique_used} series: {e}"))
            continue
        if len(points) < MIN_POINTS:
            skipped.append((f"{label}: {name}", f"{len(points)} measured time point(s) in its culture-level "
                                                 f"{technique_used} series; a curve needs {MIN_POINTS}"))
            continue
        try:
            curve = GrowthCurve(species, [t for t, _, _ in points], [v for _, v, _ in points],
                                bioreplicate.get("measurementTimeUnits") or "", _abundance_unit(context),
                                f"culture-level {technique_used}")
        except ValueError as e:
            skipped.append((f"{label}: {name}", f"culture-level {technique_used}: {e}"))
            continue
        replicates.append(Replicate([curve], name, {}))
    return replicates, skipped


def replicates_for_experiment(client, experiment: dict, spike_factor: float = SPIKE_FACTOR,
                              technique: str | None = None) -> tuple:
    """(replicates, skipped) for one mGrowthDB experiment.

    replicates: a `Replicate` per independent bioreplicate, holding one `GrowthCurve` per strain that
    reports a usable series. skipped: (label, reason) for the averages and for anything unusable.

    A strain measured by several techniques in one replicate is measured by the one with more time points,
    the others named; with the same number of points the tie is named and the strain left out, never
    settled by order (Karoline, 2026-10-13 and 2026-10-14, #292: "priority should be given to the one with
    more time points"). Two contexts of one technique (one per compartment, say) still leave it out, since
    nothing tells them apart. `technique`, the Technique setting, keeps only curves of that technique and
    names the others.
    """
    replicates, skipped = [], []
    label = experiment.get("name") or experiment.get("id") or "experiment"
    for stub in experiment.get("bioreplicates", []):
        try:
            bioreplicate = client.get_bioreplicate(stub["id"])
        except Exception as e:  # noqa: BLE001 - one unreadable bioreplicate must not lose the others
            skipped.append((f"{label}: {stub.get('name', stub.get('id'))}", f"{UNREAD} it: {e}"))
            continue
        name = bioreplicate.get("name") or str(bioreplicate.get("id"))
        if bioreplicate.get("isAverage"):
            skipped.append((f"{label}: {name}", AVERAGE))
            continue
        time_unit = bioreplicate.get("measurementTimeUnits") or ""
        strain_contexts = list(_strain_contexts(bioreplicate))
        technique = technique if technique is not None else TECHNIQUE.get()
        if technique:
            for species, context in strain_contexts:
                if (context.get("techniqueType") or "") != technique:
                    skipped.append((f"{label}: {name}, {species}",
                                    f"measured by {context.get('techniqueType') or 'an unrecorded technique'}; "
                                    f"the Technique setting keeps {technique} only"))
            strain_contexts = [(s_, c) for s_, c in strain_contexts if (c.get("techniqueType") or "") == technique]
        by_species: dict = {}
        for species, context in strain_contexts:
            by_species.setdefault(species, []).append(context)
        single_strain = len(by_species) == 1
        curves, notes = [], {}
        read: dict = {}
        for species, contexts in by_species.items():
            per_technique: dict = {}
            for context in contexts:
                per_technique.setdefault(context.get("techniqueType") or "", []).append(context)
            twice = [t for t, cs in per_technique.items() if len(cs) > 1]
            if twice:   # for example one context per compartment, which the API does not tell apart
                skipped.append((f"{label}: {name}, {species}",
                                f"{len(contexts)} measurement contexts for this strain in one replicate, "
                                f"{len(per_technique[twice[0]])} of them by {twice[0] or 'an unrecorded technique'} "
                                "(for example one per compartment), and nothing says which to use; left out"))
                continue
            if len(contexts) == 1:
                read[species] = contexts[0]
                continue
            # several techniques: the one with more time points (#292)
            sized = []
            for context in contexts:
                try:
                    sized.append((len(client.get_measurement_series(context["id"])), context))
                except Exception:  # noqa: BLE001 - an unreadable series has no points to count
                    sized.append((0, context))
            sized.sort(key=lambda pc: -pc[0])
            if sized[0][0] == sized[1][0]:
                skipped.append((f"{label}: {name}, {species}",
                                "measured by " + " and ".join(c.get("techniqueType") or "an unrecorded technique"
                                                              for _p, c in sized)
                                + f" with {sized[0][0]} time points each, so neither has more; left out rather "
                                  "than chosen by order"))
                continue
            read[species] = sized[0][1]
            for points, context in sized[1:]:
                skipped.append((f"{label}: {name}, {species}",
                                f"its {context.get('techniqueType') or 'unrecorded technique'} series "
                                f"({points} time points) is not used: its "
                                f"{sized[0][1].get('techniqueType') or 'unrecorded technique'} series has more "
                                f"({sized[0][0]}), and one strain is measured by one technique"))
        for species, context in read.items():
            try:
                points = client.get_measurement_series(context["id"])
            except Exception as e:  # noqa: BLE001 - report the context, keep the others
                skipped.append((f"{label}: {name}, {species}", f"{UNREAD} its series: {e}"))
                continue
            if len(points) < MIN_POINTS:
                skipped.append((f"{label}: {name}, {species}",
                                f"{len(points)} measured time point(s); a curve needs {MIN_POINTS}"))
                continue
            times = [t for t, _, _ in points]
            values = [v for _, v, _ in points]
            try:
                curve = GrowthCurve(species, times, values, time_unit, _abundance_unit(context),
                                    context.get("techniqueType") or "")
            except ValueError as e:
                skipped.append((f"{label}: {name}, {species}", str(e)))
                continue
            curves.append(curve)
            if spike(curve, spike_factor):
                notes[species] = _alternatives_note(client, bioreplicate, species, context["id"],
                                                    single_strain, spike_factor)
        if curves:
            replicates.append(Replicate(curves, name, notes))
        else:
            skipped.append((f"{label}: {name}", "no usable per-strain series"))
    return replicates, skipped


def replicate_sets(client, experiments, species_a: str, species_b: str,
                   spike_factor: float = SPIKE_FACTOR) -> tuple:
    """(mono_a, mono_b, co, skipped) for a species pair, across a study's experiments.

    An experiment is a monoculture set when its replicates carry one species, and the co-culture set when
    they carry exactly the pair. Anything else (a larger community, another species) is reported.
    """
    mono_a, mono_b, co, skipped = [], [], [], []
    for experiment in experiments:
        replicates, skips = replicates_for_experiment(client, experiment, spike_factor)
        skipped += skips
        label = experiment.get("name") or experiment.get("id") or "experiment"
        for replicate in replicates:
            species = set(replicate.species)
            if species == {species_a}:
                mono_a.append(replicate)
            elif species == {species_b}:
                mono_b.append(replicate)
            elif species == {species_a, species_b}:
                co.append(replicate)
            else:
                skipped.append((f"{label}: {replicate.name}",
                                f"holds {sorted(species)}, not {species_a} alone, {species_b} alone, or the pair"))
    return mono_a, mono_b, co, skipped
