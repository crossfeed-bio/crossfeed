"""mGrowthDB API client and the mapping into the crossfeed neutral network.

Wired against the live REST API, base `https://mgrowthdb.gbiomed.kuleuven.be/api/v1/`, documented at
https://mgrowthdb.readthedocs.io/en/latest/api.html .

Important: the API serves RAW growth data (study -> experiments -> bioreplicates -> measurement
contexts). It does NOT serve pre-computed interactions. Interactions are DERIVED by comparing a
strain's growth alone vs with a partner (see crossfeed.derive). Public data needs no auth. mGrowthDB is
open (see docs/DATA_GOVERNANCE.md); crossfeed pulls from it but never commits raw or pulled data.

The client works for ANY study id (get_study, get_experiment, study_experiments). It caches responses
in memory for the life of the client (and optionally on disk via `cache_dir`) so repeated pulls of the
same study do not re-hit the API, and it retries transient network failures and 5xx responses with a
short backoff. A cache is a convenience, never a substitute for pulling fresh: nothing pulled is
committed to the repository.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable

from . import __version__
from .model import Edge, InteractionNetwork, Node, Study

MGROWTHDB_API = "https://mgrowthdb.gbiomed.kuleuven.be/api/v1"
API_DOCS = "https://mgrowthdb.readthedocs.io/en/latest/api.html"


class MGrowthDBError(RuntimeError):
    """A failed mGrowthDB request: a bad id, a network error, or the API being unreachable."""


class MGrowthDBClient:
    """A thin read-only client over the mGrowthDB REST API (public endpoints, no auth needed).

    Args:
      base_url: API base; override to point at a mirror or a test server.
      timeout:  per-request timeout in seconds.
      retries:  attempts on a transient failure (network error or HTTP 5xx) before giving up.
      backoff:  base seconds between retries (grows linearly with the attempt).
      cache:    keep an in-memory response cache for the life of the client.
      cache_dir: optional directory for an on-disk JSON cache across runs (never inside the repo).
    """

    def __init__(self, base_url: str = MGROWTHDB_API, timeout: int = 30, retries: int = 3,
                 backoff: float = 0.5, cache: bool = True, cache_dir: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff = max(0.0, float(backoff))
        self._mem = {} if cache else None
        self.cache_dir = cache_dir
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _disk_path(self, key: str) -> str:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.cache_dir, f"{h}.json")

    def _cache_get(self, key: str):
        if self._mem is not None and key in self._mem:
            return self._mem[key]
        if self.cache_dir:
            p = self._disk_path(key)
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f)
                    if self._mem is not None:
                        self._mem[key] = data
                    return data
                except (OSError, ValueError):
                    return None
        return None

    def _cache_put(self, key: str, data) -> None:
        if self._mem is not None:
            self._mem[key] = data
        if self.cache_dir:
            try:
                with open(self._disk_path(key), "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except OSError:
                pass

    def _get_text(self, path: str) -> str:
        """Fetch a non-JSON representation (the CSV of a measurement context), cached like the rest."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        cached = self._cache_get(url)
        if cached is not None:
            return cached
        req = urllib.request.Request(
            url, headers={"Accept": "text/csv", "User-Agent": f"crossfeed/{__version__}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise MGrowthDBError(
                f"mGrowthDB returned HTTP {e.code} for {url} (check the id; API docs: {API_DOCS})"
            ) from e
        except urllib.error.URLError as e:
            raise MGrowthDBError(f"could not reach mGrowthDB at {url}: {e.reason}") from e
        self._cache_put(url, text)
        return text

    def _get(self, path: str, params: dict | None = None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)

        cached = self._cache_get(url)
        if cached is not None:
            return cached

        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": f"crossfeed/{__version__}"}
        )
        last = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.load(r)
                self._cache_put(url, data)
                return data
            except urllib.error.HTTPError as e:
                # 4xx are real errors (a bad id): do not retry. 5xx may be transient: retry.
                if e.code < 500:
                    raise MGrowthDBError(
                        f"mGrowthDB returned HTTP {e.code} for {url} (check the id; API docs: {API_DOCS})"
                    ) from e
                last = MGrowthDBError(f"mGrowthDB returned HTTP {e.code} for {url} (server error)")
            except urllib.error.URLError as e:
                last = MGrowthDBError(
                    f"could not reach mGrowthDB at {url}: {e.reason} "
                    "(check your network; the API may be temporarily down)"
                )
            if attempt < self.retries - 1:
                time.sleep(self.backoff * (attempt + 1))
        raise last

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

    def get_measurement_series(self, context_id) -> list:
        """The measured time series of one measurement context: [(time, value, std or None), ...].

        mGrowthDB serves the points as CSV (`measurement-context/<id>.csv`, columns time, value, std); the
        JSON representation carries only the summarized growthRate and auc. Rows without a readable time
        or value are dropped, and the points are returned in time order.
        """
        text = self._get_text(f"measurement-context/{context_id}.csv")
        points = []
        for row in csv.DictReader(io.StringIO(text)):
            try:
                time_point, value = float(row["time"]), float(row["value"])
            except (TypeError, ValueError, KeyError):
                continue
            try:
                std = float(row.get("std") or "")
            except ValueError:
                std = None
            points.append((time_point, value, std))
        return sorted(points)

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


def records_to_network(records: Iterable[dict], meta: dict | None = None) -> InteractionNetwork:
    """Map interaction records into the neutral network. Real and testable.

    Each record:
      {source, target, source_name?, target_name?, strength, significance, condition, method?, effect?,
       evidence?, community?, se?, n_with?, n_without?, outcome?, metric?,
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
            evidence=r.get("evidence"), community=tuple(r.get("community", ())),
            se=r.get("se"), n_with=r.get("n_with"), n_without=r.get("n_without"),
            outcome=r.get("outcome"), metric=r.get("metric", ""),
        ))
    return net
