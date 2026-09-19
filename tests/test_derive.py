"""Offline tests for the provisional baseline derivation (synthetic experiment dicts, no network)."""
import math

import pytest

from crossfeed.derive import _gs, interactions_from_experiments, interactions_from_replicates
from crossfeed.mgrowthdb import records_to_network

STUDY = {"id": "SMGDB_TEST", "name": "synthetic test study", "url": "http://example/study"}
A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"


def _mono(name, gr):
    return {"id": "E_" + name, "name": name, "communityStrains": [{"name": name}],
            "bioreplicates": [{"name": "r1", "measurementContexts": [
                {"techniqueType": "fc", "subject": {"type": "bioreplicate", "name": name}, "growthRate": gr}]}]}


def _co(a, b, cond, gr_a, gr_b):
    return {"id": "E_" + cond, "name": cond, "communityStrains": [{"name": a}, {"name": b}],
            "bioreplicates": [{"name": "Average", "measurementContexts": [
                {"techniqueType": "qpcr", "subject": {"type": "strain", "name": a}, "growthRate": gr_a},
                {"techniqueType": "qpcr", "subject": {"type": "strain", "name": b}, "growthRate": gr_b}]}]}


def test_pairwise_derivation():
    # A alone 0.30; with B, A grows 0.66 (facilitated); B ~ unchanged (0.31)
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    assert skipped == []
    net = records_to_network(recs, meta={"slice": "test"})
    assert net.validate() == []
    # B -> A is facilitation (0.66 vs 0.30 -> log2 > 1)
    ba = next(e for e in net.edges if e.source == _gs(B) and e.target == _gs(A))
    assert ba.effect == "facilitation" and ba.strength > 1
    # A -> B is neutral (0.31 vs 0.30 -> tiny log2, within the deadband)
    ab = next(e for e in net.edges if e.source == _gs(A) and e.target == _gs(B))
    assert ab.effect == "neutral"
    # every edge is qualitative (no significance test yet) and carries the provisional method note
    assert all(e.significance is None and "PROVISIONAL" in e.method for e in net.edges)


def test_missing_mono_is_skipped():
    # co-culture present but no mono for either strain -> both directions skipped, no fabrication
    exps = [_co(A, B, "FP_BH", 0.66, 0.31)]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    assert recs == []
    assert all("no mono growth" in reason for _, reason in skipped)


def test_three_member_skipped():
    exps = [{"id": "E", "name": "ABC",
             "communityStrains": [{"name": A}, {"name": B}, {"name": "Roseburia intestinalis L1-82"}],
             "bioreplicates": []}]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    assert recs == []
    assert any(">2 members" in reason for _, reason in skipped)


def test_baseline_edges_are_biculture_evidence():
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    recs, _ = interactions_from_experiments(STUDY, exps)
    net = records_to_network(recs)
    assert net.edges and all(e.evidence == "biculture" for e in net.edges)
    assert all(e.community == tuple(sorted([_gs(A), _gs(B)])) for e in net.edges)


def test_two_strains_of_one_species_report_the_dropped_monoculture():
    # Nodes are keyed at genus and species, so both A2-165 and the second strain key to
    # "faecalibacterium prausnitzii". Only the last monoculture read is used, and the baseline
    # says so instead of dropping one silently.
    A2 = "Faecalibacterium prausnitzii L2-6"
    exps = [_mono(A, 0.30), _mono(A2, 0.90), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    dropped = [(label, reason) for label, reason in skipped if label.startswith("monoculture ")]
    assert len(dropped) == 1
    label, reason = dropped[0]
    assert label == f"monoculture {A}"                 # the one whose value was replaced
    assert A2 in reason and _gs(A) in reason           # names the replacement and the shared key
    # behavior is unchanged: the last monoculture read (0.90) is the one compared against
    ba = next(r for r in recs if r["source"] == _gs(B) and r["target"] == _gs(A))
    assert ba["effect"] == "inhibition"                # log2(0.66 / 0.90) < -0.25


def test_one_strain_per_species_reports_nothing():
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    _, skipped = interactions_from_experiments(STUDY, exps)
    assert [s for s in skipped if s[0].startswith("monoculture ")] == []


# ---- the replicate comparison (#36) --------------------------------------------------------------

def _rep_experiment(name, species, taxa=None):
    taxa = taxa or {}
    return {"id": "E_" + name, "name": name,
            "communityStrains": [{"name": sp, "NCBId": taxa.get(sp)} for sp in species],
            "bioreplicates": [{"id": f"{name}/{i}", "name": f"{name}_{i}"} for i in (0, 1)]}


class _SeriesClient:
    """A client whose experiments carry measured series: curves[(experiment, species)] = [(v0, v1), ...]."""

    def __init__(self, experiments, curves):
        self.experiments = experiments
        self.curves = curves

    def get_study(self, study_id):
        return {"id": study_id, "name": "study", "experiments": [{"id": e["id"]} for e in self.experiments]}

    def get_experiment(self, experiment_id):
        return next(e for e in self.experiments if e["id"] == experiment_id)

    def get_bioreplicate(self, bioreplicate_id):
        name, _, index = str(bioreplicate_id).partition("/")
        experiment = next(e for e in self.experiments if e["name"] == name)
        return {"id": bioreplicate_id, "name": f"{name}_{index}", "isAverage": False,
                "measurementTimeUnits": "h",
                "measurementContexts": [
                    {"id": f"{name}/{index}/{s['name']}", "techniqueType": "qpcr", "techniqueUnits": "Cells/mL",
                     "subject": {"type": "strain", "name": s["name"]}}
                    for s in experiment["communityStrains"]]}

    def get_measurement_series(self, context_id):
        name, index, species = str(context_id).split("/")
        v0, v1 = self.curves[(name, species)][int(index)]
        return [(0.0, float(v0), None), (10.0, float(v1), None)]


def _replicate_study():
    experiments = [_rep_experiment("mono A", [A]), _rep_experiment("mono B", [B]), _rep_experiment("co", [A, B])]
    curves = {("mono A", A): [(1, 1), (1, 3)],     # areas 10 and 20
              ("mono B", B): [(1, 1), (1, 3)],
              ("co", A): [(1, 3), (3, 5)],          # areas 20 and 40 -> mean log2 difference +1
              ("co", B): [(1, 1), (1, 3)]}          # unchanged -> 0
    return _SeriesClient(experiments, curves), {"id": "S", "name": "study"}, experiments


def test_replicate_comparison_carries_uncertainty_onto_every_edge():
    client, study, exps = _replicate_study()
    records, skipped = interactions_from_replicates(client, study, exps)
    by_pair = {(r["source_name"], r["target_name"]): r for r in records}
    ba = by_pair[(B, A)]
    assert ba["effect"] == "facilitation"
    assert ba["strength"] == pytest.approx(1.0)
    assert ba["se"] == pytest.approx(math.sqrt(0.5), abs=1e-4)   # records round to four decimals
    assert (ba["n_with"], ba["n_without"]) == (2, 2)
    assert ba["outcome"] == "quantified" and ba["metric"] == "auc"
    assert ba["evidence"] == "biculture"
    ab = by_pair[(A, B)]
    assert ab["effect"] == "neutral" and ab["strength"] == pytest.approx(0.0)


def test_replicate_comparison_accepts_another_metric():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps, method="max")
    ba = next(r for r in records if r["source_name"] == B)
    assert ba["metric"] == "max" and ba["strength"] == pytest.approx(math.log2(5) / 2, abs=1e-4)


def test_growth_only_with_the_partner_is_reported_as_obligate_facilitation():
    client, study, exps = _replicate_study()
    client.curves[("mono B", B)] = [(0, 0), (0, 0)]      # B does not grow alone
    records, _ = interactions_from_replicates(client, study, exps)
    ab = next(r for r in records if r["source_name"] == A and r["target_name"] == B)
    assert ab["outcome"] == "obligate" and ab["effect"] == "facilitation" and ab["strength"] is None


def test_a_missing_monoculture_is_reported_not_guessed():
    client, study, exps = _replicate_study()
    exps = [e for e in exps if e["name"] != "mono B"]
    records, skipped = interactions_from_replicates(client, study, exps)
    assert records == []
    assert any("no monoculture replicates" in reason for _, reason in skipped)


def test_a_larger_community_is_skipped_with_a_reason():
    client, study, exps = _replicate_study()
    trio = _rep_experiment("trio", [A, B, "Roseburia intestinalis L1-82"])
    records, skipped = interactions_from_replicates(client, study, exps + [trio])
    assert len(records) == 2
    assert any(">2 members" in reason for _, reason in skipped)
