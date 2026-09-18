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


def species_index(client, max_studies: int = MAX_STUDIES) -> dict:
    """Map a genus and species key to {taxon id: a name seen for it}, crawled from mGrowthDB.

    Study ids are consecutive, so the crawl walks them and stops after MISS_RUN absent ids in a row. A
    study or experiment that cannot be read is skipped: a partial index is more useful than no index.
    """
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


def resolve_species(entries, index: dict) -> dict:
    """Resolve typed species names and taxon ids against an index from `species_index`.

    entries: strings, each either a species name ("Faecalibacterium prausnitzii", strain designations and
    case ignored) or a numeric NCBI taxon id ("853"), which is taken as given.

    One species name often carries several taxon ids in mGrowthDB: a species-level id and strain-level ids
    below it. They are the same species, so a name resolves to all of them and the caller shows which
    strains were used rather than asking the person to choose.

    Returns {"taxon_ids": [ids in the order first seen], "resolved": [(entry, {taxon id: name})],
    "unresolved": [entries mGrowthDB does not hold]}.
    """
    out = {"taxon_ids": [], "resolved": [], "unresolved": []}
    for entry in entries:
        text = (entry or "").strip()
        if not text:
            continue
        if text.isdigit():
            taxon = int(text)
            matches = {taxon: next((names[taxon] for names in index.values() if taxon in names), "")}
        else:
            matches = index.get(genus_species(text))
            if not matches:
                out["unresolved"].append(text)
                continue
            matches = dict(matches)
        out["resolved"].append((text, matches))
        for taxon in matches:
            if taxon not in out["taxon_ids"]:
                out["taxon_ids"].append(taxon)
    return out
