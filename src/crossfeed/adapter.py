"""mGrowthDB experiments to replicate growth curves.

`crossfeed.interaction` compares replicate sets of growth curves, which is the comparison the
collaboration specified. mGrowthDB serves its measurements as a time series per measurement context, one
context per strain per bioreplicate, so this module is the join between the two: it reads an experiment
and returns one `crossfeed.growth.Replicate` per bioreplicate, each holding a `GrowthCurve` per strain.

Two rules worth stating, because both are choices:

  * A bioreplicate flagged `isAverage` is the mean of the real replicates (mGrowthDB), so it is not an
    independent replicate and is left out, with a reason recorded. Including it would duplicate the data
    and shrink the spread the comparison measures.
  * Units come from the record: the time unit from the bioreplicate, the abundance unit from the
    context's technique units, falling back to the technique name when no unit string is reported (an OD
    reading and a qPCR count then still refuse to be compared, which is the point of the check).

When a strain's curve carries an implausible spike (`crossfeed.growth.spike`), the adapter looks for
other measurements of the same strain in the same replicate and says whether they are clean, because they
are evidence about the flag (in BH_14 the qPCR trace spikes while the flow cytometry trace does not). A
community-level trace counts as such an alternative only in a monoculture, where it measures that single
strain; in a co-culture it is the sum of the members. The alternative is named, never substituted: mixing
techniques between monoculture and co-culture is what register item 13 warns about.

Anything that cannot be built is reported with a reason rather than guessed at, as everywhere else in
crossfeed. Nothing pulled here is written into the repository.
"""
from __future__ import annotations

import statistics

from .growth import SPIKE_FACTOR, GrowthCurve, Replicate, spike

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
            values = [v for _, v, _ in client.get_measurement_series(context["id"])]
        except Exception:  # noqa: BLE001 - an unreadable alternative is reported, not fatal
            parts.append(f"{technique} unreadable")
            continue
        median = statistics.median(values) if values else 0
        if len(values) < MIN_POINTS or median <= 0:
            parts.append(f"{technique} not comparable")
            continue
        ratio = max(values) / median
        verdict = "also spiked" if ratio > spike_factor else "clean"
        parts.append(f"{technique} {verdict} (max/median {ratio:.1f})")
    if parts:
        return "other measurements of this strain in this replicate, not substituted: " + ", ".join(parts)
    if not single_strain:
        return ("no other measurement of this strain in this replicate (the community traces measure all "
                "members together)")
    return "no other measurement of this strain in this replicate"


def _abundance_unit(context: dict) -> str:
    return (context.get("techniqueUnits") or context.get("techniqueOriginalUnits")
            or context.get("techniqueType") or "")


def replicates_for_experiment(client, experiment: dict, spike_factor: float = SPIKE_FACTOR) -> tuple:
    """(replicates, skipped) for one mGrowthDB experiment.

    replicates: a `Replicate` per independent bioreplicate, holding one `GrowthCurve` per strain that
    reports a usable series. skipped: (label, reason) for the averages and for anything unusable.
    """
    replicates, skipped = [], []
    label = experiment.get("name") or experiment.get("id") or "experiment"
    for stub in experiment.get("bioreplicates", []):
        try:
            bioreplicate = client.get_bioreplicate(stub["id"])
        except Exception as e:  # noqa: BLE001 - one unreadable bioreplicate must not lose the others
            skipped.append((f"{label}: {stub.get('name', stub.get('id'))}", f"could not read it: {e}"))
            continue
        name = bioreplicate.get("name") or str(bioreplicate.get("id"))
        if bioreplicate.get("isAverage"):
            skipped.append((f"{label}: {name}", "average of the replicates, not an independent replicate"))
            continue
        time_unit = bioreplicate.get("measurementTimeUnits") or ""
        strain_contexts = list(_strain_contexts(bioreplicate))
        counts = {}
        for species, _ in strain_contexts:
            counts[species] = counts.get(species, 0) + 1
        for species, n in counts.items():
            if n > 1:   # for example one context per compartment, which the API does not tell apart
                skipped.append((f"{label}: {name}, {species}",
                                f"{n} measurement contexts for this strain in one replicate (for example one per "
                                "compartment), and nothing says which to use; left out"))
        strain_contexts = [(species, context) for species, context in strain_contexts if counts[species] == 1]
        single_strain = len(counts) == 1
        curves, notes = [], {}
        for species, context in strain_contexts:
            try:
                points = client.get_measurement_series(context["id"])
            except Exception as e:  # noqa: BLE001 - report the context, keep the others
                skipped.append((f"{label}: {name}, {species}", f"could not read its series: {e}"))
                continue
            if len(points) < MIN_POINTS:
                skipped.append((f"{label}: {name}, {species}",
                                f"{len(points)} measured time point(s); a curve needs {MIN_POINTS}"))
                continue
            times = [t for t, _, _ in points]
            values = [v for _, v, _ in points]
            try:
                curve = GrowthCurve(species, times, values, time_unit, _abundance_unit(context))
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
