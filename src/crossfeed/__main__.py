"""crossfeed command line: derive a network for any mGrowthDB study, or validate the neutral format.

  python -m crossfeed derive SMGDB00000004 --live                 # fetch + derive (provisional baseline)
  python -m crossfeed derive SMGDB00000004 --fixture records.json  # offline, from interaction records
  python -m crossfeed validate network.json                       # check a network against the schema
  python -m crossfeed schema --out interaction_network.schema.json # emit the neutral-format schema
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from .attribution import render_attribution
from .mgrowthdb import MGrowthDBError, records_to_network
from .schema import schema_json, validate_document


def _build(records, study_id, source_db):
    net = records_to_network(records, meta={"source_db": source_db, "study_id": study_id})
    problems = net.validate()
    if problems:
        raise SystemExit("network invalid:\n  " + "\n  ".join(problems))
    return net


def _load_deriver(spec):
    """Load a custom Deriver given as `module.path:ClassName` (or a ready instance of the same name)."""
    import importlib
    if ":" not in spec:
        raise SystemExit(f"--deriver must be 'module:ClassName', got {spec!r}")
    mod_name, _, cls_name = spec.partition(":")
    try:
        module = importlib.import_module(mod_name)
    except ImportError as e:
        raise SystemExit(f"--deriver: cannot import module {mod_name!r}: {e}") from e
    obj = getattr(module, cls_name, None)
    if obj is None:
        raise SystemExit(f"--deriver: {mod_name!r} has no {cls_name!r}")
    return obj() if isinstance(obj, type) else obj


def _derive(a):
    if a.deriver and not a.live:
        print("--deriver applies to --live (it derives from raw growth data); "
              "--fixture already holds derived records.", file=sys.stderr)
        return 2
    if a.live:
        from .derive import derive_interactions
        from .mgrowthdb import MGrowthDBClient
        deriver = _load_deriver(a.deriver) if a.deriver else None
        try:
            records, skipped = derive_interactions(MGrowthDBClient(), a.study, deriver=deriver)
        except MGrowthDBError as e:
            print(f"live fetch failed: {e}", file=sys.stderr)
            return 1
        source_db = "mGrowthDB (live)"
    else:
        with open(a.fixture, encoding="utf-8") as f:
            records, skipped = json.load(f), []
        source_db = "mGrowthDB (fixture)"

    net = _build(records, a.study, source_db)
    if a.format == "graphml":
        from .export import to_graphml
        payload = to_graphml(net)
    else:
        payload = net.to_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {a.out}: {len(net.nodes)} nodes, {len(net.edges)} edges")
    else:
        print(payload)

    print(render_attribution(net), file=sys.stderr)
    if skipped:
        print(f"\nskipped {len(skipped)} pair(s) the data did not cleanly support:", file=sys.stderr)
        for label, reason in skipped:
            print(f"  - {label}: {reason}", file=sys.stderr)
    if not net.edges:
        top = Counter(r.split(";")[0].strip() for _, r in skipped).most_common(1)
        why = f" Most common reason: {top[0][0]}." if top else ""
        print(f"\nNO interactions were derived for {a.study}: the network is empty.{why}\n"
              "The provisional baseline handles pairwise (two-member) co-cultures only, so a study built "
              "on larger or deletion consortia yields nothing until a method suited to its design is "
              "chosen (see docs/METHOD_NOTES.md).", file=sys.stderr)
    return 0


def _validate(a):
    with open(a.file, encoding="utf-8") as f:
        doc = json.load(f)
    problems = validate_document(doc)
    if problems:
        print(f"INVALID: {a.file}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"valid: {a.file}")
    return 0


def _schema(a):
    out = schema_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"wrote {a.out}")
    else:
        sys.stdout.write(out)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="crossfeed", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("derive", help="derive an interaction network for a study")
    d.add_argument("study", help="mGrowthDB study id, e.g. SMGDB00000004")
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true", help="fetch the real study from the mGrowthDB API")
    g.add_argument("--fixture", help="path to a JSON list of interaction records (offline)")
    d.add_argument("--deriver", metavar="MODULE:CLASS",
                   help="a custom Deriver to use instead of the provisional baseline (with --live)")
    d.add_argument("--format", choices=["json", "graphml"], default="json",
                   help="output format: json (the neutral format, default) or graphml (for network tools)")
    d.add_argument("--out", help="write the network here (default: stdout)")
    d.set_defaults(fn=_derive)

    v = sub.add_parser("validate", help="validate a network JSON against the neutral-format schema")
    v.add_argument("file", help="path to a network JSON document")
    v.set_defaults(fn=_validate)

    s = sub.add_parser("schema", help="emit the neutral-format JSON schema")
    s.add_argument("--out", help="write the schema here (default: stdout)")
    s.set_defaults(fn=_schema)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
