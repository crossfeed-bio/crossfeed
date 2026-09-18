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
    # the two studies plus five misses in a row after the last one, then it stops
    assert client.asked[-1] == "SMGDB00000008"
    assert len(client.asked) == 8


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
