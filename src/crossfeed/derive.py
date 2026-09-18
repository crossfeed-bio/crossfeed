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

from .mgrowthdb import MGrowthDBClient

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

    monos = {}   # genus+species -> (value, technique)
    for e in exps:
        mem = _members(e)
        if len(mem) == 1:
            v, tech = _strain_growth(e, None, metric)
            if v is not None:
                monos[_gs(mem[0])] = (v, tech)

    records, skipped = [], []
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
                        metric: str = "growthRate", deadband: float = DEADBAND):
    """Fetch a study and its experiments from the API, then derive interactions with `deriver`
    (default: the provisional BaselineDeriver). `metric`/`deadband` configure the default deriver only."""
    deriver = deriver or BaselineDeriver(metric=metric, deadband=deadband)
    study = dict(client.get_study(study_id))
    study.setdefault("id", study_id)
    exps = [client.get_experiment(e["id"]) for e in study.get("experiments", [])]
    return deriver.derive(study, exps)
