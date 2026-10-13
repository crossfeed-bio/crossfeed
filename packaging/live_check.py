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
  Reads the file the all-network workflow just derived and published (published.FILE), so the
  default derivation is checked on the whole corpus without a second derivation, and derives one study in
  gLV mode, which the daily file does not exercise. Exits 1 and names every violation, and exits 2
  when the gLV-mode study could not be read from mGrowthDB, which says nothing about the properties.
"""
import json
import math
import sys
from pathlib import Path

from grownet.published import FILE, from_payload

sys.path.insert(0, str(Path(__file__).resolve().parent))   # publish_all, beside this file
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
    payload = json.loads((Path(out_dir) / FILE).read_text(encoding="utf-8"))
    result = from_payload(payload)
    net = result["network"]
    problems = network_problems(net, "All")
    # whether the copy that reads it would serve it: a file every copy refuses (another format, no time it
    # was derived at, another derivation) passed every check here while every copy derived All live, the
    # load the file exists to prevent (found in review)
    from grownet.gui import DEFAULTS
    from grownet.published import why_not_fresh
    refused = why_not_fresh(payload, settings=DEFAULTS)
    if refused:
        problems.append(f"All: {FILE} would not be served at the defaults: {refused}")
    absent = result.get("absent")
    if absent is not None:
        problems += network_problems(absent, "All, below the threshold") if absent.edges else []
        problems += [f"All, below the threshold: {e.source} -> {e.target} has status {e.status}"
                     for e in absent.edges if e.status != "absent"]
    # the same network in every older format, for installed copies (#289): each file written for a format
    # from /v3 on, every field one that format declares, the arcs the same in number, and valid. It looped
    # over one hard-coded name, so at the next move the /v4 copy would have gone out unchecked (found in
    # review).
    import publish_all

    manifest = json.loads((Path(__file__).resolve().parents[1] / "schema" / "format_fields.json")
                          .read_text(encoding="utf-8"))
    for schema in publish_all.older_formats(manifest):
        legacy_path = Path(out_dir) / publish_all.file_for(schema)
        if not legacy_path.exists():
            problems.append(f"{legacy_path.name}: not written, so copies reading {schema} get nothing")
            continue
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            legacy["network"]["edges"]
        except Exception as e:     # noqa: BLE001 - named as that file, not as the current one (found in review)
            problems.append(f"{legacy_path.name}: could not be read: {type(e).__name__}: {e}")
            continue
        # the network AND the arcs below the threshold, which 0.4.0 reads too: a copy whose `absent` was
        # dropped served no arc below the threshold, and one whose `absent.edges` was null made every 0.4.0
        # copy derive All live, with nothing checked (found in review)
        # what a reader of that format checks before serving it: the result format it reads and the
        # derivation its defaults ask for, both from its own versions rather than from the current file,
        # which moves with the current defaults (found in review); and the time, the current file's
        readers = publish_all.READERS.get(schema) or {}
        meta = (legacy.get("network") or {}).get("meta") if isinstance(legacy.get("network"), dict) else None
        meta = meta if isinstance(meta, dict) else {}
        derivation = (meta.get("settings") or {}).get("derivation") if isinstance(meta.get("settings"), dict) \
            else None
        for what, got in (("format", legacy.get("format")), ("derivation", derivation)):
            # as the readers judge: they serve a file that records no derivation
            if got != readers.get(what) and (what == "format" or got is not None):
                problems.append(f"{legacy_path.name}: its {what} is {got!r}, and readers of {schema} accept "
                                f"{readers.get(what)!r}")
        if meta.get("derived_at") != payload["network"].get("meta", {}).get("derived_at"):
            problems.append(f"{legacy_path.name}: its derived_at differs from the current file's")
        parts = [("network", net)] + ([("absent", absent)] if absent is not None else [])
        for part, current in parts:
            problems += _older_part(legacy_path.name, schema, part, legacy.get(part), current, manifest)
    return problems, f"All: {len(net.edges)} arcs" + (f", {len(absent.edges)} below the threshold" if absent else "")


def _older_part(name: str, schema: str, part: str, doc, current, manifest: dict) -> list:
    """The problems of one network inside an older-format file: there, valid, in that format, every field
    one the format declares, and the same arcs in number as the current file's."""
    from grownet.schema import validate_document
    label = name if part == "network" else f"{name}, below the threshold"
    if not isinstance(doc, dict):
        return [f"{label}: missing, while the current file has it"]
    invalid = [f"{label}: invalid: {p}" for p in validate_document(doc)]
    if invalid:
        # its fields are not lists of objects to walk: `"nodes": null` raised here and was reported as the
        # CURRENT file unreadable, losing its results (found in review)
        return invalid
    problems = []
    if doc.get("schema") != schema:
        problems.append(f"{label}: says {doc.get('schema')}, where the file is for {schema}")
    fields = manifest["formats"].get(schema, {})
    for kind, key in (("node", "nodes"), ("edge", "edges"), ("study", "studies")):
        extra = {k for item in doc.get(key, []) for k in item} - set(fields.get(kind, ()))
        if extra:
            problems.append(f"{label}: {key} carry fields {schema} does not declare: {sorted(extra)}")
    if len(doc.get("edges", [])) != len(current.edges):
        problems.append(f"{label}: a different number of arcs than the current one")
    return problems


def check_glv_mode(study: str | None = None) -> tuple:
    """(problems, what was checked) for one study derived live in gLV mode, which the daily file is not."""
    from grownet.gui import DEFAULTS, GLV_EXAMPLE_STUDY, glv_mode, run_query
    from grownet.mgrowthdb import MGrowthDBClient
    study = study or GLV_EXAMPLE_STUDY
    result = run_query(MGrowthDBClient(cache_dir=None), [], {**glv_mode(dict(DEFAULTS)), "conditions": study},
                       all_studies=True, published=False)
    net = result["network"]
    if result["errors"]:
        # mGrowthDB could not be read: that is a run that could not check, not a property that broke
        raise RuntimeError(f"gLV mode, {study}: mGrowthDB could not be read: {'; '.join(result['errors'])}")
    problems = network_problems(net, f"gLV mode, {study}")
    if not any(e.coefficient is not None for e in net.edges):
        problems.append(f"gLV mode, {study}: no arc carries a coefficient, so the coefficient check ran on nothing")
    return problems, f"gLV mode, {study}: {len(net.edges)} arcs"


def main(out_dir: str = "out") -> int:
    """0 when every property holds, 1 when one breaks, 2 when the check could not run at all.

    A crash or an mGrowthDB outage used to exit 1 and open an issue saying arcs broke a property, naming
    none (found in review). The outcome is also written to `$GITHUB_OUTPUT`, so the workflow words the
    issue by what happened.
    """
    import os
    problems, checked, could_not = [], [], []
    # the published file is local and was just written: one grownet cannot read IS a broken property (every
    # copy's fetch would refuse it), never "could not run" (found in review)
    try:
        found, what = check_published(out_dir)
        problems += found
        checked.append(what)
    except Exception as e:         # noqa: BLE001 - an unreadable published file is a violation
        problems.append(f"All: the published file could not be read: {type(e).__name__}: {e}")
    # the gLV-mode study is read from mGrowthDB, so a failure there is an outage or a crash: could not run
    try:
        found, what = check_glv_mode()
        problems += found
        checked.append(what)
    except Exception as e:         # noqa: BLE001 - reported as could not run, never as a violation
        could_not.append(f"{type(e).__name__}: {e}")
    print("live check: " + ("; ".join(checked) or "nothing checked"))
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    for c in could_not:
        print(f"  could not run: {c}", file=sys.stderr)
    outcome = "violation" if problems else "error" if could_not else "ok"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"outcome={outcome}\n")
    if problems:
        print(f"live check: {len(problems)} violation(s)")
        return 1
    if could_not:
        print(f"live check: could not run ({len(could_not)} part(s)); this says nothing about the properties")
        return 2
    print("live check: every property holds")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
