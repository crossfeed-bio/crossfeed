"""Offline tests for the provisional baseline derivation (synthetic experiment dicts, no network)."""
import math

import pytest

from crossfeed.derive import (
    _gs,
    absence,
    adjust_significance,
    classify,
    effect_over_sd,
    interactions_from_experiments,
    interactions_from_replicates,
    output_meta,
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

def _rep_experiment(name, species, taxa=None, replicates=2, medium="broth"):
    taxa = taxa or {}
    return {"id": "E_" + name, "name": name, "cultivationMode": "batch", "compartments": [{"mediumName": medium}],
            "communityStrains": [{"name": sp, "NCBId": taxa.get(sp)} for sp in species],
            "bioreplicates": [{"id": f"{name}/{i}", "name": f"{name}_{i}"} for i in range(replicates)]}


class _SeriesClient:
    """A client whose experiments carry measured series: curves[(experiment, species)] = [(v0, v1), ...]."""

    def __init__(self, experiments, curves, measured=None):
        self.experiments = experiments
        self.curves = curves
        self.measured = measured or {}     # experiment name -> strains measured, when not its members

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
                    for s in self.measured.get(name, experiment["communityStrains"])]}

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
    assert ba["cautions"] == ["two_replicates"]                   # two replicates per side (#47)
    assert ba["experiments"] == ["E_co", "E_mono A"]              # the co-culture, then the target's monocultures
    assert ba["weight"] == pytest.approx(1.0, abs=1e-4)
    assert ba["effect_over_sd"] == pytest.approx(1.0 / SPREAD, abs=1e-3)       # 3.80: well above k = 1
    ab = by_pair[(A, B)]
    assert ab["strength"] == pytest.approx(0.0) and ab["weight"] == pytest.approx(0.0)
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
    # no experiment holds this trio minus one member, so it is not a drop-out design
    trio = _rep_experiment("trio", [A, "Roseburia intestinalis L1-82", "Bacteroides thetaiotaomicron VPI-5482"])
    records, skipped = interactions_from_replicates(client, study, exps + [trio])
    assert len(records) == 2
    assert any("no drop-out experiment" in reason for _, reason in skipped)



# ---- the effect rule and edge quality (Karoline, on #40) -----------------------------------------

@pytest.mark.parametrize("mean, outcome, effect", [
    (1.0, "quantified", "facilitation"),
    (-1.0, "quantified", "inhibition"),
    (0.0, "quantified", "neutral"),                    # no direction at all; always absent
    (None, "obligate", "facilitation"),                # the extreme of facilitation
    (None, "abolished", "inhibition"),                 # the extreme of inhibition
])
def test_classify_gives_the_direction(mean, outcome, effect):
    assert classify(mean, outcome) == effect


@pytest.mark.parametrize("mean, sd, outcome, k, status", [
    (1.0, 0.3, "quantified", 1.0, "present"),          # |1.0| >= 1 * 0.3
    (0.2, 0.3, "quantified", 1.0, "absent"),           # |0.2| < 1 * 0.3: the mean +/- sd rule
    (0.2, 0.3, "quantified", 0.5, "present"),          # |0.2| >= 0.5 * 0.3
    (0.2, 0.3, "quantified", 0.0, "present"),          # k = 0 marks nothing absent
    (1.0, 0.3, "quantified", 4.0, "absent"),           # |1.0| < 4 * 0.3
    (0.0, 0.3, "quantified", 0.0, "absent"),           # a mean of exactly zero is always absent
    (0.2, None, "quantified", 1.0, None),              # no spread (one replicate): undetermined
    (0.0, None, "quantified", 1.0, None),              # even with a zero mean (review of #58)
    (0.2, 0.0, "quantified", 1.0, "present"),          # replicates agree exactly: present
    (None, None, "obligate", 1.0, "present"),
    (None, None, "abolished", 1.0, "present"),
])
def test_absence_is_a_threshold_on_the_effect_relative_to_its_spread(mean, sd, outcome, k, status):
    assert absence(mean, sd, outcome, k) == status


def test_effect_over_sd_is_the_quantity_the_threshold_cuts():
    assert effect_over_sd(-0.6, 0.3) == pytest.approx(2.0)
    assert effect_over_sd(0.6, None) is None and effect_over_sd(0.6, 0.0) is None
    assert effect_over_sd(None, 0.3) is None


def test_absent_edges_stay_in_the_output_and_low_quality_is_left_out_by_default():
    records = [{"strength": 1.0, "sd": 0.3, "outcome": "quantified", "quality": []},
               {"strength": 0.1, "sd": 0.3, "outcome": "quantified", "quality": []},
               {"strength": 1.0, "sd": None, "outcome": "quantified", "quality": ["single_replicate"]}]
    edges, meta = output_meta(records)
    assert [e["status"] for e in edges] == ["present", "absent"]        # the absent edge is still an edge
    assert meta["hidden"] == {"low_quality": 1}
    assert meta["absence"] == {"rule": "absent when |log2 mean| < k * sd", "k": 1.0, "absent": 1}
    edges, meta = output_meta(records, include_low_quality=True, absence_threshold=0.0)
    assert [e["status"] for e in edges] == ["present", "present", None]
    assert meta["absence"]["absent"] == 0


def test_a_low_quality_edge_is_never_marked_absent():
    # issue #50: even with a zero mean or a spread that would place it below k, a low-quality edge's status
    # is undetermined, never absent
    records = [{"strength": 0.0, "sd": 0.3, "outcome": "quantified", "quality": ["strains_pooled"]},
               {"strength": 0.1, "sd": 0.3, "outcome": "quantified", "quality": ["strains_pooled"]}]
    edges, meta = output_meta(records, include_low_quality=True)
    assert [e["status"] for e in edges] == [None, None] and meta["absence"]["absent"] == 0


def test_significance_is_benjamini_hochberg_over_every_tested_comparison():
    records = [{"p_value": 0.01}, {"p_value": 0.04}, {"p_value": None}, {"p_value": 0.03}, {"p_value": 0.005}]
    assert adjust_significance(records) == 4                # the untested record is not a test
    assert [r.get("significance") for r in records] == pytest.approx([0.02, 0.04, None, 0.04, 0.02])


def test_output_meta_records_the_statistics_and_the_absence_rule():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps)
    edges, meta = output_meta(records)
    status = {e["source_name"]: e["status"] for e in edges}
    assert status == {B: "present", A: "absent"}                        # both are edges
    assert meta["statistics"]["tests"] == 2 and "Benjamini-Hochberg" in meta["statistics"]["correction"]
    assert meta["absence"]["absent"] == 1
    _, conservative = output_meta(records, correction="by")
    assert "Benjamini-Yekutieli" in conservative["statistics"]["correction"]


def test_a_single_replicate_edge_is_kept_and_flagged_low_quality():
    client, study, exps = _replicate_study()
    exps[2]["bioreplicates"] = exps[2]["bioreplicates"][:1]            # one co-culture replicate
    records, _ = interactions_from_replicates(client, study, exps)
    ba = next(r for r in records if r["source_name"] == B)
    assert ba["quality"] == ["single_replicate"] and ba["sd"] is None and ba["effect_over_sd"] is None
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
    assert absence(ba["strength"], ba["sd"], ba["outcome"]) == "present"


# ---- drop-out designs (#47) ----------------------------------------------------------------------

C = "Bacteroides thetaiotaomicron VPI-5482"


def _dropout_study(full_names=("full",), drops=("without C", "without B")):
    """The drop-out example of tests/test_interaction.py as mGrowthDB experiments. Areas are 5 * (v0 + v1):

    full community: A 20, 40; B 10, 10; C 10, 20. Without C: A 10, 20; B 10, 10. Without B: A 20, 40;
    C 40, 80.
    """
    members = {"without C": [A, B], "without B": [A, C]}
    experiments = [_rep_experiment(n, [A, B, C]) for n in full_names]
    experiments += [_rep_experiment(n, members[n]) for n in drops]
    curves = {}
    for n in full_names:
        curves.update({(n, A): [(1, 3), (3, 5)], (n, B): [(1, 1), (1, 1)], (n, C): [(1, 1), (1, 3)]})
    curves.update({("without C", A): [(1, 1), (1, 3)], ("without C", B): [(1, 1), (1, 1)],
                   ("without B", A): [(1, 3), (3, 5)], ("without B", C): [(3, 5), (7, 9)]})
    return _SeriesClient(experiments, curves), {"id": "S", "name": "study"}, experiments


def _by_arc(records):
    return {(r["source_name"], r["target_name"]): r for r in records}


def test_a_dropout_design_gives_the_hand_computed_arcs():
    client, study, exps = _dropout_study()
    records, skipped = interactions_from_replicates(client, study, exps)
    arcs = _by_arc(records)
    assert set(arcs) == {(C, A), (C, B), (B, A), (B, C)}
    # C -> A: log2 20, 40 against log2 10, 20: mean 1, sd sqrt(0.5 + 0.5) = 1
    assert arcs[(C, A)]["strength"] == pytest.approx(1.0) and arcs[(C, A)]["sd"] == pytest.approx(1.0)
    assert arcs[(C, B)]["strength"] == pytest.approx(0.0) and arcs[(C, B)]["sd"] == pytest.approx(0.0)
    assert arcs[(B, A)]["strength"] == pytest.approx(0.0) and arcs[(B, A)]["sd"] == pytest.approx(1.0)
    assert arcs[(B, C)]["strength"] == pytest.approx(-2.0)      # log2 10, 20 against log2 40, 80
    for (source, _), arc in arcs.items():
        assert arc["evidence"] == "dropout" and arc["community"] == sorted([_gs(A), _gs(B), _gs(C)])
        assert arc["quality"] == [] and arc["cautions"] == ["two_replicates"]
        drop = "without C" if source == C else "without B"
        assert arc["condition"] == drop and arc["experiments"] == ["E_full", "E_" + drop]
    assert not any("members" in reason for _, reason in skipped)


def test_dropout_arcs_share_the_absence_rule_and_the_network_contract():
    client, study, exps = _dropout_study()
    records, _ = interactions_from_replicates(client, study, exps)
    edges, _ = output_meta(records)
    status = {(e["source_name"], e["target_name"]): e["status"] for e in edges}
    # |mean| against k = 1 times sd: C -> A 1 vs 1 is not below, so present; B -> A 0 vs 1 absent;
    # C -> B has mean 0 (absent); B -> C 2 against sd sqrt(0.5 + 0.5) = 1 present
    assert status == {(C, A): "present", (B, A): "absent", (C, B): "absent", (B, C): "present"}
    net = records_to_network(edges)
    assert net.validate() == []
    assert all(e.evidence == "dropout" and e.experiments for e in net.edges)


def test_full_community_experiments_under_identical_conditions_are_pooled():
    client, study, exps = _dropout_study(full_names=("full 1", "full 2"))
    records, _ = interactions_from_replicates(client, study, exps)
    ca = _by_arc(records)[(C, A)]
    # the full community now has 4 replicates (A 20, 40, 20, 40), the drop-out 2; the mean stays 1
    assert (ca["n_with"], ca["n_without"]) == (4, 2)
    assert ca["strength"] == pytest.approx(1.0)
    assert ca["experiments"] == ["E_full 1", "E_full 2", "E_without C"]


def test_experiments_under_different_conditions_are_not_pooled():
    client, study, exps = _dropout_study(full_names=("full", "full in another medium"))
    exps[1]["compartments"] = [{"mediumName": "another medium"}]
    records, skipped = interactions_from_replicates(client, study, exps)
    assert all(r["n_with"] == 2 and "E_full in another medium" not in r["experiments"] for r in records)
    assert any(label == "full in another medium" and "no drop-out experiment" in reason
               for label, reason in skipped)
    # the same holds for monocultures: a co-culture is compared only with monocultures in its conditions
    client, study, exps = _replicate_study()
    for e in exps:
        if e["name"] == "mono B":
            e["compartments"] = [{"mediumName": "another medium"}]
    records, skipped = interactions_from_replicates(client, study, exps)
    assert records == []
    assert any("no monoculture replicates for " + B + " under this experiment's conditions" in reason
               for _, reason in skipped)


def test_an_incomplete_design_gives_arcs_for_the_dropouts_it_has():
    client, study, exps = _dropout_study(drops=("without C",))
    records, _ = interactions_from_replicates(client, study, exps)
    assert set(_by_arc(records)) == {(C, A), (C, B)}


def test_dropout_designs_can_be_switched_off():
    client, study, exps = _dropout_study()
    mono = _replicate_study()
    client.experiments += mono[2]
    client.curves.update(mono[0].curves)
    with_dropout, _ = interactions_from_replicates(client, study, exps + mono[2])
    without, skipped = interactions_from_replicates(client, study, exps + mono[2], dropout=False)
    assert {r["evidence"] for r in with_dropout} == {"biculture", "dropout"}
    assert [r for r in with_dropout if r["evidence"] == "biculture"] == without
    assert any("drop-out designs switched off" in reason for _, reason in skipped)


def test_the_removed_member_is_ignored_when_absent_and_flags_the_arcs_when_detected():
    # mGrowthDB still measures the removed member in a drop-out experiment, as in SMGDB00000008
    client, study, exps = _dropout_study()
    client.measured["without C"] = [{"name": A}, {"name": B}, {"name": C}]
    client.curves[("without C", C)] = [(0, 0), (0, 0)]
    records, _ = interactions_from_replicates(client, study, exps)
    assert _by_arc(records)[(C, A)]["quality"] == []            # read zero: a clean drop-out
    client.curves[("without C", C)] = [(0, 0), (0, 2)]          # detected in replicate 1
    records, _ = interactions_from_replicates(client, study, exps)
    arcs = _by_arc(records)
    for target in (A, B):
        assert arcs[(C, target)]["quality"] == ["removed_member_detected"]
        assert any("without C_1" in note and C in note for note in arcs[(C, target)]["notes"])
    assert arcs[(B, A)]["quality"] == []                        # the other drop-out is unaffected
    edges, meta = output_meta(records)
    assert meta["hidden"]["low_quality"] == 2 and len(edges) == 2


def test_three_replicates_carry_no_caution_and_a_caution_does_not_hide_an_edge():
    client, study, exps = _replicate_study()
    for e in exps:
        e["bioreplicates"] = [{"id": f"{e['name']}/{i}", "name": f"{e['name']}_{i}"} for i in range(3)]
        for species in (A, B):
            if (e["name"], species) in client.curves:
                client.curves[(e["name"], species)].append(client.curves[(e["name"], species)][1])
    records, _ = interactions_from_replicates(client, study, exps)
    assert all(r["cautions"] == [] for r in records)
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps)
    edges, meta = output_meta(records)
    assert len(edges) == 2 and meta["hidden"]["low_quality"] == 0
    assert {e["status"] for e in edges} == {"present", "absent"}   # cautioned edges keep their status


def test_a_replicate_with_a_late_starting_curve_is_left_out_and_reported():
    # SMGDB00000008 has two such curves: a member's first measurement (0 h) is missing
    client, study, exps = _dropout_study()

    def late_series(context_id, original=client.get_measurement_series):
        points = original(context_id)
        return points[1:] + [(20.0, points[-1][1], None)] if context_id == f"without C/1/{A}" else points
    client.get_measurement_series = late_series
    records, skipped = interactions_from_replicates(client, study, exps)
    arcs = _by_arc(records)
    assert (arcs[(C, A)]["n_with"], arcs[(C, A)]["n_without"]) == (2, 1)   # without C keeps replicate 0 only
    assert arcs[(C, A)]["quality"] == ["single_replicate"]
    assert (arcs[(B, A)]["n_with"], arcs[(B, A)]["n_without"]) == (2, 2)   # the other drop-out is untouched
    assert any(label == "community without " + C + " replicate without C_1" and "starting after" in reason
               for label, reason in skipped)


def test_experiments_whose_descriptions_differ_are_not_pooled():
    # SMGDB00000004: RI_BH +Ac and RI_BH -Ac have identical structured conditions; only the description
    # says one had initial acetate (Karoline, on #47). Duplicate runs differ by a trailing number only.
    client, study, exps = _dropout_study(full_names=("full 1", "full 2"))
    exps[0]["description"], exps[1]["description"] = "all strains, run 1", "all strains, run 2"
    records, _ = interactions_from_replicates(client, study, exps)
    assert _by_arc(records)[(C, A)]["n_with"] == 4                        # pooled
    exps[0]["description"], exps[1]["description"] = "all strains with acetate", "all strains without acetate"
    records, _ = interactions_from_replicates(client, study, exps)
    ca = [r for r in records if (r["source_name"], r["target_name"]) == (C, A)]
    assert len(ca) == 2 and all(r["n_with"] == 2 for r in ca)            # two arcs, one per full community
    assert {tuple(r["experiments"]) for r in ca} == {("E_full 1", "E_without C"), ("E_full 2", "E_without C")}


def test_an_obligate_edge_counts_its_replicates_without_growth_and_is_shown():
    client, study, exps = _replicate_study()
    client.curves[("mono B", B)] = [(0, 0), (0, 0)]      # B does not grow alone, in either replicate
    records, _ = interactions_from_replicates(client, study, exps)
    ab = next(r for r in records if r["source_name"] == A and r["target_name"] == B)
    assert ab["outcome"] == "obligate" and (ab["n_with"], ab["n_without"]) == (2, 2)
    assert ab["quality"] == [] and ab["cautions"] == ["two_replicates"]
    edges, meta = output_meta(records)
    assert meta["hidden"]["low_quality"] == 0
    assert next(e for e in edges if e["source_name"] == A)["status"] == "present"
