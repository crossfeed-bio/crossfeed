"""mGrowthDB API client and the mapping into the grownet neutral network.

Wired against the live REST API, base `https://mgrowthdb.gbiomed.kuleuven.be/api/v1/`, documented at
https://mgrowthdb.readthedocs.io/en/latest/api.html .

Important: the API serves RAW growth data (study -> experiments -> bioreplicates -> measurement
contexts). It does NOT serve pre-computed interactions. Interactions are DERIVED by comparing a
strain's growth alone vs with a partner (see grownet.derive). Public data needs no auth. mGrowthDB is
open (see docs/DATA_GOVERNANCE.md); grownet pulls from it but never commits raw or pulled data.

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
import sys
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
    """A failed mGrowthDB request: a bad id, a network error, or the API being unreachable.

    `status` is the HTTP status when mGrowthDB answered (404 for an id it does not hold), and None when it
    could not be reached, so a caller can tell "no such study" from "mGrowthDB is down" (step 7 of the
    audit, 2026-09-28: an unreachable mGrowthDB read as an empty database)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class _Status(Exception):
    """An HTTP error status from mGrowthDB, raised by `_send` for the retry logic to judge."""

    def __init__(self, code: int, reason: str = ""):
        super().__init__(f"{code} {reason}".strip())
        self.code = code


# what a dropped or refused connection raises below urllib: retried like a network error
_NETWORK = (OSError, http.client.HTTPException)


# Measurements used to be read fresh on every run, because mGrowthDB serves only the latest version of a
# study and a cached curve could silently be an old one. What makes keeping them safe is that a study's
# `uploadedAt` moves whenever the study is revised, which **Karoline confirmed for the mGrowthDB team**
# (2026-10-09): "I can confirm for the mGrowthDB team, that uploadedAt is kept fresh - it's coupled to
# study submission."
#
# So: everything a study holds may be reused while that study's `uploadedAt` is unchanged, and the study
# record itself is always read live, because it is the freshness check. A corpus run sends 3738 requests
# (2195 bioreplicate records, 930 series, 559 experiments, 54 studies); with nothing changed it now sends
# the 54 study records and nothing else. The daily All workflow runs on ephemeral runners, so it keeps
# re-reading everything unless a cache is carried deliberately, which is the conservative default for the
# one network published to readers (#182).
CACHE_VERSION = 1          # the layout of the kept files; a change here abandons the old ones
_DEFAULT = object()        # "cache_dir not given", so None can mean "keep nothing"


def cache_home(app: str = NAME) -> str:
    """Where kept responses go: the user's own cache directory, never inside the repository.

    `GROWNET_CACHE` overrides it, and the usual per-system places are used otherwise. Only the standard
    library is available here, so the paths are spelled out rather than taken from a package.
    """
    told = os.environ.get("GROWNET_CACHE")
    if told:
        return told
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, app.lower(), f"v{CACHE_VERSION}")


class MGrowthDBClient:
    """A thin read-only client over the mGrowthDB REST API (public endpoints, no auth needed).

    Args:
      base_url: API base; override to point at a mirror or a test server.
      timeout:  per-request timeout in seconds.
      retries:  attempts on a transient failure (network error or HTTP 5xx) before giving up.
      backoff:  base seconds between retries (grows linearly with the attempt).
      cache:    keep an in-memory response cache for the life of the client.
      cache_dir: where to keep responses between runs. The default is `cache_home()`, the user's own
                cache directory and never inside the repo; None or "" keeps nothing between runs.
    """

    def __init__(self, base_url: str = MGROWTHDB_API, timeout: int = 30, retries: int = 3,
                 backoff: float = 0.5, cache: bool = True, cache_dir: str | None = _DEFAULT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff = max(0.0, float(backoff))
        self._mem = {} if cache else None
        self.cache_dir = cache_home() if cache_dir is _DEFAULT else (cache_dir or None)
        # Each kept response carries the study it belongs to and the `uploadedAt` it was read at, in its
        # own file, so there is no index to keep in step and a half-written run loses nothing: a response
        # whose study has moved on is simply read again. What is in memory is only this run's knowledge.
        self._uploaded: dict = {}      # study id -> uploadedAt, as this run read it live
        self._of_record: dict = {}     # experiment or bioreplicate or context id -> study id
        # `_index_lock` guards everything below it that the threads share. One client is passed to
        # `fetch.prefetch_studies`, which runs its methods on `WORKERS` threads, and `x += 1` is a load, an
        # add and a store with a thread switch possible between them, so the counters take it too: both are
        # printed to a reader as the evidence that a network rests on kept responses (Craig's agent, #185).
        self._index_lock = threading.Lock()
        self.reused = 0                # responses served from the kept files, for the report
        self.fetched = 0               # responses read from mGrowthDB
        self.refreshed: list = []      # studies whose `uploadedAt` moved, so their responses were dropped
        # one kept-open connection per thread: a new HTTPS connection per request cost about 120 ms against
        # 55 ms on an open one, and the parallel prefetch (grownet.fetch) gives each worker its own
        self._local = threading.local()
        parsed = urllib.parse.urlsplit(self.base_url)
        self._scheme, self._host, self._prefix = parsed.scheme, parsed.netloc, parsed.path
        if self.cache_dir:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
            except OSError:
                self.cache_dir = None          # an unwritable cache is no reason to fail a search

    def _study_of(self, url: str) -> str:
        """The study a URL belongs to, from the records already read, or "" when it cannot be told.

        Only `study/<id>.json` names its study in the URL. An experiment, a bioreplicate and a series are
        reached through records that carry `studyId` (or, for a series, through the bioreplicate that lists
        it), so the client learns the ownership as it reads, from live responses and from kept ones alike.
        A URL whose study cannot be told is never served from the kept files, because nothing can say
        whether it is still current.
        """
        name = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if url.endswith(".json") and "/study/" in url:
            return name
        return self._of_record.get(name, "")

    def _learn(self, url: str, data) -> None:
        """What a record says about ownership: a study lists its experiments, an experiment and a
        bioreplicate carry `studyId`, and a bioreplicate lists the series it holds. Called for a kept
        response as well as a fresh one, so a run that reads nothing still knows what belongs where."""
        if not isinstance(data, dict):
            return
        sid = data.get("id") if "/study/" in url else data.get("studyId")
        if not isinstance(sid, str) or not sid:
            return
        learned = {}
        for key in ("experiments", "bioreplicates", "measurementContexts"):
            for item in data.get(key) or []:
                ident = item.get("id") if isinstance(item, dict) else item
                if ident:
                    learned[str(ident)] = sid
        own = data.get("id")
        if own and "/study/" not in url:
            learned[str(own)] = sid
        if learned:
            with self._index_lock:
                self._of_record.update(learned)

    def _disk_path(self, key: str) -> str:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.cache_dir, f"{h}.json")

    def _stale(self, path: str, owner) -> bool:
        """Whether a kept response may no longer be used, and drop it when so.

        `owner` is the study and the `uploadedAt` the response was read at, written beside it. It may be
        used only when this run has read that study's `uploadedAt` live and the two agree. A study this run
        has not checked is not served from, because the check is the guarantee; a study whose stamp has
        moved has that response deleted, which is the revision case.
        """
        if not isinstance(owner, (list, tuple)) or len(owner) != 2:
            return True
        sid, uploaded = owner
        live = self._uploaded.get(sid)
        if live is None:
            return True
        if live != uploaded:
            with self._index_lock:
                if sid not in self.refreshed:
                    self.refreshed.append(sid)
            try:
                os.remove(path)
            except OSError:
                pass
            return True
        return False

    def _cache_get(self, key: str):
        if self._mem is not None and key in self._mem:
            return self._mem[key]
        if not self.cache_dir:
            return None
        path = self._disk_path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                kept = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(kept, dict) or "body" not in kept or self._stale(path, kept.get("owner")):
            return None
        data = kept["body"]
        if self._mem is not None:
            self._mem[key] = data
        self._learn(key, data)                 # so a series kept from an earlier run still knows its study
        with self._index_lock:
            self.reused += 1
        return data

    def _cache_put(self, key: str, data) -> None:
        if self._mem is not None:
            self._mem[key] = data
        if not self.cache_dir:
            return
        self._learn(key, data)
        sid = self._study_of(key)
        uploaded = self._uploaded.get(sid) if sid else None
        if not sid or uploaded is None:
            return          # nothing to validate it against later, so it is not kept between runs
        try:
            with open(self._disk_path(key), "w", encoding="utf-8") as f:
                json.dump({"owner": [sid, uploaded], "body": data}, f)
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
        headers = {"Accept": accept, "User-Agent": f"grownet/{__version__}", "Connection": "keep-alive"}
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
                        f"mGrowthDB returned HTTP {e.code} for {url} (check the id; API docs: {API_DOCS})",
                        status=e.code) from None
                last = MGrowthDBError(f"mGrowthDB returned HTTP {e.code} for {url} (server error)", status=e.code)
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
        with self._index_lock:
            self.fetched += 1
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
        with self._index_lock:
            self.fetched += 1
        self._cache_put(url, data)
        return data

    def get_study(self, study_id: str) -> dict:
        """Study metadata: id, name, projectId, description, publishedAt, experiments[{id, name}].

        **Always read live when responses are kept between runs**, because its `uploadedAt` is what says
        whether everything else kept for this study may still be used (#182). Within one run the in-memory
        cache still serves it, so a study is read once however many times it is asked for.
        """
        url = f"{self.base_url}/study/{study_id}.json"
        if self._mem is not None and url in self._mem:
            return self._mem[url]
        data = json.loads(self._request(url, "application/json").decode("utf-8"))
        uploaded = data.get("uploadedAt", "")
        with self._index_lock:
            self.fetched += 1
            self._uploaded[study_id] = uploaded
        if self._mem is not None:
            self._mem[url] = data
        # reading it live is what tells the rest of this study's kept responses whether they may be used,
        # and `_cache_put` now has the stamp to write beside this one
        self._cache_put(url, data)
        return data

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

def effect_from_logratio(strength, q_value, alpha: float = 0.05) -> str:
    """Facilitation / inhibition / neutral. A None q-value is treated as qualitative (decide by sign); a
    q-value above alpha is neutral. It takes the q-value, not `significance`, which is -log10 of it and
    runs the other way (Karoline, 2026-10-03)."""
    if strength is None:
        return "neutral"
    if q_value is not None and q_value > alpha:
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
       (and the same for target), strength, significance (-log10 q), q_value, condition, method?, effect?,
       evidence?, community?, p_value?, weight?, effect_over_sd?, status?, sd?, se?, n_with?,
       n_without?, outcome?, metric?, quality?, notes?, cautions?, experiments?, cultivation_mode?, medium?,
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
        effect = r.get("effect") or effect_from_logratio(r.get("strength"), r.get("q_value"))
        net.add_edge(Edge(
            source=r["source"], target=r["target"], effect=effect,
            strength=r.get("strength"), significance=r.get("significance"), q_value=r.get("q_value"),
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
            medium=r.get("medium", ""),
            partner_abundance=r.get("partner_abundance"),
            partner_abundance_unit=r.get("partner_abundance_unit", ""),
            partner_abundance_n=r.get("partner_abundance_n"),
            metric_with=r.get("metric_with"), metric_without=r.get("metric_without"),
            target_capacity=r.get("target_capacity"),
            target_capacity_unit=r.get("target_capacity_unit", ""),
            target_capacity_n=r.get("target_capacity_n"),
            strength_bound=r.get("strength_bound"), bound_rule=r.get("bound_rule", ""),
            coefficient=r.get("coefficient"), coefficient_unit=r.get("coefficient_unit", ""),
            fit_r2=r.get("fit_r2"), fit_condition=r.get("fit_condition"),
            coefficient_sd=r.get("coefficient_sd"), coefficient_n=r.get("coefficient_n"),
            coefficient_sd_from_rate_stage=r.get("coefficient_sd_from_rate_stage"),
            fit_null_r2=r.get("fit_null_r2"),
            fit_window_share=r.get("fit_window_share"),
            rate_mismatch_to_zero=r.get("rate_mismatch_to_zero"),
            se_replicates=r.get("se_replicates"), se_rate_stage=r.get("se_rate_stage"),
            rate_stage_method=r.get("rate_stage_method", "") or "",
            rate_stage_n=r.get("rate_stage_n"),
            merged_arcs=r.get("merged_arcs"), strength_range=tuple(r.get("strength_range", ())),
            supporting_pairs=r.get("supporting_pairs"), merged_pairs=tuple(r.get("merged_pairs", ())),
        ))
    return net
