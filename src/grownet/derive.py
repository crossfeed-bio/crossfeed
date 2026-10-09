"""Derive interactions from mGrowthDB growth data.

mGrowthDB serves raw growth (mono and co-culture), not interactions. An interaction is inferred by
comparing a strain's growth ALONE vs WITH a partner, under one condition. The COMPARISON METHOD is a
scientific choice owned by the collaboration (K. Faust): which growth metric, how to read a per-strain
signal inside a community, and the significance test.

That choice plugs in through the `Deriver` interface, and two methods are in it. `IntegratedDeriver`
(grownet.integrated) is the default since 0.3.0: each organism's whole row fitted from its time course.
`ReplicateDeriver`, in this module, is the comparison of replicate sets the collaboration specified and
settled (docs/METHOD_NOTES.md), one setting away as `--derivation replicate`. Another method drops in the
same way, without touching the network model or the pipeline.

The retired `BaselineDeriver` that first ran this seam end to end was deleted in 0.3.0 (#139): the seam
has two real derivations now and needs no placeholder to demonstrate it. What it did is in
docs/METHOD_NOTES.md, where the register's `[baseline]` tags record which option it took in each menu.

"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from statistics import mean, median

from . import media as media_rules
from . import rates
from . import selection as selecting
from .adapter import replicates_for_experiment
from .growth import (
    SPIKE_FACTOR,
    GrowthCurve,
    Replicate,
    curve_features,
    fall_from_peak,
    mean_over,
    reached_stationary,
    spike,
)
from .interaction import (
    ABOLISHED,
    NO_GROWTH,
    OBLIGATE,
    QUANTIFIED,
    UNUSABLE,
    dropout_interaction_strengths,
    interaction_strength,
    rule_meta,
)
from .interaction import DROPOUT as DROPOUT_EVIDENCE
from .mgrowthdb import MGrowthDBClient, MGrowthDBError
from .model import genus_name
from .stats import CORRECTIONS, welch


def genus_species(name: str) -> str:
    """Genus + species key for matching a strain across experiments (drops the strain designation)."""
    return " ".join((name or "").split()[:2]).lower()


_gs = genus_species   # short alias used throughout this module


def _members(exp: dict) -> list:
    return [s.get("name", "") for s in exp.get("communityStrains", [])]


REPLICATE_METHOD = ("crossfeed replicate v1: mean log2({metric} in co-culture) minus mean log2({metric} in "
                    "monoculture) over replicate sets; absent when |mean| < k * sd; Welch's t-test "
                    "reported and corrected for multiple testing, not used to decide")
PRESENT, ABSENT = "present", "absent"
ABSENCE_THRESHOLD = 1.0    # k: absent when |log2 mean| < k * sd. k = 1 is the mean plus or minus sd rule
# What a network says about its own statistics. These are the **specified comparison's**: a derivation
# that tests something else says so through its own `statistics` attribute, which `output_meta` reads
# (#142 item 5). They were a module constant copied into every network, so a file derived by the
# integrated form claimed Welch's test over replicate sets, which that form does not run, and the claim
# travelled into the JSON, GraphML, the Cytoscape legend, the page and the daily artifact.
STATISTICS = {"test": "Welch's two-sided t-test on the per-replicate log2 values",
              "correction": "{name} over every comparison tested in this derivation",
              "role": "reported as support for an edge; presence is decided by the absence threshold"}

# Quality flags make an edge low quality: hidden by default, and never read as the absence of an
# interaction (Karoline, on #40). Notes inform without disqualifying, such as an excluded outlier.
SINGLE_REPLICATE = "single_replicate"
STRAINS_POOLED = "strains_pooled"
REMOVED_MEMBER_DETECTED = "removed_member_detected"
NON_BATCH = "non_batch"
# a continuous culture compared on a metric that suits it: shown, with the mode named (Karoline, 2026-10-03)
CONTINUOUS_CULTURE = "continuous_culture"
BATCH = "batch"           # the only cultivation mode derived by default (Karoline, #42)


def cultivation(exp: dict) -> str:
    """The experiment's cultivation mode, lowercased, or "unspecified".

    A growth curve from a chemostat or a serial dilution does not mean what a batch curve means: an area
    under the curve or a maximum is meaningless under dilution, and a continuous-culture growth rate is a
    different quantity. So only batch experiments are derived by default (Karoline, #42), and a mode that
    is missing or unrecognized counts as not batch rather than being assumed to be batch.
    """
    return (exp.get("cultivationMode") or "unspecified").strip().lower()
# Cautions are shown without making an edge low quality (Karoline, on #47): the edge keeps its status.
TWO_REPLICATES = "two_replicates"
# experiments that differ only in their description (a supplement, a lineage) under identical recorded
# conditions, where nothing recorded says which monoculture or drop-out matches which (Karoline, 2026-09-27)
CONDITIONS_UNVERIFIED = "conditions_unverified"
# the rows of an integrated fit cover less than half the measured course, because the model has no lag
# term and no death term and so stops at the end of the plateau after the maximum. The effect one
# organism has on another can change along the growth curve, competition first and facilitation later;
# that is not treated here, and this says the coefficient describes the phase inside the window rather
# than the whole course (Karoline, 2026-10-07: "this is not something we treat here, but something we
# can warn about", with SMGDB00000002's Roseburia and Bacteroides as her example)
WINDOW_PARTIAL = "window_partial"
# with max as the measure (Karoline, 2026-09-28): one set reached stationary phase and the other did not,
# so the maximum of one may still be rising; or the curves are too sparse to tell
STATIONARY_DIFFERS, STATIONARY_UNCHECKED = "stationary_phase_differs", "stationary_unchecked"
# an obligate or abolished arc whose set without growth is zero from its first time point: no growth cannot
# be told from no inoculum or counts below detection (Karoline, 2026-09-28: "Obligate, with a caution")
ZERO_AT_START = "zero_at_start"
# With the q-value filter on, an arc that has no p-value (obligate or abolished: no finite ratio;
# a single replicate on one side: no spread) cannot be judged by it; it is kept and says so (Karoline,
# 2026-09-30: "Keep them, labeled untested")
UNTESTED = "untested"


def zero_start_cautions(zero_start, outcome: str) -> list:
    """The zero-at-start caution of an obligate or abolished comparison."""
    if not zero_start:
        return []
    side = "without" if outcome == OBLIGATE else "with" if outcome == ABOLISHED else None
    return [ZERO_AT_START] if side and zero_start.get(side) else []


def stationary_cautions(stationary, method: str, outcome: str) -> list:
    """The stationary-phase caution of a quantified comparison on max, from its two set verdicts."""
    if method != "max" or outcome != QUANTIFIED or not stationary:
        return []
    verdicts = (stationary.get("with"), stationary.get("without"))
    if None in verdicts:
        return [STATIONARY_UNCHECKED]
    return [STATIONARY_DIFFERS] if verdicts[0] != verdicts[1] else []


def condition_key(exp: dict):
    """What counts as the same condition: the recorded conditions AND the medium by the strict rule.

    Karoline, 2026-10-07: "the strict medium matching (exclusion of cases with modifications e.g. mucin
    addition) should be applied everywhere where medium matching is done." `conditions` compares the
    compartment records, and mGrowthDB states an added sugar, a removed carbon source or a supplement only
    in the **description**, which `media.identity` reads and `conditions` does not. So `conditions` alone
    put chemically different experiments under one key: on SMGDB00000014 a single `conditions` value
    covers twelve media, from plain minimal medium to minimal medium with 0.75 per cent linoleic acid and
    a tbhq antioxidant, and the monocultures of all twelve were offered to one co-culture, to be told
    apart afterwards by the wording of their descriptions.

    Every place that asks "is this the same condition" uses this, so the strict rule cannot hold in one
    path and not another: the monoculture index both derivations read, the drop-out designs, and the run
    variants.
    """
    return conditions(exp), media_identity(exp)["key"]


def media_identity(exp: dict) -> dict:
    """The medium an experiment ran in, by the strict rule (`media.identity`).

    One place, so every medium comparison in the tool means the same thing: the capacity merge, the
    chemostat check, the second box and what an arc says it was measured in (Karoline, 2026-10-07:
    "foodnet's strict medium rule should be applied in general").
    """
    return media_rules.identity(exp)


def conditions(exp: dict) -> str:
    """The culture conditions of an experiment as a comparable key: cultivation mode and compartments.

    Replicate sets are pooled only across experiments with identical conditions, since interactions are
    usually environmentally specific (Karoline, on #47); experiments under different conditions give
    separate edges. Filtering by environment is a separate question (#61).
    """
    return json.dumps([exp.get("cultivationMode"), exp.get("compartments", [])], sort_keys=True)


# The maximal abundance of a continuous culture is a quantity a comparison can use: the culture settles at
# a level, and the level with a partner against the level without it is the same comparison as in batch.
# An area under the curve and a growth rate are not: under dilution the area says how long the run was, and
# the rate is the dilution rate (Karoline, 2026-10-03: "we don't use data when they are from chemostat. But
# we can, when the growth curve property is max ... the no-chemostat filter is too harsh").
METRICS_FOR_CONTINUOUS_CULTURE = ("max",)


def keeps_continuous_culture(metric: str, include_non_batch: bool = False) -> bool:
    return include_non_batch or metric in METRICS_FOR_CONTINUOUS_CULTURE


def _batch_only(exps, include_non_batch: bool, skipped, metric: str = "auc") -> list:
    """The experiments a derivation may use, reporting each one left out with its mode.

    Continuous culture (chemostat, serial dilution) is kept when the metric is one it suits, and when the
    user asks for it with the advanced setting. A comparison never mixes modes: `conditions` carries the
    cultivation mode, so a chemostat co-culture is compared only with chemostat monocultures.
    """
    if keeps_continuous_culture(metric, include_non_batch):
        return list(exps)
    kept = []
    for exp in exps:
        mode = cultivation(exp)
        if mode == BATCH:
            kept.append(exp)
        else:
            skipped.append((exp.get("name", "") or _exp_id(exp),
                            f"{mode}, excluded by default with the growth measure {metric}: an area under "
                            "the curve or a growth rate of a continuous culture is not comparable with a "
                            f"batch one. Use the growth measure max, which it suits, or the advanced "
                            "setting"))
    return kept


def select_experiments(exps, selection, skipped) -> list:
    """The experiments a selection asks for, with the monocultures a kept comparison needs.

    Karoline, 2026-10-04, choosing between a literal reading and this one: naming a co-culture also keeps
    the monocultures it is compared against, "chosen by the existing matching rules", because one id alone
    would otherwise give no arc at all. Those monocultures are the ones under the same conditions
    (`conditions`), from which `_choose_monocultures` picks as it always does; what came along is reported.

    An empty selection keeps everything.
    """
    if selecting.empty(selection):
        return list(exps)
    kept = [e for e in exps if selecting.matches(e, selection)]
    # the monocultures a kept comparison needs: the same recorded conditions AND the same medium by the
    # strict rule, since `conditions` compares the compartment records and mGrowthDB states an added sugar
    # or a removed carbon source only in the description. Without the medium, naming one chemistry of
    # SMGDB00000014 pulled in the monocultures of all twelve (Karoline, 2026-10-07)
    wanted = {condition_key(e) for e in kept if len(_members(e)) > 1}
    added = [e for e in exps
             if e not in kept and len(_members(e)) == 1
             and condition_key(e) in wanted]
    if added:
        skipped.append(("monocultures kept alongside the experiments named",
                        ", ".join(sorted(_exp_id(e) for e in added))
                        + ": the comparisons you named are made against them"))
    if not kept:
        skipped.append((f"study {study_ids_of(exps)}",
                        "no experiment of this study matches the media, experiments or studies entered"))
    # a medium is matched as text, so one word reaches every medium whose name or description holds it,
    # and an added or removed compound makes another environment: say how many were read, since that is
    # what the strict rule is for (Karoline, 2026-10-07, "because such changes alter interactions")
    if selection.get("media"):
        labels = sorted({media_identity(e)["label"] for e in kept})
        if len(labels) > 1:
            skipped.append(("media matched by " + ", ".join(selection["media"]),
                            f"{len(labels)} different media, which are different environments and give "
                            "separate arcs, never one pooled set: " + "; ".join(labels)
                            + ". Name an experiment id in the second box to read one of them alone"))
    return kept + added


def study_ids_of(exps) -> str:
    """The studies a list of experiments belongs to, for a message."""
    return ", ".join(sorted({str(e.get("studyId", "")) for e in exps if e.get("studyId")})) or "this study"


def _replicate_flags(n_with: int, n_without: int) -> tuple:
    """(quality, cautions) from the replicate counts of a comparison."""
    if n_with < 2 or n_without < 2:
        return [SINGLE_REPLICATE], []
    if min(n_with, n_without) == 2:
        return [], [TWO_REPLICATES]
    return [], []


NCBI, BY_NAME = "ncbi", "name"


def _designation(name: str) -> str:
    """The strain designation: what follows genus and species ("A2-165" in "Faecalibacterium duncaniae A2-165")."""
    return " ".join((name or "").split()[2:])


def strain_identities(exps, skipped) -> dict:
    """strain name -> {"id", "taxon_id", "species", "identity"} for every community strain of a study.

    A strain is identified by its NCBI taxon id (Karoline, #23): node id `ncbi:<id>`, so a strain renamed
    after a reclassification (411483 is "Faecalibacterium prausnitzii A2-165" in one study and
    "Faecalibacterium duncaniae A2-165" in others) stays one node, and two strains of one species stay
    two. The node is named with the strain name, so the network stays readable.

    An id is not trusted where it is ambiguous: when a study gives one taxon id to strains with different
    designations (in SMGDB00000008, 1506553 is both "Lachnoclostridium clostridioforme 2_1_49FAA" and
    "Lachnoclostridium symbiosum WAL-14673"), those strains, like strains without an id, are identified by
    genus and species instead (identity `name`), and the conflict is reported. `species` is always the
    genus and species of the name, the shared key for merging with species-level networks, derived from
    the name and not from a taxonomy lookup (Karoline, item 8 on #25).
    """
    names_by_taxon = {}
    for exp in exps:
        for strain in exp.get("communityStrains", []):
            if strain.get("NCBId") is not None and strain.get("name"):
                names_by_taxon.setdefault(str(strain["NCBId"]), set()).add(strain["name"])
    ambiguous = set()
    for taxon, names in names_by_taxon.items():
        if len({_designation(n) for n in names if _designation(n)}) > 1:
            ambiguous.add(taxon)
            skipped.append((f"taxon id {taxon}", "given to different strains in this study "
                            f"({', '.join(sorted(names))}); they are identified by genus and species instead"))
    identities = {}
    for exp in exps:
        for strain in exp.get("communityStrains", []):
            name = strain.get("name", "")
            taxon = None if strain.get("NCBId") is None else str(strain["NCBId"])
            if name in identities:
                continue
            if taxon is not None and taxon not in ambiguous:
                identities[name] = {"id": f"ncbi:{taxon}", "taxon_id": taxon, "species": genus_species(name),
                                    "identity": NCBI}
            else:
                identities[name] = {"id": genus_species(name), "taxon_id": taxon or "",
                                    "species": genus_species(name), "identity": BY_NAME}
    return identities


def _identity(identities: dict, name: str) -> dict:
    return identities.get(name) or {"id": genus_species(name), "taxon_id": "", "species": genus_species(name),
                                    "identity": BY_NAME}


def _mono_index(client, exps, skipped, spike_factor: float = SPIKE_FACTOR, identities=None) -> dict:
    """(node id, conditions, medium key) -> {run group: (monoculture replicates, the distinct strain names
    pooled under it, the ids of the experiments they come from, their descriptions, their names)}.

    The medium is part of the key by the strict rule (`condition_key`), so a monoculture in an unaltered
    medium is never offered to a co-culture in an altered one. `why_no_monoculture` turns a miss into a
    reason that names the medium that was there instead.

    Monocultures are pooled only when they are replicates: identical recorded conditions AND the same
    description apart from a run number (`run_group`), the rule communities already follow (Karoline, on
    #47 and on 2026-09-27). mGrowthDB records supplements, concentrations, starting densities and lineages
    in the description only, so monocultures that differ there were grown differently and stay apart.
    Only strains identified by name can pool different strains.
    """
    identities = identities if identities is not None else strain_identities(exps, [])
    index = {}
    for exp in exps:
        members = _members(exp)
        if len(members) != 1:
            continue
        replicates, skips = replicates_for_experiment(client, exp, spike_factor)
        skipped += skips
        key = (_identity(identities, members[0])["id"], *condition_key(exp))
        reps, strains, ids, descriptions, names = index.setdefault(key, {}).setdefault(
            run_group(exp), ([], set(), [], [], []))
        reps.extend(replicates)
        strains.add(members[0])
        ids.append(_exp_id(exp))
        descriptions.append(exp.get("description") or exp.get("name") or "")
        names.append(exp.get("name") or "")
    for (key, *_rest), groups in index.items():
        for _, (_, strains, _, _, _) in groups.items():
            if len(strains) > 1 and not key.startswith("ncbi:"):
                skipped.append((f"monocultures of {key}", f"{len(strains)} strains pooled into one monoculture set "
                                f"({', '.join(sorted(strains))}); edges using it are flagged {STRAINS_POOLED}"))
    return index


# ---- what a gLV coefficient is made of (#118) -----------------------------------------------------

# A gLV coefficient is an effect per unit of partner, so it needs the partner's abundance while the target
# was growing: `A_ij = r_i * (2^L - 1) / x_j_star`. Karoline chose `x_j_star` to be the partner's mean over
# the window the target's rate was fitted in (2026-10-06, on #116), because the coefficient is
# instantaneous and that window is the stretch the comparison's rate came from. Nothing here changes an
# arc: it adds a number beside it, and says why when there is none.
def partner_abundance(replicate, target: str, partner: str, rate_method: str = None,
                      window: int = None) -> dict:
    """{"value", "unit", "window", "reason"}: the partner's mean abundance over the target's rate window.

    `value` is None with a `reason` when the target has no fitted window (a curve that never rises), when
    the partner was not measured in this replicate, or when the window reaches outside the partner's
    curve.
    """
    target_curve, partner_curve = replicate.curve(target), replicate.curve(partner)
    if target_curve is None:
        return {"value": None, "unit": "", "window": None, "reason": f"{target} was not measured here"}
    if partner_curve is None:
        return {"value": None, "unit": "", "window": None,
                "reason": f"the partner {partner} was not measured in this replicate"}
    method = rate_method or rates.DEFAULT_METHOD
    try:
        if method == "baranyi":
            fit = rates.baranyi_fit(target_curve.times, target_curve.values)
        else:
            fit = rates.easylinear_fit(target_curve.times, target_curve.values,
                                       window if window is not None else rates.DEFAULT_WINDOW)
    except rates.RateUnavailable as e:
        return {"value": None, "unit": "", "window": None, "reason": f"no rate window for {target}: {e}"}
    start, end = fit.get("start"), fit.get("end")
    if start is None or end is None or end <= start:
        return {"value": None, "unit": "", "window": None,
                "reason": f"{target} has no window that rises, so there is nothing to average over"}
    value = mean_over(partner_curve, start, end)
    if value is None:
        return {"value": None, "unit": partner_curve.abundance_unit, "window": (start, end),
                "reason": f"the partner's curve does not cover {start:g} to {end:g} "
                          f"{partner_curve.time_unit}"}
    return {"value": value, "unit": partner_curve.abundance_unit, "window": (start, end), "reason": ""}


def target_capacity(replicates, target: str, max_fall: float = None) -> dict:
    """{"value", "unit", "n", "skipped"}: the target's own plateau in these co-culture replicates.

    An organism that does not grow alone has no monoculture carrying capacity, so its self-limitation
    cannot be fitted the usual way. What it does have is a plateau beside its partner, and at that plateau
    the gLV balance reads `0 = r_i + A_ii x_i + sum_j A_ij x_j`, which fits `A_ii` (#123). Only curves
    `reached_stationary` certifies count, as in #118, and the median runs over the replicates that have
    one; abundances in different units are reported rather than converted.

    **The decline limit applies here too** (Karoline, 2026-10-07, `CAPACITY_MAX_FALL`). This is the other
    place a plateau becomes a self-limitation, and it was the only one that did not refuse a curve whose
    peak it had long since lost: `reached_stationary` certifies a culture that grew, peaked and declined,
    on purpose, and the limit is what keeps a peak that was held for one measurement out of a carrying
    capacity. Without it 18 live values rested on curves past the limit, several of them with every curve
    behind the value past it: SMGDB00000007's `bhbt` B. thetaiotaomicron fell by 67 to 159 times on all
    six (#155 item 10).
    """
    limit = CAPACITY_MAX_FALL if max_fall is None else max_fall
    values, unit, skipped = [], "", []
    for i, replicate in enumerate(replicates):
        curve = replicate.curve(target)
        label = f"{target} in co-culture: replicate {replicate.name or i}"
        if curve is None:
            skipped.append((label, "no curve for this organism in this replicate"))
            continue
        settled = reached_stationary(curve, curve.times[-1])
        if settled is not True:
            skipped.append((label, "the curve is too sparse or does not rise, so stationary phase cannot "
                                   "be judged" if settled is None else
                                   "the curve had not reached stationary phase"))
            continue
        fall = fall_from_peak(curve, curve.times[-1])
        if fall is None:
            skipped.append((label, "the curve ends at zero or below, so what it held cannot be read "
                                   "from it"))
            continue
        if limit and fall > limit:
            skipped.append((label, f"the curve ends at 1/{fall:.3g} of its peak, further than the "
                                   f"{limit:g} times allowed: the peak is not a level this culture held"))
            continue
        unit = unit or curve.abundance_unit
        if curve.abundance_unit != unit:
            skipped.append((label, f"the plateau is in {curve.abundance_unit} and the others in {unit}; "
                                   "left out rather than converted"))
            continue
        values.append(curve_features(curve)["max"])
    return {"value": median(values) if values else None, "unit": unit if values else "",
            "n": len(values), "skipped": skipped}


def partner_abundances(replicates, target: str, partner: str, rate_method: str = None,
                       window: int = None) -> dict:
    """The same over a replicate set: the median of the replicates that have one, with the rest reported.

    {"value", "unit", "n", "skipped"}: `value` is None when no replicate gave one, and `skipped` holds a
    (label, reason) for each that did not, so the report says why rather than leaving a blank.
    """
    values, unit, skipped = [], "", []
    for i, replicate in enumerate(replicates):
        got = partner_abundance(replicate, target, partner, rate_method, window)
        if got["value"] is None:
            skipped.append((f"{partner} beside {target}: replicate {replicate.name or i}", got["reason"]))
            continue
        values.append(got["value"])
        unit = unit or got["unit"]
        if got["unit"] != unit:
            skipped.append((f"{partner} beside {target}: replicate {replicate.name or i}",
                            f"measured in {got['unit']}, and the others in {unit}; left out rather than "
                            "converted"))
            values.pop()
    return {"value": median(values) if values else None, "unit": unit, "n": len(values), "skipped": skipped}


# ---- growth rates beside a network (#108) --------------------------------------------------------

# A reported growth rate is an absolute quantity, not a comparison: the maximum specific growth rate of
# one organism in monoculture, which is what a generalized Lotka-Volterra simulator takes as r_i (Karoline,
# 2026-10-03: "report growth rates (main reason would be gLV support, but it could also be of interest for
# other reasons)", and the rate is the "Maximum specific growth rate in monoculture (easylinear, as
# mGrowthDB reports), median across replicates and studies, with the per-study values kept beside it").
#
# Monocultures only, and batch monocultures only: a rate from a co-culture is the organism's growth with a
# partner, which is the comparison, not the organism's own rate; and under dilution the rate a curve shows
# is the dilution rate (`METRICS_FOR_CONTINUOUS_CULTURE`).
# How far a certified curve may have fallen from its peak and still give a carrying capacity: the window
# maximum divided by the last measured value. `reached_stationary` certifies a culture that grew, peaked
# and then declined, because it has stopped growing, and the plateau recorded for it is the peak. On the
# live database (2026-10-07, all 1,331 per-strain batch curves) 443 certify and 417 of them, 94 percent,
# end more than 10 percent below their peak: the median certified curve ends at a third of its peak and
# the upper quartile at a tenth, so a decline is the ordinary shape of a batch culture of gut anaerobes
# and refusing every declining curve would take 20 of the 29 organism-study pairs that have a capacity
# down to none (Karoline, 2026-10-07: "I agree Craig's approach is too harsh"). The tail is a different
# matter: A. tumefaciens in SMGDB00000014 certifies with a peak of 8.2e7 against a last value of 1, and
# 18 curves fall by more than a thousandfold, where the peak is a spike and not a level anything held.
# 10 is the line between them and reads as a sentence: the culture still holds a tenth of its peak at the
# last measurement. It refuses 112 of the 443 and leaves 2 of the 29 pairs with no capacity, both in
# SMGDB00000012 and both named in `capacity_left_out`. The page and --capacity-max-fall can move it; 0
# switches the refusal off and keeps every certified plateau, as the tool did before 0.3.0.
CAPACITY_MAX_FALL = 10.0


def _collect_capacity(entry: dict, curve, label: str, medium: dict | None = None,
                      max_fall: float = CAPACITY_MAX_FALL) -> None:
    """Add this curve's plateau to an organism's capacities for the medium it was measured in, or say why
    it gives none.

    The plateau is certified by `reached_stationary` and taken as the curve's maximum. Every curve that
    gives none is named in `capacity_left_out`, which is what the help promises a reader. A curve that
    has fallen further from its peak than `max_fall` gives none either: see `CAPACITY_MAX_FALL`.

    `medium` is a `media.identity` result. Plateaus are collected per medium and never pooled across
    media, Karoline's decision of 2026-10-07: a capacity sits on the diagonal beside off-diagonals
    measured in one medium, so the two have to be the same medium. `merge_rates` chooses which.
    """
    settled = reached_stationary(curve, curve.times[-1])
    if settled is not True:
        entry["capacity_left_out"].append(
            (label, "the curve is too sparse or does not rise, so stationary phase cannot be judged"
             if settled is None else "the curve had not reached stationary phase"))
        return
    fall = fall_from_peak(curve, curve.times[-1])
    if fall is None:
        entry["capacity_left_out"].append(
            (label, "the curve ends at zero or below, so what it held cannot be read from it"))
        return
    if max_fall and fall > max_fall:
        entry["capacity_left_out"].append(
            (label, f"the curve ends at 1/{fall:.3g} of its peak, further than the {max_fall:g} times "
                    "allowed: the peak is not a level this culture held"))
        return
    medium = medium or {"key": "unnamed medium", "label": "unnamed medium"}
    at = entry["capacity_by_medium"].setdefault(
        medium["key"], {"label": medium["label"], "unit": curve.abundance_unit,
                        "values": [], "falls": [], "curves": [], "labels": []})
    # the alias table can make two spellings one medium, so every spelling behind a capacity is kept and
    # reported: a merge grownet made by hand is never silent (Karoline, 2026-10-07)
    if medium["label"] not in at["labels"]:
        at["labels"].append(medium["label"])
    if curve.abundance_unit != at["unit"]:
        entry["capacity_left_out"].append(
            (label, f"the plateau is in {curve.abundance_unit}, and this organism's others in "
                    f"{at['unit']}; left out rather than converted"))
        return
    at["values"].append(curve_features(curve)["max"])
    at["falls"].append(fall)
    at["curves"].append(label)


def monoculture_rates(client, exps, wanted=None, rate_method: str = None, window: int = None,
                      spike_factor: float = SPIKE_FACTOR, identities=None,
                      capacity_max_fall: float = CAPACITY_MAX_FALL) -> tuple:
    """({node id: {"name", "values", "unit", "replicates"}}, skipped): a rate per monoculture replicate.

    `wanted`, when given, is the node ids to read, so a search reads the rates of the organisms in its
    network and nothing else. A replicate whose curve carries an implausible spike, whose curve has no
    rate by this method, or whose rate is not positive is left out and reported, as in the derivation:
    nothing is replaced by another number. A value whose time unit differs from the first value of that
    organism is left out and reported too, since rates in different units are not one set.
    """
    method = rates.method_name(rate_method or rates.DEFAULT_METHOD,
                               window if window is not None else rates.DEFAULT_WINDOW)
    feature = rates.feature(method)
    skipped, found = [], {}
    identities = identities if identities is not None else strain_identities(exps, [])
    for exp in _batch_only(exps, False, skipped, method):
        members = _members(exp)
        if len(members) != 1:
            continue
        name = members[0]
        node = _identity(identities, name)
        if wanted is not None and node["id"] not in wanted:
            continue
        replicates, skips = replicates_for_experiment(client, exp, spike_factor)
        skipped += skips
        entry = found.setdefault(node["id"], {"name": name, "values": [], "unit": "", "replicates": [],
                                              "method": method, "lag_method": rates.LAG_METHOD,
                                              "lags": [], "capacity_by_medium": {},
                                              "capacity_left_out": []})
        medium = media_identity(exp)
        for i, rep in enumerate(replicates):
            label = f"{name} monoculture [{exp.get('name', '') or _exp_id(exp)}], replicate {rep.name or i}"
            curve = rep.curve(name)
            if curve is None:
                skipped.append((label, "no growth curve for this strain; no growth rate from it"))
                continue
            if spike(curve, spike_factor):
                skipped.append((label, "implausible spike in the curve; no growth rate from it"))
                entry["capacity_left_out"].append(
                    (label, "implausible spike in the curve, which would raise its maximum"))
                continue
            # a plateau is a property of the curve, so it is collected whether or not the chosen
            # estimator can fit this curve's slope. It used to sit after these refusals, which made the
            # carrying capacity, and so every diagonal, depend on the rate estimator (found 2026-10-06).
            try:
                value = feature(curve.times, curve.values)
            except rates.RateUnavailable as e:
                skipped.append((label, f"no growth rate: {e}"))
                _collect_capacity(entry, curve, label, medium, capacity_max_fall)
                continue
            if value <= 0:
                skipped.append((label, f"non-positive growth rate ({value:g})"))
                _collect_capacity(entry, curve, label, medium, capacity_max_fall)
                continue
            unit = f"1/{curve.time_unit}"
            if not entry["unit"]:
                entry["unit"] = unit
            if unit != entry["unit"]:
                skipped.append((label, f"growth rate in {unit}, and this organism's other rates are in "
                                       f"{entry['unit']}; left out rather than converted"))
                _collect_capacity(entry, curve, label, medium, capacity_max_fall)
                continue
            entry["values"].append(value)
            entry["replicates"].append(rep.name or str(i))
            # the lag always comes from the Baranyi fit, the only estimator that has one, whichever
            # estimator produced the rate (Karoline, 2026-10-06: "use the lag from Baranyi and easylinear
            # since it works better"). A curve the Baranyi guards reject keeps its rate and has no lag.
            try:
                entry["lags"].append(rates.baranyi_fit(curve.times, curve.values)["lag"])
            except rates.RateUnavailable:
                pass
            _collect_capacity(entry, curve, label, medium, capacity_max_fall)
    # an organism is kept when it has a rate or a certified plateau: a study where the estimator fitted
    # no rate still measured the plateau, and dropping it there made the capacity estimator-dependent
    # across studies as well (found 2026-10-06)
    return {nid: e for nid, e in found.items() if e["values"] or e["capacity_by_medium"]}, skipped


def growth_rates(client, study_ids, wanted=None, rate_method: str = None, window: int = None,
                 spike_factor: float = SPIKE_FACTOR, progress=None,
                 capacity_max_fall: float = CAPACITY_MAX_FALL) -> tuple:
    """(rates, skipped) over several studies: each study's monoculture rates, merged by `merge_rates`.

    The studies are the ones the search read, so their experiments and curves are already cached and no
    rate costs a new request. A study that cannot be read is reported and the others still give rates.
    """
    per_study, skipped = [], []
    for i, study_id in enumerate(study_ids):
        if progress:
            progress(i, len(study_ids), f"Reading growth rates from {study_id}")
        try:
            study = client.get_study(study_id)
            exps = [client.get_experiment(e["id"]) for e in study.get("experiments", [])]
        except MGrowthDBError as e:
            skipped.append((f"growth rates of {study_id}", f"could not be read: {e}"))
            continue
        found, skips = monoculture_rates(client, exps, wanted, rate_method, window, spike_factor,
                                         capacity_max_fall=capacity_max_fall)
        per_study.append((study_id, found))
        skipped += skips
    return merge_rates(per_study), skipped


def merge_rates(per_study) -> dict:
    """{node id: {"name", "rate", "unit", "n", "studies", "per_study", ...}}: one growth rate per organism.

    `per_study` is (study id, what `monoculture_rates` found) for each study. The rate is the median over
    every monoculture replicate of every study, Karoline's "median across replicates and studies", with
    each study's own median kept beside it in `per_study` and the number of replicates behind it in `n`.
    A study whose rates for an organism are in another time unit is left out of its median and named in
    `other_units`.

    Beside the rate, and merged the same way, come the three numbers a gLV coefficient is made of (#118):
    `capacity` with `capacity_unit`, `capacity_n` and `capacity_per_study` (the monoculture plateau, only
    from curves certified to have reached stationary phase, left out rather than converted across
    abundance units, with every curve left out and why in `capacity_left_out`; a curve can give a rate
    and no capacity, so these stay out of `skipped`, where the rate itself was not left out), `lag` with
    `lag_n` and `lag_method` (always the Baranyi fit, the only estimator that has a lag, whichever one
    produced the rate), and `method`, the estimator the rate came from. Each is None when nothing
    qualified.

    **A capacity comes from one medium**, Karoline's decision of 2026-10-07: plateaus are collected per
    medium (`media.identity`) and the medium with the most certified curves is the one published, named
    in `capacity_medium`, with every other medium's curves named in `capacity_left_out` rather than
    pooled in. `capacity_media` therefore holds exactly one label, and `capacity_other_media` says what
    else this organism has a plateau in, so a reader who wants that medium can ask for it in the second
    box. Pooling plateaus over media was how this worked before 0.3.0, and it put a diagonal from two
    chemistries beside off-diagonals measured in one of them.
    """
    merged: dict = {}
    for study_id, found in per_study:
        for nid, entry in found.items():
            at = merged.setdefault(nid, {"name": entry["name"], "unit": entry["unit"], "values": [],
                                         "studies": [], "per_study": {}, "other_units": [],
                                         "method": entry.get("method", ""), "lags": [],
                                         "lag_method": entry.get("lag_method", ""),
                                         "by_medium": {}, "capacity_left_out": []})
            if entry["values"] and entry["unit"] != at["unit"]:
                at["other_units"].append(f"{study_id} ({entry['unit']})")
                continue
            if entry["values"]:
                at["values"] += list(entry["values"])
                at["studies"].append(study_id)
                at["per_study"][study_id] = median(entry["values"])
            at["lags"] += list(entry.get("lags") or [])
            at["capacity_left_out"] += list(entry.get("capacity_left_out") or [])
            for key, found_here in (entry.get("capacity_by_medium") or {}).items():
                one = at["by_medium"].setdefault(key, {"label": found_here["label"],
                                                       "unit": found_here["unit"], "values": [],
                                                       "falls": [], "curves": [], "per_study": {},
                                                       "other_units": [], "labels": []})
                if found_here["unit"] != one["unit"]:
                    one["other_units"].append(f"{study_id} ({found_here['unit']})")
                    continue
                for spelling in found_here.get("labels") or ():
                    if spelling not in one["labels"]:
                        one["labels"].append(spelling)
                one["values"] += list(found_here["values"])
                one["falls"] += list(found_here["falls"])
                one["curves"] += list(found_here["curves"])
                one["per_study"][study_id] = median(found_here["values"])
    out = {}
    for nid, at in merged.items():
        if not at["values"]:
            continue
        # the medium with the most certified curves is the one published; a tie goes to the first label,
        # so the choice does not depend on the order the studies were read in
        order = sorted(at["by_medium"].items(), key=lambda kv: (-len(kv[1]["values"]), kv[1]["label"]))
        chosen = order[0][1] if order else None
        left_out = list(at["capacity_left_out"])
        for _key, other in order[1:]:
            left_out.append((f"{len(other['values'])} curve(s) in {other['label']}",
                             f"this organism's capacity is taken from {chosen['label']}, where more "
                             "curves reached a plateau; plateaus are not pooled across media, since a "
                             "capacity sits beside off-diagonals measured in one of them"))
        out[nid] = {"name": at["name"], "rate": median(at["values"]), "unit": at["unit"],
                    "n": len(at["values"]), "studies": at["studies"], "per_study": at["per_study"],
                    "other_units": at["other_units"], "method": at["method"],
                    "lag": median(at["lags"]) if at["lags"] else None, "lag_n": len(at["lags"]),
                    "lag_method": at["lag_method"] if at["lags"] else "",
                    "capacity": median(chosen["values"]) if chosen else None,
                    "capacity_unit": chosen["unit"] if chosen else "",
                    "capacity_n": len(chosen["values"]) if chosen else 0,
                    # how far the curves behind this plateau had fallen from their peak, merged the same
                    # way as the plateau itself: 1 is a curve that ended at its peak (Karoline, 2026-10-07)
                    "capacity_fall": median(chosen["falls"]) if chosen and chosen["falls"] else None,
                    "capacity_per_study": dict(chosen["per_study"]) if chosen else {},
                    "other_capacity_units": list(chosen["other_units"]) if chosen else [],
                    "capacity_left_out": left_out,
                    # one medium, never pooled (Karoline, 2026-10-07): the label of the medium the
                    # plateau was measured in, and what else this organism has a plateau in
                    "capacity_medium": chosen["label"] if chosen else "",
                    # every spelling the plateaus behind it were recorded under: more than one means the
                    # alias table merged two names that disagree, which is said rather than assumed
                    "capacity_medium_spellings": list(chosen["labels"]) if chosen else [],
                    "capacity_media": [chosen["label"]] if chosen else [],
                    "capacity_other_media": [other["label"] for _key, other in order[1:]]}
    return out


_QUOTED = re.compile(r'["\u201c\u201d\']([^"\u201c\u201d\']+)["\u201c\u201d\']')


def _quoted(text: str) -> set:
    """The names a description quotes, as 'controls of the "bhri" experiment' quotes bhri."""
    return {q.strip().casefold() for q in _QUOTED.findall(text or "")}


def _qualifier(name: str) -> str:
    """The words of an experiment name before its last one, where studies put what sets a line apart:
    "Evolved AtCt" -> "evolved", "Ancestral At" -> "ancestral", "At" or "CtOa" -> "" (SMGDB00000013)."""
    return " ".join((name or "").casefold().split()[:-1])


# the word a description uses for the kind of culture; what precedes it names the organisms
_CULTURE_WORD = re.compile(r"\b(?:mono|co|bi)-?cultures?\b|\bcocultures?\b", re.I)


def _setting(description: str) -> str:
    """What a description says about how a culture was grown, with the organisms and the kind of culture
    taken out: the text after its culture word ("At monoculture grown on a minimal medium with 0.1% linoleic
    acid" -> "grown on a minimal medium with 0.1% linoleic acid"), or "" when it has none."""
    m = _CULTURE_WORD.search(description or "")
    return " ".join(description[m.end():].casefold().split()) if m else ""


def _choose_monocultures(groups: dict, exp: dict):
    """(the monoculture set a co-culture is compared with, how it was chosen), or (None, why) when that is
    not known. How: "only" (the one set there is), "named" or "qualifier".

    One set under the co-culture's recorded conditions: that one. Several, told apart only by their
    descriptions: the one whose description names the co-culture experiment, as study 7's controls do
    ('controls of the "bhri" experiment'); failing that, the one whose name carries the same qualifier as the
    co-culture's ("Evolved AtCt" with "Evolved At", "CtOa" with the plain "Ct", as in study 13); failing
    that, the one whose description words the growth the same way once the organisms and the kind of culture
    are taken out (`_setting`: study 14's "At+Ct co-culture grown on a minimal medium with 0.1% linoleic
    acid" with "At monoculture grown on a minimal medium with 0.1% linoleic acid"). Otherwise none is
    guessed (Karoline, 2026-09-27: "yes to 1-3", then "yes" to the qualifier rule; 2026-09-28: "Match
    identical wording").
    """
    if len(groups) == 1:
        return next(iter(groups.values())), "only"
    name = (exp.get("name") or "").strip().casefold()
    named = [g for g in groups.values() if any(name in _quoted(d) for d in g[3])]
    if len(named) == 1:
        return named[0], "named"
    qualifier = _qualifier(exp.get("name", ""))
    same = [g for g in groups.values() if {_qualifier(n) for n in g[4]} == {qualifier}]
    if not named and len(same) == 1:
        return same[0], "qualifier"
    setting = _setting(exp.get("description", ""))
    worded = [g for g in groups.values() if setting and any(_setting(d) == setting for d in g[3])]
    if not named and len(worded) == 1:
        return worded[0], "wording"
    labels = "; ".join(sorted({g[3][0][:70] for g in groups.values()}))
    return None, (f"{len(groups)} monoculture sets under this experiment's recorded conditions, told apart only by "
                  f"their descriptions ({labels}); none names this co-culture, so which one matches it is not "
                  "known and none is guessed")


def why_no_monoculture(index, node_id: str, exp: dict, base: str) -> str:
    """Why this experiment has no monoculture set, naming a medium that differs only in what was added.

    "No monoculture under this experiment's recorded conditions" is true and unhelpful when the
    monoculture is there in the unaltered medium: on SMGDB00000004 the co-cultures are recorded in mMCB
    with and without initial acetate while the monocultures are recorded in plain mMCB, so the strict
    rule refuses the comparison. The reader deserves to know that is what happened rather than that the
    data is missing (Karoline, 2026-10-07: "the strict medium matching ... should be applied everywhere
    where medium matching is done").
    """
    from .media import differing_alterations_of_keys

    cond, key = condition_key(exp)
    for other in sorted({other for (nid, other_cond, other) in index
                         if nid == node_id and other_cond == cond and other != key}):
        differ = differing_alterations_of_keys(key, other)
        if differ is None:
            continue
        mine, theirs = differ
        return (f"{base}; one was measured in the same base medium with {theirs or 'nothing added'} "
                f"where this experiment has {mine or 'nothing added'}, and an added or removed compound "
                "makes another environment, so the two are not compared. Name that experiment in the "
                "second box to read it on its own")
    return base


def _exp_id(exp: dict) -> str:
    return str(exp.get("id", exp.get("name", "")))


def _renamed(replicates, species: str):
    """The same replicates with their single curve named `species`.

    Monoculture and co-culture records are matched by node id (`strain_identities`), and one strain can
    carry different names in different records (taxon 411483 appears under two species names), so the name
    from the co-culture record is used for both. Only strains identified by name can pool genuinely
    different strains; such an edge is flagged `strains_pooled`.
    """
    out = []
    for replicate in replicates:
        curve = replicate.curves[0]
        if curve.species == species:
            out.append(replicate)
            continue
        renamed = GrowthCurve(species, curve.times, curve.values, curve.time_unit, curve.abundance_unit)
        notes = {species: replicate.notes[curve.species]} if curve.species in replicate.notes else {}
        out.append(Replicate([renamed], replicate.name, notes))
    return out


def classify(mean, outcome: str) -> str:
    """The direction of a comparison: facilitation or inhibition.

    `obligate` (the target grows only with the source present) is the extreme of facilitation and
    `abolished` (the target grows only without it) the extreme of inhibition; neither has a log2 ratio.
    Otherwise the sign of the mean decides. A mean of exactly zero has no direction and is `neutral`, and
    is always absent (see `absence`). Whether the comparison counts as an interaction is `absence`'s
    business, not this function's.
    """
    if outcome == OBLIGATE:
        return "facilitation"
    if outcome == ABOLISHED:
        return "inhibition"
    if not mean:
        return "neutral"
    return "facilitation" if mean > 0 else "inhibition"


def effect_over_sd(mean, sd):
    """|log2 mean| / sd: the effect relative to its spread, the quantity the absence threshold k cuts.

    None when there is no log ratio (obligate, abolished) or no spread to divide by (a single replicate,
    or replicates that agree exactly).
    """
    if mean is None or sd is None or sd == 0:
        return None
    return abs(mean) / sd


def absence(mean, sd, outcome: str, k: float = ABSENCE_THRESHOLD):
    """`present` or `absent` under the absence threshold k (Karoline, option B on #54), or None.

    A comparison is absent when |log2 mean| < k * sd: its effect is smaller than k standard deviations
    of its own spread. k = 1 is the mean plus or minus sd rule; k = 0 marks nothing absent (except a mean
    of exactly zero), so everything can be exported and the cut tuned later on `effect_over_sd`. Obligate
    and abolished comparisons are present. With no spread estimate (a single replicate) the status is
    None: undetermined; such an edge is flagged single_replicate and shown. With zero spread and a
    non-zero mean the comparison is present.
    """
    if outcome in (OBLIGATE, ABOLISHED):
        return PRESENT
    if sd is None:
        return None          # checked before the zero mean: with no spread nothing can be decided
    if not mean:
        return ABSENT
    return ABSENT if abs(mean) < k * sd else PRESENT


def absolute_values(c: dict) -> tuple:
    """(with, without): the metric itself in each set, not its log2 ratio (#123).

    The comparison is a difference of means of log2 values, so 2 to that mean is the geometric mean of
    the metric in that set, and the ratio of the two is exactly the arc's strength. A set that did not
    grow has no log2 values and its value is 0, which is what the outcomes obligate and abolished record:
    `A_ij = (r_with - r_without) / x_j_star` is then a measurement where the log2 ratio does not exist.
    """
    with_log2, without_log2 = c.get("with_log2") or [], c.get("without_log2") or []
    outcome = c.get("outcome")
    first = 2 ** mean(with_log2) if with_log2 else (0.0 if outcome == ABOLISHED else None)
    second = 2 ** mean(without_log2) if without_log2 else (0.0 if outcome == OBLIGATE else None)
    return first, second


def bounded_strength(c: dict) -> tuple:
    """(the log2 bound a censored comparison's cell holds, the rule behind it), or (None, "").

    A censored comparison has no ratio, because one side did not grow. The no-growth rule that said so
    bounds that side's metric (`interaction.no_growth_bound`), so the cell holds a measured bound rather
    than a stated extreme (#129): the growing side's own geometric mean over that bound, with the sign of
    the outcome. An obligate pair gives a lower bound (at least this much facilitation) and an abolished
    one an upper bound (at most this much inhibition).
    """
    bound = c.get("bound") or {}
    if not bound.get("value"):
        return None, ""
    growing = c["with_log2"] if c["outcome"] == OBLIGATE else c["without_log2"]
    if not growing:
        return None, ""
    size = mean(growing) - math.log2(bound["value"])
    if size <= 0:
        # the bound is weaker than the measurement it is compared with, so it does not put the effect
        # away from zero. That happens with an area, where a culture that did not grow still carries the
        # area of its own inoculum; `max` and a growth rate are bounded tightly (#129).
        return None, (f"{bound['rule']}, which does not bound this effect away from zero: the arc carries "
                      "no bound and its cell is NA, and a comparison on the maximum or on the growth rate "
                      "bounds it tightly")
    return (round(size, 4) if c["outcome"] == OBLIGATE else round(-size, 4)), bound["rule"]


def _record(source: str, target: str, c: dict, method: str, quality: list, cautions: list, notes: list,
            cond: str, evidence: str, community, experiments, study_id, study_meta, identities=None,
            mode: str = BATCH, medium: str = "", partner: dict = None, capacity: dict = None) -> dict:
    """One edge record from a comparison `c` (mean, sd, se, n_with, n_without, outcome, with_log2,
    without_log2), the shape `records_to_network` reads.

    `partner`, when given, is what `partner_abundances` found for the source beside the target: the
    abundance x_j* a gLV coefficient divides by (#118). It is an extra number about the same comparison,
    so a comparison whose partner was not measured keeps its arc, with the reason beside it.
    """
    mean, sd = c["mean"], c["sd"]
    _absolute = absolute_values(c)
    _bound = bounded_strength(c)
    test = welch(c["with_log2"], c["without_log2"])
    ratio = effect_over_sd(mean, sd)
    identities = identities or {}
    src, tgt = _identity(identities, source), _identity(identities, target)
    return {
        "source": src["id"], "source_name": source,
        "target": tgt["id"], "target_name": target,
        "source_taxon_id": src["taxon_id"], "source_species": src["species"], "source_identity": src["identity"],
        "target_taxon_id": tgt["taxon_id"], "target_species": tgt["species"], "target_identity": tgt["identity"],
        "effect": classify(mean, c["outcome"]),
        "strength": None if mean is None else round(mean, 4),
        "weight": None if mean is None else round(abs(mean), 4),
        "effect_over_sd": None if ratio is None else round(ratio, 4),
        "status": None,                 # present or absent, set at output from the threshold k
        "q_value": None,                # p_value corrected for multiple testing, set at output
        "significance": None,           # -log10(q_value), set at output
        "p_value": None if test is None else test["p"],
        "sd": None if sd is None else round(sd, 4),
        "se": None if c["se"] is None else round(c["se"], 4),
        "n_with": c["n_with"], "n_without": c["n_without"],
        "outcome": c["outcome"], "metric": method,
        "quality": quality, "cautions": cautions, "notes": notes, "cultivation_mode": mode,
        "medium": medium,
        "partner_abundance": (partner or {}).get("value"),
        "partner_abundance_unit": (partner or {}).get("unit", ""),
        "partner_abundance_n": (partner or {}).get("n"),
        "partner_abundance_left_out": list((partner or {}).get("skipped", ())),
        # the two absolute numbers the strength is the ratio of, and the target's own plateau in the
        # co-culture, which together fit a row that a ratio cannot (#123)
        "metric_with": _absolute[0], "metric_without": _absolute[1],
        "strength_bound": _bound[0], "bound_rule": _bound[1],
        "target_capacity": (capacity or {}).get("value"),
        "target_capacity_unit": (capacity or {}).get("unit", ""),
        "target_capacity_n": (capacity or {}).get("n"),
        "condition": cond, "method": REPLICATE_METHOD.format(metric=method),
        "evidence": evidence, "community": sorted(_identity(identities, m)["id"] for m in community),
        "experiments": list(experiments),
        "study_id": study_id, **study_meta,
    }


def _spike_notes(flagged, target: str) -> list:
    return [f"{f['role']} replicate {f['replicate']} left out: implausible spike, maximum "
            f"{f['ratio']:.0f} times its neighbors at {', '.join(f'{t:g}' for t in f['times'])}"
            for f in flagged if f["species"] == target]


def _no_growth_kwargs(no_growth) -> dict:
    alpha, factor = no_growth or (None, None)
    return {"no_growth_alpha": alpha, "no_growth_factor": factor}


def _pairwise(client, exp, monos, method, spike_factor, study_id, study_meta, records, skipped,
              identities=None, no_growth=None, variants=1,
              capacity_max_fall: float = CAPACITY_MAX_FALL) -> None:
    """The edges of one two-member co-culture against the monocultures of its members."""
    a, b = _members(exp)
    cond = exp.get("name", "")
    co_reps, skips = replicates_for_experiment(client, exp, spike_factor)
    skipped += skips
    sets, pooled, origin, matched = {}, {}, {}, set()
    for species in (a, b):
        key = (_identity(identities or {}, species)["id"], *condition_key(exp))
        groups = monos.get(key, {})
        chosen, how = _choose_monocultures(groups, exp) if groups else (None, "")
        why = "" if chosen else how
        if how in ("named", "qualifier", "wording"):
            matched.add(species)          # the match with this co-culture is recorded, by name
        found, strains, ids = (chosen[0], chosen[1], chosen[2]) if chosen else ([], set(), [])
        if not groups:
            skipped.append((f"{a} with {b} [{cond}]",
                            why_no_monoculture(
                                monos, key[0], exp,
                                f"no monoculture replicates for {species} under this experiment's "
                                "conditions")))
        elif not chosen:
            skipped.append((f"{a} with {b} [{cond}]", f"{species}: {why}"))
        sets[species] = _renamed(found, species)
        pooled[species] = len(strains) > 1 and not key[0].startswith("ncbi:")
        origin[species] = ids
    if not (sets[a] and sets[b] and co_reps):
        if not co_reps:
            skipped.append((f"{a} with {b} [{cond}]", "no usable co-culture replicates"))
        return
    try:
        result = interaction_strength(sets[a], sets[b], co_reps, a, b, method=method, spike_factor=spike_factor,
                                      **_no_growth_kwargs(no_growth))
    except ValueError as e:
        skipped.append((f"{a} with {b} [{cond}]", str(e)))
        return
    skipped += result["skipped"]
    for key, (source, target) in (("species_a", (b, a)), ("species_b", (a, b))):
        side = result[key]
        if side["outcome"] == NO_GROWTH:
            skipped.append((f"{source} -> {target} [{cond}]", f"no growth ({method}) in either set"))
            continue
        if side["outcome"] == UNUSABLE:
            skipped.append((f"{source} -> {target} [{cond}]",
                            side.get("reason") or "every replicate of a set was left out (see above)"))
            continue
        c = {"mean": side["mean"], "sd": side["sd"], "se": side["se"], "outcome": side["outcome"],
             "n_with": side["n_co"], "n_without": side["n_mono"],
             "with_log2": side["co_log2"], "without_log2": side["mono_log2"],
             "bound": side.get("bound")}
        quality, cautions = _replicate_flags(c["n_with"], c["n_without"])
        cautions += stationary_cautions(side.get("stationary"), method, c["outcome"])
        cautions += zero_start_cautions(side.get("zero_start"), c["outcome"])
        if variants > 1 and not matched:
            # co-cultures of this pair under the same recorded conditions differ only in their description
            # (study 4's +Ac and -Ac), and nothing recorded says which one the monocultures match. When a
            # member's set was matched by name (study 7's controls, study 13's "Evolved" lines), the names
            # account for the variants, and the pair needs no caution
            cautions.append(CONDITIONS_UNVERIFIED)
        if pooled[target]:
            quality.append(STRAINS_POOLED)
        mode = cultivation(exp)
        if mode != BATCH:
            # with a metric the mode suits, the comparison holds and the arc is shown with a caution;
            # otherwise it was asked for with the advanced setting and stays low quality
            (cautions if method in METRICS_FOR_CONTINUOUS_CULTURE else quality).append(
                CONTINUOUS_CULTURE if method in METRICS_FOR_CONTINUOUS_CULTURE else NON_BATCH)
        kind, window = rates.fit_parts(method)
        partner = partner_abundances(co_reps, target, source, kind, window)
        records.append(_record(source, target, c, method, quality, cautions,
                               _spike_notes(result["flagged"], target), cond, "biculture", (a, b),
                               [_exp_id(exp), *origin[target]], study_id, study_meta, identities, mode,
                               media_identity(exp)["label"], partner,
                               target_capacity(co_reps, target, capacity_max_fall)))


def run_group(exp: dict) -> str:
    """What must agree, besides the structured conditions, for experiments to be replicates of each other.

    mGrowthDB does not detail medium components well: in SMGDB00000004 `RI_BH +Ac` and `RI_BH -Ac` (with
    and without initial acetate) have identical conditions, and only the description tells them apart
    (Karoline, on #47). So experiments of one community are pooled only when their descriptions also agree,
    ignoring a trailing run number, which is how duplicate runs are told apart ("All 1", "All 2"). Pooling
    similar but not identical conditions would need a good description of them, and is not done for now.
    """
    text = (exp.get("description") or exp.get("name") or "").strip()
    return re.sub(r"[\s_-]*\d+$", "", text).casefold()


def dropout_designs(exps, skipped) -> list:
    """The drop-out designs among a study's experiments: [(members, full experiments, {removed: experiments})].

    A design is a community of three or more members (the full community) together with experiments under
    the same conditions that each hold it minus exactly one member. Experiments of one community are
    pooled when they are replicates: identical conditions and the same `run_group`. Otherwise they give
    separate arcs, so a full community or a drop-out with several groups takes part in several designs.
    Not every member needs a drop-out (Karoline, on #47). A community of more than two members that is
    neither a full community with a drop-out nor a drop-out of one is reported, with what was missing.
    """
    by_condition = {}
    for exp in exps:
        members = frozenset(_members(exp))
        if len(members) >= 2:
            groups = by_condition.setdefault(condition_key(exp), {}).setdefault(members, {})
            groups.setdefault(run_group(exp), []).append(exp)
    designs, used = [], set()
    for communities in by_condition.values():
        for members, full_groups in communities.items():
            if len(members) < 3:
                continue
            partners = {r: list(communities[members - {r}].values())
                        for r in sorted(members) if members - {r} in communities}
            if not partners:
                continue
            for full in full_groups.values():
                remaining = {r: list(groups) for r, groups in partners.items()}
                while any(remaining.values()):
                    # one group per removed member per design; a member with several groups takes more designs
                    drops = {r: groups.pop(0) for r, groups in remaining.items() if groups}
                    designs.append((members, full, drops))
                used.update(id(e) for e in full)
            used.update(id(e) for groups in partners.values() for group in groups for e in group)
    for exp in exps:
        if len(_members(exp)) > 2 and id(exp) not in used:
            skipped.append((exp.get("name", ""), f"community of {len(_members(exp))} members with no drop-out "
                            "experiment (the community without one member) under the same conditions, and "
                            "not itself a drop-out of one; no arcs derived"))
    return designs


def _community_replicates(client, exps, members, role, spike_factor, skipped) -> tuple:
    """(replicates holding exactly `members`, what else they measured) for pooled experiments.

    A curve for a strain outside the community (in mGrowthDB the removed member is still measured) is
    taken off the replicate. When it shows a positive signal it is returned in `detected`, as
    (replicate, strain, maximum), since the drop-out may not be clean (Karoline, on #47). A replicate
    missing a member's curve cannot be compared and is left out, with a reason.
    """
    replicates, detected = [], []
    for exp in exps:
        reps, skips = replicates_for_experiment(client, exp, spike_factor)
        skipped += skips
        for rep in reps:
            outside = [c for c in rep.curves if c.species not in members]
            detected += [(rep.name, c.species, max(c.values)) for c in outside if max(c.values) > 0]
            missing = sorted(set(members) - set(rep.species))
            if missing:
                skipped.append((f"{exp.get('name', '')}: {rep.name}",
                                f"{role} replicate has no usable curve for {', '.join(missing)}; left out"))
                continue
            kept = [c for c in rep.curves if c.species in members]
            replicates.append(Replicate(kept, rep.name, {k: v for k, v in rep.notes.items() if k in members}))
    return replicates, detected


def _detected_note(role: str, detected) -> str:
    found = ", ".join(f"{strain} in replicate {name} (maximum {peak:g})" for name, strain, peak in detected)
    return f"a strain outside the {role} was measured with a positive signal: {found}"


def _common_start(full, dropouts, skipped) -> tuple:
    """(full, dropouts) unchanged, with every curve that starts after the design's usual start reported.

    Curves are compared only from a common start time (Karoline's specification, #1). A member whose first
    measurement is missing leaves its replicate out of that member's own arcs only
    (`interaction.dropout_interaction_strengths`); the replicate still serves every other member (Karoline,
    2026-09-28: "Only for its own arcs"). The usual start is the most common first time point in the design.
    """
    reps = [*full, *(r for group in dropouts.values() for r in group)]
    firsts = Counter(c.times[0] for r in reps for c in r.curves)
    if len(firsts) < 2:
        return full, dropouts
    start = firsts.most_common(1)[0][0]

    def report(role, replicates):
        for rep in replicates:
            late = [c for c in rep.curves if not math.isclose(c.times[0], start, abs_tol=1e-9)]
            if late:
                skipped.append((f"{role} replicate {rep.name}", "curve(s) starting after the common start "
                                f"{start:g}: " + ", ".join(f"{c.species} at {c.times[0]:g}" for c in late)
                                + "; this replicate is left out of those species' own arcs only, since curves "
                                "are compared only from a common start"))

    for r, group in dropouts.items():
        report(f"community without {r}", group)
    report("full community", full)
    return full, dropouts


def _variants(exps) -> dict:
    """(members, recorded conditions) -> how many description variants (`run_group`) of that community a
    study holds: more than one means experiments that differ only in their description."""
    groups = {}
    for exp in exps:
        groups.setdefault((frozenset(_members(exp)), *condition_key(exp)), set()).add(run_group(exp))
    return {key: len(g) for key, g in groups.items()}


def _dropout(client, design, method, spike_factor, study_id, study_meta, records, skipped,
             identities=None, no_growth=None, variants=None) -> None:
    """The arcs of one drop-out design, from `grownet.interaction.dropout_interaction_strengths`."""
    members, full_exps, drops = design
    label = f"drop-out design of {len(members)} members ({', '.join(e.get('name', '') for e in full_exps)})"
    full, full_detected = _community_replicates(client, full_exps, members, "full community",
                                                spike_factor, skipped)
    dropouts, detected = {}, {}
    for removed, exps in drops.items():
        reps, found = _community_replicates(client, exps, members - {removed}, f"community without {removed}",
                                            spike_factor, skipped)
        if reps:
            dropouts[removed], detected[removed] = reps, found
        else:
            skipped.append((f"{label}, without {removed}", "no usable replicates"))
    full, dropouts = _common_start(full, dropouts, skipped)
    if not full or not dropouts:
        skipped.append((label, "no usable full community replicates" if not full else "no usable drop-out"))
        return
    try:
        result = dropout_interaction_strengths(full, dropouts, method=method, spike_factor=spike_factor,
                                               **_no_growth_kwargs(no_growth))
    except ValueError as e:
        skipped.append((label, str(e)))
        return
    skipped += result["skipped"]
    for arc in result["arcs"]:
        removed, target = arc["source"], arc["target"]
        quality, cautions = _replicate_flags(arc["n_with"], arc["n_without"])
        cautions += stationary_cautions(arc.get("stationary"), method, arc["outcome"])
        cautions += zero_start_cautions(arc.get("zero_start"), arc["outcome"])
        notes = _spike_notes([f for f in result["flagged"] if f["role"] in ("full community",
                              f"community without {removed}")], target)
        if full_detected or detected[removed]:
            quality.append(REMOVED_MEMBER_DETECTED)
            if full_detected:
                notes.append(_detected_note("full community", full_detected))
            if detected[removed]:
                notes.append(_detected_note(f"community without {removed}", detected[removed]))
        mode = cultivation(full_exps[0])
        if mode != BATCH:
            (cautions if method in METRICS_FOR_CONTINUOUS_CULTURE else quality).append(
                CONTINUOUS_CULTURE if method in METRICS_FOR_CONTINUOUS_CULTURE else NON_BATCH)
        # the full community or this drop-out comes in variants told apart only by their descriptions, so
        # which drop-out goes with which full community is not recorded (Karoline, 2026-09-27)
        # the same key `_variants` builds, which carries the medium by the strict rule: looking up a
        # 2-tuple against a 3-tuple missed every time and silently turned the caution off (2026-10-07)
        key = condition_key(full_exps[0])
        if (variants or {}).get((frozenset(members), *key), 1) > 1 or \
                (variants or {}).get((frozenset(members - {removed}), *key), 1) > 1:
            cautions.append(CONDITIONS_UNVERIFIED)
        cond = ", ".join(e.get("name", "") for e in drops[removed])
        experiments = [_exp_id(e) for e in [*full_exps, *drops[removed]]]
        records.append(_record(removed, target, arc, method, quality, cautions, notes, cond, arc["evidence"],
                               members, experiments, study_id, study_meta, identities, mode,
                               media_identity(full_exps[0])["label"]))


def _wanted(exps, keep) -> set:
    """The member names `keep(name, taxon id)` accepts, over a study's experiments."""
    return {s.get("name") for exp in exps for s in exp.get("communityStrains", [])
            if s.get("name") and keep(s.get("name"), s.get("NCBId"))}


def relevant_experiments(exps, keep, dropout: bool = True) -> list:
    """The experiments a derivation limited to `keep` reads: monocultures of kept strains, two-member
    co-cultures of two kept strains, and every experiment of a drop-out design holding at least two kept
    members. A design is kept whole, since its common start is taken over all its drop-outs, so leaving
    one out could change which replicates are compared. With `keep` None: every experiment that can take
    part in a comparison, so every one with two or more members, and the monocultures of strains that
    appear in a two-member co-culture of the study, by the strain identity `_mono_index` keys them with (so
    renamed and pooled strains match as there); a monoculture no co-culture is compared with is not read
    (audit of 2026-09-28: All read 2195 replicates, many of studies with only monocultures)."""
    if keep is None:
        identities = strain_identities(exps, [])
        partners = {_identity(identities, m)["id"] for exp in exps if len(_members(exp)) == 2
                    for m in _members(exp)}
        return [exp for exp in exps if len(_members(exp)) != 1
                or _identity(identities, _members(exp)[0])["id"] in partners]
    wanted = _wanted(exps, keep)
    ids = set()
    for exp in exps:
        members = set(_members(exp))
        if (len(members) == 1 and members <= wanted) or (len(members) == 2 and members <= wanted):
            ids.add(id(exp))
    if dropout:
        for members, full, drops in dropout_designs(exps, []):
            if len(members & wanted) >= 2:
                ids.update(id(e) for e in [*full, *(e for group in drops.values() for e in group)])
    return [exp for exp in exps if id(exp) in ids]


def interactions_from_replicates(client, study: dict, exps: list, study_id: str = None,
                                 method: str = "auc", spike_factor: float = SPIKE_FACTOR,
                                 dropout: bool = True, include_non_batch: bool = False,
                                 no_growth_alpha: float = None, no_growth_factor: float = None, keep=None,
                                 selection=None, capacity_max_fall: float = CAPACITY_MAX_FALL):
    """The specified comparison, run on a study: (records, skipped).

    Two designs give edges. Each two-member co-culture is compared with the monoculture replicates of
    its members under the same conditions (`grownet.interaction.interaction_strength`, evidence
    `biculture`). Each drop-out design (`dropout_designs`) compares the full community with the community
    without one member (`grownet.interaction.dropout_interaction_strengths`, evidence `dropout`), unless
    `dropout` is False. Drop-out arcs are included by default, labeled by evidence (Craig and Karoline,
    register item 2).

    Every edge carries its mean, sd, se and replicate counts, an effect from `classify`, `quality` flags
    that make it low quality, `cautions` that do not (two replicates on a side), `notes` (an excluded
    outlier), and the ids of the `experiments` it compares, so edges that share replicates can be told
    apart. One edge per experiment; merging edges is a separate decision. Filtering low-quality edges
    happens at output (`select_edges`), so nothing computed is lost. Only batch experiments are derived
    unless `include_non_batch` is set; every edge records its `cultivation_mode`, and a non-batch edge is
    flagged `non_batch` (Karoline, #42). `no_growth_alpha` and `no_growth_factor` set the no-growth rule
    (`grownet.interaction.grew`; None means the defaults there). `selection` is what the page's second box
    asks for, media, experiments or studies (`grownet.selection`, #113); None looks at everything.
    """
    no_growth = (no_growth_alpha, no_growth_factor)
    study_id = study_id or study.get("id")
    study_meta = {
        "study_citation": study.get("name", study_id),
        "study_url": study.get("url", ""),
        "study_license": "",
    }
    records, skipped = [], []
    if exps and all(len(_members(exp)) < 2 for exp in exps):
        # SMGDB00000015 holds 91 monocultures and nothing else: say so first, not only per replicate
        skipped.append((f"study {study_id}", f"only monocultures ({len(exps)} experiments of one strain each): "
                        "an interaction needs a co-culture or a community to compare with"))
    exps = _batch_only(exps, include_non_batch, skipped, method)
    # the second box: media, experiments or studies (#113). Identities and variants are still read from
    # every experiment, so matching a strain to its monocultures is unchanged by what is selected.
    identities = strain_identities(exps, skipped)
    exps = select_experiments(exps, selection, skipped)
    # with `keep`, only what can give an interaction between kept strains is read (a search with "only the
    # species entered"); identities and variants still come from every experiment, so matching is unchanged
    relevant = {id(e) for e in relevant_experiments(exps, keep, dropout)}
    wanted = _wanted(exps, keep) if keep is not None else None
    monos = _mono_index(client, [e for e in exps if id(e) in relevant], skipped, spike_factor, identities)
    variants = _variants(exps)
    for exp in exps:
        if len(_members(exp)) == 2:
            if id(exp) not in relevant:
                if wanted is not None and set(_members(exp)) & wanted:
                    skipped.append((" with ".join(_members(exp)) + f" [{exp.get('name', '')}]",
                                    "not derived: the partner is not among the species entered"))
                continue
            _pairwise(client, exp, monos, method, spike_factor, study_id, study_meta, records, skipped,
                      identities, no_growth,
                      variants[(frozenset(_members(exp)), *condition_key(exp))],
                      capacity_max_fall)
    if dropout:
        for design in dropout_designs(exps, skipped):
            if wanted is not None and len(design[0] & wanted) < 2:
                continue
            _dropout(client, design, method, spike_factor, study_id, study_meta, records, skipped, identities,
                     no_growth, variants)
    elif any(len(_members(exp)) > 2 for exp in exps):
        skipped.append(("communities of more than two members", "drop-out designs switched off; no arcs derived"))
    return records, skipped


def is_low_quality(record) -> bool:
    return bool(record.get("quality"))


# -log10 of a q-value of exactly zero is infinite, which no file format carries. Welch reports p = 0 when
# neither side varies and the means differ, so the case is real but extreme; it is reported as this cap.
SIGNIFICANCE_CAP = 15.0


def significance_of(q_value) -> float | None:
    """-log10(q): larger is stronger evidence, 0 at q = 1 (Karoline, 2026-10-03)."""
    if q_value is None:
        return None
    if q_value <= 0:
        return SIGNIFICANCE_CAP
    return round(min(SIGNIFICANCE_CAP, -math.log10(q_value)), 4)


def adjust_significance(records, correction: str = "bh") -> int:
    """Fill each record's `q_value` and `significance`, in place.

    `q_value` is the record's p-value corrected for multiple testing, and `significance` is -log10 of it,
    so a larger significance means stronger evidence and a style can map it continuously. `correction` is
    "bh" (Benjamini-Hochberg, the default) or "by" (Benjamini-Yekutieli, valid under any dependence
    between the tests).

    The family is every comparison tested in this derivation, edges, absences and low-quality ones alike,
    since all were tested. Returns the number of tests. Records without a p-value (a single replicate on
    a side) are not tests and keep both fields None.
    """
    tested = [r for r in records if r.get("p_value") is not None]
    adjust = CORRECTIONS[correction][1]
    for record, adjusted in zip(tested, adjust([r["p_value"] for r in tested]), strict=True):
        # significant figures, not decimal places: `round(q, 6)` published an adjusted p below 5e-7 as
        # exactly 0.0, which is the strongest q-value there is and passes any filter, and `significance`
        # then came out as infinity. A strong result should not be rounded into a certainty (#155 item 14)
        record["q_value"] = float(f"{adjusted:.6g}") if adjusted else 0.0
        record["significance"] = significance_of(record["q_value"])
    return len(tested)


# Low-quality flags that leave an edge out of the output by default (Karoline, on #40 and #54). A
# single-replicate edge is shown by default and marked in the Cytoscape style instead (Karoline, on #62):
# it keeps its flag and its undetermined status, since with no spread there is nothing to decide absence on.
HIDDEN_BY_DEFAULT = (STRAINS_POOLED, REMOVED_MEMBER_DETECTED, "non_batch")


def is_hidden_by_default(record) -> bool:
    return any(flag in HIDDEN_BY_DEFAULT for flag in record.get("quality", ()))


def select_edges(records, include_low_quality: bool = False, include_absent: bool = False) -> tuple:
    """(edges, hidden) at output: what every file and the Cytoscape push hold.

    Edges with a flag in HIDDEN_BY_DEFAULT are left out unless asked, and so are edges below the absence
    threshold (Karoline, 2026-10-03: "The arc number reported in Cytoscape is not identical to the arc
    number we see because of hidden arcs"). Leaving the absences out keeps one number: what the page
    shows, what a file holds and what Cytoscape counts are the same. `include_absent` puts them back for a
    reader who wants to move the threshold in Cytoscape on `effect_over_sd` without deriving again, which
    is why they were exported before (her option B on #54). Single-replicate edges stay: they are
    interactions whose spread is unknown, shown and marked. `hidden` counts both kinds.
    """
    edges, hidden = [], {"low_quality": 0, "absent": 0}
    for record in records:
        if is_hidden_by_default(record) and not include_low_quality:
            hidden["low_quality"] += 1
        elif record.get("status") == ABSENT and not include_absent:
            hidden["absent"] += 1
        else:
            edges.append(record)
    return edges, hidden


def _merged(arcs: list) -> dict:
    """One arc for several arcs of one source, target and sign (register item 14, Karoline 2026-09-27).

    The strength is the median of the arcs' log2 means, with their range; obligate and abolished arcs,
    which have no ratio, count toward the arc without entering the median, and an arc made only of them
    keeps that outcome. A median has no sd, se or combined test, so those stay empty rather than invented.
    It lists every study, experiment and condition it rests on, and is drop-out evidence if any of its arcs
    is, since it may then be indirect.
    """
    numeric = [a["strength"] for a in arcs if a.get("strength") is not None]
    strength = round(median(numeric), 4) if numeric else None
    outcomes = {a.get("outcome") for a in arcs}
    outcome = QUANTIFIED if numeric else (outcomes.pop() if len(outcomes) == 1 else arcs[0].get("outcome"))

    def union(key):
        seen = []
        for a in arcs:
            for x in a.get(key) or []:
                if x not in seen:
                    seen.append(x)
        return seen

    studies = []
    for a in arcs:
        st = {"id": a["study_id"], "citation": a.get("study_citation", ""), "license": a.get("study_license", ""),
              "url": a.get("study_url", "")}
        if st["id"] not in {s["id"] for s in studies}:
            studies.append(st)
    conditions = list(dict.fromkeys(a.get("condition", "") for a in arcs))
    return {**arcs[0], "strength": strength, "weight": None if strength is None else round(abs(strength), 4),
            "sd": None, "se": None, "effect_over_sd": None, "p_value": None, "q_value": None,
            "significance": None,
            "n_with": None, "n_without": None, "outcome": outcome,
            "status": PRESENT if any(a.get("status") == PRESENT for a in arcs) else None,
            "quality": union("quality"), "cautions": union("cautions"), "notes": union("notes"),
            "experiments": union("experiments"), "community": sorted(set(union("community"))),
            "evidence": (DROPOUT_EVIDENCE if any(a.get("evidence") == DROPOUT_EVIDENCE for a in arcs)
                         else arcs[0].get("evidence")),
            "condition": "; ".join(c for c in conditions if c),
            "cultivation_mode": "; ".join(dict.fromkeys(a.get("cultivation_mode", "") for a in arcs)),
            "medium": "; ".join(dict.fromkeys(a.get("medium", "") for a in arcs if a.get("medium"))),
            **_merged_partner(arcs),
            "method": f"{arcs[0].get('method', '')}; merged: the median of {len(arcs)} arcs",
            "merged_arcs": len(arcs),
            "strength_range": [min(numeric), max(numeric)] if numeric else [],
            "studies": studies, "study_id": studies[0]["id"]}


def _merged_partner(arcs: list) -> dict:
    """The partner abundance of a merged arc: the median over the arcs that carry one, and only over one
    abundance unit, since abundances in different units are not one set (#118)."""
    units = {a.get("partner_abundance_unit") for a in arcs
             if a.get("partner_abundance") is not None and a.get("partner_abundance_unit")}
    unit = units.pop() if len(units) == 1 else ""
    values = [a["partner_abundance"] for a in arcs
              if a.get("partner_abundance") is not None and a.get("partner_abundance_unit") == unit] if unit else []
    left_out = [x for a in arcs for x in a.get("partner_abundance_left_out") or []]
    if not unit:
        left_out = left_out + [(f"{arcs[0].get('source_name', '')} beside "
                                f"{arcs[0].get('target_name', '')}", "the merged arcs measure the partner "
                                "in different abundance units; left out rather than converted")
                               ] if len(units) > 1 else left_out
    return {"partner_abundance": median(values) if values else None,
            "partner_abundance_unit": unit if values else "",
            "partner_abundance_n": sum(a.get("partner_abundance_n") or 0 for a in arcs) if values else 0,
            "partner_abundance_left_out": left_out}


def merge_parallel(edges: list, merge: bool = True, min_studies: int = 1) -> tuple:
    """(edges, meta) with the parallel arcs of each source and target merged (register item 14).

    Karoline's choices (2026-09-27): arcs with the same source and target merge, across conditions, studies
    and evidence; the strength is their median; arcs whose signs disagree are not merged, only arcs that
    agree; merging is an advanced setting, off by default. Absent arcs (no interaction found) have no
    direction and stay separate. `min_studies` then keeps arcs resting on at least that many studies.
    """
    info = {"merge_arcs": merge, "merged": 0, "left_apart_for_disagreeing_signs": 0, "min_studies": min_studies,
            "below_min_studies": 0, "rule": "same source and target; median of the log2 means; signs must agree"}
    if not merge and min_studies <= 1:
        return edges, info                    # off, as by default: every arc exactly as derived
    groups = {}
    for e in edges:
        groups.setdefault((e["source"], e["target"]), []).append(e)
    out, merged, conflicts = [], 0, 0
    for arcs in groups.values():
        signed = [a for a in arcs if a.get("status") != ABSENT and a.get("effect") in ("facilitation", "inhibition")]
        rest = [a for a in arcs if a not in signed]
        signs = {a["effect"] for a in signed}
        if merge and len(signed) >= 2 and len(signs) == 1:
            out.append(_merged(signed))
            merged += 1
        else:
            conflicts += merge and len(signs) > 1
            out.extend(signed)
        out.extend(rest)
    kept = [e for e in out if len(e.get("studies") or [e]) >= min_studies]
    return kept, {**info, "merged": merged, "left_apart_for_disagreeing_signs": conflicts,
                  "below_min_studies": len(out) - len(kept)}


SUPPORT_LEVELS = ("species", "strain")


def _organism(arc: dict, side: str) -> str:
    return arc.get(f"{side}_name") or arc.get(f"{side}_species") or arc[side]


def _pair(arc: dict, level: str, name_of: dict) -> str:
    """The pair of organisms an arc joins, at the level the search asked about: its species, or its strains.
    Each node is named once (`name_of`, the first name seen for its id), so a strain that two studies name
    differently (411483 as F. prausnitzii and as F. duncaniae A2-165) counts once (code review of
    2026-09-28)."""
    names = [name_of.get(arc[side], _organism(arc, side)) for side in ("source", "target")]
    if level == "strain":
        return " -> ".join(names)
    return " -> ".join(genus_species(n).capitalize() for n in names)


def merge_genus(edges: list, merge: bool = False, level: str = "species") -> tuple:
    """(edges, meta) with every node merged into its genus and the arcs between two genera merged by sign.

    Karoline's choices (2026-09-28): an advanced setting, off by default; nodes merge at the genus level
    and arcs merge by sign, so two genera can be joined by a facilitation arc and an inhibition arc;
    `supporting_pairs` counts the distinct pairs behind a genus arc, as species pairs or, when only strains
    (taxon ids) were entered, strain pairs; interactions within one genus stay, as an arc from the genus to
    itself; absent arcs are recorded as before, one per genus pair, and hidden like any absent arc. It runs
    after `merge_parallel`, so with both settings on a pair measured in several studies counts once.
    The genus is the first word of the name mGrowthDB gives (`model.genus_name`), not NCBI's lineage.
    """
    info = {"merge_genus": merge, "level": level, "genus_arcs": 0,
            "rule": "nodes by genus; arcs by source genus, target genus and sign; median of the log2 means"}
    if not merge:
        return edges, info
    groups, name_of = {}, {}
    for e in edges:
        for side in ("source", "target"):
            name_of.setdefault(e[side], _organism(e, side))
    for e in edges:
        kind = ABSENT if e.get("status") == ABSENT else e.get("effect")
        key = (genus_name(_organism(e, "source")), genus_name(_organism(e, "target")), kind)
        groups.setdefault(key, []).append(e)
    out = []
    for (source, target, kind), arcs in groups.items():
        arc = dict(arcs[0]) if len(arcs) == 1 else _merged(arcs)
        if kind == ABSENT:
            arc["status"] = ABSENT                       # every arc behind it found no interaction
        pairs = sorted({_pair(a, level, name_of) for a in arcs})
        arc.update({side: genus for side, genus in (("source", source), ("target", target))})
        for side, genus in (("source", source), ("target", target)):
            arc.update({f"{side}_name": genus, f"{side}_taxon_id": "", f"{side}_species": "",
                        f"{side}_identity": "genus"})
        arc.update(supporting_pairs=len(pairs), merged_pairs=pairs,
                   method=f"{arc.get('method', '')}; merged to genus: {len(arcs)} arcs over {len(pairs)} "
                          f"{level} pairs")
        out.append(arc)
    return out, {**info, "genus_arcs": len(out), "from_arcs": len(edges)}


# How to read a derived network, on the page and in every file written from it, so a file that travels
# without the page (a download, the daily All network) states its own terms (Craig's agent, #96). It is
# part of a derivation's meta, not of the format: `derive --fixture` only formats given records.
PROVISIONAL = ("Each interaction compares a species' growth with and without its partner across replicates "
               "(mean log2 difference). An interaction is reported when |mean| is at least k standard "
               "deviations (the absence threshold, default 1: the mean plus or minus its standard deviation "
               "stays on one side of zero). Welch's t-test, corrected for multiple testing, is shown "
               "as supporting evidence and does not decide; with few replicates, more experiments may change "
               "any of these results (see docs/METHOD_NOTES.md in the grownet repository).")


# Appended to the caution when the filter is on, since the caution then no longer holds: the adjusted p-value
# decides too
FILTER_NOTE = (" With the q-value filter on (the q-value is the p-value adjusted for multiple testing), an "
               "interaction is also left out when its q-value is above {q:g}; arcs without a p-value are "
               "kept and marked untested.")


def filter_significance(records, max_adjusted_p: float | None = None) -> tuple:
    """(records, info): the advanced filter on the adjusted p-value, off by default (register item 31).

    Karoline (2026-09-30): "add an advanced option, by default off, that allows filtering arcs on adjusted
    p-value". With it on, an interaction (status present) whose adjusted p-value is above `max_adjusted_p`
    is left out and counted, like a low-quality edge ("Left out, counted"); absent and undetermined arcs are
    not interactions and stay as they are. An arc without a p-value is kept with the caution `untested`.
    It runs after the adjustment and before merging, so a merged arc rests only on arcs that passed.
    """
    info = {"max_adjusted_p": max_adjusted_p, "left_out": 0, "untested": 0}
    if max_adjusted_p is None:
        return records, info
    kept = []
    for record in records:
        if record.get("p_value") is None:
            record["cautions"] = [*record.get("cautions", []), UNTESTED]
            info["untested"] += 1
        # adjust_significance gives every record with a p-value its q-value, so `q_value` is None here
        # only if the adjustment was skipped: a guard, not a case (Craig's agent, reviewing #106)
        elif record.get("status") == PRESENT and (record.get("q_value") is None
                                                  or record["q_value"] > max_adjusted_p):
            info["left_out"] += 1
            continue
        kept.append(record)
    return kept, info


def output_meta(records, include_low_quality: bool = False, correction: str = "bh",
                absence_threshold: float = ABSENCE_THRESHOLD, no_growth_alpha: float = None,
                no_growth_factor: float = None, merge_arcs: bool = False, min_studies: int = 1,
                merge_genera: bool = False, support_level: str = "species",
                max_adjusted_p: float | None = None, include_absent: bool = False,
                deriver=None) -> tuple:
    """(edges, meta) for writing a network.

    Sets each record's `status` from the absence threshold k (None, undetermined, for a low-quality
    edge, which is never read as an absence) and its `significance` from the chosen correction, drops
    low-quality edges unless asked, and records all of it in `meta`, so a file says how it was made and
    how many edges each rule touched. `meta.no_growth` records the no-growth rule the derivation ran with,
    since the count of obligate and abolished edges depends on it (#37); pass the same values given to
    the derivation.

    `deriver` is the derivation that made these records, and `meta.statistics` and `meta.provisional`
    come from it: a derivation states what it tests and what is provisional about it, as it already
    states its `name` and `method`. Without it the specified comparison's words are used, which is what
    every network said before 2026-10-07 whatever had derived it (#142 item 5).
    """
    for record in records:
        # a low-quality edge is never read as the absence of an interaction (Karoline, on #40; #50)
        record["status"] = None if is_low_quality(record) else absence(
            record.get("strength"), record.get("sd"), record.get("outcome"), absence_threshold)
    tests = adjust_significance(records, correction)
    records, significance_filter = filter_significance(records, max_adjusted_p)
    edges, hidden = select_edges(records, include_low_quality, include_absent)
    if max_adjusted_p is not None:
        hidden["not_significant"] = significance_filter["left_out"]
    edges, merge = merge_parallel(edges, merge_arcs, min_studies)
    edges, genus = merge_genus(edges, merge_genera, support_level)
    said = dict(getattr(deriver, "statistics", None) or STATISTICS)
    statistics = {**said, "correction": said["correction"].format(name=CORRECTIONS[correction][0]),
                  "tests": tests, "filter": significance_filter}
    if max_adjusted_p is not None:
        statistics["role"] = (f"presence is decided by the absence threshold, and an interaction whose "
                              f"q-value (the adjusted p-value) is above {max_adjusted_p:g} is left out "
                              "(the q-value filter)")
    # how many the threshold marked absent, whether or not they are in the file
    absent = hidden["absent"] + sum(1 for e in edges if e.get("status") == ABSENT)
    base = getattr(deriver, "provisional", None) or PROVISIONAL
    provisional = base + ("" if max_adjusted_p is None else FILTER_NOTE.format(q=max_adjusted_p))
    meta = {"provisional": provisional, "statistics": statistics,
            "absence": {"rule": "absent when |log2 mean| < k * sd", "k": absence_threshold, "absent": absent},
            "no_growth": {**rule_meta(no_growth_alpha, no_growth_factor),
                          "obligate": sum(1 for e in edges if e.get("outcome") == OBLIGATE),
                          "abolished": sum(1 for e in edges if e.get("outcome") == ABOLISHED)},
            "filters": {"include_low_quality": include_low_quality, "include_absent": include_absent},
            "hidden": hidden, "merge": merge,
            "genus": genus}
    return edges, meta


# ---- the pluggable derivation seam ---------------------------------------------------------------

class Deriver:
    """Strategy interface: turn a study and its experiment records into interaction records.

    The comparison method (the growth metric, how to read a per-strain signal inside a community, the
    significance test) is the scientific choice owned by the collaboration. A Deriver is how a chosen
    method plugs in: subclass it, implement `derive`, and it slots into `derive_interactions` and the
    CLI without touching the neutral model or the pipeline. Keep the record shape that
    `grownet.mgrowthdb.records_to_network` reads, and record what the data does not support in
    `skipped` rather than inventing a value.
    """

    name = "abstract"
    method = ""
    # what a network derived this way says about its own statistics and about what is provisional in it.
    # None means the specified comparison's words, which is what every derivation used to claim whether
    # or not it ran that test (#142 item 5): a derivation that tests something else states it here.
    statistics = None
    provisional = None

    def derive(self, study: dict, exps: list):
        """Return (records, skipped). `records` is a list of dicts for records_to_network; `skipped` is a
        list of (label, reason) for pairs the data did not cleanly support."""
        raise NotImplementedError


class ReplicateDeriver(Deriver):
    """The comparison the collaboration specified, over replicate growth curves.

    Reads each replicate's measured series through `grownet.adapter`, compares the replicate sets with
    `grownet.interaction.interaction_strength` (area under the curve by default; maximal abundance or a
    growth rate selectable), and emits edges carrying the standard error and the replicate counts. This is the default
    for a live derivation; the integrated form of #127 is the default since 0.3.0.
    """

    name = "replicate-v1"
    needs_client = True
    statistics = STATISTICS
    provisional = PROVISIONAL

    def __init__(self, method: str = "auc", spike_factor: float = SPIKE_FACTOR, client=None,
                 dropout: bool = True, include_non_batch: bool = False, no_growth_alpha: float = None,
                 no_growth_factor: float = None, keep=None, selection=None,
                 capacity_max_fall: float = CAPACITY_MAX_FALL):
        self.keep = keep
        self.selection = selection
        self.method = method
        self.spike_factor = spike_factor
        self.client = client
        self.dropout = dropout
        self.include_non_batch = include_non_batch
        self.no_growth_alpha = no_growth_alpha
        self.no_growth_factor = no_growth_factor
        # the decline limit reaches the co-culture plateau too, which is the other place a plateau
        # becomes a self-limitation and the only one that did not refuse a lost peak (#155 item 10)
        self.capacity_max_fall = capacity_max_fall

    def derive(self, study: dict, exps: list):
        if self.client is None:
            raise ValueError("ReplicateDeriver needs a client: it reads each replicate's measured series")
        return interactions_from_replicates(self.client, study, exps, study.get("id"),
                                            self.method, self.spike_factor, self.dropout,
                                            self.include_non_batch, self.no_growth_alpha,
                                            self.no_growth_factor, self.keep, self.selection,
                                            self.capacity_max_fall)


def derive_interactions(client: MGrowthDBClient, study_id: str, deriver: Deriver = None,
                        metric: str = "auc", spike_factor: float = SPIKE_FACTOR, dropout: bool = True,
                        include_non_batch: bool = False, no_growth_alpha: float = None,
                        no_growth_factor: float = None, keep=None, selection=None,
                        capacity_max_fall: float = CAPACITY_MAX_FALL):
    """Fetch a study and its experiments from the API, then derive interactions with `deriver`
    (default: ReplicateDeriver, the specified comparison). `metric`, `spike_factor`, `dropout` and
    `capacity_max_fall` configure the default deriver only. A deriver that reads measured series says so
    with `needs_client`."""
    deriver = deriver or ReplicateDeriver(method=metric, spike_factor=spike_factor, dropout=dropout,
                                         include_non_batch=include_non_batch, no_growth_alpha=no_growth_alpha,
                                         no_growth_factor=no_growth_factor, keep=keep, selection=selection,
                                         capacity_max_fall=capacity_max_fall)
    if getattr(deriver, "needs_client", False) and getattr(deriver, "client", None) is None:
        deriver.client = client
    if getattr(deriver, "needs_client", False):
        # read the study's growth curves in parallel first; the derivation then finds them cached
        from .fetch import prefetch_studies
        prefetch_studies(deriver.client, [study_id], include_non_batch, keep=getattr(deriver, "keep", None),
                         dropout=getattr(deriver, "dropout", True))
    study = dict(client.get_study(study_id))
    study.setdefault("id", study_id)
    exps = [client.get_experiment(e["id"]) for e in study.get("experiments", [])]
    return deriver.derive(study, exps)
