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
    if value is None and key.startswith("no_growth_"):
        value = getattr(interaction, key.upper())      # None: the rule's own default
    if value is True:
        return "on"
    if value is False:
        return "off"
    return "none" if value == "" else str(value)


def _mean_sd(e) -> str:
    if e.strength is None:
        return "no ratio (one side did not grow)"
    return f"log2 mean {e.strength:+.2f}" + ("" if e.sd is None else f" +/- {e.sd:.2f}")


def _edge_line(net, e) -> str:
    name = {nid: node.name or nid for nid, node in net.nodes.items()}
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
    if e.significance is not None:
        parts.append(f"adjusted p {e.significance:.3g}")
    parts.append(f"condition {e.condition}")
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
             f"data version: {data.get('database_version', NO_DATABASE_VERSION)}", ""]

    if result.get("study"):
        lines.append(f"study derived: {result['study']} (every species in it)")
    elif result.get("all"):
        lines.append("query: all of mGrowthDB (every study, with every partner)")
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
    absent = [e for e in net.edges if e.status == "absent"]
    hidden = meta.get("hidden", {}).get("low_quality", 0)
    rule = meta.get("no_growth", {})
    lines.append(f"result: {len(shown)} interaction(s), {len(absent)} below the absence threshold "
                 f"(k = {meta.get('absence', {}).get('k', '')}), {hidden} low-quality edge(s) hidden")
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
        lines.append("below the absence threshold (no interaction found):")
        lines += [_edge_line(net, e) for e in absent]
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
