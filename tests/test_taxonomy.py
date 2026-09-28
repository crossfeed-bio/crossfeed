"""Species name to NCBI taxon id, against a fake mGrowthDB client (no live calls)."""
import pytest

from crossfeed.taxonomy import resolve_species, species_index

FP, BH, RI = 853, 53443, 536231


class _FakeClient:
    """Answers study_experiments for two studies; every other study id is absent, as the API behaves."""

    def __init__(self, studies):
        self.studies = studies
        self.asked = []

    def study_experiments(self, study_id):
        self.asked.append(study_id)
        if study_id not in self.studies:
            raise RuntimeError(f"mGrowthDB returned HTTP 404 for {study_id}")
        return self.studies[study_id]


def _exp(*strains):
    return {"communityStrains": [{"name": n, "NCBId": t} for n, t in strains]}


def _client():
    return _FakeClient({
        "SMGDB00000001": [_exp(("Faecalibacterium prausnitzii A2-165", FP),
                               ("Blautia hydrogenotrophica DSM 10507", BH))],
        "SMGDB00000003": [_exp(("Roseburia intestinalis L1-82", RI)), _exp(("Faecalibacterium prausnitzii", FP))],
    })


def test_index_collects_names_and_ids_across_studies():
    index = species_index(_client())
    assert index["faecalibacterium prausnitzii"] == {FP: "Faecalibacterium prausnitzii A2-165"}
    assert index["blautia hydrogenotrophica"] == {BH: "Blautia hydrogenotrophica DSM 10507"}
    assert index["roseburia intestinalis"] == {RI: "Roseburia intestinalis L1-82"}


def test_crawl_stops_after_consecutive_misses():
    client = _client()
    species_index(client)
    # the two studies, then MISS_RUN misses in a row after the last one, then it stops
    from crossfeed.taxonomy import MISS_RUN
    assert client.asked[-1] == f"SMGDB{3 + MISS_RUN:08d}"
    assert len(client.asked) == 3 + MISS_RUN


def test_a_gap_of_missing_studies_does_not_hide_later_ones():
    # twelve absent ids between two studies (2 to 13): the old limit of five stopped before the second
    from crossfeed.taxonomy import species_index as index_of
    later = _client()
    later.studies = {"SMGDB00000001": later.studies["SMGDB00000001"], "SMGDB00000014": later.studies["SMGDB00000003"]}
    assert len(index_of(later)) == len(species_index(_client()))


def test_name_and_taxon_id_both_resolve():
    index = species_index(_client())
    r = resolve_species(["Faecalibacterium prausnitzii", " 53443 ", ""], index)
    assert r["taxon_ids"] == [FP, BH]
    assert r["resolved"][0] == ("Faecalibacterium prausnitzii", {FP: "Faecalibacterium prausnitzii A2-165"})
    assert r["resolved"][1] == ("53443", {BH: "Blautia hydrogenotrophica DSM 10507"})
    assert r["unresolved"] == []


def test_strain_designation_and_case_are_ignored():
    index = species_index(_client())
    r = resolve_species(["faecalibacterium PRAUSNITZII L2-6"], index)
    assert r["taxon_ids"] == [FP]


def test_unknown_name_is_reported_not_guessed():
    r = resolve_species(["Escherichia coli"], species_index(_client()))
    assert r["unresolved"] == ["Escherichia coli"] and r["taxon_ids"] == []


def test_a_name_with_several_strain_ids_uses_them_all():
    strains = _exp(("Bacteroides fragilis NCTC 9343", 1), ("Bacteroides fragilis YCH46", 2))
    client = _FakeClient({"SMGDB00000001": [strains]})
    r = resolve_species(["Bacteroides fragilis"], species_index(client))
    # the species-level id and the strain-level ids are the same species: search with all of them
    assert r["taxon_ids"] == [1, 2]
    entry, matches = r["resolved"][0]
    assert entry == "Bacteroides fragilis"
    assert matches == {1: "Bacteroides fragilis NCTC 9343", 2: "Bacteroides fragilis YCH46"}


def test_repeated_entries_give_one_id():
    index = species_index(_client())
    r = resolve_species(["Faecalibacterium prausnitzii", "853"], index)
    assert r["taxon_ids"] == [FP]
    assert [e for e, _ in r["resolved"]] == ["Faecalibacterium prausnitzii", "853"]


@pytest.mark.parametrize("bad", [{"communityStrains": [{"name": "No id"}]}, {"communityStrains": []}, {}])
def test_strains_without_ids_are_ignored(bad):
    assert species_index(_FakeClient({"SMGDB00000001": [bad]})) == {}


def test_common_ways_of_typing_are_understood_and_the_rest_say_why():
    from crossfeed.taxonomy import split_entries
    index = {"blautia hydrogenotrophica": {476272: "Blautia hydrogenotrophica DSM 10507"},
             "blautia obeum": {40520: "Blautia obeum ATCC 29174"}}
    entries = split_entries(["Blautia hydrogenotrophica, Blautia obeum", "- 476272", "NCBI:txid40520"])
    assert entries == ["Blautia hydrogenotrophica", "Blautia obeum", "476272", "NCBI:txid40520"]
    r = resolve_species(entries + ["B. obeum", "Blautia hydrogentrophica", "99999999", "%%%", "Blauta"], index)
    assert [e for e, _ in r["resolved"]] == entries                          # commas, a dash, txid: all fine
    why, hints = r["reasons"], r["suggestions"]
    assert why["Blauta"] == "no genus or species of this name in mGrowthDB" and hints["Blauta"] == ["Blautia"]
    assert hints["B. obeum"] == ["Blautia obeum"]                              # an abbreviated genus
    assert hints["Blautia hydrogentrophica"] == ["Blautia hydrogenotrophica"]  # a close spelling
    assert why["99999999"] == "no strain in mGrowthDB has NCBI taxon id 99999999"   # not taken as found
    assert why["%%%"].startswith("not readable")


def test_the_current_name_is_the_most_recently_published_one():
    from crossfeed.taxonomy import species_index as build

    class Dated(_FakeClient):
        dates = {"SMGDB00000001": "2025-11-01", "SMGDB00000003": "2024-01-01"}

        def get_study(self, sid):
            if sid not in self.studies:
                from crossfeed.mgrowthdb import MGrowthDBError
                raise MGrowthDBError("mGrowthDB returned HTTP 404")        # as the real client does
            return {"id": sid, "publishedAt": self.dates[sid], "experiments": [{"id": sid}]}

        def get_experiment(self, eid):
            return self.studies[eid][0]

        def study_experiments(self, sid):
            return [self.get_experiment(e["id"]) for e in self.get_study(sid)["experiments"]]

    client = Dated({"SMGDB00000001": [_exp(("Faecalibacterium duncaniae A2-165", FP))],
                    "SMGDB00000003": [_exp(("Faecalibacterium prausnitzii A2-165", FP))]})
    index = build(client)
    assert index.current[FP] == "Faecalibacterium duncaniae A2-165"          # study 1 is the more recent
    assert "faecalibacterium prausnitzii" in index and "faecalibacterium duncaniae" in index   # both resolve


def test_a_genus_alone_stands_for_every_strain_of_it():
    # Karoline (2026-09-28): a genus entered resolves to all its strains in mGrowthDB, and the species it
    # expanded to are listed; "[Clostridium]" is a different first word, so it is not Clostridium
    index = {"blautia hydrogenotrophica": {476272: "Blautia hydrogenotrophica DSM 10507"},
             "blautia obeum": {40520: "Blautia obeum ATCC 29174", 7: "Blautia obeum A2-235"},
             "[clostridium] scindens": {29347: "[Clostridium] scindens ATCC 35704"},
             "clostridium butyricum": {1492: "Clostridium butyricum"}}
    r = resolve_species(["blautia", "Clostridium"], index)
    assert r["taxon_ids"] == [476272, 40520, 7, 1492] and r["unresolved"] == []
    assert r["genera"] == {"blautia": ["Blautia hydrogenotrophica", "Blautia obeum"],
                           "Clostridium": ["Clostridium butyricum"]}
