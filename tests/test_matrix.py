"""The adjacency matrix and the gLV package, on hand-built networks (#108).

Karoline's conventions, 2026-10-03: a cell holds the log2 mean as it is; the diagonal is -1 by convention;
rows are affected and columns are the actor; an empty or absent cell is 0; each organism appears once, so
arcs of one pair are merged across studies by their median, and a pair whose arcs disagree in sign is left
at 0 and named. Then, on the first build: "obligate and abolished arcs need to carry numbers reflecting
the strong effect, how about 10 with the appropriate sign?", so a comparison with no ratio enters the
matrix as +10 (obligate) or -10 (abolished).

Those conventions are the **adjacency matrix**, which is what this file checks. The gLV package left them
behind on #119, on her decision on #116: it holds fitted coefficients, one matrix per abundance unit, and
`tests/test_glv_coefficients.py` checks it.
"""
import csv
import io
import zipfile

from grownet import matrix
from grownet.mgrowthdb import records_to_network


def _net(records):
    return records_to_network(records)


def _arc(source, target, strength, **extra):
    return {"source": source, "target": target, "source_name": source.upper(), "target_name": target.upper(),
            "effect": "facilitation" if strength > 0 else "inhibition", "strength": strength,
            "weight": abs(strength), "status": "present", "outcome": "quantified", "study_id": "S1", **extra}


def _read(text):
    table = list(csv.reader(io.StringIO(text)))
    names = table[0][1:]
    values = {(row[0], names[i]): float(cell) for row in table[1:] for i, cell in enumerate(row[1:])}
    return names, values


def test_a_cell_is_the_effect_of_the_column_on_the_row():
    # one arc: a affects b by +1.5. dx_b/dt reads row b, column a
    names, values = _read(matrix.matrix_csv(_net([_arc("a", "b", 1.5)])))
    assert names == ["A", "B"]
    assert values[("B", "A")] == 1.5          # the actor is the column
    assert values[("A", "B")] == 0.0          # nothing says b affects a
    assert values[("A", "A")] == 0.0 and values[("B", "B")] == 0.0


def test_the_glv_matrix_carries_minus_one_on_the_diagonal():
    names, values = _read(matrix.matrix_csv(_net([_arc("a", "b", 1.5)]), matrix.DIAGONAL))
    assert values[("A", "A")] == -1.0 and values[("B", "B")] == -1.0
    assert values[("B", "A")] == 1.5          # the diagonal is a convention, the rest is untouched


def test_each_organism_appears_once_and_parallel_arcs_merge_by_their_median():
    # the same pair in three studies: +1, +2, +6 give the median, not the mean (4.5 would be the mean)
    arcs = [_arc("a", "b", 1.0, study_id="S1"), _arc("a", "b", 2.0, study_id="S2"),
            _arc("a", "b", 6.0, study_id="S3")]
    names, values = _read(matrix.matrix_csv(_net(arcs)))
    assert names == ["A", "B"] and values[("B", "A")] == 2.0


def test_a_pair_whose_arcs_disagree_in_sign_is_left_at_zero_and_named():
    arcs = [_arc("a", "b", 1.0, study_id="S1"), _arc("a", "b", -2.0, study_id="S2")]
    net = _net(arcs)
    names, values = _read(matrix.matrix_csv(net))
    assert values[("B", "A")] == 0.0
    _, _, conflicts = matrix.rows(net)
    assert conflicts == [("B", "A")]          # (affected, actor), by their labels


def test_an_absent_arc_is_zero():
    _, values = _read(matrix.matrix_csv(_net([_arc("a", "b", -0.2, status="absent")])))
    assert values[("B", "A")] == 0.0          # the threshold judged it no interaction


def test_an_obligate_arc_is_plus_ten_and_an_abolished_one_minus_ten():
    """Karoline, 2026-10-03: "obligate and abolished arcs need to carry numbers reflecting the strong
    effect, how about 10 with the appropriate sign?" Neither has a log2 ratio, since one side did not grow
    at all, so the matrix states the extreme instead of leaving the cell at 0."""
    arcs = [dict(_arc("a", "b", 1.0), strength=None, outcome="obligate", effect="facilitation"),
            dict(_arc("a", "c", 1.0), strength=None, outcome="abolished", effect="inhibition")]
    _, values = _read(matrix.matrix_csv(_net(arcs)))
    assert values[("B", "A")] == 10.0 and values[("C", "A")] == -10.0
    assert matrix.EXTREME == 10.0


def test_an_arc_with_no_ratio_does_not_pull_the_median_of_the_arcs_that_have_one():
    # one study quantified the pair at +1.5, another found the target obligate on the source. The cell
    # keeps the measured value: an extreme that is a convention must not outvote a measurement
    # (register item 14: such arcs count without entering the median)
    arcs = [_arc("a", "b", 1.5, study_id="S1"),
            dict(_arc("a", "b", 1.0, study_id="S2"), strength=None, outcome="obligate")]
    _, values = _read(matrix.matrix_csv(_net(arcs)))
    assert values[("B", "A")] == 1.5
    assert matrix.by_convention(_net(arcs)) == []     # so the README does not call this cell a convention


def test_an_extreme_that_contradicts_a_measured_arc_leaves_the_cell_at_zero():
    # +10 from an obligate arc against a measured -2.0: the signs disagree, so the pair is not merged
    arcs = [_arc("a", "b", -2.0, study_id="S1"),
            dict(_arc("a", "b", 1.0, study_id="S2"), strength=None, outcome="obligate")]
    net = _net(arcs)
    _, values = _read(matrix.matrix_csv(net))
    assert values[("B", "A")] == 0.0
    assert matrix.rows(net)[2] == [("B", "A")]


def test_the_rates_file_says_what_each_median_rests_on():
    net = _net([_arc("a", "b", 1.5)])
    rates = {"a": {"rate": 0.42, "unit": "1/h", "n": 6, "studies": ["S1", "S2"],
                   "method": "growth_rate:easylinear:5", "lag": 1.25, "lag_method": "baranyi",
                   "capacity": 2.0e8, "capacity_unit": "Cells/mL", "capacity_n": 4}}
    table = list(csv.reader(io.StringIO(matrix.rates_csv(rates, net))))
    assert table[0] == ["organism", "growth_rate", "unit", "replicates", "studies", "method", "lag",
                        "lag_method", "carrying_capacity", "capacity_unit", "capacity_curves"]
    # the lag names its own estimator, since it is Baranyi's whichever one produced the rate
    assert table[1] == ["A", "0.42", "1/h", "6", "S1 S2", "growth_rate:easylinear:5", "1.25", "baranyi",
                        "2e+08", "Cells/mL", "4"]
    # a rate with none of the gLV quantities keeps its row and leaves them empty (#118)
    plain = list(csv.reader(io.StringIO(matrix.rates_csv({"a": {"rate": 0.42, "unit": "1/h"}}, net))))
    assert plain[1] == ["A", "0.42", "1/h", "", "", "", "", "", "", "", ""]
    assert len(table) == 2                    # b has no rate, so it has no row


def test_the_package_holds_a_matrix_the_rates_and_a_readme():
    """The three files, and the README's standing content. What the numbers in them are is #119's, in
    tests/test_glv_coefficients.py: coefficients, so the package needs growth-rate arcs."""
    rate = {"rate": 0.4, "n": 3, "unit": "1/h", "method": "growth_rate:baranyi", "capacity": 1.0e9,
            "capacity_unit": "Cells/mL", "capacity_n": 3}
    net = _net([_arc("a", "b", 1.5, metric="growth_rate:baranyi", partner_abundance=2.0e8,
                     partner_abundance_unit="Cells/mL"),
                _arc("b", "a", -0.5, metric="growth_rate:baranyi", partner_abundance=1.0e8,
                     partner_abundance_unit="Cells/mL")])
    net.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}, "source_db": "mGrowthDB (live)"})
    with zipfile.ZipFile(io.BytesIO(matrix.glv_package(net, {"a": rate}))) as archive:
        assert sorted(archive.namelist()) == ["README.txt", "growth_rates.csv",
                                              "interaction_matrix.Cells_per_mL.csv"]
        readme = archive.read("README.txt").decode()
        _, values = _read(archive.read("interaction_matrix.Cells_per_mL.csv").decode())
    # only A has a rate and a capacity, so only A is in the matrix: -0.4 / 1e9
    assert values == {("A", "A"): -4.0e-10}
    assert "A[i][j] is the effect of j on i" in readme
    assert "k = 1.0" in readme
    # an organism that cannot be fitted is named, since a simulation needs its parameters from elsewhere
    assert "B: no growth rate" in readme


def test_the_order_is_stable_so_two_runs_line_up():
    arcs = [_arc("b", "a", 1.0), _arc("c", "a", 1.0)]
    first = matrix.matrix_csv(_net(arcs))
    second = matrix.matrix_csv(_net(list(reversed(arcs))))
    assert first == second and first.splitlines()[0] == ",A,B,C"


def test_a_genus_node_takes_the_median_rate_of_its_strains():
    # a network merged to the genus level has no strain nodes, so Blautia's rate is the median of the two
    # Blautia strains that have one: 0.3 and 0.5 give 0.4
    net = _net([dict(_arc("blautia", "roseburia", 1.0), source_name="Blautia", target_name="Roseburia",
                     source_identity="genus", target_identity="genus")])
    rates = {"ncbi:1": {"name": "Blautia hydrogenotrophica DSM 10507", "rate": 0.3, "unit": "1/h", "n": 2,
                        "studies": ["S1"]},
             "ncbi:2": {"name": "Blautia wexlerae", "rate": 0.5, "unit": "1/h", "n": 1, "studies": ["S2"]}}
    aligned = matrix.for_nodes(net, rates)
    assert aligned["blautia"]["rate"] == 0.4 and aligned["blautia"]["n"] == 3
    assert aligned["blautia"]["studies"] == ["S1", "S2"]
    assert "roseburia" not in aligned            # no monoculture of any Roseburia strain, so no rate


def test_a_cell_that_holds_the_convention_says_so_in_the_readme():
    # a reader has to know which numbers were measured and which are the stated extreme
    net = _net([dict(_arc("a", "b", 1.0), strength=None, outcome="obligate")])
    assert matrix.by_convention(net) == [("B", "A", 10.0)]
    readme = matrix.readme(net, {}, [], [], matrix.by_convention(net))
    assert "CONVENTIONS, NOT MEASUREMENTS" in readme
    assert "A on B: 10" in readme.split("CONVENTIONS, NOT MEASUREMENTS")[1]


def test_a_rate_is_reported_under_the_name_the_network_uses():
    # a strain renamed after a reclassification (411483) carries its current name in the network; the rates
    # must not fall back to the name the study that measured them used (#24)
    net = _net([_arc("ncbi:411483", "b", 1.0, source_name="Faecalibacterium duncaniae")])
    rates = {"ncbi:411483": {"name": "Faecalibacterium prausnitzii A2-165", "rate": 0.7, "unit": "1/h",
                             "n": 3, "studies": ["S1"]}}
    assert matrix.for_nodes(net, rates)["ncbi:411483"]["name"] == "Faecalibacterium duncaniae"
    assert "Faecalibacterium duncaniae" in matrix.rates_csv(matrix.for_nodes(net, rates), net)


def test_the_files_name_the_media_the_arcs_came_from():
    """Karoline, 2026-10-04: a gLV simulation is of one environment, so the package says which media its
    numbers were measured in, and says it loudly when there is more than one."""
    one = _net([dict(_arc("a", "b", 1.5), medium="mMCB")])
    one.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert matrix.media(one) == ["mMCB"]
    assert "Every arc was measured in one medium: mMCB." in matrix.readme(one, {}, [], [])

    mixed = _net([dict(_arc("a", "b", 1.5), medium="mMCB"),
                  dict(_arc("b", "a", -0.5, study_id="S2"), medium="Wilkins-Chalgren")])
    mixed.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert matrix.media(mixed) == ["mMCB", "Wilkins-Chalgren"]
    text = matrix.readme(mixed, {}, [], [])
    assert "THESE ARCS COME FROM 2 MEDIA" in text and "second box" in text
    # and a program reading the payload sees the same, as data
    assert matrix.glv_payload(mixed, {})["caveats"]["media"] == ["mMCB", "Wilkins-Chalgren"]


def test_the_package_counts_the_arcs_a_glv_simulation_should_not_use():
    """Karoline, 2026-10-04: drop-out arcs may act through a third species, so a package that holds them
    says how many and which switch leaves them out."""
    net = _net([_arc("a", "b", 1.5, evidence="dropout"), _arc("b", "a", 1.0, evidence="biculture")])
    net.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert matrix.dropout_arcs(net) == 1
    text = matrix.readme(net, {}, [], [])
    assert "1 ARC(S) COME FROM DROP-OUT DESIGNS" in text and "Include drop-out communities" in text
    assert matrix.glv_payload(net, {})["caveats"]["dropout_arcs"] == 1
    # a package without any says so plainly, so a reader knows the question was asked
    direct = _net([_arc("a", "b", 1.5, evidence="biculture")])
    direct.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert "none comes from a drop-out design" in matrix.readme(direct, {}, [], [])
