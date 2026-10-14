"""The five fields of grownet.interaction_network/v4 (Karoline, 2026-10-12, on #266, #217 and #209)."""
import xml.etree.ElementTree as ET

from grownet.derive import against_other_removals, metric_unit, strain_identities
from grownet.export import to_graphml
from grownet.mgrowthdb import records_to_network
from grownet.model import SCHEMA, InteractionNetwork
from grownet.schema import validate_document


def test_the_unit_of_the_two_metric_values_follows_the_metric():
    """#214: 190 of 223 live arcs carried no unit for metric_with and metric_without."""
    assert metric_unit("auc", "Cells/mL", "h") == "Cells/mL x h"
    assert metric_unit("max", "Cells/mL", "h") == "Cells/mL"
    assert metric_unit("growth_rate:easylinear:5", "Cells/mL", "h") == "1/h"
    assert metric_unit("auc", "", "h") == "" and metric_unit("unknown", "Cells/mL", "h") == ""


def _drop(source, strength, with_=3.5, target="t", medium="WC"):
    return {"source": source, "target": target, "evidence": "dropout", "strength": strength,
            "metric_with": with_, "study_id": "S8", "medium": medium, "metric": "auc"}


def test_a_drop_out_arc_against_the_other_removals_of_its_target():
    """#209 option 2: what this removal did beyond the level its group shares, the median of the others."""
    group = [_drop("a", 1.0), _drop("b", 2.0), _drop("c", 4.0)]
    pair = [_drop("d", 1.0, with_=9.0), _drop("e", 3.0, with_=9.0)]          # two: no reference
    other = {"source": "x", "target": "t", "evidence": "biculture", "strength": 5.0, "metric_with": 3.5,
             "study_id": "S8", "medium": "WC", "metric": "auc"}
    records = [*group, *pair, other]
    against_other_removals(records)
    assert [r["vs_other_removals"] for r in group] == [1.0 - 3.0, 2.0 - 2.5, 4.0 - 1.5]
    assert [r["vs_other_removals"] for r in pair] == [None, None]
    assert other["vs_other_removals"] is None, "a biculture arc has no group of removals"
    # another reference is another group: same target, another medium
    split = [_drop("a", 1.0), _drop("b", 2.0), _drop("c", 4.0, medium="other")]
    against_other_removals(split)
    assert [r["vs_other_removals"] for r in split] == [None, None, None]


def test_a_refused_taxon_id_is_kept_and_said_not_to_be_a_join_key():
    """#217 option b: SMGDB00000008 gives 1506553 to two strains. The id stays, the node says why it is not
    the identity, and the node id is the name, as before."""
    exps = [{"communityStrains": [{"name": "Lachnoclostridium clostridioforme 2_1_49FAA", "NCBId": 1506553},
                                  {"name": "Lachnoclostridium symbiosum WAL-14673", "NCBId": 1506553},
                                  {"name": "Bacteroides ovatus 3_8_47FAA", "NCBId": 665954}]}]
    ids = strain_identities(exps, [])
    refused = ids["Lachnoclostridium symbiosum WAL-14673"]
    assert refused["taxon_id"] == "1506553" and refused["identity"] == "name"
    assert "1506553" in refused["taxon_id_refused"] and "not a join key" in refused["taxon_id_refused"]
    assert ids["Bacteroides ovatus 3_8_47FAA"]["taxon_id_refused"] == ""


def test_every_v4_field_reaches_the_file_graphml_and_validation():
    net = records_to_network([{
        "source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
        "strength": 1.0, "study_id": "S1", "metric_unit": "Cells/mL x h", "window": 30.0, "window_unit": "h",
        "vs_other_removals": -0.5, "source_taxon_id": "1506553",
        "source_taxon_id_refused": "mGrowthDB gives taxon id 1506553 to different strains in this study"}])
    doc = net.to_dict()
    assert doc["schema"] == SCHEMA == "grownet.interaction_network/v4"
    (edge,) = doc["edges"]
    assert (edge["metric_unit"], edge["window"], edge["window_unit"], edge["vs_other_removals"]) == \
        ("Cells/mL x h", 30.0, "h", -0.5)
    node = next(n for n in doc["nodes"] if n["id"] == "a")
    assert node["taxon_id_refused"].startswith("mGrowthDB gives taxon id 1506553")
    notes = []
    assert validate_document(doc, notes) == [] and not [n for n in notes if "declare" in n], notes
    # and back: a v4 file reads into the same fields
    again = InteractionNetwork.from_dict(doc)
    assert again.edges[0].window == 30.0 and again.nodes["a"].taxon_id_refused == node["taxon_id_refused"]
    graphml = ET.fromstring(to_graphml(net))
    keys = {k.get("attr.name") for k in graphml.iter("{http://graphml.graphdrawing.org/xmlns}key")}
    assert {"metric_unit", "window", "window_unit", "vs_other_removals", "taxon_id_refused"} <= keys


def test_a_v3_file_still_reads_and_validates():
    """Additions, not changes of meaning: a v3 document without the five fields is valid and reads."""
    doc = {"schema": "grownet.interaction_network/v3", "meta": {}, "studies": [{"id": "S1"}],
           "nodes": [{"id": "a"}, {"id": "b"}],
           "edges": [{"source": "a", "target": "b", "effect": "facilitation", "study_ids": ["S1"]}]}
    assert validate_document(doc) == []
    net = InteractionNetwork.from_dict(doc)
    assert net.edges[0].metric_unit == "" and net.edges[0].window is None


def test_a_merged_arc_says_nothing_one_member_said_alone():
    """Found in review: `_merged` spread the first arc, so a genus arc that was the median of twelve arcs
    over 20 h and 30 h windows said `window 20` and carried one member's `vs_other_removals`."""
    from grownet.derive import _merged

    def arc(window, vs, mw, unit="Cells/mL x h"):
        return {"source": "a", "target": "b", "strength": 1.0, "study_id": "S8", "window": window,
                "window_unit": "h", "metric_unit": unit, "vs_other_removals": vs, "metric_with": mw,
                "metric_without": 1.0, "evidence": "dropout"}
    mixed = _merged([arc(20.0, -0.5, 2.0), arc(30.0, 0.7, 3.0)])
    assert mixed["window"] is None and mixed["vs_other_removals"] is None and mixed["metric_with"] is None
    assert mixed["window_unit"] == "h" and mixed["metric_unit"] == "Cells/mL x h", "agreed values are kept"
    same = _merged([arc(30.0, -0.5, 2.0), arc(30.0, 0.7, 2.0)])
    assert same["window"] == 30.0 and same["metric_with"] == 2.0 and same["vs_other_removals"] is None


def test_the_derivation_itself_fills_the_v4_fields():
    """Found in review: the test above writes the fields into its own records, so blanking `metric_unit` or
    `window` in derive.py or integrated.py, not carrying `taxon_id_refused`, or deleting the
    `against_other_removals` call all left the suite green. These read what the product produces."""
    from test_glv_mode_end_to_end import TimeCourseClient
    from test_gui import A, B, FakeClient

    from grownet.derive import _record, output_meta
    from grownet.gui import glv_mode, run_query
    replicate = run_query(FakeClient(), [A, B], {"derivation": "replicate", "include_absent": True})
    for e in replicate["network"].edges:
        assert (e.metric_unit, e.window, e.window_unit) == ("Cells/mL x h", 10.0, "h"), e
    integrated = run_query(TimeCourseClient(), [A, B], glv_mode({}))
    assert integrated["network"].edges
    for e in integrated["network"].edges:
        assert e.metric_unit.startswith("1/") and e.window and e.window_unit, e
    # a refused taxon id travels from the identities onto the record and so onto the node
    identities = {"S": {"id": "s", "taxon_id": "1506553", "species": "s", "identity": "name",
                        "taxon_id_refused": "mGrowthDB gives taxon id 1506553 to different strains"},
                  "T": {"id": "ncbi:2", "taxon_id": "2", "species": "t", "identity": "ncbi", "taxon_id_refused": ""}}
    c = {"mean": 1.0, "sd": 0.5, "se": 0.3, "outcome": "quantified", "n_with": 3, "n_without": 3,
         "with_log2": [1.0, 1.1, 0.9], "without_log2": [0.0, 0.1, -0.1], "window": (0.0, 30.0),
         "units": ("Cells/mL", "h")}
    record = _record("S", "T", c, "auc", [], [], [], "", "dropout", ("S", "T"), ["E1"], "S8", {}, identities)
    assert record["source_taxon_id_refused"].startswith("mGrowthDB gives") and record["window"] == 30.0
    # and output_meta sets vs_other_removals on a group of drop-out arcs measured against one reference
    group = [{**record, "source": f"s{i}", "strength": v} for i, v in enumerate((1.0, 2.0, 4.0))]
    edges, _ = output_meta(group, include_absent=True)
    assert sorted(e["vs_other_removals"] for e in edges) == sorted([1.0 - 3.0, 2.0 - 2.5, 4.0 - 1.5])


def test_vs_other_removals_is_a_median_within_one_study_and_metric():
    """Found in review: with two others in every group, a mean passed for the median, and dropping the study
    and the metric from the grouping key passed too."""
    group = [_drop(s, v) for s, v in zip("abcd", (1.0, 2.0, 4.0, 10.0), strict=True)]
    other_study = [{**_drop(s, 9.0), "study_id": "S9"} for s in "ef"]
    other_metric = [{**_drop(s, -9.0), "metric": "max"} for s in "gh"]
    records = [*group, *other_study, *other_metric]
    against_other_removals(records)
    # a: others 2, 4, 10 -> median 4 (a mean would give 5.33)
    assert [r["vs_other_removals"] for r in group] == [1.0 - 4.0, 2.0 - 4.0, 4.0 - 2.0, 10.0 - 2.0]
    assert all(r["vs_other_removals"] is None for r in [*other_study, *other_metric]), "groups of two"



def test_a_merged_arc_keeps_no_one_comparison_s_bound_capacity_or_fit():
    """Round 2 of the review: after the first fix the merge still spread `arcs[0]` for every field it did
    not name, so a quantified genus arc carried one obligate member's bound and rule and one member's
    coefficient and fit. Every field describing one comparison is now kept only where all agree; the
    coefficient is the members' median, as the strength is."""
    from grownet.derive import COMPARISON_FIELDS, _merged
    first = {"source": "a", "target": "b", "strength": None, "outcome": "obligate", "study_id": "S1",
             "strength_bound": 3.47, "bound_rule": "no growth: at most 1.5 times its start",
             "target_capacity": 6.3e8, "coefficient": -4.35e-10, "coefficient_unit": "1/(h x Cells/mL)",
             "fit_r2": 0.983, "rate_mismatch_to_zero": -0.15}
    second = {**first, "strength": 4.4, "outcome": "quantified", "strength_bound": None, "bound_rule": "",
              "target_capacity": 5.0e8, "coefficient": -5.57e-10, "fit_r2": 0.91, "rate_mismatch_to_zero": -0.2}
    merged = _merged([first, second])
    for key in ("strength_bound", "target_capacity", "fit_r2", "rate_mismatch_to_zero"):
        assert merged[key] is None, key
    assert merged["bound_rule"] == "" and merged["coefficient_unit"] == "1/(h x Cells/mL)"
    assert abs(merged["coefficient"] - (-4.35e-10 + -5.57e-10) / 2) < 1e-20, "the members' median"
    assert {"strength_bound", "coefficient", "fit_r2", "se_rate_selection"} <= set(COMPARISON_FIELDS)


def test_a_merged_arc_s_cell_is_labelled_as_a_merged_arc_not_an_old_network():
    """The merge fix emptied a merged arc's two rates, which sent its gLV cell to the fallback labelled "a
    network derived before the two absolute rates were recorded ... derive again", false of a merged arc."""
    from grownet.matrix import _per_arc
    from grownet.model import Edge
    base = dict(source="a", target="b", effect="inhibition", strength=-0.5, partner_abundance=2e8,
                merged_arcs=2)
    assert _per_arc(Edge(**base, coefficient=-4.96e-10), 0.4) == (-4.96e-10, "rates")
    value, how = _per_arc(Edge(**base), 0.4)
    assert how == "merged" and abs(value - 0.4 * (2 ** -0.5 - 1) / 2e8) < 1e-20
    assert _per_arc(Edge(**{**base, "merged_arcs": None}), 0.4)[1] == "ratio", "an unmerged old arc"


def test_arcs_from_an_organism_to_itself_are_counted_as_arcs():
    """Round 2: the count was of self PAIRS left in the matrix, so a genus with arcs of both signs to itself
    (dropped as a conflict) read as 1 where the file held 5; and the conflict list named the self pair as a
    0 cell, which it has none of."""
    from grownet import matrix
    net = records_to_network([
        {"source": "g", "target": "g", "effect": "inhibition", "strength": -1.0, "study_id": "S1"},
        {"source": "g", "target": "g", "effect": "facilitation", "strength": 1.0, "study_id": "S1"},
        {"source": "h", "target": "h", "effect": "inhibition", "strength": -0.5, "study_id": "S1"}])
    assert matrix.counts(net)["within_one_organism"] == 3
    about = matrix.matrix_about(net)
    assert "3 arc(s) are from one organism to itself" in about and "DISAGREE IN SIGN" not in about


def test_the_integrated_form_carries_a_refused_taxon_id_too():
    """Round 2 of the review: the refusal was tested through `derive._record` only, and the integrated form
    builds its own records, so blanking it there survived."""
    import json

    import test_glv_mode_end_to_end as e2e
    from test_glv_mode_end_to_end import A, B, TimeCourseClient

    from grownet.gui import glv_mode, run_query
    # one NCBI id for two strains of one study, in the experiments the client serves (they are built at
    # import, so patching TAXA afterwards changed nothing: the first version of this test did that)
    shared = json.loads(json.dumps(e2e.EXPERIMENTS))
    for exp in shared:
        for strain in exp["communityStrains"]:
            strain["NCBId"] = e2e.TAXA[A]

    class SharedId(TimeCourseClient):
        def study_experiments(self, study_id):
            return shared

        def get_experiment(self, experiment_id):
            return next(e for e in shared if e["id"] == experiment_id)
    r = run_query(SharedId(), [A, B], glv_mode({}))
    # BOTH strains share the id, so both nodes, the arc's source and its target, carry the refusal
    nodes = list(r["network"].nodes.values())
    assert len(nodes) == 2 and all("not a join key" in n.taxon_id_refused for n in nodes), nodes


def test_a_merged_arc_drops_unit_and_value_fields_its_members_disagree_on():
    """Round 2: the fixture's members agreed on window_unit, metric_unit and metric_without, so only the
    "kept" branch was tested."""
    from grownet.derive import _merged
    a = {"source": "a", "target": "b", "strength": 1.0, "study_id": "S1", "window_unit": "h",
         "metric_unit": "Cells/mL x h", "metric_without": 1.0}
    b = {**a, "window_unit": "min", "metric_unit": "CFUs/mL x h", "metric_without": 2.0}
    merged = _merged([a, b])
    assert (merged["window_unit"], merged["metric_unit"], merged["metric_without"]) == ("", "", None)


def test_every_field_of_one_comparison_is_kept_only_where_the_members_agree():
    """Round 3 of the review: the test above covered 7 of the 21 fields, so dropping any of the other 14
    from COMPARISON_FIELDS left the suite green. Here the members disagree on every one."""
    from grownet.derive import COMPARISON_FIELDS, _merged
    # written out, not read from the tuple, so a field dropped from it fails here
    assert set(COMPARISON_FIELDS) == {
        "strength_bound", "bound_rule", "target_capacity", "target_capacity_unit", "target_capacity_n",
        "coefficient", "coefficient_unit", "coefficient_sd", "coefficient_n", "coefficient_sd_from_rate_stage",
        "fit_r2", "fit_condition", "fit_null_r2", "fit_window_share", "rate_mismatch_to_zero",
        "se_replicates", "se_rate_stage", "se_rate_selection", "rate_selection_spread", "rate_stage_method",
        "rate_stage_n"}
    first = {"source": "a", "target": "b", "strength": 1.0, "outcome": "quantified", "study_id": "S1"}
    second = {**first, "strength": 3.0, "study_id": "S2"}
    for i, key in enumerate(COMPARISON_FIELDS):
        first[key], second[key] = (f"{key} one", f"{key} two") if key in (
            "bound_rule", "target_capacity_unit", "fit_condition", "rate_stage_method") else (i + 1.0, i + 2.0)
    first["coefficient_unit"] = second["coefficient_unit"] = "1/(h x Cells/mL)"   # so the median is taken
    merged = _merged([first, second])
    for key in COMPARISON_FIELDS:
        if key == "coefficient":
            assert merged[key] == (first[key] + second[key]) / 2, "the members' median"
        elif key == "coefficient_unit":
            assert merged[key] == "1/(h x Cells/mL)"
        else:
            assert merged[key] in (None, ""), key
    # a median over three is the middle one, not the mean (median and mean of two agree)
    third = {**second, "strength": 5.0, "study_id": "S3", "coefficient": 100.0}
    assert _merged([first, second, third])["coefficient"] == second["coefficient"]


def test_a_merged_coefficient_needs_every_member_s_in_one_unit():
    """Round 3 of the review: with `any` for `all`, a member without a coefficient made the median raise,
    and without the unit condition it took a median across units."""
    from grownet.derive import _merged
    one = {"source": "a", "target": "b", "strength": 1.0, "outcome": "quantified", "study_id": "S1",
           "coefficient": -4e-10, "coefficient_unit": "1/(h x Cells/mL)"}
    other_unit = {**one, "study_id": "S2", "coefficient": -6e-2, "coefficient_unit": "1/(h x OD)"}
    assert _merged([one, other_unit])["coefficient"] is None
    missing = {**one, "study_id": "S2", "coefficient": None}
    assert _merged([one, missing])["coefficient"] is None


def test_a_package_with_a_merged_arc_says_its_cell_came_from_the_median_ratio():
    """Round 3 of the review: `_per_arc` labels a merged arc's cell, and nothing downstream was tested, so
    the README could say every cell came from measured rates while one came from the merged ratio."""
    from grownet import matrix
    net = records_to_network([
        {"source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "inhibition",
         "strength": -0.5, "sd": 0.1, "study_id": "S1", "merged_arcs": 2, "partner_abundance": 2e8,
         "partner_abundance_unit": "Cells/mL", "outcome": "quantified", "metric": "growth_rate:easylinear:5"}])
    rates = {nid: {"name": nid.upper(), "rate": 0.4, "unit": "1/h", "n": 3, "studies": ["S1"],
                   "capacity": 1e9, "capacity_unit": "Cells/mL", "capacity_n": 3} for nid in ("a", "b")}
    got = matrix.coefficients(net, rates)
    assert got["from_absolute_rates"] is False
    assert got["from_merged_ratio"] == [("B", "A")] and got["from_the_ratio"] == []
    readme = matrix.readme_from(got, net, rates)
    assert "CELLS FROM MERGED ARCS, TAKEN FROM THEIR MEDIAN LOG2 RATIO" in readme and "A on B" in readme
    assert "a network derived before the two absolute rates" not in readme


def test_only_present_quantified_arcs_to_oneself_count_as_within_one_organism():
    """Round 3 of the review: the count's condition was untested, so counting every self arc, or the absent
    and censored ones, left the suite green."""
    from grownet import matrix
    net = records_to_network([
        {"source": "g", "target": "g", "effect": "inhibition", "strength": -1.0, "study_id": "S1"},
        {"source": "g", "target": "g", "effect": "facilitation", "strength": 0.05, "sd": 1.0,
         "status": "absent", "study_id": "S1"},
        {"source": "h", "target": "h", "effect": "facilitation", "strength": None, "outcome": "obligate",
         "study_id": "S1"},                                   # censored: it reports an extreme, so it counts
        {"source": "k", "target": "k", "effect": "facilitation", "strength": None, "outcome": "quantified",
         "study_id": "S1"},                                   # no number and no extreme: nothing to count
        {"source": "a", "target": "b", "effect": "inhibition", "strength": -1.0, "study_id": "S1"}])
    assert matrix.counts(net)["within_one_organism"] == 2
