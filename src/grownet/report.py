"""The report of one search (#76): what was asked, how, and everything the search found or skipped.

Karoline's words (#72): "a last one with the detailed comments of the search, which can also be downloaded
as a text file that will also include all the settings". The same text is shown on the page and served as
a download, so the two cannot differ. It names the tool and its version (Karoline, on #78), every setting
with its value, and every reason a pair gave no edge.
"""
from __future__ import annotations

from . import interaction
from .adapter import condensed
from .help import SETTINGS
from .mgrowthdb import MGROWTHDB_API, NO_DATABASE_VERSION


def _value(key: str, value) -> str:
    if value is None and key == "max_adjusted_p":
        return "off"
    if value is None and key.startswith("no_growth_"):
        value = getattr(interaction, key.upper())      # None: the rule's own default
    if value is True:
        return "on"
    if value is False:
        return "off"
    return "none" if value == "" else str(value)


def _bound_line(e) -> str:
    """How the report writes a censored arc's bound, with the rule that produced it (#129).

    The cell of such a pair is `NA`, because a matrix cell cannot say that a number is a floor, so this
    report is where the bound is stated (Karoline, 2026-10-08).
    """
    size = getattr(e, "strength_bound", None)
    rule = f" [{e.bound_rule}]" if getattr(e, "bound_rule", "") else ""
    if size is None:
        return rule.strip()
    direction = "at least" if size > 0 else "at most"
    return f"{direction} log2 {size:+.4g}" + rule


def _mean_sd(e) -> str:
    if e.strength is None:
        bound = _bound_line(e)
        if bound and getattr(e, "strength_bound", None) is not None:
            return f"no ratio (one side did not grow), so the cell is NA and the arc carries the bound: {bound}"
        # a ratio is also undefined when both sides grew and the fitted effect at least cancels the
        # organism's own rate, which is not "one side did not grow" (found 2026-10-06)
        if e.outcome not in ("obligate", "abolished"):
            return "no log2 ratio: the fitted effect at least cancels this organism's own growth rate"
        # no bound either: the rule says why, and the cell is NA rather than 0, which would read as no
        # interaction about the strongest effect in the set (#129)
        return "no ratio (one side did not grow), so the cell is NA" + (f": {bound}" if bound else "")
    return f"log2 mean {e.strength:+.2f}" + ("" if e.sd is None else f" +/- {e.sd:.2f}")


def _edge_line(net, e) -> str:
    # an arc left out of the network is listed from its own network, so its nodes are looked up there
    name = {nid: node.name or nid for nid, node in net.nodes.items()}
    name.update({nid: nid for nid in (e.source, e.target) if nid not in name})
    direction = e.effect if e.outcome in (None, "quantified") else f"{e.effect} ({e.outcome})"
    parts = [f"{name[e.source]} -> {name[e.target]}: {direction}", _mean_sd(e)]
    if e.merged_arcs:
        low_high = f", range {e.strength_range[0]:+.2f} to {e.strength_range[1]:+.2f}" if e.strength_range else ""
        parts.append(f"median of {e.merged_arcs} merged arcs{low_high}")
    if e.supporting_pairs:
        parts.append(f"{e.supporting_pairs} supporting pair(s): {'; '.join(e.merged_pairs)}")
    else:
        parts.append(f"replicates {e.n_with if e.n_with is not None else '?'} with / "
                     f"{e.n_without if e.n_without is not None else '?'} without")
    # the q-value under its own name, and `significance` under its own. This printed `significance`,
    # which is -log10(q), labelled "adjusted p": a reader screening the report for "adjusted p < 0.05"
    # therefore discarded every strongly supported arc and kept the ones with q near 1, since the label
    # ran the opposite way to the number (found 2026-10-07; the line predates 0.3.0)
    if e.q_value is not None:
        parts.append(f"adjusted p (q) {e.q_value:.3g}")
    if e.significance is not None:
        parts.append(f"significance -log10(q) {e.significance:.3g}")
    if getattr(e, "coefficient", None) is not None:
        parts.append(f"fitted coefficient {e.coefficient:.4g} {e.coefficient_unit}".strip())
        if e.fit_r2 is not None and e.fit_condition is not None:
            # the same row with no interactions at all beside it, so a reader sees how much the partners
            # bought rather than taking the fit's own R2 as evidence of an interaction (#142 item 9)
            null = getattr(e, "fit_null_r2", None)
            beside = f" (no interactions at all: {null:.3f})" if null is not None else ""
            parts.append(f"fit r2 {e.fit_r2:.3f}{beside}, condition {e.fit_condition:.3g}")
        # the two halves of the standard error, on their own designs, so a reader can see which stage the
        # uncertainty comes from and that the rate stage reached the test at all (#142 item 2)
        if getattr(e, "se_rate_stage", None) is not None:
            parts.append(f"se {e.se_replicates:.3g} from the co-culture replicates and "
                         f"{e.se_rate_stage:.3g} from the rate stage"
                         + (f" ({e.rate_stage_method})" if e.rate_stage_method else ""))
    if getattr(e, "metric_with", None) is not None and getattr(e, "metric_without", None) is not None:
        parts.append(f"{name[e.target]} at {e.metric_with:.4g} with / {e.metric_without:.4g} without "
                     f"({e.metric})")
    if getattr(e, "partner_abundance", None) is not None:
        parts.append(f"{name[e.source]} at {e.partner_abundance:.4g} "
                     f"{e.partner_abundance_unit} over the window")
    parts.append(f"condition {e.condition}")
    if e.medium:
        parts.append(f"medium {e.medium}")
    parts.append("study " + " ".join(e.study_ids))
    if e.evidence == "dropout":
        parts.append("drop-out community, possibly indirect")
    parts += [f"low quality: {q}" for q in e.quality] + [f"caution: {c}" for c in e.cautions]
    parts += list(e.notes)
    return "  - " + "; ".join(parts)


def report_text(result: dict) -> str:
    """The report as plain text, from a `gui.run_query` result."""
    net = result["network"]
    meta = net.meta
    settings = meta.get("settings", {})
    data = meta.get("data", {})
    when = meta.get("derived_at", meta.get("derived_on", "")).replace("T", " ")
    lines = [f"{meta.get('tool', 'grownet')} report",
             f"run: {when}",
             f"tool: {meta.get('tool', 'grownet')} {meta.get('tool_version', '')}",
             f"data: {meta.get('source_db', 'mGrowthDB')}, {data.get('api', MGROWTHDB_API)}, read at "
             f"{data.get('retrieved_at', when).replace('T', ' ')}",
             f"data version: {data.get('database_version', NO_DATABASE_VERSION)}"]
    # what was read and what was reused, since a reader should be able to see that a network rests on
    # measurements kept from an earlier run, and which studies were read again because mGrowthDB has a
    # newer version of them (#182)
    client = result.get("client")
    if client is not None and getattr(client, "cache_dir", None):
        reused, fetched = getattr(client, "reused", 0), getattr(client, "fetched", 0)
        refreshed = getattr(client, "refreshed", []) or []
        line = (f"reads: {fetched} from mGrowthDB, {reused} reused from an earlier run "
                f"(kept while a study's uploadedAt is unchanged)")
        if refreshed:
            line += f"; read again because their uploadedAt moved: {', '.join(sorted(refreshed))}"
        lines.append(line)
    lines.append("")

    if result.get("study"):
        lines.append(f"study derived: {result['study']} (every species in it)")
    elif result.get("all"):
        lines.append("query: all of mGrowthDB (every study, with every partner)")
        if result.get("published"):
            lines.append(f"  from the network derived once a day in the grownet repository, at {result['published']}")
    else:
        lines.append("species entered: " + (", ".join(result.get("entries", [])) or "none"))
    genera = result.get("genera", {})
    for entry, matches in result["resolved"]:
        if entry in genera:
            lines.append(f"  {entry} (genus): {', '.join(genera[entry])}")
        lines.append(f"  {entry}: " + ", ".join(f"{n} (taxon {t})" for t, n in sorted(matches.items())))
    for entry in result["unresolved"]:
        hints = result.get("suggestions", {}).get(entry)
        lines.append(f"  not used: {entry}: {result.get('reasons', {}).get(entry, 'not in mGrowthDB')}"
                     + (f" (did you mean: {', '.join(hints)}?)" if hints else ""))
    lines.append("studies searched: " + (", ".join(result["studies"]) or "none"))
    for sid, dates in data.get("studies", {}).items():
        lines.append(f"  {sid}: uploaded {dates.get('uploaded_at', '')[:10] or '?'}, published "
                     f"{dates.get('published_at', '')[:10] or '?'}")
    if result.get("excluded"):
        lines.append("left out by Exclude these studies: " + ", ".join(result["excluded"]))
    lines.append("")

    lines.append("settings:")
    for key, (label, flag, _) in SETTINGS.items():
        if key in settings:
            lines.append(f"  {label} ({flag.split()[0]}): {_value(key, settings[key])}")
    lines.append("")

    shown = [e for e in net.edges if e.status != "absent"]
    # the arcs the threshold marked absent are left out of the file by default, so the report says both
    # what the file holds and what was left out, and the two numbers always add up (Karoline, 2026-10-03)
    in_file = [e for e in net.edges if e.status == "absent"]
    left_out = meta.get("hidden", {}).get("absent", 0)
    absent_net = net if in_file else result.get("absent")
    absent = in_file or (list(absent_net.edges) if absent_net else [])
    hidden = meta.get("hidden", {}).get("low_quality", 0)
    rule = meta.get("no_growth", {})
    k = meta.get("absence", {}).get("k", "")
    lines.append(f"result: {len(shown)} interaction(s) written, {len(in_file) + left_out} below the absence "
                 f"threshold (k = {k})"
                 + (", left out of the network" if left_out else ", kept in the network")
                 + f", {hidden} low-quality edge(s) hidden")
    applied = meta.get("statistics", {}).get("filter", {})
    if applied.get("max_adjusted_p") is not None:
        lines.append(f"q-value filter (q is the adjusted p-value): interactions above "
                     f"{applied['max_adjusted_p']:g} left out: "
                     f"{applied.get('left_out', 0)}; kept untested (no p-value): {applied.get('untested', 0)}")
    if rule:
        lines.append(f"no-growth rule: {rule.get('test', '')}; alpha {rule.get('alpha')}, factor "
                     f"{rule.get('factor')}; {rule.get('obligate', 0)} obligate, {rule.get('abolished', 0)} abolished")
    merge = meta.get("merge", {})
    if merge.get("merge_arcs") or merge.get("min_studies", 1) > 1:
        lines.append(f"merged arcs: {merge.get('rule', '')}; {merge.get('merged', 0)} merged, "
                     f"{merge.get('left_apart_for_disagreeing_signs', 0)} pair(s) left apart for disagreeing signs, "
                     f"{merge.get('below_min_studies', 0)} arc(s) below {merge.get('min_studies', 1)} studies")
    stats = meta.get("statistics", {})
    if stats:
        lines.append(f"statistics: {stats.get('test', '')}; {stats.get('correction', '')}; "
                     f"{stats.get('tests', 0)} test(s); {stats.get('role', '')}")
    for error in result["errors"]:
        lines.append(f"error: {error}")
    lines.append("")

    lines.append("interactions:" if shown else "interactions: none")
    lines += [_edge_line(net, e) for e in shown]
    if absent:
        lines.append("below the absence threshold (no interaction found"
                     + (", left out of the network):" if left_out else "):"))
        lines += [_edge_line(absent_net, e) for e in absent]
    lines.append("")

    rates = meta.get("growth_rates") or {}
    if rates:
        organisms = rates.get("organisms", {})
        lines.append(f"growth rates ({rates.get('rule', '')}):" if organisms
                     else "growth rates: asked for, none could be computed")
        for nid, rate in sorted(organisms.items(), key=lambda kv: str(kv[1].get("name", kv[0])).lower()):
            per_study = "; ".join(f"{sid} {value:.4g}" for sid, value in sorted(rate.get("per_study", {}).items()))
            extra = []
            if rate.get("lag") is not None:
                extra.append(f"lag {rate['lag']:.3g} {rate.get('unit', '1/h').removeprefix('1/')}")
            if rate.get("capacity") is not None:
                extra.append(f"carrying capacity {rate['capacity']:.4g} {rate.get('capacity_unit', '')}"
                             f" from {rate.get('capacity_n', 0)} "
                             + ("row(s)" if rate.get("n_label") else "curve(s)"))
                # a certified curve that grew, peaked and then declined has its peak recorded as the
                # plateau, so what it held at the last measurement is published beside it (Karoline,
                # 2026-10-07, closing open decision 4 of #141)
                fall = rate.get("capacity_fall")
                if fall is not None and fall > 1.01:
                    extra.append(f"those curves ended at 1/{fall:.3g} of their peak (median)")
            # the help promises that every curve giving no capacity is named here with its reason, and
            # nothing rendered them: an empty carrying capacity read as absence (found 2026-10-06)
            # a capacity comes from one medium and is never pooled across them, since it sits beside
            # off-diagonals measured in one of them (Karoline, 2026-10-07). The medium it came from is
            # said, and so is every other medium this organism has a plateau in, which the second box
            # can ask for.
            # where the self-limitation behind the diagonal came from: fitted with the partners, or
            # -r/K at a measured plateau because the fit implied none (#142 item 7)
            if rate.get("capacity_source"):
                extra.append(rate["capacity_source"])
            if rate.get("capacity_medium"):
                extra.append(f"capacity measured in {rate['capacity_medium']}")
                # more than one spelling means the alias table merged names that disagree, which is said
                spellings = [name for name in (rate.get("capacity_medium_spellings") or [])
                             if name != rate["capacity_medium"]]
                if spellings:
                    extra.append("also recorded as " + ", ".join(spellings)
                                 + ", read as one medium by the alias table")
            others = rate.get("capacity_other_media") or []
            if others:
                extra.append(f"{len(others)} other medium(s) hold a plateau of this organism, named below")
            left = rate.get("capacity_left_out") or []
            if left:
                extra.append(f"{len(left)} curve(s) gave no capacity")
            # a derivation that fits each row has fitted rows rather than monoculture replicates, and
            # says so, so the count is not read as a number of cultures (#142 item 4)
            lines.append(f"  - {rate.get('name', nid)}: {rate['rate']:.4g} {rate.get('unit', '')}, median of "
                         f"{rate.get('n', 0)} {rate.get('n_label', 'monoculture replicate(s)')}"
                         + (f" ({per_study})" if per_study else "")
                         + ("; " + ", ".join(extra) if extra else ""))
            for label in others:
                lines.append(f"      a plateau in {label} is not pooled into the capacity above")
            for label, why in left:
                lines.append(f"      no capacity from {label}: {why}")
        missing = rates.get("without_a_rate") or []
        if missing:
            lines.append("  no growth rate (a gLV simulation needs one from elsewhere): " + ", ".join(missing))
        lines.append("")

    if result.get("steady") is not None:
        from .steady import as_text
        lines += as_text(result["steady"]).splitlines()
        lines.append("")

    skips = condensed(result["skipped"])
    lines.append(f"pairs the data did not support ({len(skips)}):" if skips
                 else "pairs the data did not support: none")
    lines += [f"  - {label}: {reason}" for label, reason in skips]
    lines.append("")

    lines.append("sources (cite the studies behind the edges you use):")
    for sid, study in sorted(net.studies.items()):
        lines.append(f"  - {sid}: {study.citation or sid} [{study.license or 'license: see study'}]"
                     + (f" {study.url}" if study.url else ""))
    if not net.studies:
        lines.append("  none")
    return "\n".join(lines) + "\n"
