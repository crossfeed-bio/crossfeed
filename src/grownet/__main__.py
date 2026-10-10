"""grownet command line: derive interaction networks from mGrowthDB.

  python -m grownet derive SMGDB00000004 --live                 # every species in one study
  python -m grownet derive --live --species "Faecalibacterium duncaniae" \
      "Blautia hydrogenotrophica" "Roseburia intestinalis"
  python -m grownet derive SMGDB00000004 --fixture records.json  # offline, from interaction records
  python -m grownet validate network.json                       # check a network against the schema
  python -m grownet schema --out interaction_network.schema.json # emit the neutral-format schema
  python -m grownet gui                                          # a local page for species names
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from .adapter import condensed, unread
from .attribution import render_attribution
from .derive import CAPACITY_MAX_FALL
from .mgrowthdb import MGrowthDBError, records_to_network
from .schema import schema_json, validate_document

DERIVE_EXAMPLES = """examples:
  the local page's Example, written to a file, with its report, and sent to Cytoscape:
    grownet derive --live --species "Faecalibacterium duncaniae" "Blautia hydrogenotrophica" "Roseburia intestinalis" \\
        --out example.json --report example_report.txt --to-cytoscape

  a strain and a taxon id, every partner, as GraphML:
    grownet derive --live --species "Faecalibacterium duncaniae A2-165" 476272 --all-partners \\
        --format graphml --out example.graphml

  a genus (all its species in mGrowthDB) with every partner, one node per genus:
    grownet derive --live --species Bacteroides --all-partners --merge-genera --out bacteroides.json

  all of mGrowthDB (the page's All), arcs merged across studies and then to genus:
    grownet derive --live --all --merge-arcs --merge-genera --out all_genera.json

  every species in one study, stricter about what counts as an interaction:
    grownet derive SMGDB00000004 --live --absence-threshold 2 --out study4.json

  one medium only, which is what a gLV simulation wants (the page's second box):
    grownet derive --live --species Blautia --conditions "Wilkins-Chalgren" --out wc.json

  one named comparison, with the monocultures it is made against:
    grownet derive --live --species Bacteroides Roseburia --conditions EMGDB000000024 --out one_arc.json

  the adjacency matrix of one study, as CSV:
    grownet derive SMGDB00000004 --live --format matrix --out study4_matrix.csv

  the parameters of a generalized Lotka-Volterra simulation, with the growth rates beside them:
    grownet derive SMGDB00000004 --live --report-rates --glv study4_glv.zip \\
        --rates study4_rates.csv --report study4_report.txt

  the same parameters sent into a waiting R session (in R: library(grownet); grownet_listen()):
    grownet derive SMGDB00000004 --live --report-rates --to-r

"""


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


def _metric(a) -> str:
    from .gui import metric_name
    return metric_name({"metric": a.metric, "rate_method": a.rate_method, "rate_window": a.rate_window})


def _rate_flags(a) -> str:
    """Why the growth-rate options cannot be used as given, or "": checked before anything is derived, so
    a run never writes a network and then refuses to write the files beside it."""
    if a.report_rates and not a.live:
        return "--report-rates reads the monoculture curves, so it needs --live"
    for flag, path in (("--rates", a.rates), ("--glv", a.glv), ("--to-r", a.to_r)):
        if path and not a.report_rates:
            return f"{flag} writes the growth rates of the run, so it needs --report-rates"
    if a.steady_check and not a.report_rates:
        return "--steady-check scores the growth rates and coefficients of the run, so it needs --report-rates"
    if a.glv and a.metric != "growth_rate" and not a.deriver and a.derivation == "replicate":
        # a coefficient divides by a log2 ratio of growth rates, so the area or the maximum cannot make
        # one (#119); --glv-mode sets both at once
        return ("--glv writes fitted gLV coefficients, and a coefficient needs the log2 ratio of a "
                f"growth rate, not of {a.metric}: add --metric growth_rate, or use --glv-mode")
    return ""


def _derive(a):
    if a.glv_mode:
        # the button sets them, and says so, rather than leaving a reader to remember them (#113). The
        # the metric came with the coefficients of #119: L is the log2 ratio of a growth rate. The rate
        # method is the reader's own setting (easylinear by default), with the lag always Baranyi's.
        a.report_rates, a.no_dropout, a.metric = True, True, "growth_rate"
        print("gLV mode: growth rates on, drop-out communities off, the comparison on the growth rate",
              file=sys.stderr)
    problem = _rate_flags(a)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    if a.species or a.all_studies:
        return _derive_species(a)
    if not a.study:
        print("derive needs a study id, or --species with names (see grownet derive --help)", file=sys.stderr)
        return 2
    if a.deriver and not a.live:
        print("--deriver applies to --live (it derives from raw growth data); "
              "--fixture already holds derived records.", file=sys.stderr)
        return 2
    extra = None
    if a.live:
        from .derive import derive_interactions, output_meta
        from .mgrowthdb import MGrowthDBClient
        # --no-cache reads everything again rather than reusing what an earlier run kept (#182)
        client = MGrowthDBClient(**({"cache_dir": None} if a.no_cache else {}))
        # --derivation picks the integrated form here as it does on the search path. It was read only by
        # the pre-flight guard and by --species, so `derive <STUDY> --derivation integrated` quietly ran
        # the default derivation and recorded nothing (found 2026-10-06).
        from .gui import chosen_deriver
        deriver = _load_deriver(a.deriver) if a.deriver else chosen_deriver(
            {"derivation": a.derivation, "spike_factor": a.spike_factor,
             "include_non_batch": a.include_non_batch}, client)
        try:
            from .selection import parse as parse_selection
            records, skipped = derive_interactions(client, a.study, deriver=deriver,
                                                   metric=_metric(a), spike_factor=a.spike_factor,
                                                   dropout=not a.no_dropout,
                                                   include_non_batch=a.include_non_batch,
                                                   no_growth_alpha=a.no_growth_alpha,
                                                   no_growth_factor=a.no_growth_factor,
                                                   capacity_max_fall=a.capacity_max_fall,
                                                   selection=parse_selection(a.conditions))
            records, extra = output_meta(records, a.include_low_quality, a.correction, a.absence_threshold,
                                         a.no_growth_alpha, a.no_growth_factor, a.merge_arcs, a.min_studies,
                                         a.merge_genera, max_adjusted_p=a.max_adjusted_p,
                                         include_absent=a.include_absent,
                                         # the derivation says what it tests (#142 item 5)
                                         deriver=deriver)
            extra["settings"] = {"metric": a.metric, "rate_method": a.rate_method, "rate_window": a.rate_window,
                                 "derivation": a.derivation,
                                 "merge_arcs": a.merge_arcs, "min_studies": a.min_studies,
                                 "merge_genera": a.merge_genera,
                                 "spike_factor": a.spike_factor,
                                 "capacity_max_fall": a.capacity_max_fall,
                                 "absence_threshold": a.absence_threshold,
                                 "include_low_quality": a.include_low_quality, "correction": a.correction,
                                 "include_dropout": not a.no_dropout, "include_non_batch": a.include_non_batch,
                                 "no_growth_alpha": a.no_growth_alpha, "no_growth_factor": a.no_growth_factor,
                                 "max_adjusted_p": a.max_adjusted_p, "report_rates": a.report_rates,
                                 "conditions": " ".join(a.conditions),
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
    if a.live:
        from .mgrowthdb import data_versions
        net.meta["data"] = data_versions(client, [a.study], net.meta["derived_at"])
    errors = []
    failed = unread(skipped)
    if failed:
        # a request that failed after its retries: the network is incomplete (audit step 7)
        errors.append(f"{len(failed)} replicate(s) or growth curve(s) could not be read from mGrowthDB (for "
                      f"example {failed[0][0]}: {failed[0][1]}); the result is incomplete, so run it again")
        print(f"warning: {errors[0]}", file=sys.stderr)
    organism_rates = {}
    if a.report_rates:
        organism_rates, skipped = _rates_of(a, client, [a.study], net, skipped, records)
    result = {"study": a.study, "entries": [], "resolved": [], "unresolved": [], "studies": [a.study],
              "rates": organism_rates, "client": client if a.live else None,
              "skipped": skipped, "errors": errors, "network": net}
    return _emit(a, net, skipped, extra, a.study, result)


def _derive_species(a):
    """What the local page does, from the command line: names to studies to one network (#78)."""
    flag = "--all" if a.all_studies else "--species"
    if a.all_studies and a.species:
        print("--all derives every study; leave out --species", file=sys.stderr)
        return 2
    if not a.live:
        print(f"{flag} searches mGrowthDB, so it needs --live", file=sys.stderr)
        return 2
    if a.deriver:
        print(f"{flag} uses the default derivation; --deriver applies to one study", file=sys.stderr)
        return 2
    from .gui import DEFAULTS, run_query
    from .mgrowthdb import MGrowthDBClient
    settings = {**DEFAULTS, "metric": a.metric, "rate_method": a.rate_method, "rate_window": a.rate_window,
                "spike_factor": a.spike_factor, "capacity_max_fall": a.capacity_max_fall,
                "absence_threshold": a.absence_threshold, "include_low_quality": a.include_low_quality,
                "include_absent": a.include_absent,
                "correction": a.correction, "include_dropout": not a.no_dropout,
                "include_non_batch": a.include_non_batch,
                "conditions": "\n".join([*a.conditions, *(a.study or "").split(",")]).strip(),
                "only_entered": not a.all_partners, "exclude_studies": a.exclude_studies,
                "merge_arcs": a.merge_arcs, "min_studies": a.min_studies, "merge_genera": a.merge_genera,
                "report_rates": a.report_rates, "derivation": a.derivation,
                "no_growth_alpha": a.no_growth_alpha,
                "no_growth_factor": a.no_growth_factor, "max_adjusted_p": a.max_adjusted_p}
    client = MGrowthDBClient(**({"cache_dir": None} if a.no_cache else {}))
    try:
        result = run_query(client, a.species or [], settings, all_studies=a.all_studies,
                           published=not a.no_published)
        result["client"] = client
    except MGrowthDBError as e:
        print(f"live fetch failed: {e}", file=sys.stderr)
        return 1
    for entry, matches in result["resolved"]:
        names = ", ".join(f"{name} ({tid})" for tid, name in sorted(matches.items()))
        print(f"{entry}: {names}", file=sys.stderr)
    for entry in result["unresolved"]:
        hints = result["suggestions"].get(entry)
        print(f"not used: {entry}: {result['reasons'].get(entry, 'not in mGrowthDB')}"
              + (f" (did you mean: {', '.join(hints)}?)" if hints else ""), file=sys.stderr)
    for error in result["errors"]:
        print(error, file=sys.stderr)
    print("studies searched: " + (", ".join(result["studies"]) or "none"), file=sys.stderr)
    net = result["network"]
    problems = net.validate()
    if problems:
        raise SystemExit("network invalid:\n  " + "\n  ".join(problems))
    extra = {"absence": result["absence"], "hidden": result["hidden"]}
    if not net.edges:
        import html

        from .gui import _empty_reason
        print("\nno interactions: " + html.unescape(_empty_reason(result)), file=sys.stderr)
    label = "all of mGrowthDB" if a.all_studies else " and ".join(a.species)
    return _emit(a, net, result["skipped"], extra, label, result)


def _rates_of(a, client, study_ids, net, skipped, records=None):
    """(rates by node id, skipped): the monoculture growth rates of these studies, keyed by the network's
    own nodes, with the network's meta recording them as the page does.

    A derivation that fits each row carries its own rate and self-limitation on every arc (#127), and
    those are the parameters that go with its coefficients, so they are used when they are there rather
    than fitting the monocultures a second way.
    """
    from . import matrix, rates
    from .derive import growth_rates
    from .integrated import METRIC as INTEGRATED
    from .integrated import fitted_rates
    fitted = fitted_rates(records or [])
    if fitted:
        # An organism whose fit implies no plateau is given the measured one inside `two_stage`, before
        # its partners are fitted against it, from the monocultures of its own condition (#142 item 7).
        # The second pass that used to read every study's monocultures and substitute a plateau afterwards
        # published a row no fit had produced, and is gone; each row's `capacity_source` says where its
        # diagonal came from, or why it has none.
        for nid, entry in sorted(fitted.items()):
            if entry.get("capacity") is None:
                print(f"{entry.get('name', nid)}: {entry.get('capacity_source') or 'no plateau'}, so it "
                      "has no self-limitation and no row in a matrix", file=sys.stderr)
        net.meta["growth_rates"] = matrix.rate_meta(net, fitted, INTEGRATED)
        return fitted, skipped
    found, rate_skips = growth_rates(client, study_ids, wanted=set(net.nodes),
                                     rate_method=a.rate_method, window=a.rate_window,
                                     spike_factor=a.spike_factor,
                                     capacity_max_fall=a.capacity_max_fall)
    organism_rates = matrix.for_nodes(net, found)
    net.meta["growth_rates"] = matrix.rate_meta(net, organism_rates,
                                                rates.method_name(a.rate_method, a.rate_window))
    return organism_rates, skipped + rate_skips


def _emit(a, net, skipped, extra, label, result):
    """Write the network, and the report when asked, and say what it holds, skipped and hid."""
    if a.format == "graphml":
        from .export import to_graphml
        payload = to_graphml(net)
    elif a.format == "matrix":
        from .matrix import matrix_csv
        payload = matrix_csv(net)        # the plain adjacency matrix: its diagonal is 0, the gLV one is -1
    else:
        payload = net.to_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {a.out}: {len(net.nodes)} nodes, {len(net.edges)} edges")
    else:
        print(payload)

    if a.report:
        # the same report the local page shows and downloads (#76): every setting, the version, every reason
        from .report import report_text
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(report_text(result))
        print(f"wrote the report to {a.report}", file=sys.stderr)

    organism_rates = result.get("rates") or {}
    if (a.rates or a.glv) and not organism_rates:
        print("no growth rate could be computed for any organism of this network; the report says why "
              "each one has none", file=sys.stderr)
        return 1
    if a.rates:
        from .matrix import rates_csv
        with open(a.rates, "w", encoding="utf-8") as f:
            f.write(rates_csv(organism_rates, net))
        print(f"wrote the growth rates to {a.rates}: {len(organism_rates)} organism(s)", file=sys.stderr)
    checked = []
    if a.steady_check and organism_rates:
        # a chemostat steady state is an independent test of the parameters: it satisfies A x = -(r - D)
        # and was never used to fit them (#125)
        from . import steady
        from .matrix import CannotConvert, coefficients
        try:
            got = coefficients(net, organism_rates)
        except CannotConvert as e:
            print(f"no steady-state check: {e}", file=sys.stderr)
        else:
            found = steady.find(result["client"], net) if result.get("client") is not None else []
            checked = steady.check(got, organism_rates, found)
            scored = sum(1 for one in checked if one["used"])
            print(f"steady-state check: {scored} chemostat(s) scored, {len(checked) - scored} not "
                  "(the report says why each)", file=sys.stderr)
            result["steady"] = checked
            if a.report:
                from .report import report_text
                with open(a.report, "w", encoding="utf-8") as f:
                    f.write(report_text(result))
    if a.glv:
        from . import steady as steady_module
        from .matrix import glv_package
        extra_files = {"steady_state_check.txt": steady_module.as_text(checked)} if a.steady_check else None
        with open(a.glv, "wb") as f:
            f.write(glv_package(net, organism_rates, extra_files))
        print(f"wrote the gLV parameters to {a.glv}: the interaction matrix, the growth rates and a README",
              file=sys.stderr)

    if a.to_r:
        from .matrix import glv_payload
        from .rbridge import DEFAULT_PORT, RError, send
        try:
            answer = send(glv_payload(net, organism_rates), port=a.r_port or DEFAULT_PORT)
        except RError as e:
            print(f"grownet: {e}", file=sys.stderr)
            return 1
        print(f"sent to R: {answer.get('organisms', 0)} organism(s), "
              f"{answer.get('growth_rates', 0)} growth rate(s), "
              f"{answer.get('placeholders', 0)} placeholder cell(s); the R session printed what it holds",
              file=sys.stderr)

    if a.to_cytoscape:
        from .cytoscape import CytoscapeError, send
        try:
            sent = send(net, port=a.cytoscape_port, name=label)
        except CytoscapeError as e:
            print(f"grownet: {e}", file=sys.stderr)
            return 1
        print(f"sent to Cytoscape: network {sent['suid']}"
              + (f", style {sent['style']}" if sent["style"] else "")
              + (f"; {sent['warning']}" if sent.get("warning") else ""), file=sys.stderr)

    print(render_attribution(net), file=sys.stderr)
    skipped = condensed(skipped)
    if skipped:
        print(f"\nskipped {len(skipped)} pair(s) the data did not cleanly support:", file=sys.stderr)
        for label, reason in skipped:
            print(f"  - {label}: {reason}", file=sys.stderr)
    if extra:
        if extra["absence"]["absent"]:
            left_out = extra["hidden"].get("absent", 0)
            where = ("left out of the network, so the file holds the interactions it reports; keep them with "
                     "--include-absent" if left_out else "in the file, with status absent")
            print(f"\n{extra['absence']['absent']} comparison(s) came out below the absence threshold "
                  f"(|log2 mean| < {extra['absence']['k']:g} * sd): {where}. The report lists them.",
                  file=sys.stderr)
        if extra["hidden"]["low_quality"]:
            print(f"{extra['hidden']['low_quality']} low-quality edge(s) hidden; show them with "
                  "--include-low-quality.", file=sys.stderr)
    if not net.edges and "reasons" not in result:        # a species search has said why already
        top = Counter(r.split(";")[0].strip() for _, r in skipped).most_common(1)
        why = f" Most common reason: {top[0][0]}." if top else ""
        print(f"\nNO interactions were derived for {label}: the network is empty.{why}\n"
              "grownet derives interactions from pairwise (two-member) co-cultures and from drop-out "
              "designs (a community plus the same community without one member); other larger communities "
              "yield nothing until a method suited to their design is chosen (see docs/METHOD_NOTES.md).",
              file=sys.stderr)
    return 0


def _probability(text: str) -> float:
    """A threshold for --max-adjusted-p: a number above 0 and at most 1."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(f"{text} is not a p-value threshold (above 0, at most 1)")
    return value


def _style(a):
    """The style as a file, for a Cytoscape that is not running or a user who prefers to import it."""
    from .cytoscape import style_xml
    payload = style_xml()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {a.out}: import it with File, Import, Styles from File")
    else:
        print(payload, end="")


def _validate(a):
    with open(a.file, encoding="utf-8") as f:
        doc = json.load(f)
    notes = []
    problems = validate_document(doc, notes)
    if problems:
        print(f"INVALID: {a.file}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    from .model import SCHEMA
    read = doc.get("schema")
    # The note belongs to /v0 alone: that is where `significance` is the corrected p-value. It moved to
    # -log10 of it in /v1, which is why the id moved then, and /v2 changed no field's meaning at all. The
    # test was `read != SCHEMA`, so the /v2 bump silently extended the note to /v1 files and told their
    # readers the opposite of the truth, in the one command that exists to say how to read a file
    # (found 2026-10-07).
    older = (" (schema grownet.interaction_network/v0: `significance` there is the corrected p-value, "
             "not -log10 of it)") if read == "grownet.interaction_network/v0" else ""
    if read != SCHEMA and not older:
        older = f" (schema {read}; `significance` means what it means in {SCHEMA})"
    print(f"valid: {a.file}{older}")
    # a field this version does not declare: the reader drops it, so the file is valid and the note is
    # the only place a misspelling or a newer version shows up at all
    for note in notes:
        print(f"  note: {note}")
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
    ap = argparse.ArgumentParser(prog="grownet", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser(
        "derive", help="derive an interaction network for species, or for one study",
        description="Derive an interaction network from mGrowthDB growth curves: for species, strains,\n"
                    "genera or NCBI taxon ids (as the local page does), for all of mGrowthDB (--all, the\n"
                    "page's All button), or for every species in one study. The settings are the local\n"
                    "page's Advanced settings, with the same defaults.",
        epilog=DERIVE_EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    what = d.add_argument_group("what to derive")
    what.add_argument("study", nargs="?", default="",
                      help="an mGrowthDB study id (e.g. SMGDB00000004) to derive every species in it; with "
                           "--species, comma separated study ids to search instead of every study holding "
                           "them, the same as naming them in --conditions (the page's second box)")
    what.add_argument("--species", nargs="+", metavar="NAME",
                      help="species or strain names, NCBI taxon ids, or a genus (all its species): every study "
                           "holding them is searched and one network returned, as on the local page (needs "
                           "--live)")
    what.add_argument("--all", action="store_true", dest="all_studies",
                      help="every study in mGrowthDB, with every partner, as the page's All button (needs "
                           "--live; the study argument then limits it to those studies)")
    what.add_argument("--no-published", action="store_true",
                      help="with --all, derive live even when the network derived once a day in the grownet "
                           "repository is less than a day old (it is used only with the default settings)")
    what.add_argument("--no-cache", action="store_true",
                      help="read everything from mGrowthDB again, instead of reusing what an earlier run "
                           "read for a study whose uploadedAt has not changed. The kept responses live in "
                           "the user cache directory (GROWNET_CACHE overrides it), never in the repository")
    what.add_argument("--conditions", nargs="+", default=[], metavar="NAME",
                      help="media, experiment ids or study ids to look at (the page's second box): a medium "
                           "is matched as text against the medium name, the description and the experiment "
                           "name, an id picks that study (SMGDB...) or experiment (EMGDB...), and naming a "
                           "comparison keeps the monocultures it is made against. Empty looks at every medium")
    what.add_argument("--exclude-studies", default="", metavar="IDS",
                      help="with --species or --all, comma separated study ids never to search (default: none)")
    what.add_argument("--all-partners", action="store_true",
                      help="with --species, also keep interactions with species not entered (the page's "
                           "'Only interactions between the species entered', unticked)")
    source = what.add_mutually_exclusive_group(required=True)
    source.add_argument("--live", action="store_true", help="read the growth curves from the mGrowthDB API")
    source.add_argument("--fixture", help="derive from a JSON list of interaction records instead (offline, "
                                          "for testing)")
    what.add_argument("--deriver", metavar="MODULE:CLASS",
                      help="plug in your own derivation method instead of the default one (one study, with "
                           "--live)")

    settings = d.add_argument_group("settings (the local page's Advanced settings)")
    settings.add_argument("--rate-method", choices=["easylinear", "baranyi"], default="easylinear",
                          help="with --metric growth_rate: easylinear (default), the steepest part of the log "
                               "curve as mGrowthDB computes its reported rates, or baranyi, a fitted growth "
                               "model; a curve the model does not describe is left out and reported. The lag "
                               "reported beside a rate comes from the Baranyi fit either way")
    settings.add_argument("--rate-window", type=int, default=5, metavar="N",
                          help="with easylinear: the points in each fitted window (default 5, as mGrowthDB)")
    settings.add_argument("--derivation", choices=["replicate", "integrated"], default="integrated",
                          help="integrated (default), which fits each organism's row from the whole time "
                               "course and gives the gLV coefficients directly; or replicate, the "
                               "specified comparison of replicate sets (the page's Derivation setting)")
    settings.add_argument("--metric", choices=["auc", "max", "growth_rate"], default="auc",
                          help="the growth property compared: auc, the area under the curve (default); max, the "
                               "maximal abundance; or growth_rate, the maximum specific growth rate")
    settings.add_argument("--include-absent", action="store_true",
                          help="also write the arcs below the absence threshold, which are left out so that "
                               "the file and Cytoscape hold exactly the interactions that are reported; they "
                               "carry status absent and effect_over_sd, so a reader can move k in Cytoscape "
                               "without deriving again")
    settings.add_argument("--include-low-quality", action="store_true",
                          help="also show low-quality interactions (pooled strains, a chemostat curve, a "
                               "drop-out whose removed member was still detected); single-replicate ones are "
                               "always shown, flagged")
    settings.add_argument("--no-dropout", action="store_true",
                          help="leave out interactions from drop-out communities (a community against the same "
                               "community without one member); included by default, labeled as possibly "
                               "indirect")
    settings.add_argument("--include-non-batch", action="store_true",
                          help="also derive from chemostat and serial dilution experiments with a growth "
                               "measure that does not suit them (auc, growth_rate), flagged non_batch. With "
                               "--metric max they are derived anyway, marked continuous_culture")
    settings.add_argument("--absence-threshold", type=float, default=1.0, metavar="K",
                          help="an interaction counts as absent (the species do not affect each other) when "
                               "its effect is small against its spread, |log2 mean| < K * sd; default 1, the "
                               "mean plus or minus sd crossing zero; 0 marks only a mean of exactly zero absent")
    settings.add_argument("--correction", choices=["bh", "by"], default="bh",
                          help="multiple testing correction of the reported p-values, whichever test the "
                               "derivation ran (the network's meta.statistics names it), over every "
                               "comparison one derivation tests: bh (Benjamini-Hochberg, default) or by "
                               "(Benjamini-Yekutieli)")
    settings.add_argument("--max-adjusted-p", type=_probability, default=None, metavar="Q",
                          help="also leave out interactions whose adjusted p-value is above Q (for example "
                               "0.05); arcs without a p-value are kept, marked untested. Off by default: with "
                               "two or three replicates the test misses many real effects, and an adjusted "
                               "p-value depends on the other comparisons in the same derivation")
    settings.add_argument("--spike-factor", type=float, default=100.0, metavar="F",
                          help="leave out a growth curve with one or two points F times above both neighbors "
                               "(default 100; 0 keeps every curve)")
    settings.add_argument("--capacity-max-fall", type=float, default=CAPACITY_MAX_FALL, metavar="F",
                          help="a monoculture that grew, peaked and then declined has stopped growing, so its "
                               "carrying capacity is recorded as that peak; leave out a curve whose last "
                               "measurement is below 1/F of its peak, where the peak was not a level the "
                               "culture held (default 10; 0 keeps every certified plateau)")
    settings.add_argument("--no-growth-alpha", type=float, default=None, metavar="ALPHA",
                          help="before any comparison, check that a species grew: across the replicate growth "
                               "curves of that species in one culture condition, the rise from the first time "
                               "point to the maximum is tested (paired t-test); not significant at ALPHA and "
                               "below the factor means no growth (default 0.05; 0 switches the check off)")
    settings.add_argument("--no-growth-factor", type=float, default=None, metavar="F",
                          help="replicate growth curves that rose at least F times (geometric mean over the "
                               "replicates) count as growth whatever the test says (default 1.5; 2 is "
                               "stricter; 0 leaves the test alone)")

    settings.add_argument("--glv-mode", action="store_true",
                          help="the page's gLV mode button: report growth rates, leave out drop-out "
                               "communities, and compare the growth rate, which is what a fitted "
                               "generalized Lotka-Volterra coefficient is made of")
    settings.add_argument("--report-rates", action="store_true",
                          help="also report each organism's maximum specific growth rate in monoculture, "
                               "the median over replicates and studies, with the lag and the monoculture "
                               "carrying capacity beside it (the page's Report growth rates); needed for "
                               "--glv")
    settings.add_argument("--merge-arcs", action="store_true",
                          help="merge the arcs of each source and target, across conditions and studies, into "
                               "one with the median log2 mean and its range; arcs whose signs disagree are not "
                               "merged (off by default: interactions are condition-specific)")
    settings.add_argument("--merge-genera", action="store_true",
                          help="one node per genus, and the arcs between two genera merged by sign, with the "
                               "median log2 mean and the number of species pairs behind each (strain pairs when "
                               "only taxon ids were entered); with --merge-arcs a pair measured in several "
                               "studies counts once (off by default)")
    settings.add_argument("--min-studies", type=int, default=1, metavar="N",
                          help="keep arcs resting on at least N studies (default 1; above 1 it needs merged arcs)")

    outputs = d.add_argument_group("outputs (what the local page's result section offers)")
    outputs.add_argument("--format", choices=["json", "graphml", "matrix"], default="json",
                         help="the network format: json (the neutral format, default), matrix (the adjacency "
                              "matrix as CSV: one cell per ordered pair, holding the effect of the column on "
                              "the row, arcs of a pair merged by their median, and a measured bound from "
                              "the no-growth rule for an obligate or abolished pair) or graphml "
                              "(Cytoscape, "
                              "Gephi, igraph, networkx)")
    outputs.add_argument("--out", metavar="FILE", help="write the network to FILE (default: the screen)")
    outputs.add_argument("--to-cytoscape", action="store_true",
                         help="also send the network into a Cytoscape running on this machine, styled as in "
                              "the legend")
    outputs.add_argument("--cytoscape-port", type=int, default=1234, metavar="PORT",
                         help="the port Cytoscape's CyREST listens on (default 1234)")
    outputs.add_argument("--rates", metavar="FILE",
                         help="write the growth rates to FILE as CSV (needs --report-rates)")
    outputs.add_argument("--glv", metavar="FILE",
                         help="write the parameters of a generalized Lotka-Volterra simulation to FILE, a zip "
                              "of one matrix of fitted coefficients per abundance unit, the matching growth "
                              "rates and a README (needs --report-rates; under --derivation replicate it "
                              "also needs --metric growth_rate, which the default derivation does not, "
                              "and --glv-mode sets both)")
    outputs.add_argument("--steady-check", action="store_true",
                         help="score the gLV parameters against the chemostat steady states mGrowthDB "
                              "holds for these organisms: the report gets the comparison and the zip a "
                              "steady_state_check.txt. It reads curves the search did not need, so it is "
                              "off unless asked for (needs --report-rates)")
    outputs.add_argument("--to-r", action="store_true",
                         help="also send the gLV parameters into an R session waiting for them (the page's "
                              "Send to R; in R: library(grownet); grownet_listen()). Needs --report-rates")
    outputs.add_argument("--r-port", type=int, default=None, metavar="PORT",
                         help="the port the R session listens on (default 8793, what grownet_listen() uses)")
    outputs.add_argument("--report", metavar="FILE",
                         help="write the report of the search to FILE: every setting, the tool version, every "
                              "interaction, every pair the data did not support, and the sources")
    d.set_defaults(fn=_derive)

    y = sub.add_parser("style", help="write the Cytoscape style as XML, for File, Import, Styles from File")
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
    try:
        return a.fn(a)
    except OSError as e:
        # a file that cannot be read or written is the user's to fix, so it gets a line, not a traceback
        # (Karoline, 2026-09-28: the README's fixture path, run outside a clone)
        if e.filename is None:
            raise
        where = "" if os.path.isabs(e.filename) else f" (relative to {os.getcwd()})"
        print(f"grownet: {e.filename}{where}: {e.strerror}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"grownet: the file given is not valid JSON ({e})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
