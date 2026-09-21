"""Offline tests for the provisional baseline derivation (synthetic experiment dicts, no network)."""
import math

import pytest

from crossfeed.derive import (
    _gs,
    adjust_significance,
    classify,
    interactions_from_experiments,
    interactions_from_replicates,
    output_meta,
    select_edges,
)
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
    # Two-point curves over 10 h, so the area is 5 * (v0 + v1).
    curves = {("mono A", A): [(1, 1), (1, 1.4)],    # areas 10 and 12
              ("mono B", B): [(1, 1), (1, 1.4)],
              ("co", A): [(1, 3), (1, 3.8)],        # areas 20 and 24: each doubles, mean log2 difference 1
              ("co", B): [(1, 1), (1, 1.4)]}        # unchanged: mean 0, and the spread crosses zero
    return _SeriesClient(experiments, curves), {"id": "S", "name": "study"}, experiments


# log2 10 and log2 12 differ by 0.2630, so each set's variance is 0.2630^2 / 2 = 0.0346, the sd of the
# comparison is sqrt(0.0346 + 0.0346) = 0.2630, and the se is sqrt(0.0346 / 2 + 0.0346 / 2) = 0.1860.
SPREAD = math.log2(12 / 10)


def test_replicate_comparison_carries_uncertainty_onto_every_edge():
    client, study, exps = _replicate_study()
    records, skipped = interactions_from_replicates(client, study, exps)
    by_pair = {(r["source_name"], r["target_name"]): r for r in records}
    ba = by_pair[(B, A)]
    assert ba["effect"] == "facilitation"                         # 1.0 - 0.263 stays above zero
    assert ba["strength"] == pytest.approx(1.0, abs=1e-4)
    assert ba["sd"] == pytest.approx(SPREAD, abs=1e-4)            # records round to four decimals
    assert ba["se"] == pytest.approx(SPREAD / math.sqrt(2), abs=1e-4)
    assert (ba["n_with"], ba["n_without"]) == (2, 2)
    assert ba["outcome"] == "quantified" and ba["metric"] == "auc"
    assert ba["evidence"] == "biculture" and ba["quality"] == [] and ba["notes"] == []
    ab = by_pair[(A, B)]
    assert ab["effect"] == "absent" and ab["strength"] == pytest.approx(0.0)    # 0 +/- 0.263 crosses zero
    # Welch's t on 2 vs 2 log2 values is reported but does not decide; B -> A differs, A -> B does not
    assert ba["p_value"] < 0.05 and ab["p_value"] == pytest.approx(1.0)


def test_replicate_comparison_accepts_another_metric():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps, method="max")
    ba = next(r for r in records if r["source_name"] == B)
    # maxima: A alone 1 and 1.4, A with B 3 and 3.8
    expected = (math.log2(3) + math.log2(3.8)) / 2 - (math.log2(1) + math.log2(1.4)) / 2
    assert ba["metric"] == "max" and ba["strength"] == pytest.approx(expected, abs=1e-4)


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



# ---- the effect rule and edge quality (Karoline, on #40) -----------------------------------------

@pytest.mark.parametrize("mean, sd, outcome, quality, effect", [
    (1.0, 0.3, "quantified", [], "facilitation"),       # interval entirely above zero
    (-1.0, 0.3, "quantified", [], "inhibition"),        # entirely below
    (0.2, 0.3, "quantified", [], "absent"),             # crosses zero on clean data: no edge at all
    (0.2, 0.3, "quantified", ["single_replicate"], "facilitation"),   # low quality keeps the mean's sign
    (0.2, None, "quantified", ["single_replicate"], "facilitation"),  # no sd with one replicate
    (None, None, "obligate", [], "facilitation"),       # grows only with the source
    (None, None, "abolished", [], "inhibition"),        # grows only without it
])
def test_classify_follows_the_decided_rule(mean, sd, outcome, quality, effect):
    assert classify(mean, sd, outcome, quality) == effect


def test_absences_never_become_edges_and_low_quality_is_hidden_by_default():
    records = [{"effect": "facilitation", "quality": []}, {"effect": "absent", "quality": [], "source": "a"},
               {"effect": "facilitation", "quality": ["single_replicate"]}]
    edges, hidden, absent = select_edges(records)
    assert edges == records[:1]
    assert hidden == {"low_quality": 1}
    assert [r["source"] for r in absent] == ["a"]
    edges, _, absent = select_edges(records, include_low_quality=True)
    assert len(edges) == 2 and len(absent) == 1           # an absence is never an edge, whatever the setting


def test_significance_is_benjamini_hochberg_over_every_tested_comparison():
    records = [{"p_value": 0.01}, {"p_value": 0.04}, {"p_value": None}, {"p_value": 0.03}, {"p_value": 0.005}]
    assert adjust_significance(records) == 4                # the untested record is not a test
    assert [r.get("significance") for r in records] == pytest.approx([0.02, 0.04, None, 0.04, 0.02])


def test_output_meta_records_the_statistics_and_the_absences():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps)
    edges, meta = output_meta(records)
    assert [e["source_name"] for e in edges] == [B]
    assert meta["statistics"]["tests"] == 2 and "Benjamini-Hochberg" in meta["statistics"]["correction"]
    _, conservative = output_meta(records, correction="by")
    assert "Benjamini-Yekutieli" in conservative["statistics"]["correction"]
    assert [a["source_name"] for a in meta["absent"]] == [A]
    assert meta["absent"][0]["n_with"] == 2 and meta["absent"][0]["significance"] is not None


def test_a_single_replicate_edge_is_kept_and_flagged_low_quality():
    client, study, exps = _replicate_study()
    exps[2]["bioreplicates"] = exps[2]["bioreplicates"][:1]            # one co-culture replicate
    records, _ = interactions_from_replicates(client, study, exps)
    ba = next(r for r in records if r["source_name"] == B)
    assert ba["quality"] == ["single_replicate"] and ba["sd"] is None
    assert ba["effect"] == "facilitation"                              # the sign of the mean, flagged


def test_pooled_strains_are_reported_and_flag_the_edge():
    client, study, exps = _replicate_study()
    other = _rep_experiment("mono A2", ["Faecalibacterium prausnitzii L2-6"])
    client.curves[("mono A2", "Faecalibacterium prausnitzii L2-6")] = [(1, 1), (1, 1.4)]
    records, skipped = interactions_from_replicates(client, study, exps + [other])
    ba = next(r for r in records if r["source_name"] == B)
    assert "strains_pooled" in ba["quality"]
    assert any("2 strains pooled" in reason for _, reason in skipped)


def test_an_excluded_outlier_is_a_note_not_a_quality_issue():
    client, study, exps = _replicate_study()
    exps[0]["bioreplicates"].append({"id": "mono A/2", "name": "mono A_2"})
    client.curves[("mono A", A)] = client.curves[("mono A", A)] + [(1, 1)]
    real = client.get_measurement_series

    def spiked(context_id):
        if context_id == f"mono A/2/{A}":
            return [(0.0, 1.0, None), (5.0, 1.0e6, None), (10.0, 1.0, None)]
        return real(context_id)

    client.get_measurement_series = spiked
    records, _ = interactions_from_replicates(client, study, exps)
    ba = next(r for r in records if r["source_name"] == B)
    assert ba["quality"] == [] and ba["effect"] == "facilitation"
    assert ba["notes"] and "implausible spike" in ba["notes"][0] and "mono A_2" in ba["notes"][0]
