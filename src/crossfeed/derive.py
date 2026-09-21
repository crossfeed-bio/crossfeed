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

import json
import math
import re
from collections import Counter

from .adapter import replicates_for_experiment
from .growth import SPIKE_FACTOR, GrowthCurve, Replicate
from .interaction import ABOLISHED, NO_GROWTH, OBLIGATE, UNUSABLE, dropout_interaction_strengths, interaction_strength
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
REMOVED_MEMBER_DETECTED = "removed_member_detected"
# Cautions are shown without making an edge low quality (Karoline, on #47): the edge keeps its status.
TWO_REPLICATES = "two_replicates"


def conditions(exp: dict) -> str:
    """The culture conditions of an experiment as a comparable key: cultivation mode and compartments.

    Replicate sets are pooled only across experiments with identical conditions, since interactions are
    usually environmentally specific (Karoline, on #47); experiments under different conditions give
    separate edges. Filtering by environment is a separate question (#61).
    """
    return json.dumps([exp.get("cultivationMode"), exp.get("compartments", [])], sort_keys=True)


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
    """(node id, conditions) -> (monoculture replicates, the distinct strain names pooled under it, the ids
    of the experiments they come from). Only strains identified by name can pool different strains."""
    identities = identities if identities is not None else strain_identities(exps, [])
    index = {}
    for exp in exps:
        members = _members(exp)
        if len(members) != 1:
            continue
        replicates, skips = replicates_for_experiment(client, exp, spike_factor)
        skipped += skips
        key = (_identity(identities, members[0])["id"], conditions(exp))
        reps, strains, ids = index.setdefault(key, ([], set(), []))
        reps.extend(replicates)
        strains.add(members[0])
        ids.append(_exp_id(exp))
    for (key, _), (_, strains, _) in index.items():
        if len(strains) > 1 and not key.startswith("ncbi:"):
            skipped.append((f"monocultures of {key}", f"{len(strains)} strains pooled into one monoculture set "
                            f"({', '.join(sorted(strains))}); edges using it are flagged {STRAINS_POOLED}"))
    return index


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
    None: undetermined, and such an edge is flagged low quality anyway. With zero spread and a non-zero
    mean the comparison is present.
    """
    if outcome in (OBLIGATE, ABOLISHED):
        return PRESENT
    if sd is None:
        return None          # checked before the zero mean: with no spread nothing can be decided
    if not mean:
        return ABSENT
    return ABSENT if abs(mean) < k * sd else PRESENT


def _record(source: str, target: str, c: dict, method: str, quality: list, cautions: list, notes: list,
            cond: str, evidence: str, community, experiments, study_id, study_meta, identities=None) -> dict:
    """One edge record from a comparison `c` (mean, sd, se, n_with, n_without, outcome, with_log2,
    without_log2), the shape `records_to_network` reads."""
    mean, sd = c["mean"], c["sd"]
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
        "significance": None,           # adjusted for multiple testing, set at output
        "p_value": None if test is None else test["p"],
        "sd": None if sd is None else round(sd, 4),
        "se": None if c["se"] is None else round(c["se"], 4),
        "n_with": c["n_with"], "n_without": c["n_without"],
        "outcome": c["outcome"], "metric": method,
        "quality": quality, "cautions": cautions, "notes": notes,
        "condition": cond, "method": REPLICATE_METHOD.format(metric=method),
        "evidence": evidence, "community": sorted(_identity(identities, m)["id"] for m in community),
        "experiments": list(experiments),
        "study_id": study_id, **study_meta,
    }


def _spike_notes(flagged, target: str) -> list:
    return [f"{f['role']} replicate {f['replicate']} left out: implausible spike, maximum "
            f"{f['ratio']:.0f} times its neighbours at {', '.join(f'{t:g}' for t in f['times'])}"
            for f in flagged if f["species"] == target]


def _pairwise(client, exp, monos, method, spike_factor, study_id, study_meta, records, skipped,
              identities=None) -> None:
    """The edges of one two-member co-culture against the monocultures of its members."""
    a, b = _members(exp)
    cond = exp.get("name", "")
    co_reps, skips = replicates_for_experiment(client, exp, spike_factor)
    skipped += skips
    sets, pooled, origin = {}, {}, {}
    for species in (a, b):
        key = (_identity(identities or {}, species)["id"], conditions(exp))
        found, strains, ids = monos.get(key, ([], set(), []))
        if not found:
            skipped.append((f"{a} with {b} [{cond}]",
                            f"no monoculture replicates for {species} under this experiment's conditions"))
        sets[species] = _renamed(found, species)
        pooled[species] = len(strains) > 1 and not key[0].startswith("ncbi:")
        origin[species] = ids
    if not (sets[a] and sets[b] and co_reps):
        if not co_reps:
            skipped.append((f"{a} with {b} [{cond}]", "no usable co-culture replicates"))
        return
    try:
        result = interaction_strength(sets[a], sets[b], co_reps, a, b, method=method, spike_factor=spike_factor)
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
            skipped.append((f"{source} -> {target} [{cond}]", "every replicate of a set was left out (see above)"))
            continue
        c = {"mean": side["mean"], "sd": side["sd"], "se": side["se"], "outcome": side["outcome"],
             "n_with": side["n_co"], "n_without": side["n_mono"],
             "with_log2": side["co_log2"], "without_log2": side["mono_log2"]}
        quality, cautions = _replicate_flags(c["n_with"], c["n_without"])
        if pooled[target]:
            quality.append(STRAINS_POOLED)
        records.append(_record(source, target, c, method, quality, cautions,
                               _spike_notes(result["flagged"], target), cond, "biculture", (a, b),
                               [_exp_id(exp), *origin[target]], study_id, study_meta, identities))


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
            groups = by_condition.setdefault(conditions(exp), {}).setdefault(members, {})
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
    """(full, dropouts) without the replicates holding a curve that starts after the design's usual start.

    Curves are compared only from a common start time (Karoline's specification, #1). In a community
    replicate every member has a curve, so a member whose first measurement is missing takes its whole
    replicate out; it is reported. The usual start is the most common first time point in the design.
    """
    reps = [*full, *(r for group in dropouts.values() for r in group)]
    firsts = Counter(c.times[0] for r in reps for c in r.curves)
    if len(firsts) < 2:
        return full, dropouts
    start = firsts.most_common(1)[0][0]

    def keep(role, replicates):
        kept = []
        for rep in replicates:
            late = [c for c in rep.curves if not math.isclose(c.times[0], start, abs_tol=1e-9)]
            if late:
                skipped.append((f"{role} replicate {rep.name}", "curve(s) starting after the common start "
                                f"{start:g}: " + ", ".join(f"{c.species} at {c.times[0]:g}" for c in late)
                                + "; left out, since curves are compared only from a common start"))
            else:
                kept.append(rep)
        return kept

    kept = {r: keep(f"community without {r}", group) for r, group in dropouts.items()}
    return keep("full community", full), {r: group for r, group in kept.items() if group}


def _dropout(client, design, method, spike_factor, study_id, study_meta, records, skipped,
             identities=None) -> None:
    """The arcs of one drop-out design, from `crossfeed.interaction.dropout_interaction_strengths`."""
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
        result = dropout_interaction_strengths(full, dropouts, method=method, spike_factor=spike_factor)
    except ValueError as e:
        skipped.append((label, str(e)))
        return
    skipped += result["skipped"]
    for arc in result["arcs"]:
        removed, target = arc["source"], arc["target"]
        quality, cautions = _replicate_flags(arc["n_with"], arc["n_without"])
        notes = _spike_notes([f for f in result["flagged"] if f["role"] in ("full community",
                              f"community without {removed}")], target)
        if full_detected or detected[removed]:
            quality.append(REMOVED_MEMBER_DETECTED)
            if full_detected:
                notes.append(_detected_note("full community", full_detected))
            if detected[removed]:
                notes.append(_detected_note(f"community without {removed}", detected[removed]))
        cond = ", ".join(e.get("name", "") for e in drops[removed])
        experiments = [_exp_id(e) for e in [*full_exps, *drops[removed]]]
        records.append(_record(removed, target, arc, method, quality, cautions, notes, cond, arc["evidence"],
                               members, experiments, study_id, study_meta, identities))


def interactions_from_replicates(client, study: dict, exps: list, study_id: str = None,
                                 method: str = "auc", spike_factor: float = SPIKE_FACTOR,
                                 dropout: bool = True):
    """The specified comparison, run on a study: (records, skipped).

    Two designs give edges. Each two-member co-culture is compared with the monoculture replicates of
    its members under the same conditions (`crossfeed.interaction.interaction_strength`, evidence
    `biculture`). Each drop-out design (`dropout_designs`) compares the full community with the community
    without one member (`crossfeed.interaction.dropout_interaction_strengths`, evidence `dropout`), unless
    `dropout` is False. Drop-out arcs are included by default, labeled by evidence (Craig and Karoline,
    register item 2).

    Every edge carries its mean, sd, se and replicate counts, an effect from `classify`, `quality` flags
    that make it low quality, `cautions` that do not (two replicates on a side), `notes` (an excluded
    outlier), and the ids of the `experiments` it compares, so edges that share replicates can be told
    apart. One edge per experiment; merging edges is a separate decision. Filtering low-quality edges
    happens at output (`select_edges`), so nothing computed is lost.
    """
    study_id = study_id or study.get("id")
    study_meta = {
        "study_citation": study.get("name", study_id),
        "study_url": study.get("url", ""),
        "study_license": "",
    }
    records, skipped = [], []
    identities = strain_identities(exps, skipped)
    monos = _mono_index(client, exps, skipped, spike_factor, identities)
    for exp in exps:
        if len(_members(exp)) == 2:
            _pairwise(client, exp, monos, method, spike_factor, study_id, study_meta, records, skipped,
                      identities)
    if dropout:
        for design in dropout_designs(exps, skipped):
            _dropout(client, design, method, spike_factor, study_id, study_meta, records, skipped, identities)
    elif any(len(_members(exp)) > 2 for exp in exps):
        skipped.append(("communities of more than two members", "drop-out designs switched off; no arcs derived"))
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


# Low-quality flags that leave an edge out of the output by default (Karoline, on #40 and #54). A
# single-replicate edge is shown by default and marked in the Cytoscape style instead (Karoline, on #62):
# it keeps its flag and its undetermined status, since with no spread there is nothing to decide absence on.
HIDDEN_BY_DEFAULT = (STRAINS_POOLED, REMOVED_MEMBER_DETECTED, "non_batch")


def is_hidden_by_default(record) -> bool:
    return any(flag in HIDDEN_BY_DEFAULT for flag in record.get("quality", ()))


def select_edges(records, include_low_quality: bool = False) -> tuple:
    """(edges, hidden) at output. Edges with a flag in HIDDEN_BY_DEFAULT are left out unless asked;
    `hidden` counts them. Single-replicate edges and absent edges stay in: marking or hiding them is the
    display's job, so a user can see them."""
    edges, hidden = [], {"low_quality": 0}
    for record in records:
        if is_hidden_by_default(record) and not include_low_quality:
            hidden["low_quality"] += 1
        else:
            edges.append(record)
    return edges, hidden


def output_meta(records, include_low_quality: bool = False, correction: str = "bh",
                absence_threshold: float = ABSENCE_THRESHOLD) -> tuple:
    """(edges, meta) for writing a network.

    Sets each record's `status` from the absence threshold k (None, undetermined, for a low-quality
    edge, which is never read as an absence) and its `significance` from the chosen correction, drops
    low-quality edges unless asked, and records all of it in `meta`, so a file says how it was made and
    how many edges each rule touched.
    """
    for record in records:
        # a low-quality edge is never read as the absence of an interaction (Karoline, on #40; #50)
        record["status"] = None if is_low_quality(record) else absence(
            record.get("strength"), record.get("sd"), record.get("outcome"), absence_threshold)
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

    def __init__(self, method: str = "auc", spike_factor: float = SPIKE_FACTOR, client=None,
                 dropout: bool = True):
        self.method = method
        self.spike_factor = spike_factor
        self.client = client
        self.dropout = dropout

    def derive(self, study: dict, exps: list):
        if self.client is None:
            raise ValueError("ReplicateDeriver needs a client: it reads each replicate's measured series")
        return interactions_from_replicates(self.client, study, exps, study.get("id"),
                                            self.method, self.spike_factor, self.dropout)


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
                        metric: str = "auc", spike_factor: float = SPIKE_FACTOR, dropout: bool = True):
    """Fetch a study and its experiments from the API, then derive interactions with `deriver`
    (default: ReplicateDeriver, the specified comparison). `metric`, `spike_factor` and `dropout` configure
    the default deriver only. A deriver that reads measured series says so with `needs_client`."""
    deriver = deriver or ReplicateDeriver(method=metric, spike_factor=spike_factor, dropout=dropout)
    if getattr(deriver, "needs_client", False) and getattr(deriver, "client", None) is None:
        deriver.client = client
    study = dict(client.get_study(study_id))
    study.setdefault("id", study_id)
    exps = [client.get_experiment(e["id"]) for e in study.get("experiments", [])]
    return deriver.derive(study, exps)
