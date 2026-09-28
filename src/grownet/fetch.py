"""Fetch from mGrowthDB in parallel, so a search waits on the network once instead of hundreds of times.

A search spent nearly all its time waiting on requests made one after another: about 840 of them, near
100 ms each, for the Example (59 s for the species list, 25 s for the search). The derivation itself is
fast. So these functions read, a few requests at a time, exactly what the derivation is about to read, into
the client's in-memory cache. The derivation then runs unchanged and finds everything there: the results
cannot differ from a derivation that fetched one request at a time, and anything a prefetch misses is
simply fetched when asked for, as before.

At most WORKERS requests are in flight at once, each worker on its own kept-open connection (see
`MGrowthDBClient._connection`), which keeps the load on mGrowthDB modest. Nothing is kept between sessions:
mGrowthDB shows only the latest version of a study, and its change history is not in the API, so a cache
across sessions could not tell when it had gone stale (Karoline, 2026-09-27).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .adapter import _strain_contexts
from .derive import BATCH, cultivation
from .mgrowthdb import MGrowthDBError

WORKERS = 6


def _each(fn, items, progress=None, message="", failures=None):
    """fn over items, WORKERS at a time; a failed item gives None (the derivation will meet and report the
    same failure when it asks for that item itself). `failures`, when given, collects (item, error)."""
    items = list(items)
    results = [None] * len(items)

    def run(i):
        try:
            results[i] = fn(items[i])
        except (MGrowthDBError, OSError, ValueError, KeyError) as e:
            results[i] = None
            if failures is not None:
                failures.append((items[i], e))
        return i

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for done, _ in enumerate(pool.map(run, range(len(items))), start=1):
            if progress and (done == len(items) or done % 10 == 0):
                progress(done, len(items), f"{message} ({done} of {len(items)})")
    return results


def can_prefetch(client) -> bool:
    """Whether a client offers the single-record reads a prefetch uses (test doubles often do not; they
    then get the one-by-one path, which is what a prefetch only speeds up)."""
    return all(hasattr(client, name) for name in
               ("get_study", "get_experiment", "get_bioreplicate", "get_measurement_series"))


def prefetch_studies(client, study_ids, include_non_batch: bool = False, progress=None, keep=None,
                     dropout: bool = True) -> None:
    """Load what deriving these studies reads: the studies, their experiments, the bioreplicates of the
    experiments that are derived (batch only unless `include_non_batch`, as `derive._batch_only`), and
    the series of each strain's measurement context that `adapter.replicates_for_experiment` reads."""
    if not can_prefetch(client):
        return
    studies = [s for s in _each(client.get_study, study_ids) if s]
    experiment_ids = [e["id"] for s in studies for e in s.get("experiments", [])]
    experiments = [e for e in _each(client.get_experiment, experiment_ids, progress, "Reading experiments") if e]
    derived = [e for e in experiments if include_non_batch or cultivation(e) == BATCH]
    # only what the derivation reads (derive.relevant_experiments), per study: with `keep`, what can give an
    # interaction between kept strains; without it, what can take part in any comparison
    from .derive import relevant_experiments
    by_study = {}
    for e in derived:
        by_study.setdefault(e.get("studyId"), []).append(e)
    derived = [e for group in by_study.values() for e in relevant_experiments(group, keep, dropout)]
    stubs = [b["id"] for e in derived for b in e.get("bioreplicates", [])]
    bioreplicates = [b for b in _each(client.get_bioreplicate, stubs, progress, "Reading replicates") if b]
    contexts = []
    for bioreplicate in bioreplicates:
        if bioreplicate.get("isAverage"):
            continue
        pairs = list(_strain_contexts(bioreplicate))
        counts = {}
        for species, _ in pairs:
            counts[species] = counts.get(species, 0) + 1
        contexts += [context["id"] for species, context in pairs if counts[species] == 1]
    _each(client.get_measurement_series, contexts, progress, "Reading growth curves")


def study_ids_in_order(client, study_id_format: str, max_studies: int, miss_run: int) -> list:
    """The ids of the studies mGrowthDB holds, found as `taxonomy.species_index` always found them: in id
    order, stopping after `miss_run` absent ids in a row. Ids are asked for WORKERS at a time; the stop is
    judged in order, so the answer is the same as asking one by one."""
    found, misses, n = [], 0, 1
    while n <= max_studies and misses < miss_run:
        batch = list(range(n, min(n + WORKERS, max_studies + 1)))
        failures = []
        studies = _each(client.get_study, [study_id_format.format(i) for i in batch], failures=failures)
        # only "no such study" (HTTP 404) ends the crawl; anything else (unreachable, a timeout, a server
        # error after its retries) is reported, never read as mGrowthDB holding fewer studies
        down = [(sid, e) for sid, e in failures if getattr(e, "status", None) != 404]
        if down:
            sid, e = down[0]
            raise MGrowthDBError(f"mGrowthDB could not be read (asking for {sid}): {e}",
                                 status=getattr(e, "status", None))
        for i, study in zip(batch, studies, strict=True):
            if misses >= miss_run:
                break
            if study is None:
                misses += 1
            else:
                misses = 0
                found.append(study_id_format.format(i))
        n = batch[-1] + 1
    return found
