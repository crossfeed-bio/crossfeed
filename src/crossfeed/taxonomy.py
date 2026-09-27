"""Resolve species names to NCBI taxon ids, from mGrowthDB's own records.

mGrowthDB queries take NCBI taxon ids (`MGrowthDBClient.search`), while people type species names. Every
strain in mGrowthDB carries its taxon id (`NCBId` on an experiment's community strains), so the mapping is
built from the database itself: no second external service, and only names that mGrowthDB actually holds,
which are the only ones with data to find.

`species_index` crawls the studies once (the client caches responses, on disk when a cache_dir is set) and
returns genus and species keys mapped to the taxon ids seen under them. `resolve_species` turns what a
person typed, names or numeric taxon ids, into ids, and reports what mGrowthDB does not hold.

Nothing pulled here is written into the repository (see docs/DATA_GOVERNANCE.md).
"""
from __future__ import annotations

import difflib
import re

from .derive import genus_species

STUDY_ID = "SMGDB{:08d}"
MISS_RUN = 5          # stop crawling after this many consecutive study ids are absent
MAX_STUDIES = 500     # a hard stop, so a crawl can never run away


def _strain_entries(exp: dict):
    """(name, taxon id) for every community strain of an experiment that carries a taxon id."""
    for strain in exp.get("communityStrains", []):
        name, taxon = strain.get("name"), strain.get("NCBId")
        if name and taxon is not None:
            yield name, int(taxon)


def species_index(client, max_studies: int = MAX_STUDIES, progress=None) -> dict:
    """Map a genus and species key to {taxon id: a name seen for it}, crawled from mGrowthDB.

    Study ids are consecutive, so the crawl walks them and stops after MISS_RUN absent ids in a row. The
    studies and their experiments are read in parallel (`crossfeed.fetch`), then walked in id order, so the
    first name seen for a taxon is the same as a one-by-one crawl would keep. A study or experiment that
    cannot be read is skipped: a partial index is more useful than no index.
    """
    from .fetch import _each, study_ids_in_order

    if not (hasattr(client, "get_study") and hasattr(client, "get_experiment")):
        return _species_index_one_by_one(client, max_studies)
    ids = study_ids_in_order(client, STUDY_ID, max_studies, MISS_RUN)
    experiment_ids = [e["id"] for sid in ids for e in (client.get_study(sid) or {}).get("experiments", [])]
    _each(client.get_experiment, experiment_ids, progress, "Reading the species list of mGrowthDB")
    index = {}
    for sid in ids:
        try:
            experiments = client.study_experiments(sid)       # from the cache the parallel reads filled
        except Exception:      # noqa: BLE001 - one unreadable study is skipped, the rest still count
            continue
        for exp in experiments:
            for name, taxon in _strain_entries(exp):
                index.setdefault(genus_species(name), {}).setdefault(taxon, name)
    return index


def _species_index_one_by_one(client, max_studies: int) -> dict:
    """The crawl for a client that only lists a study's experiments (as test doubles do)."""
    index, misses = {}, 0
    for n in range(1, max_studies + 1):
        if misses >= MISS_RUN:
            break
        try:
            experiments = client.study_experiments(STUDY_ID.format(n))
        except Exception:      # noqa: BLE001 - an absent id is expected; any other failure skips one study
            misses += 1
            continue
        misses = 0
        for exp in experiments:
            for name, taxon in _strain_entries(exp):
                index.setdefault(genus_species(name), {}).setdefault(taxon, name)
    return index


# a list marker or numbering someone pasted along with a name: "- ", "* ", "1. ", "2) "
_BULLET = re.compile(r"^\s*(?:[-*\u2022]+|\d+[.)])\s+")
# an NCBI taxon id written the ways NCBI and papers write it: 476272, txid476272, NCBI:txid476272, taxid:476272
_TAXON_ID = re.compile(r"(?i)^(?:ncbi\s*[:_-]?\s*)?(?:txid|taxid|taxon(?:\s*id)?)?\s*[:=]?\s*(\d+)$")
# what a species or strain name can hold: it starts with a letter (or "[" as in "[Clostridium] scindens")
_NAME = re.compile(r"^[\[A-Za-z][A-Za-z0-9 .,'\-\[\]()/:+]*$")


def split_entries(lines) -> list:
    """The entries in what someone typed or pasted: one per line, and also split at commas and semicolons,
    which no species or strain name contains; list markers are dropped."""
    out = []
    for line in lines:
        for part in re.split(r"[,;]", line or ""):
            part = _BULLET.sub("", part).strip()
            if part:
                out.append(part)
    return out


def _display(key: str) -> str:
    return key[:1].upper() + key[1:]


def _suggestions(text: str, index: dict) -> list:
    """Names mGrowthDB holds that the person may have meant: the species of a genus given alone, an
    abbreviated genus ("B. hydrogenotrophica"), or a close spelling."""
    key = genus_species(text)
    words = key.split()
    if len(words) == 1:
        return [_display(k) for k in sorted(index) if k.split()[0] == words[0]][:8]
    if len(words) >= 2 and (words[0].endswith(".") or len(words[0]) == 1):
        initial, epithet = words[0].rstrip(".")[:1], words[1]
        return [_display(k) for k in sorted(index)
                if len(k.split()) > 1 and k.split()[0].startswith(initial) and k.split()[1] == epithet][:8]
    return [_display(k) for k in difflib.get_close_matches(key, list(index), n=3, cutoff=0.8)]


def resolve_species(entries, index: dict) -> dict:
    """Resolve typed species names and taxon ids against an index from `species_index`.

    entries: strings, each either a species name ("Faecalibacterium prausnitzii", strain designations and
    case ignored) or a numeric NCBI taxon id ("853"), which is taken as given.

    One species name often carries several taxon ids in mGrowthDB: a species-level id and strain-level ids
    below it. They are the same species, so a name resolves to all of them and the caller shows which
    strains were used rather than asking the person to choose.

    An entry may carry a list marker ("- ", "1. ") and an id may be written as NCBI writes it ("txid476272").
    Returns {"taxon_ids": [ids in the order first seen], "resolved": [(entry, {taxon id: name})],
    "unresolved": [entries that gave nothing], "reasons": {entry: why}, "suggestions": {entry: [names]}}:
    unreadable text, a taxon id no strain in mGrowthDB carries, a genus alone, or a name mGrowthDB does
    not hold, with the names it does hold that the person may have meant.
    """
    out = {"taxon_ids": [], "resolved": [], "unresolved": [], "reasons": {}, "suggestions": {}}

    def fail(text, reason, suggestions=()):
        out["unresolved"].append(text)
        out["reasons"][text] = reason
        if suggestions:
            out["suggestions"][text] = list(suggestions)

    for entry in entries:
        text = _BULLET.sub("", (entry or "")).strip()
        if not text:
            continue
        taxon_id = _TAXON_ID.match(text)
        if taxon_id:
            taxon = int(taxon_id.group(1))
            name = next((names[taxon] for names in index.values() if taxon in names), None)
            if name is None:
                # an id no strain in mGrowthDB carries can give no result, so it is not taken as found
                fail(text, f"no strain in mGrowthDB has NCBI taxon id {taxon}")
                continue
            matches = {taxon: name}
        elif not _NAME.match(text):
            fail(text, "not readable as a species or strain name, nor as an NCBI taxon id")
            continue
        else:
            matches = index.get(genus_species(text))
            if not matches:
                hints = _suggestions(text, index)
                if len(genus_species(text).split()) == 1:
                    reason = "a genus alone: give the species" + ("" if hints else "; mGrowthDB holds no species of it")
                else:
                    reason = "no species or strain of this name in mGrowthDB"
                fail(text, reason, hints)
                continue
            matches = dict(matches)
        out["resolved"].append((text, matches))
        for taxon in matches:
            if taxon not in out["taxon_ids"]:
                out["taxon_ids"].append(taxon)
    return out
