"""Offline tests for the provisional baseline derivation (synthetic experiment dicts, no network)."""
import math

import pytest

from grownet import interaction
from grownet.derive import (
    PROVISIONAL,
    SIGNIFICANCE_CAP,
    _gs,
    absence,
    adjust_significance,
    classify,
    effect_over_sd,
    interactions_from_experiments,
    interactions_from_replicates,
    output_meta,
    significance_of,
)
from grownet.mgrowthdb import records_to_network


@pytest.fixture(autouse=True)
def _no_growth_rule_off(monkeypatch):
    """These examples predate the no-growth rule (#37) and check the ratio math, the windows, the spike
    guard and the outcomes on hand-computed curves. The rule is switched off here so each test keeps
    checking what it says it checks; `TestNoGrowthRule` covers the rule itself."""
    monkeypatch.setattr(interaction, "NO_GROWTH_ALPHA", 0.0)
    monkeypatch.setattr(interaction, "NO_GROWTH_FACTOR", 0.0)

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


def _four_records():
    return [{"strength": 1.0, "sd": 0.3, "outcome": "quantified", "quality": []},
            {"strength": 0.1, "sd": 0.3, "outcome": "quantified", "quality": []},
            {"strength": 1.0, "sd": None, "outcome": "quantified", "quality": ["single_replicate"]},
            {"strength": 1.0, "sd": 0.3, "outcome": "quantified", "quality": ["strains_pooled"]}]


def test_an_absent_edge_is_left_out_of_the_file_and_counted():
    """Karoline, 2026-10-03: "The arc number reported in Cytoscape is not identical to the arc number we
    see because of hidden arcs", so the file holds what the page counts, and the rest is reported."""
    records = _four_records()
    edges, meta = output_meta(records)
    # a single-replicate edge is an interaction whose spread is unknown: shown, status undetermined
    # (Karoline, on #62); the absent one and the pooled-strain one are left out and counted
    assert [e["status"] for e in edges] == ["present", None]
    assert meta["hidden"] == {"low_quality": 1, "absent": 1}
    assert meta["absence"] == {"rule": "absent when |log2 mean| < k * sd", "k": 1.0, "absent": 1}
    assert meta["filters"]["include_absent"] is False


def test_asking_for_the_absent_arcs_puts_them_back():
    records = _four_records()
    edges, meta = output_meta(records, include_absent=True)
    assert [e["status"] for e in edges] == ["present", "absent", None]
    assert meta["hidden"]["absent"] == 0 and meta["absence"]["absent"] == 1
    assert meta["filters"]["include_absent"] is True
    # k = 0 marks nothing absent, so there is nothing to leave out either way
    edges, meta = output_meta(_four_records(), include_low_quality=True, absence_threshold=0.0)
    assert [e["status"] for e in edges] == ["present", "present", None, None]
    assert meta["absence"]["absent"] == 0 and meta["hidden"]["absent"] == 0


def test_a_low_quality_edge_is_never_marked_absent():
    # issue #50: even with a zero mean or a spread that would place it below k, a low-quality edge's status
    # is undetermined, never absent
    records = [{"strength": 0.0, "sd": 0.3, "outcome": "quantified", "quality": ["strains_pooled"]},
               {"strength": 0.1, "sd": 0.3, "outcome": "quantified", "quality": ["strains_pooled"]}]
    edges, meta = output_meta(records, include_low_quality=True)
    assert [e["status"] for e in edges] == [None, None] and meta["absence"]["absent"] == 0


def test_the_q_value_is_benjamini_hochberg_over_every_tested_comparison():
    records = [{"p_value": 0.01}, {"p_value": 0.04}, {"p_value": None}, {"p_value": 0.03}, {"p_value": 0.005}]
    assert adjust_significance(records) == 4                # the untested record is not a test
    assert [r.get("q_value") for r in records] == pytest.approx([0.02, 0.04, None, 0.04, 0.02])


def test_significance_is_minus_log10_of_the_q_value():
    # Karoline, 2026-10-03: significance runs the other way from q, so a style can map it continuously
    records = [{"p_value": 0.01}, {"p_value": 0.04}, {"p_value": None}]
    adjust_significance(records)
    assert records[0]["q_value"] == pytest.approx(0.02)
    assert records[0]["significance"] == pytest.approx(1.699, abs=1e-3)   # -log10(0.02)
    assert records[1]["significance"] == pytest.approx(1.3979, abs=1e-3)  # -log10(0.04)
    assert records[2].get("significance") is None and records[2].get("q_value") is None
    # a q-value of exactly 1 is no evidence at all, and reads as zero
    assert significance_of(1.0) == 0.0
    # Welch reports p = 0 when neither side varies and the means differ: -log10(0) is infinite, so it caps
    assert significance_of(0.0) == SIGNIFICANCE_CAP
    assert significance_of(1e-30) == SIGNIFICANCE_CAP
    assert significance_of(None) is None


def test_the_adjusted_p_filter_leaves_out_interactions_above_it_and_keeps_untested_arcs():
    # Karoline (2026-09-30): "an advanced option, by default off, that allows filtering arcs on adjusted
    # p-value"; failing interactions "Left out, counted"; arcs without a p-value "Keep them, labeled untested"
    def records():
        return [{"strength": 1.0, "sd": 0.3, "outcome": "quantified", "quality": [], "p_value": 0.001},
                {"strength": 1.0, "sd": 0.3, "outcome": "quantified", "quality": [], "p_value": 0.4},
                {"strength": 0.1, "sd": 0.3, "outcome": "quantified", "quality": [], "p_value": 0.9},
                {"strength": None, "sd": None, "outcome": "obligate", "quality": [], "p_value": None},
                {"strength": 1.0, "sd": None, "outcome": "quantified", "quality": ["single_replicate"],
                 "p_value": None}]
    # include_absent keeps the absent arc in sight: this test is about the q-value filter, not about which
    # arcs a file holds (that is test_an_absent_edge_is_left_out_of_the_file_and_counted)
    edges, meta = output_meta(records(), include_absent=True)             # off by default: nothing moves
    assert len(edges) == 5 and not any("untested" in e.get("cautions", []) for e in edges)
    assert "not_significant" not in meta["hidden"] and meta["statistics"]["filter"]["max_adjusted_p"] is None
    assert meta["provisional"] == PROVISIONAL
    edges, meta = output_meta(records(), max_adjusted_p=0.05, include_absent=True)
    # the non-significant interaction is left out; the absent arc, the obligate arc and the single
    # replicate stay, the last two marked untested
    assert [(e["outcome"], e["status"], e.get("p_value")) for e in edges] == [
        ("quantified", "present", 0.001), ("quantified", "absent", 0.9), ("obligate", "present", None),
        ("quantified", None, None)]
    assert [("untested" in e.get("cautions", [])) for e in edges] == [False, False, True, True]
    assert meta["hidden"]["not_significant"] == 1
    assert meta["statistics"]["filter"] == {"max_adjusted_p": 0.05, "left_out": 1, "untested": 2}
    assert "left out" in meta["statistics"]["role"] and "0.05" in meta["provisional"]
    # the caution is part of the format: a network carrying it is built and validates (it did not at first,
    # found by a live derivation of SMGDB00000008)
    base = {"source": "a", "target": "b", "source_name": "Alpha one", "target_name": "Beta two", "study_id": "S1"}
    net = records_to_network([{**base, **e} for e in edges], meta=meta)
    assert net.validate() == [] and ("untested",) in [e.cautions for e in net.edges]


def test_output_meta_records_the_statistics_and_the_absence_rule():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps)
    edges, meta = output_meta(records, include_absent=True)
    status = {e["source_name"]: e["status"] for e in edges}
    assert status == {B: "present", A: "absent"}                        # both are edges when asked for
    assert meta["statistics"]["tests"] == 2 and "Benjamini-Hochberg" in meta["statistics"]["correction"]
    assert meta["absence"]["absent"] == 1
    _, conservative = output_meta(records, correction="by", include_absent=True)
    assert "Benjamini-Yekutieli" in conservative["statistics"]["correction"]
    # the no-growth rule's numbers travel with the network, since the obligate count depends on them (#37)
    assert (meta["no_growth"]["alpha"], meta["no_growth"]["obligate"], meta["no_growth"]["abolished"]) == (0.0, 0, 0)
    _, chosen = output_meta(records, no_growth_alpha=0.01, no_growth_factor=4.0, include_absent=True)
    assert (chosen["no_growth"]["alpha"], chosen["no_growth"]["factor"]) == (0.01, 4.0)


def test_a_single_replicate_edge_is_kept_and_flagged_low_quality():
    client, study, exps = _replicate_study()
    exps[2]["bioreplicates"] = exps[2]["bioreplicates"][:1]            # one co-culture replicate
    records, _ = interactions_from_replicates(client, study, exps)
    ba = next(r for r in records if r["source_name"] == B)
    assert ba["quality"] == ["single_replicate"] and ba["sd"] is None and ba["effect_over_sd"] is None
    assert ba["effect"] == "facilitation"                              # the sign of the mean, flagged
    edges, meta = output_meta(records)                                 # shown by default (Karoline, on #62)
    assert any(e["source_name"] == B for e in edges) and meta["hidden"]["low_quality"] == 0


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
    edges, _ = output_meta(records, include_absent=True)     # the test is about the rule, not the file
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
    edges, meta = output_meta(records, include_absent=True)   # about the flag, not which arcs ship
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
    edges, meta = output_meta(records, include_absent=True)
    assert len(edges) == 2 and meta["hidden"]["low_quality"] == 0
    assert {e["status"] for e in edges} == {"present", "absent"}   # cautioned edges keep their status


def test_a_replicate_with_a_late_starting_curve_is_left_out_of_that_species_arcs_only():
    # SMGDB00000008 has two such curves: a member's first measurement (0 h) is missing. Karoline
    # (2026-09-28, "Only for its own arcs"): the replicate is left out of the late member's arcs, and still
    # serves every other member, which once lost it too
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
    assert (arcs[(C, B)]["n_with"], arcs[(C, B)]["n_without"]) == (2, 2)   # B's curves there start on time
    assert "single_replicate" not in arcs[(C, B)]["quality"]
    assert any(label == "community without " + C + " replicate without C_1" and "starting after" in reason
               for label, reason in skipped)


def test_experiments_whose_descriptions_differ_are_not_pooled():
    # SMGDB00000004: RI_BH +Ac and RI_BH -Ac have identical structured conditions; only the description
    # says one had initial acetate (Karoline, on #47). Duplicate runs differ by a trailing number only.
    client, study, exps = _dropout_study(full_names=("full 1", "full 2"))
    exps[0]["description"], exps[1]["description"] = "all strains, run 1", "all strains, run 2"
    records, _ = interactions_from_replicates(client, study, exps)
    assert _by_arc(records)[(C, A)]["n_with"] == 4                        # pooled
    # Karoline, 2026-10-07, the strict rule everywhere: a supplement stated in the description makes
    # another medium, so a full community that states one is not compared with a drop-out that does not.
    # Both runs state it here, in media the drop-outs are not in, so neither arc is derived and the
    # refusal names the medium that was there. "with initial acetate" rather than "with acetate": the
    # reader of descriptions catches the first and not the second, which is its own open question.
    exps[0]["description"] = "all strains with initial acetate"
    exps[1]["description"] = "all strains without initial acetate"
    records, _ = interactions_from_replicates(client, study, exps)
    assert [r for r in records if (r["source_name"], r["target_name"]) == (C, A)] == []


def test_an_obligate_edge_counts_its_replicates_without_growth_and_is_shown():
    client, study, exps = _replicate_study()
    client.curves[("mono B", B)] = [(0, 0), (0, 0)]      # B does not grow alone, in either replicate
    records, _ = interactions_from_replicates(client, study, exps)
    ab = next(r for r in records if r["source_name"] == A and r["target_name"] == B)
    assert ab["outcome"] == "obligate" and (ab["n_with"], ab["n_without"]) == (2, 2)
    # B's monoculture is zero from its first point, so the arc also says that no growth cannot be told from
    # no inoculum (Karoline, 2026-09-28)
    assert ab["quality"] == [] and ab["cautions"] == ["two_replicates", "zero_at_start"]
    edges, meta = output_meta(records)
    assert meta["hidden"]["low_quality"] == 0
    assert next(e for e in edges if e["source_name"] == A)["status"] == "present"


# ---- strain identity by taxon id (#23) -----------------------------------------------------------

from grownet.derive import strain_identities  # noqa: E402

A2 = "Faecalibacterium prausnitzii L2-6"


def _strain_study(names_and_taxa, mono_of=None):
    """Monocultures of each strain and one co-culture of the first two. `mono_of` names the strain whose
    monoculture the co-culture's first member uses, to test that another strain's monoculture is not used."""
    (a, ta), (b, tb) = names_and_taxa[:2]
    taxa = dict(names_and_taxa)
    monos = [_rep_experiment("mono " + n, [n], taxa) for n, _ in names_and_taxa if n != a or mono_of is None]
    if mono_of:
        monos.append(_rep_experiment("mono " + mono_of, [mono_of], taxa))
    co = _rep_experiment("co", [a, b], taxa)
    curves = {("co", a): [(1, 3), (1, 3.8)], ("co", b): [(1, 1), (1, 1.4)]}
    for e in monos:
        curves[(e["name"], e["communityStrains"][0]["name"])] = [(1, 1), (1, 1.4)]
    return _SeriesClient(monos + [co], curves), {"id": "S", "name": "study"}, monos + [co]


def test_nodes_are_strains_keyed_by_taxon_id_and_named_by_strain():
    client, study, exps = _strain_study([(A, 411483), (B, 853), (A2, 718252)])
    records, _ = interactions_from_replicates(client, study, exps)
    net = records_to_network(records)
    node = net.nodes["ncbi:411483"]
    assert node.name == A and node.taxon_id == "411483" and node.identity == "ncbi"
    assert node.species == "faecalibacterium prausnitzii"          # derived from the name (#25, item 8)
    assert {(e.source, e.target) for e in net.edges} == {("ncbi:853", "ncbi:411483"), ("ncbi:411483", "ncbi:853")}
    assert "ncbi:718252" not in net.nodes                              # the other strain has no co-culture


def test_a_monoculture_of_another_strain_of_the_species_is_never_used():
    # the co-culture holds A (A2-165); only L2-6 was grown alone. By genus and species they would match.
    client, study, exps = _strain_study([(A, 411483), (B, 853)], mono_of=A2)
    exps[-2]["communityStrains"][0]["NCBId"] = 718252                  # the L2-6 monoculture
    records, skipped = interactions_from_replicates(client, study, exps)
    assert records == []
    assert any(f"no monoculture replicates for {A}" in reason for _, reason in skipped)


def test_one_taxon_id_under_two_names_is_one_node():
    # 411483 is "prausnitzii A2-165" in one record and "duncaniae A2-165" in another (a reclassification)
    renamed = "Faecalibacterium duncaniae A2-165"
    exps = [_rep_experiment("mono", [renamed], {renamed: 411483}), _rep_experiment("co", [A, B], {A: 411483, B: 853})]
    ids = strain_identities(exps, [])
    assert ids[A]["id"] == ids[renamed]["id"] == "ncbi:411483"


def test_a_taxon_id_given_to_two_different_strains_falls_back_to_names_and_is_reported():
    # SMGDB00000008 gives 1506553 to L. clostridioforme 2_1_49FAA and L. symbiosum WAL-14673
    lc, ls = "Lachnoclostridium clostridioforme 2_1_49FAA", "Lachnoclostridium symbiosum WAL-14673"
    skipped = []
    ids = strain_identities([_rep_experiment("co", [lc, ls], {lc: 1506553, ls: 1506553})], skipped)
    assert ids[lc]["id"] == "lachnoclostridium clostridioforme" and ids[lc]["identity"] == "name"
    assert ids[ls]["id"] == "lachnoclostridium symbiosum" and ids[ls]["taxon_id"] == "1506553"
    assert any(label == "taxon id 1506553" and "different strains" in reason for label, reason in skipped)


def test_a_strain_without_a_taxon_id_is_identified_by_name_and_marked():
    client, study, exps = _replicate_study()                          # these records carry no taxon ids
    records, _ = interactions_from_replicates(client, study, exps)
    net = records_to_network(records)
    assert set(net.nodes) == {_gs(A), _gs(B)}
    assert all(n.identity == "name" and n.taxon_id == "" for n in net.nodes.values())


# ---- cultivation mode (#42) ----------------------------------------------------------------------

def _mode(exps, mode):
    for e in exps:
        e["cultivationMode"] = mode
    return exps


def test_a_batch_study_derives_and_every_edge_records_the_mode():
    client, study, exps = _replicate_study()
    records, skipped = interactions_from_replicates(client, study, exps)
    assert len(records) == 2 and all(r["cultivation_mode"] == "batch" for r in records)
    assert all(r["quality"] == [] for r in records)
    assert not any("excluded by default" in reason for _, reason in skipped)


def test_a_chemostat_study_derives_nothing_and_the_reason_names_the_mode():
    client, study, exps = _replicate_study()
    records, skipped = interactions_from_replicates(client, study, _mode(exps, "chemostat"))
    assert records == []
    excluded = [(label, reason) for label, reason in skipped if "excluded by default" in reason]
    assert len(excluded) == 3 and all("chemostat" in reason for _, reason in excluded)


def test_chemostats_derive_when_asked_and_their_edges_are_flagged():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, _mode(exps, "chemostat"), include_non_batch=True)
    assert len(records) == 2
    assert all(r["cultivation_mode"] == "chemostat" and r["quality"] == ["non_batch"] for r in records)
    edges, meta = output_meta(records)          # non_batch is hidden by default, like the other flags
    assert edges == [] and meta["hidden"]["low_quality"] == 2


def test_an_experiment_without_a_mode_is_excluded_rather_than_assumed_to_be_batch():
    client, study, exps = _replicate_study()
    for e in exps:
        del e["cultivationMode"]
    records, skipped = interactions_from_replicates(client, study, exps)
    assert records == []
    assert any("unspecified, excluded by default" in reason for _, reason in skipped)


def test_a_dropout_design_in_a_chemostat_is_excluded_too():
    client, study, exps = _dropout_study()
    records, skipped = interactions_from_replicates(client, study, _mode(exps, "serial dilution"))
    assert records == []
    assert any("serial dilution, excluded by default" in reason for _, reason in skipped)


# ---- conditions recorded only in descriptions (Karoline, 2026-09-27) -----------------------------

def _described(name, species, description):
    exp = _rep_experiment(name, species)
    exp["description"] = description
    return exp


def test_a_monoculture_in_an_altered_medium_is_not_offered_to_a_co_culture_in_the_plain_one():
    """SMGDB00000014's shape: A grown alone with and without a supplement, under identical recorded
    conditions.

    Karoline, 2026-10-07: "the strict medium matching (exclusion of cases with modifications e.g. mucin
    addition) should be applied everywhere where medium matching is done." A supplement stated in the
    description makes another medium, so these are not two sets of one condition to be told apart by
    their wording: they are two conditions. The co-culture is in the plain medium, so it is compared with
    the plain monoculture and the oleic one is not offered to it at all. Before the rule reached the
    monoculture index both were offered and neither was chosen, and the pair was refused.
    """
    exps = [_described("A plain", [A], "A on minimal medium"), _described("A oleic", [A], "A with 1% oleic acid"),
            _described("B alone", [B], "B on minimal medium"), _described("co", [A, B], "A and B")]
    curves = {("A plain", A): [(1, 1), (1, 1.4)], ("A oleic", A): [(1, 6), (1, 7)],
              ("B alone", B): [(1, 1), (1, 1.4)], ("co", A): [(1, 3), (1, 3.8)], ("co", B): [(1, 1), (1, 1.4)]}
    records, _ = interactions_from_replicates(_SeriesClient(exps, curves), {"id": "S"}, exps)
    arc = _by_arc(records)[(B, A)]
    assert "E_A plain" in arc["experiments"] and "E_A oleic" not in arc["experiments"]
    # and it is not cautioned, because nothing was ambiguous: the media decided it
    assert "conditions_unverified" not in arc["cautions"]


def test_the_monoculture_set_whose_description_names_the_co_culture_is_used():
    # SMGDB00000007's shape: each co-culture has its own controls, 'controls of the "co" experiment'. The
    # named set (areas 10, 12) is used, not the other (areas 30, 30), so B -> A is the hand-computed +1.0.
    exps = [_described("A1", [A], 'A controls of the "co" experiment'),
            _described("A2", [A], 'A controls of the "other" experiment'),
            _described("B1", [B], 'B controls of the "co" experiment'), _described("co", [A, B], "A and B")]
    curves = {("A1", A): [(1, 1), (1, 1.4)], ("A2", A): [(3, 3), (3, 3)], ("B1", B): [(1, 1), (1, 1.4)],
              ("co", A): [(1, 3), (1, 3.8)], ("co", B): [(1, 1), (1, 1.4)]}
    records, _ = interactions_from_replicates(_SeriesClient(exps, curves), {"id": "S"}, exps)
    arc = _by_arc(records)[(B, A)]
    assert arc["strength"] == pytest.approx(1.0) and "E_A1" in arc["experiments"] and "E_A2" not in arc["experiments"]
    assert "conditions_unverified" not in arc["cautions"]


def test_co_cultures_in_an_altered_medium_have_no_monoculture_to_compare_with():
    # SMGDB00000004's shape: RI_BH +Ac and -Ac under identical recorded conditions, one monoculture set
    # per strain, and the acetate stated only on the co-cultures.
    exps = [_described("mono A", [A], "A"), _described("mono B", [B], "B"),
            _described("co +Ac", [A, B], "A and B with initial acetate"),
            _described("co -Ac", [A, B], "A and B without initial acetate")]
    curves = {("mono A", A): [(1, 1), (1, 1.4)], ("mono B", B): [(1, 1), (1, 1.4)]}
    for n in ("co +Ac", "co -Ac"):
        curves.update({(n, A): [(1, 3), (1, 3.8)], (n, B): [(1, 1), (1, 1.4)]})
    records, skipped = interactions_from_replicates(_SeriesClient(exps, curves), {"id": "S"}, exps)
    # Karoline, 2026-10-07: the strict rule everywhere. "with initial acetate" and "without initial
    # acetate" are two media and the monocultures are in neither, so there is nothing to compare rather
    # than two comparisons to caution. The refusal names the medium that was there instead.
    assert records == []
    reason = next(r for _label, r in skipped if "same base medium" in r)
    assert "acetate" in reason and "another environment" in reason
    assert "Name that experiment in the second box" in reason


def test_a_pair_with_one_co_culture_is_not_cautioned():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, exps)
    assert not any("conditions_unverified" in r["cautions"] for r in records)


def test_dropout_arcs_are_cautioned_when_the_full_community_has_description_variants():
    # two full communities told apart only by their descriptions: which drop-out goes with which is not recorded
    client, study, exps = _dropout_study(full_names=("full +glc", "full -glc"))
    records, _ = interactions_from_replicates(client, study, exps)
    assert records and all("conditions_unverified" in r["cautions"] for r in records)
    plain, _ = interactions_from_replicates(*_dropout_study()[:1], {"id": "S"}, _dropout_study()[2])
    assert not any("conditions_unverified" in r["cautions"] for r in plain)


def test_the_monoculture_set_with_the_co_cultures_qualifier_is_used():
    # SMGDB00000013's shape: plain, "Ancestral" and "Evolved" lines of A, none naming a co-culture. The
    # co-culture "Evolved AB" takes "Evolved A" (areas 10, 12: B -> A is +1.0), the plain "AB" takes "A"
    exps = [_described("A", [A], "monoculture of A"), _described("Ancestral A", [A], "ancestral A, controls"),
            _described("Evolved A", [A], "A evolved for 10 weeks"), _described("B", [B], "monoculture of B"),
            _described("Evolved AB", [A, B], "evolved A with B"), _described("AB", [A, B], "A with B")]
    curves = {("A", A): [(3, 3), (3, 3)], ("Ancestral A", A): [(2, 2), (2, 2)], ("Evolved A", A): [(1, 1), (1, 1.4)],
              ("B", B): [(1, 1), (1, 1.4)]}
    for n in ("Evolved AB", "AB"):
        curves.update({(n, A): [(1, 3), (1, 3.8)], (n, B): [(1, 1), (1, 1.4)]})
    records, skipped = interactions_from_replicates(_SeriesClient(exps, curves), {"id": "S"}, exps)
    by_exp = {(r["source_name"], r["target_name"], r["condition"]): r for r in records}
    evolved = by_exp[(B, A, "Evolved AB")]
    assert evolved["strength"] == pytest.approx(1.0) and "E_Evolved A" in evolved["experiments"]
    assert "E_A" in by_exp[(B, A, "AB")]["experiments"] and "E_Evolved A" not in by_exp[(B, A, "AB")]["experiments"]
    assert not any("none is guessed" in r for _, r in skipped)
    # matched by name, so no caution, although the pair has description-only variants
    assert not any("conditions_unverified" in r["cautions"] for r in records)



def test_the_monoculture_set_worded_like_the_co_culture_is_used():
    # SMGDB00000014's shape (Karoline, 2026-09-28: "Match identical wording"): two series of A on 0.1%
    # linoleic acid, a dose response ("Growth of A on ...") and the controls of the co-culture ("A
    # monoculture grown on ..."). Neither names the co-culture nor carries a qualifier, but only the second
    # words the growth as the co-culture does once the organisms and the kind of culture are taken out.
    # The co-culture takes it: A's areas 10 and 12 there against 20 and 24 together, so B -> A is +1.0.
    exps = [_described("A_LA_0.1", [A], "Growth of A on minimal medium with 0.1% linoleic acid"),
            _described("A_LA_0.1_mono", [A], "A monoculture grown on a minimal medium with 0.1% linoleic acid"),
            _described("B_LA_0.1_mono", [B], "B monoculture grown on a minimal medium with 0.1% linoleic acid"),
            _described("A_B_LA_0.1_co", [A, B], "A+B co-culture grown on a minimal medium with 0.1% linoleic acid")]
    curves = {("A_LA_0.1", A): [(3, 3), (3, 3)], ("A_LA_0.1_mono", A): [(1, 1), (1, 1.4)],
              ("B_LA_0.1_mono", B): [(1, 1), (1, 1.4)],
              ("A_B_LA_0.1_co", A): [(1, 3), (1, 3.8)], ("A_B_LA_0.1_co", B): [(1, 1), (1, 1.4)]}
    records, skipped = interactions_from_replicates(_SeriesClient(exps, curves), {"id": "S14"}, exps)
    arc = next(r for r in records if (r["source_name"], r["target_name"]) == (B, A))
    assert arc["strength"] == pytest.approx(1.0) and "E_A_LA_0.1_mono" in arc["experiments"]
    assert "E_A_LA_0.1" not in arc["experiments"] and "conditions_unverified" not in arc["cautions"]
    assert not any("none is guessed" in r for _, r in skipped)


def test_a_study_of_monocultures_only_says_so():
    # SMGDB00000015's shape: nothing but monocultures, so nothing to compare, stated once up front
    exps = [_described("A", [A], "A alone"), _described("B", [B], "B alone")]
    curves = {("A", A): [(1, 1), (1, 1.4)], ("B", B): [(1, 1), (1, 1.4)]}
    records, skipped = interactions_from_replicates(_SeriesClient(exps, curves), {"id": "S15"}, exps)
    assert records == [] and skipped[0][1].startswith("only monocultures (2 experiments of one strain each)")


# ---- merging parallel arcs (register item 14, Karoline 2026-09-27) --------------------------------

from grownet.derive import merge_parallel  # noqa: E402


def _arc(strength, study="S1", effect=None, status="present", outcome="quantified", evidence="biculture",
         condition="c", source="ncbi:1", target="ncbi:2"):
    effect = effect or ("facilitation" if (strength or 1) > 0 else "inhibition")
    return {"source": source, "target": target, "source_name": "A", "target_name": "B", "effect": effect,
            "strength": strength, "weight": None if strength is None else abs(strength), "sd": 0.1, "se": 0.05,
            "status": status, "outcome": outcome, "evidence": evidence, "condition": condition,
            "experiments": [f"E_{study}_{condition}"], "quality": [], "cautions": [], "notes": [],
            "community": [], "method": "m", "study_id": study, "study_citation": f"study {study}"}


def test_agreeing_arcs_merge_into_their_median_with_the_range_and_every_study():
    # 1.0, 2.0 and 4.0 from two studies: median 2.0, range 1.0 to 4.0, three arcs, both studies
    edges, meta = merge_parallel([_arc(1.0, "S1", condition="a"), _arc(2.0, "S1", condition="b"),
                                  _arc(4.0, "S2", condition="c")])
    assert len(edges) == 1 and meta["merged"] == 1
    arc = edges[0]
    assert (arc["strength"], arc["strength_range"], arc["merged_arcs"]) == (2.0, [1.0, 4.0], 3)
    assert [s["id"] for s in arc["studies"]] == ["S1", "S2"] and arc["condition"] == "a; b; c"
    assert arc["sd"] is None and arc["significance"] is None          # a median has no sd or combined test


def test_arcs_whose_signs_disagree_are_not_merged():
    edges, meta = merge_parallel([_arc(1.0), _arc(-0.5)])
    assert len(edges) == 2 and meta["merged"] == 0 and meta["left_apart_for_disagreeing_signs"] == 1


def test_an_absent_arc_stays_separate_and_a_drop_out_makes_the_merge_possibly_indirect():
    edges, _ = merge_parallel([_arc(1.0), _arc(2.0, evidence="dropout"), _arc(0.1, status="absent")])
    merged = [e for e in edges if e.get("merged_arcs")]
    assert len(edges) == 2 and merged[0]["strength"] == 1.5 and merged[0]["evidence"] == "dropout"
    assert any(e["status"] == "absent" and not e.get("merged_arcs") for e in edges)


def test_obligate_arcs_count_without_entering_the_median():
    edges, _ = merge_parallel([_arc(None, outcome="obligate", effect="facilitation"), _arc(1.5), _arc(2.5)])
    assert (edges[0]["strength"], edges[0]["merged_arcs"], edges[0]["outcome"]) == (2.0, 3, "quantified")
    only, _ = merge_parallel([_arc(None, outcome="obligate", effect="facilitation", study=s) for s in ("S1", "S2")])
    assert only[0]["strength"] is None and only[0]["outcome"] == "obligate"


def test_the_minimum_of_supporting_studies_keeps_well_replicated_arcs():
    arcs = [_arc(1.0, "S1"), _arc(2.0, "S2"), _arc(1.0, "S1", source="ncbi:3")]   # two pairs
    edges, meta = merge_parallel(arcs, merge=True, min_studies=2)
    assert [e["source"] for e in edges] == ["ncbi:1"] and meta["below_min_studies"] == 1


def test_merging_off_leaves_every_arc_as_derived():
    arcs = [_arc(1.0), _arc(2.0)]
    edges, meta = merge_parallel(arcs, merge=False)
    assert edges is arcs and meta["merged"] == 0


def test_a_merged_arc_makes_a_valid_network_citing_every_study():
    from grownet.export import to_graphml
    edges, _ = merge_parallel([_arc(1.0, "S1"), _arc(3.0, "S2")])
    net = records_to_network(edges)
    assert net.validate() == [] and net.edges[0].study_ids == ("S1", "S2") and set(net.studies) == {"S1", "S2"}
    assert net.edges[0].merged_arcs == 2 and net.edges[0].strength_range == (1.0, 3.0)
    assert 'key="e_merged_arcs">2<' in to_graphml(net) and 'key="e_strength_range">1 3<' in to_graphml(net)


# ---- merging to genus (Karoline 2026-09-28) ------------------------------------------------------

from grownet.derive import merge_genus  # noqa: E402

BH, BO, FP = "Blautia hydrogenotrophica DSM 10507", "Blautia obeum ATCC 29174", "Faecalibacterium prausnitzii A2-165"


def _garc(strength, source_name, target_name, study="S1", status="present", source=None, target=None):
    arc = _arc(strength, study, status=status, source=source or f"id:{source_name}",
               target=target or f"id:{target_name}")
    return {**arc, "source_name": source_name, "target_name": target_name}


def test_arcs_between_two_genera_merge_by_sign_and_count_their_species_pairs():
    arcs = [_garc(1.0, BH, FP), _garc(3.0, BO, FP), _garc(-2.0, BO, FP, study="S2")]
    edges, meta = merge_genus(arcs, merge=True)
    by_effect = {e["effect"]: e for e in edges}
    assert set(by_effect) == {"facilitation", "inhibition"} and meta["genus_arcs"] == 2   # stratified by sign
    up = by_effect["facilitation"]
    assert (up["source"], up["target"], up["strength"], up["strength_range"]) == ("Blautia", "Faecalibacterium",
                                                                                   2.0, [1.0, 3.0])
    assert up["supporting_pairs"] == 2 and up["merged_pairs"] == [
        "Blautia hydrogenotrophica -> Faecalibacterium prausnitzii", "Blautia obeum -> Faecalibacterium prausnitzii"]
    down = by_effect["inhibition"]
    assert (down["strength"], down["supporting_pairs"], down["sd"]) == (-2.0, 1, 0.1)   # one arc keeps its sd


def test_the_pairs_are_strains_when_only_strains_were_entered():
    two_strains = [_garc(1.0, "Blautia obeum ATCC 29174", FP), _garc(2.0, "Blautia obeum A2-235", FP)]
    species, _ = merge_genus(two_strains, merge=True, level="species")
    strains, _ = merge_genus(two_strains, merge=True, level="strain")
    assert species[0]["supporting_pairs"] == 1 and strains[0]["supporting_pairs"] == 2


def test_interactions_within_a_genus_stay_as_an_arc_to_itself_and_absent_arcs_as_one():
    edges, _ = merge_genus([_garc(1.0, BH, BO), _garc(0.05, BH, FP, status="absent"),
                            _garc(-0.02, BO, FP, status="absent")], merge=True)
    loop = [e for e in edges if e["source"] == e["target"]]
    assert [(e["source"], e["effect"]) for e in loop] == [("Blautia", "facilitation")]
    absent = [e for e in edges if e["status"] == "absent"]
    assert len(absent) == 1 and absent[0]["supporting_pairs"] == 2 and absent[0]["target"] == "Faecalibacterium"


def test_with_arcs_merged_across_studies_a_pair_counts_once():
    # BH -> FP measured in three studies (1, 1, 1) and BO -> FP once (5): the genus median is over the two
    # pairs, 3.0, not over four arcs, which would give 1.0
    arcs = [_garc(1.0, BH, FP, study=s) for s in ("S1", "S2", "S3")] + [_garc(5.0, BO, FP, study="S4")]
    edges, meta = output_meta(arcs, include_low_quality=True, absence_threshold=0.0, merge_arcs=True,
                              merge_genera=True)
    assert len(edges) == 1 and edges[0]["strength"] == 3.0 and edges[0]["supporting_pairs"] == 2
    assert meta["genus"]["merge_genus"] is True and meta["genus"]["from_arcs"] == 2
    alone, _ = output_meta([dict(a) for a in arcs], include_low_quality=True, absence_threshold=0.0,
                           merge_genera=True)
    assert alone[0]["strength"] == 1.0                                # without it, each arc counts


def test_merging_to_genus_is_off_by_default_and_gives_a_valid_network_with_genus_nodes():
    arcs = [_garc(1.0, BH, FP), _garc(3.0, BO, FP)]
    assert merge_genus(arcs)[0] is arcs
    from grownet.export import to_graphml
    net = records_to_network(merge_genus(arcs, merge=True)[0])
    assert net.validate() == [] and set(net.nodes) == {"Blautia", "Faecalibacterium"}
    assert net.nodes["Blautia"].identity == "genus" and net.nodes["Blautia"].taxon_id == ""
    assert net.edges[0].supporting_pairs == 2 and 'key="e_supporting_pairs">2<' in to_graphml(net)


def test_the_genus_rule_skips_qualifiers_and_keeps_ncbi_brackets():
    # Craig's agent on #85: "unclassified" and "uncultured" collapsed into a genus called Unclassified;
    # Karoline (2026-09-28): such an organism joins its genus, and "[Clostridium]" is not Clostridium
    from grownet.model import genus_name
    cases = {"Candidatus Arthromitus sp": "Arthromitus", "unclassified Bacteroides": "Bacteroides",
             "uncultured Candidatus Saccharibacteria": "Saccharibacteria", "Blautia sp. SC05B48": "Blautia",
             "[Clostridium] scindens VPI 13733": "[Clostridium]", "clostridium butyricum": "Clostridium",
             "": "unknown", "unclassified": "unknown"}
    assert {name: genus_name(name) for name in cases} == cases
    edges, _ = merge_genus([_garc(1.0, "unclassified Bacteroides", FP), _garc(2.0, "unclassified Blautia", FP),
                            _garc(3.0, "[Clostridium] scindens VPI 13733", FP)], merge=True)
    assert sorted(e["source"] for e in edges) == ["Bacteroides", "Blautia", "[Clostridium]"]


def test_a_strain_named_differently_by_two_studies_counts_as_one_genus_pair():
    # code review of 2026-09-28: taxon 411483 is F. prausnitzii A2-165 in one study and F. duncaniae A2-165
    # in another; its arcs to Blautia counted as two species pairs. Both carry one node id, so one pair.
    old = _garc(1.0, "Faecalibacterium prausnitzii A2-165", BH, study="S1", source="ncbi:411483")
    new = _garc(2.0, "Faecalibacterium duncaniae A2-165", BH, study="S2", source="ncbi:411483")
    edges, _ = merge_genus([old, new], merge=True)
    assert edges[0]["supporting_pairs"] == 1
    assert edges[0]["merged_pairs"] == ["Faecalibacterium prausnitzii -> Blautia hydrogenotrophica"]


def test_skipping_uncompared_monocultures_changes_no_arc():
    # Craig's agent on #95: "Networks identical" was shown once against mGrowthDB, and nothing held it. A
    # filter that skips too much gives fewer arcs, not an error. So: one study with a monoculture no
    # co-culture uses (C), a strain named differently in its monoculture and its co-culture but sharing a
    # taxon id (A2 as A), and a second strain of B pooled into B's monocultures; derived with the filter
    # and with every experiment read, the records must be the same, and the filter must read less.
    import grownet.derive as derive_module
    C, A2, B2 = "Roseburia intestinalis L1-82", "Faecalibacterium duncaniae A2-165", "Blautia hydrogenotrophica S5a33"
    taxa = {A: 411483, A2: 411483, B: 53443, C: 536231}
    exps = [_rep_experiment("mono A", [A2], taxa), _rep_experiment("mono B", [B], taxa),
            _rep_experiment("mono B2", [B2], taxa), _rep_experiment("mono C", [C], taxa),
            _rep_experiment("co", [A, B], taxa)]
    curves = {("mono A", A2): [(1, 1), (1, 1.4)], ("mono B", B): [(1, 1), (1, 1.4)],
              ("mono B2", B2): [(1, 1.2), (1, 1.3)], ("mono C", C): [(1, 2), (1, 2.2)],
              ("co", A): [(1, 3), (1, 3.8)], ("co", B): [(1, 1), (1, 1.4)]}

    def derive(read_everything):
        client = _SeriesClient([dict(e) for e in exps], dict(curves))
        read = []
        real = client.get_bioreplicate
        client.get_bioreplicate = lambda bid: read.append(bid) or real(bid)
        real_filter = derive_module.relevant_experiments
        if read_everything:            # set by hand: monkeypatch.undo() would also undo this file's settings
            derive_module.relevant_experiments = lambda e, keep, dropout=True: list(e)
        try:
            records, _ = interactions_from_replicates(client, {"id": "S", "name": "study"}, client.experiments)
        finally:
            derive_module.relevant_experiments = real_filter
        return records, read

    filtered, read_filtered = derive(False)
    everything, read_everything = derive(True)
    assert filtered == everything and filtered                     # the same arcs, and there are some
    assert not any(b.startswith("mono C/") for b in read_filtered)  # C has no co-culture: not read
    assert any(b.startswith("mono C/") for b in read_everything) and len(read_filtered) < len(read_everything)


# ---- continuous culture with the metric it suits (Karoline, 2026-10-03) --------------------------

def test_a_chemostat_study_derives_with_max_and_the_arcs_say_so():
    """Karoline: "we don't use data when they are from chemostat. But we can, when the growth curve
    property is max ... the no-chemostat filter is too harsh, we should allow it when max is the growth
    property being compared"."""
    client, study, exps = _replicate_study()
    records, skipped = interactions_from_replicates(client, study, _mode(exps, "chemostat"), method="max")
    assert len(records) == 2
    for record in records:
        assert record["cultivation_mode"] == "chemostat"
        assert "continuous_culture" in record["cautions"]      # shown, with the mode named
        assert record["quality"] == []                         # not low quality: the comparison holds
    assert not any("excluded by default" in reason for _, reason in skipped)
    edges, meta = output_meta(records, include_absent=True)
    assert len(edges) == 2 and meta["hidden"]["low_quality"] == 0


@pytest.mark.parametrize("metric", ["auc", "growth_rate"])
def test_a_chemostat_study_is_still_left_out_for_a_metric_it_does_not_suit(metric):
    client, study, exps = _replicate_study()
    records, skipped = interactions_from_replicates(client, study, _mode(exps, "chemostat"), method=metric)
    assert records == []
    excluded = [reason for _, reason in skipped if "excluded by default" in reason]
    assert excluded and all("chemostat" in reason and metric in reason for reason in excluded)
    assert all("max" in reason for reason in excluded)          # the reason names the way out


def test_asking_for_non_batch_with_another_metric_still_marks_it_low_quality():
    client, study, exps = _replicate_study()
    records, _ = interactions_from_replicates(client, study, _mode(exps, "chemostat"), method="auc",
                                              include_non_batch=True)
    assert len(records) == 2
    for record in records:
        assert record["quality"] == ["non_batch"] and "continuous_culture" not in record["cautions"]
    edges, meta = output_meta(records)                          # hidden by default, as before
    assert edges == [] and meta["hidden"]["low_quality"] == 2


def test_a_comparison_never_mixes_a_chemostat_with_a_batch_culture():
    # the cultivation mode is part of the conditions key, so the sets cannot be pooled across modes
    client, study, exps = _replicate_study()
    for exp in exps:
        if exp["name"] == "mono B":
            exp["cultivationMode"] = "chemostat"
    records, skipped = interactions_from_replicates(client, study, exps, method="max")
    assert not [r for r in records if r["target_name"] == B]
    assert any("no monoculture replicates for " + B in reason for _, reason in skipped)
