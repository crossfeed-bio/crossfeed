"""mGrowthDB access and mapping into the crossfeed neutral network.

The live HTTP client is intentionally a TODO: it must be wired against the real API
(https://mgrowthdb.readthedocs.io/en/latest/api.html) rather than guessed. The mapping
from interaction RECORDS to an InteractionNetwork is real and testable, so the pipeline
seam can be exercised on a fixture before the live API is connected.

An interaction record (the shape crossfeed consumes) mirrors how mGrowthDB reports a
co-growth interaction: a directed pair with a growth log-ratio, an adjusted p-value, the
experimental condition, and the study it came from. See docs/DATA_GOVERNANCE.md: mGrowthDB
is open, so pulling is fine; per-study licenses are respected at the edge level.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .model import Edge, InteractionNetwork, Node, Study

MGROWTHDB_API = "https://mgrowthdb.gbiomed.kuleuven.be"   # base; endpoints per the API docs (to wire)
API_DOCS = "https://mgrowthdb.readthedocs.io/en/latest/api.html"


def effect_from_logratio(strength: Optional[float], significance: Optional[float], alpha: float = 0.05) -> str:
    """Facilitation (significant positive), inhibition (significant negative), else neutral."""
    if strength is None or significance is None:
        return "neutral"
    if significance > alpha:
        return "neutral"
    return "facilitation" if strength > 0 else "inhibition"


def records_to_network(records: Iterable[dict], meta: Optional[dict] = None) -> InteractionNetwork:
    """Map mGrowthDB interaction records into the neutral network. Real and testable.

    Each record:
      {source, target, source_name?, target_name?, strength, significance, condition,
       method?, effect?, study_id, study_citation?, study_license?, study_url?}
    """
    net = InteractionNetwork(meta=dict(meta or {}))
    for r in records:
        for side in ("source", "target"):
            nid = r[side]
            if nid not in net.nodes:
                net.add_node(Node(id=nid, name=r.get(f"{side}_name", "")))
        sid = r["study_id"]
        if sid not in net.studies:
            net.add_study(Study(
                id=sid,
                citation=r.get("study_citation", ""),
                license=r.get("study_license", ""),
                url=r.get("study_url", ""),
            ))
        effect = r.get("effect") or effect_from_logratio(r.get("strength"), r.get("significance"))
        net.add_edge(Edge(
            source=r["source"],
            target=r["target"],
            effect=effect,
            strength=r.get("strength"),
            significance=r.get("significance"),
            condition=r.get("condition", ""),
            method=r.get("method", ""),
            study_ids=(sid,),
        ))
    return net


class MGrowthDBClient:
    """Thin client over the mGrowthDB API. The HTTP calls are TODO (wire per API_DOCS)."""

    def __init__(self, base_url: str = MGROWTHDB_API):
        self.base_url = base_url.rstrip("/")

    def fetch_study_interactions(self, study_id: str) -> list:
        raise NotImplementedError(
            "Wire the live mGrowthDB API call here, per %s . Return a list of interaction "
            "records in the shape records_to_network() consumes. Until then, load records from "
            "a local export or fixture and call records_to_network()." % API_DOCS
        )

    def build_network(self, study_id: str, meta: Optional[dict] = None) -> InteractionNetwork:
        records = self.fetch_study_interactions(study_id)
        m = {"source_db": "mGrowthDB", "study_id": study_id}
        m.update(meta or {})
        return records_to_network(records, meta=m)
