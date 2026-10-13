"""Properties of what grownet derives from the REAL mGrowthDB, checked on a schedule (#237).

Every other check in this project is closed over the repository: the gate reads source text, the suite is
offline by design (`tests/conftest.py`), the release check compares version strings. So nothing verified
that what the tool derives from the live corpus has the shape and the arithmetic its own documentation
promises, while every claim the artifacts make is about that corpus.

This checks PROPERTIES rather than numbers, so it does not go stale when mGrowthDB gains data: no arc
count and no rate is asserted, only what must hold of any arc the tool writes.

  1. every arc carries the fields its evidence and outcome promise;
  2. the arithmetic between fields holds, under the derivation that made the arc;
  3. the network validates against the shipped schema, with no undeclared key and no incomplete run;
  4. it is not empty, and every study an arc cites is in the network with something to cite.

Usage: python packaging/live_check.py [OUT_DIR]
  Reads OUT_DIR/all_result.json, the file the all-network workflow just derived and published, so the
  default derivation is checked on the whole corpus without a second derivation, and derives one study in
  gLV mode, which the daily file does not exercise. Exits 1 and names every violation.
"""
import json
import math
import sys
from pathlib import Path

from grownet.published import FILE, from_payload
from grownet.schema import validate_document

# strength, weight, sd and effect_over_sd are written rounded to 4 decimals; the coefficient is not rounded.
# ROUNDED is a whole unit in the last place, the slack for an identity between two rounded values;
# HALF_UNIT is the most rounding moves one value, which the per-arc bound below propagates.
ROUNDED = 1e-4
HALF_UNIT = 5e-5
EXACT = 1e-9
CENSORED = ("obligate", "abolished")


def _have(e, *names):
    return [n for n in names if getattr(e, n) in (None, "", ())]


def arc_problems(e, derivation: str, k: float | None = None, names: dict | None = None) -> list:
    """What is wrong with one arc, as sentences naming it; [] when nothing is."""
    names = names or {}
    where = (f"{names.get(e.source, e.source)} -> {names.get(e.target, e.target)} "
             f"({e.evidence}, {e.outcome}, {e.medium or e.condition})")
    out = []
    missing = _have(e, "study_ids", "metric", "experiments", "evidence")
    if not (e.medium or e.condition):
        missing.append("medium or condition")
    if e.outcome in CENSORED:
        if e.strength is not None:
            out.append(f"{where}: a {e.outcome} arc has no ratio, and carries strength {e.strength}")
        # the bound itself may be absent, when the rule bounds nothing away from zero; the rule never is
        missing += _have(e, "bound_rule")
    else:
        missing += _have(e, "strength", "metric_with", "metric_without", "n_with", "n_without")
        # an arc with no spread is undetermined (status None) and has no test; any other has one
        if e.status is not None:
            missing += _have(e, "sd", "q_value", "p_value")
    if e.evidence == "biculture" and e.status != "absent" and e.outcome not in CENSORED:
        missing += _have(e, "partner_abundance")
    if missing:
        out.append(f"{where}: missing {', '.join(sorted(set(missing)))}")

    s = e.strength
    if s is not None:
        if e.weight is not None and abs(e.weight - abs(s)) > ROUNDED:
            out.append(f"{where}: weight {e.weight} is not |strength| {abs(s)}")
        if s and e.effect != ("facilitation" if s > 0 else "inhibition"):
            out.append(f"{where}: effect {e.effect} disagrees with the sign of strength {s}")
        ratio = abs(s) / e.sd if e.sd else None
        # recomputed from two values the file already rounded, so the honest tolerance is what that
        # rounding allows for THIS arc, U/sd + |strength| U/sd^2, plus the ratio's own rounding U. A fixed
        # tolerance sat three times above today's worst residual (3.7e-3 at sd 0.21) and the residual grows
        # as 1/sd^2, so a smaller sd would have made it cry wolf or be loosened past use (Craig's agent,
        # on #281). This bound is tighter than the fixed one on almost every arc, and cannot go stale.
        if ratio is not None and e.effect_over_sd is not None and \
                abs(e.effect_over_sd - ratio) > HALF_UNIT / e.sd + abs(s) * HALF_UNIT / e.sd ** 2 + HALF_UNIT:
            out.append(f"{where}: effect_over_sd {e.effect_over_sd} is not |strength| / sd {ratio:.6g}")
        if k is not None and e.sd and e.status in ("present", "absent"):
            below = abs(s) < k * e.sd
            if (e.status == "absent") != below and abs(abs(s) - k * e.sd) > ROUNDED:
                out.append(f"{where}: status {e.status} with |strength| {abs(s)} against k * sd {k * e.sd:.6g}")
        mw, mwo = e.metric_with, e.metric_without
        if derivation == "replicate" and mw and mwo and mw > 0 and mwo > 0 and abs(s - math.log2(mw / mwo)) > ROUNDED:
            out.append(f"{where}: strength {s} is not log2(metric_with / metric_without) {math.log2(mw / mwo):.6g}")
    if e.q_value is not None and e.significance is not None and e.q_value > 0:
        if abs(e.significance - (-math.log10(e.q_value))) > 1e-3 * max(1, e.significance):
            out.append(f"{where}: significance {e.significance} is not -log10(q_value) {-math.log10(e.q_value):.6g}")
    if e.coefficient is not None:
        mw, mwo, x = e.metric_with, e.metric_without, e.partner_abundance
        if not e.coefficient_unit:
            out.append(f"{where}: a coefficient with no unit")
        if derivation == "integrated" and None not in (mw, mwo) and x:
            want = (mw - mwo) / x
            if abs(e.coefficient - want) > EXACT * max(abs(want), abs(e.coefficient)):
                out.append(f"{where}: coefficient {e.coefficient:.6g} is not (metric_with - metric_without) / "
                           f"partner_abundance {want:.6g}")
    return out


def network_problems(net, label: str) -> list:
    """Properties 3 and 4, and every arc's, for one derived network."""
    meta = net.meta
    derivation = (meta.get("settings") or {}).get("derivation", "")
    k = (meta.get("absence") or {}).get("k")
    out = []
    if not net.edges:
        out.append(f"{label}: no arcs at all")
    names = {nid: node.name or nid for nid, node in net.nodes.items()}
    for e in net.edges:
        out += [f"{label}: {p}" for p in arc_problems(e, derivation, k, names)]
        for sid in e.study_ids:
            study = net.studies.get(sid)
            if study is None:
                out.append(f"{label}: {e.source} -> {e.target} cites {sid}, which the network does not list")
            elif not (study.citation or study.url):
                out.append(f"{label}: study {sid} has nothing to cite")
    notes = []
    problems = validate_document(net.to_dict(), notes)
    out += [f"{label}: invalid: {p}" for p in problems]
    out += [f"{label}: validate says: {n}" for n in notes if "does not declare" in n or "INCOMPLETE" in n]
    if meta.get("complete") is False:
        out.append(f"{label}: the run could not read everything: {meta.get('errors')}")
    return out


def check_published(out_dir: str) -> tuple:
    """(problems, what was checked) for the file the workflow just wrote."""
    result = from_payload(json.loads((Path(out_dir) / FILE).read_text(encoding="utf-8")))
    net = result["network"]
    problems = network_problems(net, "All")
    absent = result.get("absent")
    if absent is not None:
        problems += network_problems(absent, "All, below the threshold") if absent.edges else []
        problems += [f"All, below the threshold: {e.source} -> {e.target} has status {e.status}"
                     for e in absent.edges if e.status != "absent"]
    return problems, f"All: {len(net.edges)} arcs" + (f", {len(absent.edges)} below the threshold" if absent else "")


def check_glv_mode(study: str | None = None) -> tuple:
    """(problems, what was checked) for one study derived live in gLV mode, which the daily file is not."""
    from grownet.gui import DEFAULTS, GLV_EXAMPLE_STUDY, glv_mode, run_query
    from grownet.mgrowthdb import MGrowthDBClient
    study = study or GLV_EXAMPLE_STUDY
    result = run_query(MGrowthDBClient(cache_dir=None), [], {**glv_mode(dict(DEFAULTS)), "conditions": study},
                       all_studies=True, published=False)
    net = result["network"]
    problems = [f"gLV mode, {study}: {e}" for e in result["errors"]]
    problems += network_problems(net, f"gLV mode, {study}")
    if not any(e.coefficient is not None for e in net.edges):
        problems.append(f"gLV mode, {study}: no arc carries a coefficient, so the coefficient check ran on nothing")
    return problems, f"gLV mode, {study}: {len(net.edges)} arcs"


def main(out_dir: str = "out") -> int:
    problems, checked = [], []
    for run in (lambda: check_published(out_dir), check_glv_mode):
        found, what = run()
        problems += found
        checked.append(what)
    print("live check: " + "; ".join(checked))
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print(f"live check: {len(problems)} violation(s)" if problems else "live check: every property holds")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
