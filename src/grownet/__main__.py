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
import math
import os
import sys
from collections import Counter

from .adapter import about_a_pair, condensed, unread
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
    grownet derive SMGDB00000004 --live --glv-mode --glv study4_glv.zip \\
        --rates study4_rates.csv --report study4_report.txt

  the same parameters sent into a waiting R session (in R: library(grownet); grownet_listen()):
    grownet derive SMGDB00000004 --live --glv-mode --to-r

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


def _bad_settings(a) -> str:
    """Why a numeric setting cannot be used as given, or "": the same bounds the page applies.

    The page coerces every one of these (`gui.parse_settings`) and the command line took them as typed,
    so the two routes disagreed about what a legal setting is and a nonsense one reached
    `meta.settings` as the provenance of the run: `--rate-window -3` gave 0 edges and recorded -3,
    `--absence-threshold -1` gave 18 edges reported as "|log2 mean| < -1 * sd", `--no-growth-factor -2`
    gave 10 edges over 3 nodes. Each exited 0 (#221 item 4). Refusing is the right half of "refuse or
    announce": the page clamps because a form cannot stop and ask, and a command can.
    """
    if a.rate_window is not None and a.rate_window < 2:
        return (f"--rate-window must hold at least 2 points, not {a.rate_window}; the growth rate is a "
                "line fitted over a window of points")
    for flag, value in (("--spike-factor", a.spike_factor), ("--capacity-max-fall", a.capacity_max_fall),
                        ("--absence-threshold", a.absence_threshold),
                        ("--no-growth-alpha", a.no_growth_alpha),
                        ("--no-growth-factor", a.no_growth_factor)):
        # the finite check comes first, because `nan < 0` is False and `inf < 0` is False, so neither
        # is caught by the bound below. `float()` takes "nan", "inf" and "1e999", and the live path
        # copies the parsed value into `meta.settings`, where `json.dumps` writes the bare tokens `NaN`
        # and `Infinity`. RFC 8259 section 6 forbids both, so R refuses the whole network while
        # grownet's own `validate` accepts it, because Python's json module reads the specials by
        # default (#258, the command line's half of #195). `--max-adjusted-p` needs none of this:
        # `_probability` already refuses anything outside `0 < value <= 1`, which both fail.
        if value is not None and not math.isfinite(value):
            return (f"{flag} must be a finite number, and was {value}; no threshold can be compared "
                    "against it, and it reaches meta.settings as a token no strict JSON parser reads")
        if value is not None and value < 0:
            return f"{flag} cannot be negative, and was {value}"
    if a.min_studies is not None and a.min_studies < 1:
        return f"--min-studies must be at least 1, and was {a.min_studies}"
    # a significance level, like --max-adjusted-p, which argparse already refuses above 1. This took any
    # non-negative number, and 5 switches the no-growth rule off entirely (every set counts as grown, so
    # no censored or obligate arc can exist) while `meta.no_growth` records "alpha": 5.0 as the level the
    # test ran at. The help documents exactly one way to switch it off, which is 0 (#250).
    if a.no_growth_alpha is not None and a.no_growth_alpha > 1:
        return (f"--no-growth-alpha is a significance level, so at most 1, and was {a.no_growth_alpha}; "
                "0 switches the no-growth check off, which is the documented way")
    if a.min_studies and a.min_studies > 1 and not a.merge_arcs and not a.merge_genera:
        # the one that silently empties a network: without merging, an arc carries no `studies` key, so
        # `len(e.get("studies") or [e])` is 1 for every arc and the filter removes all of them (#220)
        return (f"--min-studies {a.min_studies} counts the studies behind a MERGED arc, and nothing is "
                "merged here, so every arc counts as 1 and the network would come out empty: add "
                "--merge-arcs (or --merge-genera), or drop --min-studies")
    return ""


# The settings the --fixture route does not apply, measured rather than reasoned: with a fixture built so
# that each one had something to act on (the same pair from two studies for merging, a q-value of 0.40 for
# the filter, a tiny effect with a spread for the threshold, a single_replicate arc for the quality
# filter), EVERY one of them left the arcs byte-identical. The mechanism is that `output_meta` runs only
# on the live path, so the fixture route has no output stage at all: no absence threshold, no merging, no
# q-value filter. Ten or more settings were accepted and discarded in silence, and the report printed an
# empty `settings:` heading and a literal `(k = )` (#222 item 1).
FIXTURE_IGNORES = {
    "metric": "--metric", "rate_method": "--rate-method", "rate_window": "--rate-window",
    "spike_factor": "--spike-factor", "capacity_max_fall": "--capacity-max-fall",
    "no_growth_alpha": "--no-growth-alpha", "no_growth_factor": "--no-growth-factor",
    "derivation": "--derivation", "include_non_batch": "--include-non-batch",
    "absence_threshold": "--absence-threshold", "correction": "--correction",
    "max_adjusted_p": "--max-adjusted-p", "merge_arcs": "--merge-arcs",
    "merge_genera": "--merge-genera", "min_studies": "--min-studies",
    "include_low_quality": "--include-low-quality", "include_absent": "--include-absent",
}


def _fixture_flags(a) -> str:
    """Why a setting cannot be used with --fixture, or "": it holds records someone already derived.

    Refusing is the half of "refuse or announce" a command can do, which is the rule #221 settled for
    every other setting, and it is what `--deriver` already does here with almost these words. Nothing
    is applied silently and nothing changes about what the route produces.
    """
    if a.live:
        return ""
    from .gui import DEFAULTS

    settings = _settings_of(a)
    asked = [flag for key, flag in sorted(FIXTURE_IGNORES.items())
             if key in settings and key in DEFAULTS and settings[key] != DEFAULTS[key]]
    if not asked:
        return ""
    return (f"{', '.join(asked)} cannot apply to --fixture, which holds records someone already derived: "
            "there is no derivation to configure and no output stage runs, so the setting would be "
            "recorded and not applied. Use --live to derive, or drop "
            + (asked[0] if len(asked) == 1 else "them") + ".")


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
    wants_coefficients = [flag for flag, on in (("--glv", a.glv), ("--to-r", a.to_r)) if on]
    if wants_coefficients and a.metric != "growth_rate" and not a.deriver and a.derivation == "replicate":
        # a coefficient divides by a log2 ratio of growth rates, so the area or the maximum cannot make
        # one (#119); --glv-mode sets all of it at once. `--to-r` was left out of this guard while the
        # integrated form was the default, where the metric does not matter, so with the comparison back
        # as the default it wrote the whole network to stdout and then died with a CannotConvert
        # traceback, which is the one thing this function exists to prevent (2026-10-10)
        return (f"{wants_coefficients[0]} writes fitted gLV coefficients, and a coefficient needs the "
                f"log2 ratio of a growth rate, not of {a.metric}: add --metric growth_rate, or use "
                "--glv-mode, which also selects the derivation that fits the row")
    return ""


def _settings_of(a) -> dict:
    """Every setting of this run, built in ONE place for every derive path.

    There were two of these, written by hand, and they disagreed: `derive <STUDY> --live` recorded 20
    keys and the species path 23, the difference including `include_absent` and `steady_check`, which are
    not n/a on either. And `steady_check` was wrong on BOTH, because the species path took it from
    `DEFAULTS` rather than from the flag, so a run that scored a chemostat recorded that it had not
    (#233). `report.py` promises "every setting with its value", so two reports of one study differing in
    their arcs and identical in their settings block is the thing a reader cannot see past.
    """
    from .gui import DEFAULTS

    return {**DEFAULTS,
            "metric": a.metric, "rate_method": a.rate_method, "rate_window": a.rate_window,
            "derivation": a.derivation, "deriver": getattr(a, "deriver", "") or "",
            "merge_arcs": a.merge_arcs, "min_studies": a.min_studies, "merge_genera": a.merge_genera,
            "spike_factor": a.spike_factor, "capacity_max_fall": a.capacity_max_fall,
            "absence_threshold": a.absence_threshold,
            "include_low_quality": a.include_low_quality, "correction": a.correction,
            "include_dropout": not a.no_dropout, "include_non_batch": a.include_non_batch,
            "no_growth_alpha": a.no_growth_alpha, "no_growth_factor": a.no_growth_factor,
            "max_adjusted_p": a.max_adjusted_p, "report_rates": a.report_rates,
            "include_absent": getattr(a, "include_absent", False),
            "steady_check": getattr(a, "steady_check", False),
            # these two were left to come from DEFAULTS, which turned a setting the report did not
            # mention into one it stated the OPPOSITE of: `derive <STUDY> --exclude-studies <that study>
            # --all-partners` recorded "Exclude these studies: none" and "Only interactions between the
            # species entered: on", having searched the study and kept every partner. Missing was better
            # than wrong, and `report.py` promises every setting with its value (found reviewing #242).
            "exclude_studies": getattr(a, "exclude_studies", "") or "",
            "only_entered": not getattr(a, "all_partners", False),
            # the page encodes the second box one selector per LINE, and `selection.parse` splits on
            # newlines, commas and semicolons: space is the one separator it does not split on. The
            # single-study path recorded `--conditions "WC" "mucin"` space-joined, so the record parsed
            # back as one medium named "WC mucin", which matches nothing, while the run used the list.
            "conditions": "\n".join(getattr(a, "conditions", None) or [])}


def _resolve(a, announce=True):
    """Settle what the run will actually use, before anything is checked or derived.

    gLV mode sets four settings and `--derivation` carries no default of its own, so the parsed arguments
    are NOT what runs: `_rate_flags` tests `a.derivation == "replicate"` and would pass anything if it
    saw the unresolved `None`. Pulled out of `_derive` so that a test of the help page's own commands
    checks what a run would check rather than a copy of this logic, which is how a fourth broken example
    reached the page (#234).
    """
    if a.glv_mode:
        # the button sets them, and says so, rather than leaving a reader to remember them (#113). The
        # the metric came with the coefficients of #119: L is the log2 ratio of a growth rate. The rate
        # method is the reader's own setting (easylinear by default), with the lag always Baranyi's.
        a.report_rates, a.no_dropout, a.metric = True, True, "growth_rate"
        # and the integrated form, which is the one a coefficient should be fitted by (Karoline,
        # 2026-10-10). It is gLV mode that selects it, not the default, because it cannot express a
        # drop-out arc or a censored one and a network needs both.
        #
        # **An explicit `--derivation` wins**, because overriding it silently broke the one command the
        # decision register prints as the record of its own measurement:
        # `derive SMGDB00000007 --live --glv-mode --derivation <either> --steady-check` gave the same
        # answer for both arms, so the table a reader checks with it read as though the two derivations
        # were one. That command was added because two readers took the table for a fabrication when it
        # was missing; overriding the flag unfixed it the same day (found 2026-10-10).
        chosen = a.derivation
        if chosen is None:
            a.derivation = "integrated"
        told = ("and the integrated form" if chosen is None else
                f"and the {chosen} derivation, which you asked for and gLV mode does not override")
        if announce:
            print("gLV mode: growth rates on, drop-out communities off, the comparison on the growth "
                  f"rate, {told}", file=sys.stderr)
    if a.derivation is None:
        # the page and the command line must agree on what runs when nothing is chosen, so this reads
        # the page's own defaults rather than repeating the value
        from .gui import DEFAULTS
        a.derivation = DEFAULTS["derivation"]
    return a


def _derive(a):
    _resolve(a)
    problem = _bad_settings(a) or _rate_flags(a) or _fixture_flags(a)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    if a.species or a.all_studies:
        return _derive_species(a)
    # Flags that only the search path can act on. The help says they apply "with --species or --all" and
    # nothing enforced it, so `derive <STUDY> --exclude-studies <that study>` searched it and the network
    # held it. Recording the flag as asked is not enough on its own: the report would then say the
    # study was excluded while the arcs come from it, so the run is refused instead (found reviewing
    # #242, which made the record truthful and left the contradiction).
    cannot_act = [flag for flag, on in (("--exclude-studies", a.exclude_studies),
                                        ("--all-partners", a.all_partners)) if on]
    if cannot_act:
        print(f"{cannot_act[0]} narrows a search over several studies, and this run derives the one "
              f"study {a.study}: it would be recorded and not applied. Use --species or --all, or drop "
              f"{cannot_act[0]}.", file=sys.stderr)
        return 2
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
            extra["settings"] = _settings_of(a)
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
    net.meta["errors"] = list(errors)
    net.meta["complete"] = not errors
    organism_rates = {}
    if a.report_rates:
        organism_rates, skipped = _rates_of(a, client, [a.study], net, skipped, records)
    result = {"study": a.study, "entries": [], "resolved": [], "unresolved": [], "studies": [a.study],
              "rates": organism_rates, "client": client if a.live else None,
              "skipped": skipped, "errors": errors, "network": net}
    code = _emit(a, net, skipped, extra, a.study, result)
    # the species and All paths exit 1 on an incomplete run since #243; this path exited 0 when curves
    # could not be read, so the two paths still disagreed about the same failure (#247)
    return _incomplete(result) if code == 0 else code


def _species_flags(a) -> str:
    """Why a search over several studies cannot be run as given, or "".

    Pulled out of `_derive_species` so that one function holds every pre-flight check of this path and a
    test of the help page's own commands reaches all of them. The test applied `_rate_flags` alone, so
    two of the three guards were never consulted and an example printed on the page could exit 2 with
    the suite green (found reviewing this branch, which added that test).
    """
    flag = "--all" if a.all_studies else "--species"
    if a.all_studies and a.species:
        return "--all derives every study; leave out --species"
    if not a.live:
        return f"{flag} searches mGrowthDB, so it needs --live"
    if a.deriver:
        return f"{flag} uses the default derivation; --deriver applies to one study"
    return ""


def _derive_species(a):
    """What the local page does, from the command line: names to studies to one network (#78)."""
    problem = _species_flags(a)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    from .gui import run_query
    from .mgrowthdb import MGrowthDBClient
    settings = {**_settings_of(a),
                "conditions": "\n".join([*a.conditions, *(a.study or "").split(",")]).strip()}
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
    for note in result.get("notes", ()):
        print(f"note: {note}", file=sys.stderr)
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
    # "all of mGrowthDB" only when nothing narrowed it: the second box and Exclude these studies both
    # narrow All, which is deliberate, and saying otherwise is the same false claim the page carried
    narrowing = [x for x in (*a.conditions, *(a.exclude_studies or "").split(",")) if x and x.strip()]
    label = ("all of mGrowthDB" if not narrowing else "All, narrowed to " + ", ".join(
        x.strip() for x in narrowing)) if a.all_studies else " and ".join(a.species)
    code = _emit(a, net, result["skipped"], extra, label, result)
    # An incomplete run must not exit 0, and the two derive paths disagreed about the same failure:
    # `derive <a bad id> --live` exits 1 while the species and All paths collected the identical 404
    # into `errors` and exited 0, so a script could not tell a complete run from an incomplete one
    # (#247). This is safe to key on only because `errors` is fetch failures and nothing else now:
    # the advisory messages travel in `notes`, which is the split #242 makes.
    return _incomplete(result) if code == 0 else code


def _incomplete(result) -> int:
    """1, with the reason, when a run could not read everything it asked for; 0 otherwise."""
    if not result.get("errors"):
        return 0
    print(f"\nthis run is INCOMPLETE: {len(result['errors'])} study or curve could not be read from "
          "mGrowthDB (the messages are above). The network holds what was readable, and its meta records "
          "the errors; run it again when mGrowthDB is reachable if you need all of it.", file=sys.stderr)
    return 1


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
        # `--include-absent` cannot do anything here and said nothing: `derive --all --format matrix
        # --include-absent` gives a file byte-identical to the default, because this format's convention
        # is that an empty or absent cell is 0 (Karoline, 2026-10-03), so an arc below the threshold has
        # nowhere else to go. The matrix records no settings either, so nothing in the file says the flag
        # was asked for and dropped (#218 item 2). Announced rather than refused, because the run itself
        # is legitimate and nothing false is written: what is wrong is only the reader's expectation.
        if getattr(a, "include_absent", False):
            absent_now = sum(1 for e in net.edges if e.status == "absent")
            print("--include-absent has no effect with --format matrix: this format's convention is that "
                  "an empty or absent cell is 0, so an arc below the threshold has no cell of its own to "
                  f"be kept in{f' ({absent_now} in this network)' if absent_now else ''}. The JSON and "
                  "GraphML formats carry them with status absent; use one of those, or read the arcs "
                  "below the threshold from the report.", file=sys.stderr)
    else:
        payload = net.to_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {a.out}: {len(net.nodes)} nodes, {len(net.edges)} edges")
        if a.format == "matrix" and a.out != os.devnull:
            # the grid carries no provenance and no key for 0 or NA, so it travels with a description
            # (Karoline, 2026-10-12, on #212: a sidecar file)
            from .matrix import about_name, matrix_about
            about = about_name(a.out)
            with open(about, "w", encoding="utf-8") as f:
                f.write(matrix_about(net, os.path.basename(a.out)))
            print(f"wrote {about}: what the matrix is, how it was made, and its 0 and NA cells")
    else:
        print(payload)
        if a.format == "matrix":
            print("the matrix's description (settings, the meaning of 0 and NA, the sources) is written "
                  "beside it only with --out", file=sys.stderr)

    if a.report:
        # the same report the local page shows and downloads (#76): every setting, the version, every reason
        from .report import report_text
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(report_text(result))
        print(f"wrote the report to {a.report}", file=sys.stderr)

    organism_rates = result.get("rates") or {}
    # This used to `return 1` here, before the skipped-pair list, the absence note, the low-quality note,
    # the sources block and the "NO interactions were derived" explanation, and it pointed at a report
    # that was only written if --report was given: asking for --rates printed 7 lines of stderr and
    # asking for less printed 74, including 35 copies of the exact cause (#221 item 3). The diagnosis is
    # the thing the person needs, so it is printed and the exit code is carried to the end.
    no_rates = bool(a.rates or a.glv or a.to_r) and not organism_rates
    if no_rates:
        print("no growth rate could be computed for any organism of this network, so "
              + ", ".join(f for f, on in (("--rates", a.rates), ("--glv", a.glv), ("--to-r", a.to_r)) if on)
              + " wrote nothing"
              + (f"; {a.report} says why each organism has none" if a.report
                 else "; the reasons are below, and --report writes them to a file"),
              file=sys.stderr)
    if a.rates and organism_rates:
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
    if a.glv and organism_rates:
        from . import steady as steady_module
        from .matrix import glv_package
        extra_files = {"steady_state_check.txt": steady_module.as_text(checked)} if a.steady_check else None
        with open(a.glv, "wb") as f:
            f.write(glv_package(net, organism_rates, extra_files))
        print(f"wrote the gLV parameters to {a.glv}: the interaction matrix, the growth rates and a README",
              file=sys.stderr)

    if a.to_r and organism_rates:
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
        pairs = [s for s in skipped if about_a_pair(*s)]
        notes = [s for s in skipped if not about_a_pair(*s)]
        # the count used to include the notes about the input, so it answered a question nobody asked
        # and not "how many pairs gave nothing" (#232)
        print(f"\nskipped {len(pairs)} pair(s) the data did not cleanly support"
              + (f", and {len(notes)} note(s) on the data read" if notes else "") + ":", file=sys.stderr)
        for label, reason in pairs + notes:
            print(f"  - {label}: {reason}", file=sys.stderr)
    if extra:
        if extra["absence"]["absent"]:
            left_out = extra["hidden"].get("absent", 0)
            # and the suggestion is only made where the chosen format can carry them: on --format matrix
            # an absent cell is 0 by that format's own convention, so suggesting the flag there sent a
            # reader to one that does nothing (#218 item 2, the same defect one step upstream)
            keeps_absent = a.format != "matrix"
            where = ("left out of the network, so the file holds the interactions it reports"
                     + ("; keep them with --include-absent" if keeps_absent else
                        ", and --format matrix cannot carry them: an absent cell is 0 in that format, so "
                        "read them from the report or use the JSON or GraphML format")
                     if left_out else "in the file, with status absent")
            print(f"\n{extra['absence']['absent']} comparison(s) came out below the absence threshold "
                  f"(|log2 mean| < {extra['absence']['k']:g} * sd): {where}. The report lists them.",
                  file=sys.stderr)
        if extra["hidden"]["low_quality"]:
            print(f"{extra['hidden']['low_quality']} low-quality edge(s) hidden; show them with "
                  "--include-low-quality.", file=sys.stderr)
    if not net.edges and "reasons" not in result:        # a species search has said why already
        top = Counter(r.split(";")[0].strip() for _, r in skipped).most_common(1)
        why = f" Most common reason: {top[0][0]}." if top else ""
        # and the settings the reader changed that can empty a network on their own, which the page says
        # and the command line did not: `--spike-factor 1` is a legal value that empties it, so no
        # refusal applies, and the "most common reason" above is a line that is also present at the
        # defaults where the same study yields an arc. So the setting that did it was the one thing the
        # message did not mention (#250, the command-line half of #220).
        import html as _html

        from .gui import _settings_to_try
        try_these = _html.unescape(_settings_to_try(_settings_of(a)))
        for tag in ("<strong>", "</strong>"):
            try_these = try_these.replace(tag, "")
        why += try_these
        print(f"\nNO interactions were derived for {label}: the network is empty.{why}\n"
              "grownet derives interactions from pairwise (two-member) co-cultures and from drop-out "
              "designs (a community plus the same community without one member); other larger communities "
              "yield nothing until a method suited to their design is chosen (see docs/METHOD_NOTES.md).",
              file=sys.stderr)
    return 1 if no_rates else 0


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
                           "repository is less than 36 hours old, was derived by the same derivation this run would "
                           "use, and the settings are the defaults; otherwise it derives live")
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
    # None means "not given", so gLV mode can tell a reader's explicit choice from the default it fills
    settings.add_argument("--derivation", choices=["replicate", "integrated"], default=None,
                          help="replicate (default), the specified comparison of replicate sets, the only "
                               "form that gives drop-out arcs and the no-growth rule's censored bounds; "
                               "or integrated, which fits each organism's row from the whole time course "
                               "and gives the gLV coefficients directly, which --glv-mode selects. "
                               "Integrated derives no arc from a community of three or more, so no "
                               "drop-out arc (the page's Derivation setting)")
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
                              "the row, arcs of a pair merged by their median, and NA for an obligate or "
                              "abolished pair, whose measured bound travels on the arc) or graphml "
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
                              "rates and a README (needs --report-rates; under the default derivation it "
                              "also needs --metric growth_rate, which the integrated form does not, and "
                              "--glv-mode sets all of them, the integrated form included)")
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
