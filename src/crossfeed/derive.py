"""Derive interactions from mGrowthDB growth data.

mGrowthDB serves raw growth (mono and co-culture), not interactions. An interaction is inferred by
comparing a strain's growth ALONE vs WITH a partner, under one condition. The COMPARISON METHOD is a
scientific choice owned by the collaboration (K. Faust): which growth metric, how to read a per-strain
signal inside a community, and the significance test.

That choice plugs in through the `Deriver` interface. `BaselineDeriver` is ONE transparent, provisional
implementation so the seam runs end to end on real data today; the agreed method arrives as another
`Deriver` and drops in without touching the network model or the pipeline.

Baseline v0 (documented and conservative):
  * metric: per-strain `growthRate` (1/h), a RATE that travels better across techniques than an absolute
    AUC. The mono and co techniques are recorded per edge; a technique mismatch is FLAGGED, not hidden.
  * mono growth: the strain's growthRate in its single-strain experiment (community-level context).
  * co growth: the strain's growthRate in a PAIRWISE (2-member) co-culture, from the per-strain context
    (subject.type == "strain"). Co-cultures with more than two members are SKIPPED (not a clean pairwise
    attribution). A missing per-strain context skips that strain, with a reason; nothing is fabricated.
  * strength = log2(co / mono); effect by sign with a documented deadband; NO significance test yet, so
    every edge is qualitative (significance = None), recorded as such by the neutral model.
"""
from __future__ import annotations

import math

from .adapter import replicates_for_experiment
from .growth import SPIKE_FACTOR, GrowthCurve, Replicate
from .interaction import ABOLISHED, NO_GROWTH, OBLIGATE, interaction_strength
from .mgrowthdb import MGrowthDBClient
from .stats import CORRECTIONS, welch

METHOD = ("crossfeed baseline v0 (PROVISIONAL): log2(growthRate co / mono), pairwise co-cultures only, "
          "no significance test; comparison method to be scoped with K. Faust")
DEADBAND = 0.25   # |log2 ratio| below this reads neutral in the baseline (documented, provisional)


def genus_species(name: str) -> str:
    """Genus + species key for matching a strain across experiments (drops the strain designation)."""
    return " ".join((name or "").split()[:2]).lower()


_gs = genus_species   # short alias used throughout this module


def _strain_growth(exp: dict, want_strain: str = None, metric: str = "growthRate"):
    """(value, technique) for a strain's growth in an experiment, or (None, None).

    mono (want_strain is None): the community-level context (subject.type == 'bioreplicate').
    co (want_strain given): the per-strain context (subject.type == 'strain', genus+species match).
    Prefers a bioreplicate named like 'Average(...)' when present.
    """
    result = (None, None)
    brs = exp.get("bioreplicates", [])
    ordered = sorted(brs, key=lambda b: 0 if str(b.get("name", "")).startswith("Average") else 1)
    for br in ordered:
        for mc in br.get("measurementContexts", []):
            val = mc.get(metric)
            if val is None:
                continue
            sub = mc.get("subject") or {}
            if want_strain is None:
                if sub.get("type") == "bioreplicate":
                    result = (val, mc.get("techniqueType"))
                    return result
            else:
                if sub.get("type") == "strain" and _gs(sub.get("name", "")) == _gs(want_strain):
                    result = (val, mc.get("techniqueType"))
                    return result
    return result


def _members(exp: dict) -> list:
    return [s.get("name", "") for s in exp.get("communityStrains", [])]


def interactions_from_experiments(study: dict, exps: list, study_id: str = None,
                                  metric: str = "growthRate", deadband: float = DEADBAND):
    """Pure derivation, no network: return (records, skipped) from a study dict and its experiment dicts.
    `records` feed crossfeed.mgrowthdb.records_to_network; `skipped` lists (label, reason) for everything
    the data did not cleanly support. This is the PROVISIONAL baseline; see the module docstring."""
    study_id = study_id or study.get("id")

    records, skipped = [], []

    monos = {}        # genus+species -> (value, technique)
    mono_strain = {}  # genus+species -> the strain name whose value is held
    for e in exps:
        mem = _members(e)
        if len(mem) == 1:
            v, tech = _strain_growth(e, None, metric)
            if v is not None:
                key = _gs(mem[0])
                held = mono_strain.get(key)
                if held is not None and held != mem[0]:
                    # Nodes are keyed at genus and species, so strains of one species share a key and only
                    # the last monoculture read is used. Which one to keep is a method choice (METHOD_NOTES
                    # setting 7), so the baseline keeps its behavior and reports what it dropped.
                    skipped.append((f"monoculture {held}",
                                    f"another strain of the same species ({mem[0]}) also has a monoculture; "
                                    f"both key to '{key}' and only the last is used"))
                monos[key] = (v, tech)
                mono_strain[key] = mem[0]

    study_meta = {
        "study_citation": study.get("name", study_id),
        "study_url": study.get("url", ""),
        "study_license": "",   # per-study license is not exposed in the study endpoint; TODO resolve with mGrowthDB
    }
    for e in exps:
        mem = _members(e)
        if len(mem) < 2:
            continue
        if len(mem) > 2:
            skipped.append((e.get("name", e.get("id")), "co-culture has >2 members; not a clean pairwise attribution"))
            continue
        cond = e.get("name", "")
        a, b = mem[0], mem[1]
        for focal, partner in ((a, b), (b, a)):
            mono = monos.get(_gs(focal))
            co_v, co_tech = _strain_growth(e, focal, metric)
            if mono is None:
                skipped.append((f"{partner}->{focal} [{cond}]", f"no mono growth for {focal}"))
                continue
            if co_v is None:
                skipped.append((f"{partner}->{focal} [{cond}]", f"no per-strain co-culture growth for {focal}"))
                continue
            mono_v, mono_tech = mono
            if mono_v <= 0 or co_v <= 0:
                skipped.append((f"{partner}->{focal} [{cond}]", "non-positive growth value"))
                continue
            strength = math.log2(co_v / mono_v)
            effect = "neutral" if abs(strength) < deadband else ("facilitation" if strength > 0 else "inhibition")
            if mono_tech != co_tech:
                note = METHOD + f"; TECHNIQUE MISMATCH mono={mono_tech} co={co_tech}"
            else:
                note = METHOD + f"; technique {co_tech}"
            records.append({
                "source": _gs(partner), "source_name": partner,
                "target": _gs(focal), "target_name": focal,
                "effect": effect, "strength": round(strength, 4), "significance": None,
                "condition": cond, "method": note,
                "evidence": "biculture", "community": sorted([_gs(a), _gs(b)]),
                "study_id": study_id, **study_meta,
            })
    return records, skipped


REPLICATE_METHOD = ("crossfeed replicate v1: mean log2({metric} in co-culture) minus mean log2({metric} in "
                    "monoculture) over replicate sets; absent when |mean| < k * sd; Welch's t-test "
                    "reported and corrected for multiple testing, not used to decide")
PRESENT, ABSENT = "present", "absent"
ABSENCE_THRESHOLD = 1.0    # k: absent when |log2 mean| < k * sd. k = 1 is the mean plus or minus sd rule
STATISTICS = {"test": "Welch's two-sided t-test on the per-replicate log2 values",
              "correction": "{name} over every comparison tested in this derivation",
              "role": "reported as support for an edge; presence is decided by the absence threshold"}

# Quality flags make an edge low quality: hidden by default, and never read as the absence of an
# interaction (Karoline, on #40). Notes inform without disqualifying, such as an excluded outlier.
SINGLE_REPLICATE = "single_replicate"
STRAINS_POOLED = "strains_pooled"


def _mono_index(client, exps, skipped, spike_factor: float = SPIKE_FACTOR) -> dict:
    """genus and species key -> (monoculture replicates, the distinct strain names pooled under it)."""
    index = {}
    for exp in exps:
        members = _members(exp)
        if len(members) != 1:
            continue
        replicates, skips = replicates_for_experiment(client, exp, spike_factor)
        skipped += skips
        reps, strains = index.setdefault(genus_species(members[0]), ([], set()))
        reps.extend(replicates)
        strains.add(members[0])
    for key, (_, strains) in index.items():
        if len(strains) > 1:
            skipped.append((f"monocultures of {key}", f"{len(strains)} strains pooled into one monoculture set "
                            f"({', '.join(sorted(strains))}); edges using it are flagged {STRAINS_POOLED}"))
    return index


def _renamed(replicates, species: str):
    """The same replicates with their single curve named `species`.

    A strain is named slightly differently between experiments (and taxon 411483 even appears under two
    species names), so monoculture and co-culture records are matched at genus and species and the name
    from the co-culture record is used for both. When the key holds genuinely different strains, the edge
    is flagged `strains_pooled`. Node identity by taxon id replaces this (issue #23).
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
    None: undetermined, and such an edge is flagged low quality anyway. With zero spread and a non-zero
    mean the comparison is present.
    """
    if outcome in (OBLIGATE, ABOLISHED):
        return PRESENT
    if not mean:
        return ABSENT
    if sd is None:
        return None
    return ABSENT if abs(mean) < k * sd else PRESENT


def interactions_from_replicates(client, study: dict, exps: list, study_id: str = None,
                                 method: str = "auc", spike_factor: float = SPIKE_FACTOR):
    """The specified comparison, run on a study: (records, skipped).

    For each pairwise co-culture experiment, the replicates of that experiment are compared with the
    monoculture replicates of each member through `crossfeed.interaction.interaction_strength`. Every edge
    carries its mean, sd, se and replicate counts, an effect from `classify`, `quality` flags that make it
    low quality, and `notes` that do not (an excluded outlier). One edge per condition, as before; merging
    edges across conditions is a separate decision. Filtering neutral and low-quality edges happens at
    output (`select_edges`), so nothing computed is lost.
    """
    study_id = study_id or study.get("id")
    study_meta = {
        "study_citation": study.get("name", study_id),
        "study_url": study.get("url", ""),
        "study_license": "",
    }
    records, skipped = [], []
    monos = _mono_index(client, exps, skipped, spike_factor)

    for exp in exps:
        members = _members(exp)
        if len(members) < 2:
            continue
        cond = exp.get("name", "")
        if len(members) > 2:
            skipped.append((f"{cond}", "co-culture has >2 members; not a clean pairwise attribution"))
            continue
        a, b = members
        co_reps, skips = replicates_for_experiment(client, exp, spike_factor)
        skipped += skips
        sets, pooled = {}, {}
        for species in (a, b):
            found, strains = monos.get(genus_species(species), ([], set()))
            if not found:
                skipped.append((f"{a} with {b} [{cond}]", f"no monoculture replicates for {species}"))
            sets[species] = _renamed(found, species)
            pooled[species] = len(strains) > 1
        if not (sets[a] and sets[b] and co_reps):
            if not co_reps:
                skipped.append((f"{a} with {b} [{cond}]", "no usable co-culture replicates"))
            continue
        try:
            result = interaction_strength(sets[a], sets[b], co_reps, a, b, method=method,
                                          spike_factor=spike_factor)
        except ValueError as e:
            skipped.append((f"{a} with {b} [{cond}]", str(e)))
            continue
        skipped += result["skipped"]
        method_note = REPLICATE_METHOD.format(metric=method)
        for key, (source, target) in (("species_a", (b, a)), ("species_b", (a, b))):
            side = result[key]
            if side["outcome"] == NO_GROWTH:
                skipped.append((f"{source} -> {target} [{cond}]", f"no growth ({method}) in either set"))
                continue
            quality = []
            if side["n_co"] < 2 or side["n_mono"] < 2:
                quality.append(SINGLE_REPLICATE)
            if pooled[target]:
                quality.append(STRAINS_POOLED)
            notes = [f"{f['role']} replicate {f['replicate']} left out: implausible spike, maximum "
                     f"{f['ratio']:.0f} times the median at {', '.join(f'{t:g}' for t in f['times'])}"
                     for f in result["flagged"] if f["species"] == target]
            mean, sd = side["mean"], side["sd"]
            test = welch(side["co_log2"], side["mono_log2"])
            records.append({
                "source": genus_species(source), "source_name": source,
                "target": genus_species(target), "target_name": target,
                "effect": classify(mean, side["outcome"]),
                "strength": None if mean is None else round(mean, 4),
                "weight": None if mean is None else round(abs(mean), 4),
                "effect_over_sd": None if effect_over_sd(mean, sd) is None else round(effect_over_sd(mean, sd), 4),
                "status": None,                 # present or absent, set at output from the threshold k
                "significance": None,           # Benjamini-Hochberg adjusted, set at output
                "p_value": None if test is None else test["p"],
                "sd": None if sd is None else round(sd, 4),
                "se": None if side["se"] is None else round(side["se"], 4),
                "n_with": side["n_co"], "n_without": side["n_mono"],
                "outcome": side["outcome"], "metric": method,
                "quality": quality, "notes": notes,
                "condition": cond, "method": method_note,
                "evidence": "biculture", "community": sorted([genus_species(a), genus_species(b)]),
                "study_id": study_id, **study_meta,
            })
    return records, skipped


def is_low_quality(record) -> bool:
    return bool(record.get("quality"))


def adjust_significance(records, correction: str = "bh") -> int:
    """Fill each record's `significance` with its adjusted p-value, in place.

    `correction` is "bh" (Benjamini-Hochberg, the default) or "by" (Benjamini-Yekutieli, valid under any
    dependence between the tests).

    The family is every comparison tested in this derivation, edges, absences and low-quality ones alike,
    since all were tested. Returns the number of tests. Records without a p-value (a single replicate on
    a side) are not tests and keep `significance` None.
    """
    tested = [r for r in records if r.get("p_value") is not None]
    adjust = CORRECTIONS[correction][1]
    for record, adjusted in zip(tested, adjust([r["p_value"] for r in tested]), strict=True):
        record["significance"] = round(adjusted, 6)
    return len(tested)


def select_edges(records, include_low_quality: bool = False) -> tuple:
    """(edges, hidden) at output. Low-quality edges are left out by default (Karoline, on #40 and #54);
    `hidden` counts them. Absent edges stay in: hiding them is the display's job, so a user can see them."""
    edges, hidden = [], {"low_quality": 0}
    for record in records:
        if is_low_quality(record) and not include_low_quality:
            hidden["low_quality"] += 1
        else:
            edges.append(record)
    return edges, hidden


def output_meta(records, include_low_quality: bool = False, correction: str = "bh",
                absence_threshold: float = ABSENCE_THRESHOLD) -> tuple:
    """(edges, meta) for writing a network.

    Sets each record's `status` from the absence threshold k and its `significance` from the chosen
    correction, drops low-quality edges unless asked, and records all of it in `meta`, so a file says how
    it was made and how many edges each rule touched.
    """
    for record in records:
        record["status"] = absence(record.get("strength"), record.get("sd"), record.get("outcome"),
                                   absence_threshold)
    tests = adjust_significance(records, correction)
    edges, hidden = select_edges(records, include_low_quality)
    statistics = {**STATISTICS, "correction": STATISTICS["correction"].format(name=CORRECTIONS[correction][0]),
                  "tests": tests}
    absent = sum(1 for e in edges if e.get("status") == ABSENT)
    meta = {"statistics": statistics,
            "absence": {"rule": "absent when |log2 mean| < k * sd", "k": absence_threshold, "absent": absent},
            "filters": {"include_low_quality": include_low_quality}, "hidden": hidden}
    return edges, meta


# ---- the pluggable derivation seam ---------------------------------------------------------------

class Deriver:
    """Strategy interface: turn a study and its experiment records into interaction records.

    The comparison method (the growth metric, how to read a per-strain signal inside a community, the
    significance test) is the scientific choice owned by the collaboration. A Deriver is how a chosen
    method plugs in: subclass it, implement `derive`, and it slots into `derive_interactions` and the
    CLI without touching the neutral model or the pipeline. Keep the record shape that
    `crossfeed.mgrowthdb.records_to_network` reads, and record what the data does not support in
    `skipped` rather than inventing a value.
    """

    name = "abstract"
    method = ""

    def derive(self, study: dict, exps: list):
        """Return (records, skipped). `records` is a list of dicts for records_to_network; `skipped` is a
        list of (label, reason) for pairs the data did not cleanly support."""
        raise NotImplementedError


class ReplicateDeriver(Deriver):
    """The comparison the collaboration specified, over replicate growth curves.

    Reads each replicate's measured series through `crossfeed.adapter`, compares the replicate sets with
    `crossfeed.interaction.interaction_strength` (area under the curve by default, maximal abundance
    selectable), and emits edges carrying the standard error and the replicate counts. This is the default
    for a live derivation; `BaselineDeriver` remains only as the retired placeholder it always was.
    """

    name = "replicate-v1"
    needs_client = True

    def __init__(self, method: str = "auc", spike_factor: float = SPIKE_FACTOR, client=None):
        self.method = method
        self.spike_factor = spike_factor
        self.client = client

    def derive(self, study: dict, exps: list):
        if self.client is None:
            raise ValueError("ReplicateDeriver needs a client: it reads each replicate's measured series")
        return interactions_from_replicates(self.client, study, exps, study.get("id"),
                                            self.method, self.spike_factor)


class BaselineDeriver(Deriver):
    """The provisional v0 baseline: log2(growthRate co / mono), pairwise co-cultures only, no significance
    test. A transparent placeholder that runs the seam end to end; meant to be replaced by the method
    agreed with K. Faust."""

    name = "baseline-v0"
    method = METHOD

    def __init__(self, metric: str = "growthRate", deadband: float = DEADBAND):
        self.metric = metric
        self.deadband = deadband

    def derive(self, study: dict, exps: list):
        return interactions_from_experiments(study, exps, study.get("id"), self.metric, self.deadband)


def derive_interactions(client: MGrowthDBClient, study_id: str, deriver: Deriver = None,
                        metric: str = "auc", spike_factor: float = SPIKE_FACTOR):
    """Fetch a study and its experiments from the API, then derive interactions with `deriver`
    (default: ReplicateDeriver, the specified comparison). `metric` and `spike_factor` configure the
    default deriver only. A deriver that reads measured series says so with `needs_client`."""
    deriver = deriver or ReplicateDeriver(method=metric, spike_factor=spike_factor)
    if getattr(deriver, "needs_client", False) and getattr(deriver, "client", None) is None:
        deriver.client = client
    study = dict(client.get_study(study_id))
    study.setdefault("id", study_id)
    exps = [client.get_experiment(e["id"]) for e in study.get("experiments", [])]
    return deriver.derive(study, exps)
