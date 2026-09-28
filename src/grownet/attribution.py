"""Edge-level per-study attribution.

Per-study licenses are respected by citing every study that supports a network at the edge
level (each edge names the studies behind it), rather than bundling. Adopted with K. Faust,
2026-09-14: it keeps the per-study terms clean and makes clear exactly which measurements
stand behind each edge.
"""
from __future__ import annotations

from .model import InteractionNetwork


def edge_citations(net: InteractionNetwork) -> list:
    """Each edge with the studies (id and license) that support it."""
    rows = []
    for e in net.edges:
        rows.append({
            "edge": f"{e.source}->{e.target}",
            "effect": e.effect,
            "studies": [
                {"id": s, "license": net.studies[s].license if s in net.studies else ""}
                for s in e.study_ids
            ],
        })
    return rows


def studies_with_edges(net: InteractionNetwork) -> dict:
    """Each study mapped to the edges it supports (edge-level resolution)."""
    out = {sid: [] for sid in net.studies}
    for e in net.edges:
        for s in e.study_ids:
            out.setdefault(s, []).append(f"{e.source}->{e.target}")
    return out


def render_attribution(net: InteractionNetwork) -> str:
    """A human-readable attribution block: studies, licenses, and the edges each supports."""
    lines = ["Sources (cited at the edge level; per-study licenses respected):"]
    edges_by_study = studies_with_edges(net)
    for sid, study in sorted(net.studies.items()):
        n = len(edges_by_study.get(sid, []))
        lic = study.license or "license: see study"
        cite = study.citation or sid
        lines.append(f"  {sid}: {cite} [{lic}] supports {n} edge(s)")
    return "\n".join(lines)
