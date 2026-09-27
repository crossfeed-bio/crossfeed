"""crossfeed command line: derive a network for any mGrowthDB study, or validate the neutral format.

  python -m crossfeed derive SMGDB00000004 --live                 # fetch + derive one study
  python -m crossfeed derive --live --species "Faecalibacterium duncaniae" "Blautia hydrogenotrophica"
  python -m crossfeed derive SMGDB00000004 --fixture records.json  # offline, from interaction records
  python -m crossfeed validate network.json                       # check a network against the schema
  python -m crossfeed schema --out interaction_network.schema.json # emit the neutral-format schema
  python -m crossfeed gui                                          # a local page for species names
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from .attribution import render_attribution
from .mgrowthdb import MGrowthDBError, records_to_network
from .schema import schema_json, validate_document


def _build(records, study_id, source_db, extra=None):
    meta = {"source_db": source_db, "study_id": study_id, **(extra or {})}
    net = records_to_network(records, meta=meta)
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
    if a.species:
        return _derive_species(a)
    if not a.study:
        print("derive needs a study id, or --species with names (see crossfeed derive --help)", file=sys.stderr)
        return 2
    if a.deriver and not a.live:
        print("--deriver applies to --live (it derives from raw growth data); "
              "--fixture already holds derived records.", file=sys.stderr)
        return 2
    extra = None
    if a.live:
        from .derive import derive_interactions, output_meta
        from .mgrowthdb import MGrowthDBClient
        deriver = _load_deriver(a.deriver) if a.deriver else None
        try:
            records, skipped = derive_interactions(MGrowthDBClient(), a.study, deriver=deriver,
                                                   metric=a.metric, spike_factor=a.spike_factor,
                                                   dropout=not a.no_dropout,
                                                   include_non_batch=a.include_non_batch,
                                                   no_growth_alpha=a.no_growth_alpha,
                                                   no_growth_factor=a.no_growth_factor)
            records, extra = output_meta(records, a.include_low_quality, a.correction, a.absence_threshold,
                                         a.no_growth_alpha, a.no_growth_factor)
            extra["settings"] = {"metric": a.metric, "spike_factor": a.spike_factor,
                                 "absence_threshold": a.absence_threshold,
                                 "include_low_quality": a.include_low_quality, "correction": a.correction,
                                 "include_dropout": not a.no_dropout, "include_non_batch": a.include_non_batch,
                                 "no_growth_alpha": a.no_growth_alpha, "no_growth_factor": a.no_growth_factor,
                                 "deriver": a.deriver or ""}
        except MGrowthDBError as e:
            print(f"live fetch failed: {e}", file=sys.stderr)
            return 1
        source_db = "mGrowthDB (live)"
    else:
        with open(a.fixture, encoding="utf-8") as f:
            records, skipped = json.load(f), []
        source_db = "mGrowthDB (fixture)"

    net = _build(records, a.study, source_db, extra)
    return _emit(a, net, skipped, extra, a.study)


def _derive_species(a):
    """What the local page does, from the command line: names to studies to one network (#78)."""
    if not a.live:
        print("--species searches mGrowthDB, so it needs --live", file=sys.stderr)
        return 2
    if a.deriver:
        print("--species uses the default derivation; --deriver applies to one study", file=sys.stderr)
        return 2
    from .gui import DEFAULTS, run_query
    from .mgrowthdb import MGrowthDBClient
    settings = {**DEFAULTS, "metric": a.metric, "spike_factor": a.spike_factor,
                "absence_threshold": a.absence_threshold, "include_low_quality": a.include_low_quality,
                "correction": a.correction, "include_dropout": not a.no_dropout,
                "include_non_batch": a.include_non_batch, "studies": a.study or "",
                "only_entered": not a.all_partners, "exclude_studies": a.exclude_studies,
                "no_growth_alpha": a.no_growth_alpha,
                "no_growth_factor": a.no_growth_factor}
    try:
        result = run_query(MGrowthDBClient(), a.species, settings)
    except MGrowthDBError as e:
        print(f"live fetch failed: {e}", file=sys.stderr)
        return 1
    for entry, matches in result["resolved"]:
        names = ", ".join(f"{name} ({tid})" for tid, name in sorted(matches.items()))
        print(f"{entry}: {names}", file=sys.stderr)
    if result["unresolved"]:
        print("not in mGrowthDB: " + ", ".join(result["unresolved"]), file=sys.stderr)
    for error in result["errors"]:
        print(error, file=sys.stderr)
    print("studies searched: " + (", ".join(result["studies"]) or "none"), file=sys.stderr)
    net = result["network"]
    problems = net.validate()
    if problems:
        raise SystemExit("network invalid:\n  " + "\n  ".join(problems))
    extra = {"absence": result["absence"], "hidden": result["hidden"]}
    return _emit(a, net, result["skipped"], extra, " and ".join(a.species))


def _emit(a, net, skipped, extra, label):
    """Write the network and report what it holds, what was skipped, and what is hidden."""
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

    if a.to_cytoscape:
        from .cytoscape import CytoscapeError, send
        try:
            sent = send(net, port=a.cytoscape_port, name=label)
        except CytoscapeError as e:
            print(f"crossfeed: {e}", file=sys.stderr)
            return 1
        print(f"sent to Cytoscape: network {sent['suid']}"
              + (f", style {sent['style']}" if sent["style"] else "")
              + (f"; {sent['warning']}" if sent.get("warning") else ""), file=sys.stderr)

    print(render_attribution(net), file=sys.stderr)
    if skipped:
        print(f"\nskipped {len(skipped)} pair(s) the data did not cleanly support:", file=sys.stderr)
        for label, reason in skipped:
            print(f"  - {label}: {reason}", file=sys.stderr)
    if extra:
        if extra["absence"]["absent"]:
            print(f"\n{extra['absence']['absent']} edge(s) have status absent (|log2 mean| < "
                  f"{extra['absence']['k']:g} * sd); they are in the file, and the Cytoscape style hides them "
                  "by default.", file=sys.stderr)
        if extra["hidden"]["low_quality"]:
            print(f"{extra['hidden']['low_quality']} low-quality edge(s) hidden; show them with "
                  "--include-low-quality.", file=sys.stderr)
    if not net.edges:
        top = Counter(r.split(";")[0].strip() for _, r in skipped).most_common(1)
        why = f" Most common reason: {top[0][0]}." if top else ""
        print(f"\nNO interactions were derived for {label}: the network is empty.{why}\n"
              "crossfeed derives interactions from pairwise (two-member) co-cultures and from drop-out "
              "designs (a community plus the same community without one member); other larger communities "
              "yield nothing until a method suited to their design is chosen (see docs/METHOD_NOTES.md).",
              file=sys.stderr)
    return 0


def _style(a):
    """The style as a file, for a Cytoscape that is not running or a user who prefers to import it."""
    from .cytoscape import style
    payload = json.dumps([style()], indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print(f"wrote {a.out}: import it with File, Import, Styles from File")
    else:
        print(payload)
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


def _gui(a):
    from .gui import serve
    serve(port=a.port, open_browser=not a.no_browser)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The command line, apart from running it, so the help page can be checked against it (#78)."""
    ap = argparse.ArgumentParser(prog="crossfeed", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("derive", help="derive an interaction network for a study, or for species")
    d.add_argument("study", nargs="?", default="",
                   help="mGrowthDB study id, e.g. SMGDB00000004; with --species, comma separated study ids "
                        "to search instead of every study holding the species")
    d.add_argument("--species", nargs="+", metavar="NAME",
                   help="species or strain names, or NCBI taxon ids, as on the local page: every study holding "
                        "them is searched and one network returned (needs --live)")
    d.add_argument("--exclude-studies", default="", metavar="IDS",
                   help="with --species, comma separated study ids never to search (default: none)")
    d.add_argument("--all-partners", action="store_true",
                   help="with --species, keep interactions with species not entered too (the page's "
                        "'Only interactions between the species entered', unticked)")
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true", help="fetch the real study from the mGrowthDB API")
    g.add_argument("--fixture", help="path to a JSON list of interaction records (offline)")
    d.add_argument("--deriver", metavar="MODULE:CLASS",
                   help="a custom Deriver to use instead of the provisional baseline (with --live)")
    d.add_argument("--metric", choices=["auc", "max"], default="auc",
                   help="the growth property compared (default: auc, the area under the curve)")
    d.add_argument("--include-low-quality", action="store_true",
                   help="also emit the low-quality edges hidden by default (pooled strains, an unclean drop-out); "
                        "single-replicate edges are always emitted, flagged")
    d.add_argument("--no-dropout", action="store_true",
                   help="leave out arcs from drop-out designs (a community against the same community without "
                        "one member); included by default, labeled evidence dropout")
    d.add_argument("--include-non-batch", action="store_true",
                   help="also derive from chemostat and serial dilution experiments (excluded by default: "
                        "a continuous-culture curve is not comparable with a batch one)")
    d.add_argument("--to-cytoscape", action="store_true",
                   help="also send the network into a running Cytoscape through CyREST on localhost")
    d.add_argument("--cytoscape-port", type=int, default=1234, metavar="PORT",
                   help="the CyREST port to send to (default 1234)")
    d.add_argument("--absence-threshold", type=float, default=1.0, metavar="K",
                   help="an edge is absent when |log2 mean| < K * sd (default 1, the mean plus or minus sd rule; "
                        "0 marks nothing absent)")
    d.add_argument("--correction", choices=["bh", "by"], default="bh",
                   help="multiple testing correction: bh (Benjamini-Hochberg, default) or by (Benjamini-Yekutieli)")
    d.add_argument("--spike-factor", type=float, default=100.0,
                   help="leave out a curve with one or two points this many times above both neighbours "
                        "(0 keeps all)")
    d.add_argument("--no-growth-alpha", type=float, default=None, metavar="ALPHA",
                   help="a set has not grown when its rise from the first time point is not significant at "
                        "ALPHA (paired t-test on log2 max / start per replicate; default 0.05, 0 switches the "
                        "rule off)")
    d.add_argument("--no-growth-factor", type=float, default=None, metavar="F",
                   help="a set that rose at least F times (geometric mean over replicates) has grown whatever "
                        "the test says (default 1.5; 2, one doubling, is more stringent; 0 leaves the test alone)")
    d.add_argument("--format", choices=["json", "graphml"], default="json",
                   help="output format: json (the neutral format, default) or graphml (for network tools)")
    d.add_argument("--out", help="write the network here (default: stdout)")
    d.set_defaults(fn=_derive)

    y = sub.add_parser("style", help="write the Cytoscape style, for Import Styles from File")
    y.add_argument("--out", help="write it here (default: stdout)")
    y.set_defaults(fn=_style)

    v = sub.add_parser("validate", help="validate a network JSON against the neutral-format schema")
    v.add_argument("file", help="path to a network JSON document")
    v.set_defaults(fn=_validate)

    g2 = sub.add_parser("gui", help="open a local page: type species names, get their interactions")
    g2.add_argument("--port", type=int, default=0, help="port to serve on (default: a free one)")
    g2.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    g2.set_defaults(fn=_gui)

    s = sub.add_parser("schema", help="emit the neutral-format JSON schema")
    s.add_argument("--out", help="write the schema here (default: stdout)")
    s.set_defaults(fn=_schema)

    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
