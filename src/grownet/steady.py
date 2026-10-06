"""Scoring a gLV package against a chemostat steady state (#125, from #124 item 4a).

Karoline, 2026-10-06: "you can check accuracy of fit using study 7 for mono-cultures and pairs with study
5's controls, which are steady state community abundances (without perturbation, ignoring the extra
species, which are at small abundance)", and then "go ahead with ... the chemostat validation".

A package is built from batch co-cultures and never sees a chemostat, so a chemostat is an independent
test of it. A continuous culture holds

    dx_i/dt = x_i ( r_i + sum_j A_ij x_j ) - D x_i

so at steady state `A x* = -(r - D)`, with D the dilution rate mGrowthDB records on the compartment. This
module reads the observed steady states, solves that system for the package's own numbers, and reports
both with their ratio. It only reports: no coefficient, rate or network changes because of a check.

The rules it applies, stated once:
  * **the observed steady state** of a vessel is the mean of its measurements over the last quarter of the
    run, and an organism's steady state is the median over the vessels, with every vessel and organism it
    could not read named with the reason;
  * **a perturbed run is named**, not used, since what Karoline asked for is the unperturbed state, and a
    run whose records say neither way is scored with that said;
  * **nothing is compared across abundance units or media**, as nothing is converted anywhere else;
  * **an organism the fit gives no positive state**, observed at or near zero, agrees in direction, and
    the check says so rather than printing a ratio.
"""
from __future__ import annotations

import re
import statistics

from .adapter import replicates_for_experiment
from .growth import SPIKE_FACTOR, cut

# the share of the run that counts as the end of it, where a chemostat is at its steady state
TAIL = 0.25
MIN_POINTS = 2          # fewer measurements in that window than this, and no steady state is read
# an organism observed below this share of the largest steady state of its run counts as washed out
WASHED_OUT = 0.01
# Whether a run was perturbed is in free text only: mGrowthDB has no field for it (the notes of #62 say
# so), and the two unperturbed runs are called "No perturbations" and "Control vessels ... but no
# perturbations", so a search for the word alone would mark exactly the wrong ones. These two patterns are
# read in order: a denial first, then the words the perturbed runs use ("The pH of the feed was changed
# from 6.4 to 3.7 and the feed was stopped for 12 hrs", "a feed perturbation as well as addition of fresh
# medium"). Neither matching leaves it unknown, which is reported rather than guessed.
_NOT_PERTURBED = re.compile(r"\b(no|without|not)\s+(further\s+|any\s+)?perturb", re.I)
_PERTURBED = re.compile(r"perturb|pulse[ds]?\b|was stopped|were stopped|changed from|decreased from"
                        r"|increased from|addition of fresh|wash[- ]?out", re.I)


def _dilution(exp: dict):
    """The dilution rate of an experiment's compartments, or None when none is recorded."""
    for comp in exp.get("compartments") or []:
        value = comp.get("dilutionRate")
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _medium(exp: dict) -> str:
    for comp in exp.get("compartments") or []:
        if comp.get("mediumName"):
            return str(comp["mediumName"])
    return ""


def _words(name: str) -> list:
    """A medium name as its lowercase alphanumeric words, so two spellings of one medium compare equal."""
    return [w for w in re.split(r"[^a-z0-9]+", (name or "").casefold()) if w]


# a word that states what was taken out of a medium or added to it: two names that differ by one of these
# are two environments, however much else they share ("WC" against "WC-free" is the clearest case)
CHANGED = {"free", "without", "minus", "depleted", "plus", "supplemented", "diluted", "with"}


def same_medium(a: str, b: str) -> bool:
    """Whether two medium names are the same medium.

    mGrowthDB writes one medium several ways: SMGDB00000007 has "Wilkins-Chalgren Anaerobe Broth (WC)"
    and SMGDB00000005 has "Wilkins-Chalgren". Reduced to words, the shorter name's words are all in the
    longer one, which is the rule here, and the shorter name has to bring at least two of them unless the
    two names are the same words. One word is not enough: mGrowthDB holds "Mucin" and "MDb-MM basal
    medium mucin DoS", a defined medium with mucin added, which a one-word match called the same medium
    (found 2026-10-06). A word that states an omission or an addition makes the two differ whatever else
    they share. An empty name matches nothing: a run whose medium is unrecorded is not scored against a
    package, since a coefficient is specific to its environment.
    """
    first, second = _words(a), _words(b)
    if not first or not second:
        return False
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    if CHANGED & (set(longer) ^ set(shorter)):
        return False
    return len(shorter) >= 2 and set(shorter) <= set(longer)


def _perturbed(exp: dict):
    """True, False, or None when the records say neither way."""
    text = " ".join(str(exp.get(key) or "") for key in ("name", "description"))
    # mGrowthDB serves no perturbations field today (its experiment records hold name, description,
    # cultivationMode, compartments, communityStrains and bioreplicates), so the free-text rules below are
    # the whole rule. This reads one if the API ever adds it.
    if exp.get("perturbations"):
        return True
    if _NOT_PERTURBED.search(text):
        return False
    return True if _PERTURBED.search(text) else None


def _tail_mean(curve, tail: float = TAIL):
    """(value, window, points): the mean over the end of the run, and the window it was taken over.

    The window is the last `tail` of the curve's span, widened to the last `MIN_POINTS` measurements when
    it holds fewer than that: SMGDB00000005's chemostats have nine points over 400 h, so a quarter of the
    run holds one measurement, and a mean of one point is the point. The window is returned either way,
    so what was averaged is on the record.
    """
    times, values = cut(curve, None)
    if len(values) < MIN_POINTS:
        return None, (times[0], times[-1]), len(values)
    span = times[-1] - times[0]
    start = times[-1] - tail * span if span > 0 else times[0]
    inside = [(t, v) for t, v in zip(times, values, strict=True) if t >= start - 1e-9]
    if len(inside) < MIN_POINTS:
        inside = list(zip(times, values, strict=True))[-MIN_POINTS:]
        start = inside[0][0]
    return sum(v for _, v in inside) / len(inside), (start, times[-1]), len(inside)


def observed(client, exps: list, spike_factor: float = SPIKE_FACTOR) -> list:
    """The steady states of the continuous cultures among `exps`, one entry per experiment.

    {"study_id", "experiment", "name", "medium", "dilution", "unit", "window", "vessels", "perturbed",
     "why_not", "organisms": {name: {"value", "vessels", "spread"}}, "left_out": [(what, why)]}

    `why_not` is empty when the run can be scored, and otherwise says why it cannot: a missing dilution
    rate, perturbations, or no organism read. Nothing is derived here and nothing is cached beyond what
    the client already caches, so a check costs the curves of these experiments and nothing else.
    """
    out = []
    for exp in exps:
        if (exp.get("cultivationMode") or "").lower() == "batch":
            continue
        name = exp.get("name") or exp.get("id") or "experiment"
        reps, skipped = replicates_for_experiment(client, exp, spike_factor)
        entry = {"study_id": exp.get("studyId", ""), "experiment": exp.get("id", ""), "name": name,
                 "medium": _medium(exp), "dilution": _dilution(exp), "unit": "", "window": None,
                 "vessels": len(reps), "perturbed": _perturbed(exp), "why_not": "",
                 "organisms": {}, "left_out": [(what, why) for what, why in skipped]}
        if entry["perturbed"] is None:
            entry["left_out"].append((name, "mGrowthDB records no perturbations field and this run's "
                                            "description says neither way, so whether its end is an "
                                            "unperturbed steady state is not known from the records"))
        windows = []
        for strain in exp.get("communityStrains") or []:
            species = strain.get("name")
            values, points = [], 0
            for i, rep in enumerate(reps):
                curve = rep.curve(species)
                if curve is None:
                    entry["left_out"].append((f"{name}: {species}, vessel {rep.name or i}",
                                              "no curve for this organism in this vessel"))
                    continue
                value, window, points = _tail_mean(curve)
                if value is None:
                    entry["left_out"].append((f"{name}: {species}, vessel {rep.name or i}",
                                              f"{points} measurement(s) over the last quarter of the "
                                              "run, too few for a steady state"))
                    continue
                if not entry["unit"]:
                    entry["unit"] = curve.abundance_unit
                if curve.abundance_unit != entry["unit"]:
                    entry["left_out"].append((f"{name}: {species}, vessel {rep.name or i}",
                                              f"measured in {curve.abundance_unit}, and this run in "
                                              f"{entry['unit']}; left out rather than converted"))
                    continue
                values.append(value)
                windows.append(window)
            if values:
                entry["organisms"][species] = {"value": statistics.median(values), "vessels": len(values),
                                               "spread": (min(values), max(values))}
        if windows:
            entry["window"] = (min(w[0] for w in windows), max(w[1] for w in windows))
        reasons = []
        if entry["dilution"] is None:
            reasons.append("no dilution rate is recorded on its compartments, and a steady state cannot "
                           "be predicted without one")
        if entry["perturbed"] is True:
            reasons.append("the run carries perturbations, so its end is not an unperturbed steady state")
        if not entry["organisms"]:
            reasons.append("no organism of it could be read")
        entry["why_not"] = "; ".join(reasons)
        out.append(entry)
    return out


def find(client, net, progress=None) -> list:
    """The observed steady states of every continuous culture mGrowthDB holds for this network's
    organisms, including studies the search itself never read.

    The organisms are looked up by taxon id through the API's own search, so this costs one search, the
    studies it names, and the curves of their continuous cultures. A study that cannot be read is skipped
    rather than losing the others.
    """
    taxa = sorted({node.taxon_id for node in net.nodes.values() if node.taxon_id})
    if not taxa:
        return []
    try:
        found = client.search(strain_ncbi_ids=",".join(str(t) for t in taxa))
    except Exception:            # noqa: BLE001 - a check that cannot look studies up reports nothing
        return []
    studies = list(found.get("studies", []))
    out = []
    for i, sid in enumerate(studies):
        if progress:
            progress(i, len(studies), f"Reading the chemostats of {sid}")
        try:
            exps = client.study_experiments(sid)
        except Exception:        # noqa: BLE001 - same reason, one unreadable study at a time
            continue
        for entry in observed(client, exps):
            entry["study_id"] = entry["study_id"] or sid
            out.append(entry)
    return out


def solve(rows: list, rhs: list):
    """The solution of `rows x = rhs` by Gaussian elimination with partial pivoting, or None if singular.

    Standard library only, like everything else here, and the systems are as small as the matrices are.
    """
    n = len(rhs)
    work = [list(row) + [rhs[i]] for i, row in enumerate(rows)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(work[r][col]))
        if abs(work[pivot][col]) < 1e-300:
            return None
        work[col], work[pivot] = work[pivot], work[col]
        for r in range(n):
            if r == col:
                continue
            factor = work[r][col] / work[col][col]
            for k in range(col, n + 1):
                work[r][k] -= factor * work[col][k]
    return [work[i][n] / work[i][i] for i in range(n)]


def predicted(block: dict, rates: dict, dilution: float, organisms: list = None) -> dict:
    """The steady state the package predicts: the solution of `A x = -(r - D)`.

    {"values": {organism: x}, "notes": {organism: why it is not a state}, "why_not": ""}. `organisms`
    restricts the system to a sub-community, which is what a chemostat holding some of the matrix's
    organisms needs; the others are reported rather than silently set to anything.
    """
    names, ids = block["organisms"], block["ids"]
    keep = [i for i, name in enumerate(names) if organisms is None or name in organisms]
    if not keep:
        return {"values": {}, "notes": {}, "why_not": "no organism in common"}
    rows = [[block["matrix"][i][j] for j in keep] for i in keep]
    rhs = []
    for i in keep:
        rate = rates.get(ids[i]) or {}
        rhs.append(-((rate.get("rate") or 0.0) - dilution))
    answer = solve(rows, rhs)
    if answer is None:
        return {"values": {}, "notes": {},
                "why_not": "the matrix of this sub-community is singular, so it has no single steady state"}
    values = {names[i]: answer[k] for k, i in enumerate(keep)}
    notes = {name: "not positive, so the fit gives this organism no steady state above zero"
             for name, value in values.items() if value <= 0}
    return {"values": values, "notes": notes, "why_not": ""}


def _fits(block: dict, unit: str, medium: str, organisms: set) -> bool:
    """Whether this matrix can be compared with a run in `unit` and `medium`: same abundance unit, at
    least one organism in common, and the same medium where the package records one at all."""
    named = [name for name in block.get("media") or [] if name]
    return bool(block["abundance_unit"] == unit and organisms.intersection(block["organisms"])
                and (not named or any(same_medium(name, medium) for name in named)))


def _washed_out(value: float, biggest: float) -> bool:
    """Whether the chemostat lost this organism: nothing left, or under a hundredth of the largest steady
    state of the same run (SMGDB00000011's Faecalibacterium duncaniae is zero in every vessel while the
    others hold 1e8)."""
    return value <= 0 or (biggest > 0 and value <= WASHED_OUT * biggest)


def check(coefficients: dict, rates: dict, seen: list) -> list:
    """Score a package against each observed steady state: one entry per observation.

    {"name", "study_id", "experiment", "medium", "dilution", "used", "why_not", "rows": [...]} , where a
    row is {"organism", "predicted", "observed", "ratio", "note"}. A matrix is matched to an observation
    by abundance unit, by medium and by sharing at least one organism; `used` False always carries the
    reason, so a reader never has to guess why a chemostat was not scored.
    """
    out = []
    for entry in seen:
        result = {"name": entry["name"], "study_id": entry["study_id"],
                  "experiment": entry["experiment"], "medium": entry["medium"],
                  "dilution": entry["dilution"], "vessels": entry["vessels"],
                  "window": entry["window"], "used": False, "why_not": entry["why_not"], "rows": []}
        if result["why_not"]:
            out.append(result)
            continue
        here = set(entry["organisms"])
        block = next((b for b in coefficients["matrices"]
                      if _fits(b, entry["unit"], entry["medium"], here)), None)
        if block is None:
            units = sorted({b["abundance_unit"] for b in coefficients["matrices"]})
            media = sorted({name for b in coefficients["matrices"] for name in b.get("media") or []})
            theirs = ", ".join(name for name in media if name) or "an unrecorded medium"
            if not any(here.intersection(b["organisms"]) for b in coefficients["matrices"]):
                result["why_not"] = ("no organism of this run is in the package, so there is nothing to "
                                     "compare")
            elif entry["unit"] not in units:
                result["why_not"] = (f"this run measures {entry['unit']} and the package holds "
                                     f"{', '.join(units) or 'nothing'}; left out rather than converted")
            else:
                result["why_not"] = (f"this run is in {entry['medium'] or 'an unrecorded medium'} and the "
                                     f"package was measured in {theirs}, and a coefficient is specific to "
                                     "its environment")
            out.append(result)
            continue
        shared = [name for name in block["organisms"] if name in here]
        got = predicted(block, rates, entry["dilution"], shared)
        if got["why_not"]:
            result["why_not"] = got["why_not"]
            out.append(result)
            continue
        biggest = max((o["value"] for o in entry["organisms"].values()), default=0.0)
        for name in shared:
            value, seen_here = got["values"][name], entry["organisms"][name]["value"]
            row = {"organism": name, "predicted": value, "observed": seen_here, "ratio": None, "note": ""}
            gone = _washed_out(seen_here, biggest)
            if value <= 0 and gone:
                row["note"] = ("the fit washes this organism out and the chemostat did too, so the two "
                               "agree in direction")
            elif value <= 0:
                row["note"] = ("the fit washes this organism out while the chemostat holds it: "
                               + got["notes"].get(name, ""))
            elif gone:
                row["note"] = "the chemostat washed this organism out and the fit keeps it"
            else:
                row["ratio"] = value / seen_here
            result["rows"].append(row)
        result["used"] = True
        result["left_out"] = [name for name in entry["organisms"] if name not in shared]
        if not [name for name in block.get("media") or [] if name]:
            result["note"] = ("the package records no medium, so this comparison does not know whether "
                              "the two were measured in the same environment")
        out.append(result)
    return out


def _number(value: float) -> str:
    return f"{value:.4g}"


def as_text(checks: list) -> str:
    """The check as the report and the package print it: one block per chemostat."""
    if not checks:
        return ("steady-state check: mGrowthDB holds no continuous culture of these organisms, so there "
                "is nothing to score this package against.\n")
    lines = ["steady-state check: what this package predicts for a chemostat, against what the chemostat",
             "held. A continuous culture satisfies A x = -(r - D) at steady state, so these numbers come",
             "from the package alone and the observations were never used to make it.", ""]
    for check_one in checks:
        head = f"  {check_one['name']} ({check_one['study_id'] or check_one['experiment']})"
        if not check_one["used"]:
            lines.append(f"{head}: not scored, because {check_one['why_not']}.")
            continue
        lines.append(f"{head}, dilution rate {check_one['dilution']:g} /h, "
                     f"{check_one['vessels']} vessel(s):")
        if check_one.get("note"):
            lines.append(f"      note: {check_one['note']}")
        for row in check_one["rows"]:
            if row["ratio"] is not None:
                lines.append(f"      {row['organism']}: predicted {_number(row['predicted'])}, "
                             f"observed {_number(row['observed'])}, "
                             f"{_number(row['ratio'])}x observed")
            else:
                lines.append(f"      {row['organism']}: predicted {_number(row['predicted'])}, "
                             f"observed {_number(row['observed'])}: {row['note']}")
        for name in check_one.get("left_out", []):
            lines.append(f"      {name}: in the chemostat and not in the package, so not scored")
    lines.append("")
    return "\n".join(lines) + "\n"
