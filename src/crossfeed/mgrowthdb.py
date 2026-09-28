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
import datetime
import hashlib
import http.client
import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable

from . import __version__
from .brand import NAME
from .model import Edge, InteractionNetwork, Node, Study

MGROWTHDB_API = "https://mgrowthdb.gbiomed.kuleuven.be/api/v1"
API_DOCS = "https://mgrowthdb.readthedocs.io/en/latest/api.html"


class MGrowthDBError(RuntimeError):
    """A failed mGrowthDB request: a bad id, a network error, or the API being unreachable."""


class _Status(Exception):
    """An HTTP error status from mGrowthDB, raised by `_send` for the retry logic to judge."""

    def __init__(self, code: int, reason: str = ""):
        super().__init__(f"{code} {reason}".strip())
        self.code = code


# what a dropped or refused connection raises below urllib: retried like a network error
_NETWORK = (OSError, http.client.HTTPException)


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
        # one kept-open connection per thread: a new HTTPS connection per request cost about 120 ms against
        # 55 ms on an open one, and the parallel prefetch (crossfeed.fetch) gives each worker its own
        self._local = threading.local()
        parsed = urllib.parse.urlsplit(self.base_url)
        self._scheme, self._host, self._prefix = parsed.scheme, parsed.netloc, parsed.path
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

    def _connection(self, fresh: bool = False):
        conn = getattr(self._local, "conn", None)
        if fresh or conn is None:
            if conn is not None:
                conn.close()
            kind = http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
            conn = self._local.conn = kind(self._host, timeout=self.timeout)
        return conn

    def _send(self, url: str, accept: str) -> bytes:
        """One request over this thread's open connection, reopened once if the server dropped it."""
        path = url[len(f"{self._scheme}://{self._host}"):] if url.startswith(f"{self._scheme}://") else url
        headers = {"Accept": accept, "User-Agent": f"crossfeed/{__version__}", "Connection": "keep-alive"}
        for attempt in (0, 1):
            conn = self._connection(fresh=attempt == 1)
            try:
                conn.request("GET", path, headers=headers)
                response = conn.getresponse()
                body = response.read()
            except _NETWORK:
                if attempt == 1:
                    raise
                continue                          # a kept-open connection the server had closed: reopen
            if response.status >= 400:
                raise _Status(response.status, response.reason)
            return body
        raise OSError("unreachable")               # not reached

    def _request(self, url: str, accept: str) -> bytes:
        """`_send` with the retry rule: a 4xx is a real error (a bad id) and is not retried; a 5xx or a
        network failure may be transient and is retried with a growing pause. JSON and CSV alike."""
        last = None
        for attempt in range(self.retries):
            try:
                return self._send(url, accept)
            except _Status as e:
                if e.code < 500:
                    raise MGrowthDBError(
                        f"mGrowthDB returned HTTP {e.code} for {url} (check the id; API docs: {API_DOCS})"
                    ) from None
                last = MGrowthDBError(f"mGrowthDB returned HTTP {e.code} for {url} (server error)")
            except _NETWORK as e:
                last = MGrowthDBError(
                    f"could not reach mGrowthDB at {url}: {getattr(e, 'reason', e) or type(e).__name__} "
                    "(check your network; the API may be temporarily down)"
                )
            if attempt < self.retries - 1:
                time.sleep(self.backoff * (attempt + 1))
        raise last

    def _get_text(self, path: str) -> str:
        """Fetch a non-JSON representation (the CSV of a measurement context), cached like the rest."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        cached = self._cache_get(url)
        if cached is not None:
            return cached
        text = self._request(url, "text/csv").decode("utf-8")
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
        data = json.loads(self._request(url, "application/json").decode("utf-8"))
        self._cache_put(url, data)
        return data

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


def provenance(today: datetime.date | None = None, now: datetime.datetime | None = None) -> dict:
    """What made a network and when: the tool, its version, and the derivation date and time (local, with
    its offset). mGrowthDB changes over time, so the same version can derive a different network later;
    the time says which data it saw."""
    now = now or datetime.datetime.now().astimezone()
    return {"tool": NAME, "tool_version": __version__,
            "derived_on": (today or now.date()).isoformat(),
            "derived_at": now.isoformat(timespec="seconds")}


# mGrowthDB publishes no version of the database as a whole (its API has no version endpoint), so the
# version of the data behind a network is when it was read plus each study's own upload and publication
# dates, which change when a study is corrected.
NO_DATABASE_VERSION = "mGrowthDB publishes no database version; each study's upload and publication dates are given"


def data_versions(client, study_ids, retrieved_at: str) -> dict:
    """The data a search read: the API, when, and for each study its uploadedAt and publishedAt."""
    studies = {}
    for sid in study_ids:
        try:
            study = client.get_study(sid)          # cached by the client, so no second request
        except MGrowthDBError:
            continue
        studies[sid] = {"uploaded_at": study.get("uploadedAt", ""), "published_at": study.get("publishedAt", "")}
    return {"api": MGROWTHDB_API, "retrieved_at": retrieved_at, "database_version": NO_DATABASE_VERSION,
            "studies": studies}


def records_to_network(records: Iterable[dict], meta: dict | None = None) -> InteractionNetwork:
    """Map interaction records into the neutral network. Real and testable.

    Each record:
      {source, target, source_name?, target_name?, source_taxon_id?, source_species?, source_identity?
       (and the same for target), strength, significance, condition, method?, effect?,
       evidence?, community?, p_value?, weight?, effect_over_sd?, status?, sd?, se?, n_with?,
       n_without?, outcome?, metric?, quality?, notes?, cautions?, experiments?, cultivation_mode?,
       merged_arcs?, strength_range?, supporting_pairs?, merged_pairs?,
       study_id, study_citation?, study_license?, study_url?,
       studies? (a merged arc: [{id, citation, license, url}], one per study it rests on)}

    `meta` starts from `provenance()` (tool, version, derivation date); keys given in `meta` win.
    """
    net = InteractionNetwork(meta={**provenance(), **(meta or {})})
    for r in records:
        for side in ("source", "target"):
            nid = r[side]
            if nid not in net.nodes:
                net.add_node(Node(id=nid, name=r.get(f"{side}_name", ""), taxon_id=r.get(f"{side}_taxon_id", ""),
                                  species=r.get(f"{side}_species", ""), identity=r.get(f"{side}_identity", "")))
        # a merged arc (register item 14) rests on several studies and lists them; any other on one
        studies = r.get("studies") or [{"id": r["study_id"], "citation": r.get("study_citation", ""),
                                        "license": r.get("study_license", ""), "url": r.get("study_url", "")}]
        for st in studies:
            if st["id"] not in net.studies:
                net.add_study(Study(id=st["id"], citation=st.get("citation", ""),
                                    license=st.get("license", ""), url=st.get("url", "")))
        sid = r.get("study_id", studies[0]["id"])
        effect = r.get("effect") or effect_from_logratio(r.get("strength"), r.get("significance"))
        net.add_edge(Edge(
            source=r["source"], target=r["target"], effect=effect,
            strength=r.get("strength"), significance=r.get("significance"),
            condition=r.get("condition", ""), method=r.get("method", ""),
            study_ids=tuple(st["id"] for st in studies) if r.get("studies") else (sid,),
            evidence=r.get("evidence"), community=tuple(r.get("community", ())),
            p_value=r.get("p_value"), weight=r.get("weight"), effect_over_sd=r.get("effect_over_sd"),
            status=r.get("status"), sd=r.get("sd"), se=r.get("se"),
            n_with=r.get("n_with"), n_without=r.get("n_without"),
            outcome=r.get("outcome"), metric=r.get("metric", ""),
            quality=tuple(r.get("quality", ())), notes=tuple(r.get("notes", ())),
            cautions=tuple(r.get("cautions", ())), experiments=tuple(r.get("experiments", ())),
            cultivation_mode=r.get("cultivation_mode", ""),
            merged_arcs=r.get("merged_arcs"), strength_range=tuple(r.get("strength_range", ())),
            supporting_pairs=r.get("supporting_pairs"), merged_pairs=tuple(r.get("merged_pairs", ())),
        ))
    return net
