"""The adjacency matrix and the gLV package, on hand-built networks (#108).

Karoline's conventions, 2026-10-03: a cell holds the log2 mean as it is; the diagonal is -1 by convention;
rows are affected and columns are the actor; an empty or absent cell is 0; each organism appears once, so
arcs of one pair are merged across studies by their median, and a pair whose arcs disagree in sign is left
at 0 and named.
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


def test_an_absent_arc_and_an_arc_without_a_ratio_are_zero():
    arcs = [_arc("a", "b", -0.2, status="absent"),
            dict(_arc("a", "c", 1.0), strength=None, outcome="obligate")]
    _, values = _read(matrix.matrix_csv(_net(arcs)))
    assert values[("B", "A")] == 0.0 and values[("C", "A")] == 0.0


def test_the_rates_file_says_what_each_median_rests_on():
    net = _net([_arc("a", "b", 1.5)])
    rates = {"a": {"rate": 0.42, "unit": "1/h", "n": 6, "studies": ["S1", "S2"]}}
    table = list(csv.reader(io.StringIO(matrix.rates_csv(rates, net))))
    assert table[0] == ["organism", "growth_rate", "unit", "replicates", "studies"]
    assert table[1] == ["A", "0.42", "1/h", "6", "S1 S2"]
    assert len(table) == 2                    # b has no rate, so it has no row


def test_the_package_holds_the_two_files_and_a_readme_that_states_the_conventions():
    net = _net([_arc("a", "b", 1.5), _arc("b", "a", -0.5)])
    net.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}, "source_db": "mGrowthDB (live)"})
    with zipfile.ZipFile(io.BytesIO(matrix.glv_package(net, {"a": {"rate": 0.4, "n": 3}}))) as archive:
        assert sorted(archive.namelist()) == ["README.txt", "growth_rates.csv", "interaction_matrix.csv"]
        readme = archive.read("README.txt").decode()
        _, values = _read(archive.read("interaction_matrix.csv").decode())
    assert values[("A", "A")] == -1.0 and values[("B", "A")] == 1.5 and values[("A", "B")] == -0.5
    assert "A[i][j] is the effect of j on i" in readme
    assert "not a fitted glv coefficient" in readme.lower()
    assert "k = 1.0" in readme
    # an organism without a rate is named, since a simulation needs one from elsewhere
    assert "B" in readme.split("no growth rate")[1]


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


def test_a_pair_that_interacts_but_has_no_number_is_named_in_the_readme():
    # an obligate arc has no log2 ratio (one side did not grow), so its cell is 0 like an empty one: the
    # README says so, rather than letting a simulator read it as no interaction
    net = _net([dict(_arc("a", "b", 1.0), strength=None, outcome="obligate")])
    assert matrix.unquantified(net) == [("B", "A")]
    readme = matrix.readme(net, {}, [], [], matrix.unquantified(net))
    assert "no number" in readme and "A on B" in readme.split("no number")[1]
