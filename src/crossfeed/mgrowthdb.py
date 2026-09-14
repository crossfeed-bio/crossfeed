"""mGrowthDB API client and the mapping into the crossfeed neutral network.

Wired against the live REST API, base `https://mgrowthdb.gbiomed.kuleuven.be/api/v1/`, documented at
https://mgrowthdb.readthedocs.io/en/latest/api.html .

Important: the API serves RAW growth data (study -> experiments -> bioreplicates -> measurement
contexts). It does NOT serve pre-computed interactions. Interactions are DERIVED by comparing a
strain's growth alone vs with a partner (see crossfeed.derive). Public data needs no auth. mGrowthDB is
open (see docs/DATA_GOVERNANCE.md); crossfeed pulls from it but never commits raw or pulled data.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Iterable, Optional

from .model import Edge, InteractionNetwork, Node, Study

MGROWTHDB_API = "https://mgrowthdb.gbiomed.kuleuven.be/api/v1"
API_DOCS = "https://mgrowthdb.readthedocs.io/en/latest/api.html"


class MGrowthDBClient:
    """A thin read-only client over the mGrowthDB REST API (public endpoints, no auth needed)."""

    def __init__(self, base_url: str = MGROWTHDB_API, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: Optional[dict] = None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "crossfeed/0.0.1"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def get_study(self, study_id: str) -> dict:
        """Study metadata: id, name, projectId, description, publishedAt, experiments[{id, name}]."""
        return self._get(f"study/{study_id}.json")

    def get_experiment(self, experiment_id: str) -> dict:
        """Experiment: cultivationMode, communityStrains[], bioreplicates[] (each with measurementContexts)."""
        return self._get(f"experiment/{experiment_id}.json")

    def get_bioreplicate(self, bioreplicate_id) -> dict:
        return self._get(f"bioreplicate/{bioreplicate_id}.json")

    def get_measurement_context(self, context_id) -> dict:
        """A single measurement context: techniqueType, subject, auc, growthRate, units, ..."""
        return self._get(f"measurement-context/{context_id}.json")

    def search(self, strain_ncbi_ids=None, metabolite_chebi_ids=None) -> dict:
        return self._get("search.json", {
            "strainNcbiIds": strain_ncbi_ids, "metaboliteChebiIds": metabolite_chebi_ids,
        })

    def study_experiments(self, study_id: str) -> list:
        """Full experiment records for a study (study metadata lists experiment ids only)."""
        study = self.get_study(study_id)
        return [self.get_experiment(e["id"]) for e in study.get("experiments", [])]


# ---- record -> network (the neutral mapping) -----------------------------------------------------

def effect_from_logratio(strength, significance, alpha: float = 0.05) -> str:
    """Facilitation / inhibition / neutral. A None significance is treated as qualitative (decide by
    sign); a significance above alpha is neutral."""
    if strength is None:
        return "neutral"
    if significance is not None and significance > alpha:
        return "neutral"
    return "facilitation" if strength > 0 else "inhibition"


def records_to_network(records: Iterable[dict], meta: Optional[dict] = None) -> InteractionNetwork:
    """Map interaction records into the neutral network. Real and testable.

    Each record:
      {source, target, source_name?, target_name?, strength, significance, condition, method?, effect?,
       study_id, study_citation?, study_license?, study_url?}
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
                id=sid, citation=r.get("study_citation", ""),
                license=r.get("study_license", ""), url=r.get("study_url", ""),
            ))
        effect = r.get("effect") or effect_from_logratio(r.get("strength"), r.get("significance"))
        net.add_edge(Edge(
            source=r["source"], target=r["target"], effect=effect,
            strength=r.get("strength"), significance=r.get("significance"),
            condition=r.get("condition", ""), method=r.get("method", ""), study_ids=(sid,),
        ))
    return net
