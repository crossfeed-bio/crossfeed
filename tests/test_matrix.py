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
    # a censored cell is written `NA` since #129 settled, which float() cannot read: it is kept as it is
    values = {(row[0], names[i]): (cell if cell == "NA" else float(cell))
              for row in table[1:] for i, cell in enumerate(row[1:])}
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
    at all. The stated extreme carried that cell until #129 settled on 2026-10-08: the cell is now `NA`,
    the measured bound travels on the arc, and the number 10 is in no output. 0 would be wrong in the
    other direction, since it reads as no interaction about the strongest effect there is."""
    arcs = [dict(_arc("a", "b", 1.0), strength=None, outcome="obligate", effect="facilitation"),
            dict(_arc("a", "c", 1.0), strength=None, outcome="abolished", effect="inhibition")]
    text = matrix.matrix_csv(_net(arcs))
    _, values = _read(text)
    assert values[("B", "A")] == "NA" and values[("C", "A")] == "NA"
    assert not any(cell in ("10", "-10") for row in text.splitlines()[1:] for cell in row.split(",")[1:])
    assert sorted(matrix.bounded_cells(_net(arcs))) == [("B", "A", None), ("C", "A", None)]


def test_an_arc_with_no_ratio_does_not_pull_the_median_of_the_arcs_that_have_one():
    # one study quantified the pair at +1.5, another found the target obligate on the source. The cell
    # keeps the measured value: an extreme that is a convention must not outvote a measurement
    # (register item 14: such arcs count without entering the median)
    arcs = [_arc("a", "b", 1.5, study_id="S1"),
            dict(_arc("a", "b", 1.0, study_id="S2"), strength=None, outcome="obligate")]
    _, values = _read(matrix.matrix_csv(_net(arcs)))
    assert values[("B", "A")] == 1.5
    assert matrix.bounded_cells(_net(arcs)) == []     # and the cell is not listed as censored either


def test_a_censored_arc_that_contradicts_a_measured_arc_leaves_the_cell_at_zero():
    # an obligate arc (facilitation, so positive) against a measured -2.0: the signs disagree, so the
    # pair is not merged. The censored arc carries no number since #129 settled, and its DIRECTION still
    # counts in the disagreement, which is what keeps this cell a conflict rather than -2.0
    arcs = [_arc("a", "b", -2.0, study_id="S1"),
            dict(_arc("a", "b", 1.0, study_id="S2"), strength=None, outcome="obligate")]
    net = _net(arcs)
    _, values = _read(matrix.matrix_csv(net))
    assert values[("B", "A")] == 0.0                  # a conflict is 0 and named, not NA
    assert matrix.rows(net)[2] == [("B", "A")]
    assert matrix.bounded_cells(net) == []


def test_the_rates_file_says_what_each_median_rests_on():
    net = _net([_arc("a", "b", 1.5)])
    rates = {"a": {"rate": 0.42, "unit": "1/h", "n": 6, "studies": ["S1", "S2"],
                   "method": "growth_rate:easylinear:5", "lag": 1.25, "lag_method": "baranyi",
                   "capacity": 2.0e8, "capacity_unit": "Cells/mL", "capacity_n": 4}}
    table = list(csv.reader(io.StringIO(matrix.rates_csv(rates, net))))
    # capacity_curves_left_out added 2026-10-06: an empty capacity read as absence, because the curves
    # that gave none were collected and never shown where the capacity is read
    # capacity_fall_from_peak added 2026-10-07: the plateau is the peak of a curve that may have declined
    # after it, so what those curves held at their last measurement travels with the number
    # doubling_time added 2026-10-08 (#173): ln(2) / rate, in the time unit of the rate, derived from the
    # column beside it. ln(2) / 0.42 = 1.6504 h by hand
    assert table[0] == ["organism", "growth_rate", "unit", "replicates", "studies", "method", "lag",
                        "lag_method", "carrying_capacity", "capacity_unit", "capacity_curves",
                        "capacity_curves_left_out", "capacity_fall_from_peak", "capacity_medium",
                        "capacity_source", "doubling_time"]
    # the lag names its own estimator, since it is Baranyi's whichever one produced the rate
    assert table[1] == ["A", "0.42", "1/h", "6", "S1 S2", "growth_rate:easylinear:5", "1.25", "baranyi",
                        "2e+08", "Cells/mL", "4", "", "", "", "", "1.65"]
    # a rate with none of the gLV quantities keeps its row and leaves them empty (#118)
    plain = list(csv.reader(io.StringIO(matrix.rates_csv({"a": {"rate": 0.42, "unit": "1/h"}}, net))))
    assert plain[1] == ["A", "0.42", "1/h", "", "", "", "", "", "", "", "", "", "", "", "", "1.65"]

    # and a capacity that rests on fewer curves than were read says how many gave none, so an empty or
    # thin capacity does not read as absence (found 2026-10-06)
    thin = {"a": {"rate": 0.42, "unit": "1/h", "capacity": 2.0e8, "capacity_unit": "Cells/mL",
                  "capacity_n": 1, "capacity_left_out": [("A rep 2", "had not reached stationary phase"),
                                                         ("A rep 3", "had not reached stationary phase")]}}
    # read by name rather than by position, since columns are appended over time (the fall from the peak
    # and the medium in 2026-10-07, the doubling time in 2026-10-08), and this fixture states none of them
    thin_table = list(csv.reader(io.StringIO(matrix.rates_csv(thin, net))))
    assert dict(zip(thin_table[0], thin_table[1], strict=True))["capacity_curves_left_out"] == "2"
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


def test_a_cell_with_no_ratio_is_named_as_such():
    """A reader has to know which cells hold no number and why. Since #129 settled (2026-10-08) such a
    cell is `NA` and `bounded_cells` names it, with the arc's measured bound where there is one; this arc
    carries none, so the listing reports None. `tests/test_measured_bound.py` checks a real bound."""
    net = _net([dict(_arc("a", "b", 1.0), strength=None, outcome="obligate")])
    assert matrix.bounded_cells(net) == [("B", "A", None)]
    assert matrix.counts(net)["arcs"] == 1            # it reaches the matrix: a cell a reader sees


def test_an_arc_from_one_organism_to_itself_is_counted_apart_from_the_cells():
    """A self pair has no cell of its own, so it is not counted as one.

    `--merge-genera` produces within-genus arcs by design (Karoline, on `derive.merge_genus`:
    "interactions within one genus stay, as an arc from the genus to itself"), and the plain matrix writes
    the DIAGONAL at that position. Counting them as cells promised 45 where the CSV held 44, and the arc
    the JSON reported printed as 0, which in that file means no interaction (#248).

    Nothing read `cells` or `within_one_organism`: reverting `counts` to `len(values)` and 0 left the
    whole suite green, so the page could promise a cell the CSV does not hold again (found reviewing
    round 10).
    """
    net = _net([_arc("a", "b", 1.0), _arc("a", "a", 0.5)])
    got = matrix.counts(net)
    assert got["arcs"] == 2                       # both reach the matrix
    assert got["within_one_organism"] == 1        # one of them is a pair with itself
    assert got["cells"] == 1                      # and so makes no cell: only A -> B does

    # the CSV is the thing that must agree, so it is read rather than assumed: exactly one off-diagonal
    # position carries a number, and the self pair's position holds the diagonal
    _names, values = _read(matrix.matrix_csv(net))
    off = {pair: v for pair, v in values.items() if pair[0] != pair[1] and v not in (0, 0.0)}
    assert len(off) == got["cells"], (off, got)
    assert values[("A", "A")] == 0.0              # the diagonal, not the 0.5 arc


def test_a_rate_is_reported_under_the_name_the_network_uses():
    # a strain renamed after a reclassification (411483) carries its current name in the network; the rates
    # must not fall back to the name the study that measured them used (#24)
    net = _net([_arc("ncbi:411483", "b", 1.0, source_name="Faecalibacterium duncaniae")])
    rates = {"ncbi:411483": {"name": "Faecalibacterium prausnitzii A2-165", "rate": 0.7, "unit": "1/h",
                             "n": 3, "studies": ["S1"]}}
    assert matrix.for_nodes(net, rates)["ncbi:411483"]["name"] == "Faecalibacterium duncaniae"
    assert "Faecalibacterium duncaniae" in matrix.rates_csv(matrix.for_nodes(net, rates), net)


def test_the_network_says_which_media_its_arcs_came_from():
    """Karoline, 2026-10-04: a gLV simulation is of one environment, so the package says which media its
    numbers were measured in, and says it loudly when there is more than one."""
    one = _net([dict(_arc("a", "b", 1.5), medium="mMCB")])
    one.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert matrix.media(one) == ["mMCB"]

    mixed = _net([dict(_arc("a", "b", 1.5), medium="mMCB"),
                  dict(_arc("b", "a", -0.5, study_id="S2"), medium="Wilkins-Chalgren")])
    mixed.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert matrix.media(mixed) == ["mMCB", "Wilkins-Chalgren"]


def test_the_package_counts_the_arcs_a_glv_simulation_should_not_use():
    """Karoline, 2026-10-04: drop-out arcs may act through a third species, so a package that holds them
    says how many and which switch leaves them out."""
    net = _net([_arc("a", "b", 1.5, evidence="dropout"), _arc("b", "a", 1.0, evidence="biculture")])
    net.meta.update({"tool_version": "9.9.9", "absence": {"k": 1.0}})
    assert matrix.dropout_arcs(net) == 1
    direct = _net([_arc("a", "b", 1.5, evidence="biculture")])
    assert matrix.dropout_arcs(direct) == 0


def test_an_ill_conditioned_matrix_prints_no_equilibrium_and_says_why():
    """#142 item 9: the equilibrium was solved with no condition estimate, `steady.solve`'s only test
    being an absolute pivot below 1e-300, and printed to four significant digits with a categorical
    verdict. A near-singular block returned a number like 1e24 and had it reported as a steady state, and
    a change of 0.05 percent in one coefficient flipped the verdict. The condition number now decides
    whether the solution is printed at all, and is printed beside it when it is."""
    from grownet.steady import MAX_EQUILIBRIUM_CONDITION, condition_of
    nearly = [[-1.0e-10, -1.0e-10], [-1.0e-10, -1.0e-10 * (1 + 1e-12)]]
    assert condition_of(nearly) > MAX_EQUILIBRIUM_CONDITION
    assert condition_of([[-1.0e-10, 0.0], [0.0, -2.0e-10]]) < MAX_EQUILIBRIUM_CONDITION
    assert condition_of([[0.0, 0.0], [0.0, 0.0]]) == float("inf")


def test_the_readme_states_the_diagonal_the_derivation_actually_produced():
    """#155 item 11. The off-diagonal prose was branched by derivation and the diagonal's was not, so the
    default's README said `K_i` is "the plateau of the curves that reached stationary phase" when on that
    path `A_ii` is a parameter of the fit and `K = -r_i / A_ii` is derived from it, the opposite
    direction. The same package's `growth_rates.csv` said `capacity_source = "fitted from the monoculture
    time courses"` two files away.
    """
    from grownet import matrix

    integrated = " ".join(matrix.DIAGONAL_PROSE["integrated"])
    replicate = " ".join(matrix.DIAGONAL_PROSE["replicate"])
    assert "FITTED, not divided" in integrated
    assert "K_i = -r_i / A[i][i]" in integrated and "the plateau that fit implies" in integrated
    assert "capacity_source" in integrated          # where a reader checks it per organism
    # the comparison measures the plateau and divides, which is the other direction
    assert "the plateau of the curves that reached stationary phase" in replicate
    assert "FITTED, not divided" not in replicate
    # and each names the section that holds the diagonals its own path cannot fit
    assert "DIAGONALS THAT ARE NOT A FIT" in integrated
    assert "SELF-LIMITATION FITTED AT A CO-CULTURE PLATEAU" in replicate


def test_a_diagonal_that_is_not_a_fit_is_named_in_the_readme():
    """The integrated path's equivalent of SELF-LIMITATION FITTED AT A CO-CULTURE PLATEAU, which is
    populated from `edge.target_capacity` and so was unreachable there: an organism whose fit implies no
    plateau has a measured one put in its place, and appeared in no section at all (#155 item 11)."""
    from grownet import matrix

    got = {"matrices": [], "censored_cells": [], "left_out": [], "pairs_left_out": [],
           "across_units": [], "obligate_rows": [], "plateau_rows": [],
           "rate_methods": ["integrated:two_stage"], "lag_methods": [],
           "substituted_rows": [("Streptococcus thermophilus STpos",
                                 "-r/K at the measured plateau 0.105 g/L of 1 monoculture curve(s): "
                                 "the fit implies none")]}
    net = _net([_arc("a", "b", 1.5)])
    net.meta["settings"] = {"derivation": "integrated"}
    text = matrix.readme_from(got, net, {})
    heading = "\nDIAGONALS THAT ARE NOT A FIT\n"      # the section, not the prose that points at it
    assert heading in text
    assert "Streptococcus thermophilus STpos" in text and "the fit implies none" in text
    assert "its A[i][i] came out at or above zero" in text
    # and the section is absent when every diagonal is a fit, though the prose still names it
    plain = matrix.readme_from({**got, "substituted_rows": []}, net, {})
    assert heading not in plain and "DIAGONALS THAT ARE NOT A FIT below names" in plain


def test_a_genus_row_counts_replicates_and_keeps_where_its_capacity_came_from():
    """Round 3 of the review, on a live gLV package with --merge-genera: Agrobacterium has one strain, whose
    row says 3 replicates, 3 capacity curves and a capacity fitted from the monoculture time courses, and
    its genus row said 1, 1 and nothing. A genus of one strain is that strain; a genus of several sums the
    replicates and the curves its capacity rests on, and says where the capacity came from, or that the
    strains disagree."""
    net = _net([dict(_arc("agro", "blautia", 1.0), source_name="Agrobacterium", target_name="Blautia",
                     source_identity="genus", target_identity="genus")])
    fitted = "fitted from the monoculture time courses"
    agro = {"name": "Agrobacterium tumefaciens C58", "rate": 0.6, "unit": "1/h", "n": 1, "replicates": 3,
            "studies": ["S1"], "capacity": 2e8, "capacity_unit": "Cells/mL", "capacity_n": 1,
            "capacity_curves": 3, "capacity_source": fitted, "capacity_medium": "WC",
            "per_study": {"S1": 0.6}, "capacity_left_out": [["S1 rep 4", "no plateau"]]}
    b1 = {"name": "Blautia hydrogenotrophica", "rate": 0.3, "unit": "1/h", "n": 1, "replicates": 3,
          "studies": ["S1"], "capacity": 1e8, "capacity_unit": "Cells/mL", "capacity_n": 1,
          "capacity_curves": 3, "capacity_source": fitted, "capacity_medium": "WC"}
    b2 = {**b1, "name": "Blautia wexlerae", "replicates": 2, "capacity": 3e8, "capacity_curves": 2}
    aligned = matrix.for_nodes(net, {"ncbi:1": agro, "ncbi:2": b1, "ncbi:3": b2})

    one = aligned["agro"]
    assert {k: one[k] for k in ("replicates", "capacity_curves", "capacity_source", "capacity_medium")} == \
        {"replicates": 3, "capacity_curves": 3, "capacity_source": fitted, "capacity_medium": "WC"}
    assert one["name"] == "Agrobacterium" and one["merged_from"] == ["Agrobacterium tumefaciens C58"]
    # whole: what a merge of several empties is the strain's here
    assert one["per_study"] == {"S1": 0.6} and one["capacity_left_out"] == [["S1 rep 4", "no plateau"]]

    two = aligned["blautia"]
    assert two["capacity"] == 2e8                                   # median of 1e8 and 3e8
    assert two["replicates"] == 5 and two["capacity_curves"] == 5   # 3 + 2, not the 2 fitted rows
    assert two["capacity_source"] == fitted and two["capacity_medium"] == "WC"

    # strains that disagree say so, rather than one of them speaking for the genus
    b3 = {**b2, "capacity_source": "-r/K at the measured plateau", "capacity_medium": "mMCB"}
    mixed = matrix.for_nodes(net, {"ncbi:2": b1, "ncbi:3": b3})["blautia"]
    assert mixed["capacity_source"] == f"mixed: -r/K at the measured plateau; {fitted}"
    assert mixed["capacity_medium"] == "mixed: WC; mMCB"
    # and a strain with no plateau neither counts curves nor speaks for the capacity it is not in
    b4 = {**b2, "capacity": None, "capacity_curves": None, "capacity_source": "none: no plateau"}
    partial = matrix.for_nodes(net, {"ncbi:2": b1, "ncbi:3": b4})["blautia"]
    assert partial["capacity"] == 1e8 and partial["capacity_curves"] == 3
    assert partial["capacity_source"] == fitted and partial["replicates"] == 5
    # with no capacity at all there are no curves to count, and every strain's reason is kept
    b5 = {**b1, "capacity": None, "capacity_curves": 0, "capacity_source": "none: the fit implies none"}
    none = matrix.for_nodes(net, {"ncbi:2": b5, "ncbi:3": b4})["blautia"]
    assert none["capacity"] is None and none["capacity_curves"] is None
    assert none["capacity_source"] == "mixed: none: no plateau; none: the fit implies none"


def test_a_renamed_strain_s_rate_joins_its_genus_by_its_current_name():
    """Round 4 of the review (#24): the genus merge of the arcs used the current name and the rates the
    study's, so `merged_from` said F. prausnitzii beside arcs saying F. duncaniae, and a strain moved to
    another genus left that genus with no rate, hence no diagonal."""
    rate = {"name": "Faecalibacterium prausnitzii A2-165", "rate": 0.7, "unit": "1/h", "n": 3, "studies": ["S1"]}
    genus = dict(source_identity="genus", target_identity="genus")
    same = _net([dict(_arc("faecalibacterium", "blautia", 1.0), source_name="Faecalibacterium",
                      target_name="Blautia", **genus)])
    row = matrix.for_nodes(same, {"ncbi:411483": rate}, {411483: "Faecalibacterium duncaniae A2-165"})
    assert row["faecalibacterium"]["merged_from"] == ["Faecalibacterium duncaniae A2-165"]
    assert matrix.for_nodes(same, {"ncbi:411483": rate})["faecalibacterium"]["merged_from"] == [
        "Faecalibacterium prausnitzii A2-165"], "without current names, the study's (the control)"
    moved = _net([dict(_arc("ruminococcus", "blautia", 1.0), source_name="Ruminococcus", target_name="Blautia",
                       **genus)])
    assert "ruminococcus" not in matrix.for_nodes(moved, {"ncbi:411483": rate})
    got = matrix.for_nodes(moved, {"ncbi:411483": rate}, {411483: "Ruminococcus duncaniae A2-165"})
    assert got["ruminococcus"]["rate"] == 0.7
    # a rate keyed otherwise is not renamed, as a name-keyed node is not, even when its key is the id's digits
    kept = matrix.for_nodes(same, {"411483": rate}, {411483: "Faecalibacterium duncaniae A2-165"})
    assert kept["faecalibacterium"]["merged_from"] == ["Faecalibacterium prausnitzii A2-165"]


def test_a_genus_row_of_several_strains_says_what_a_strain_row_says_beside_its_numbers():
    """Round 4 of the review. A genus of several strains dropped `n_label`, so the report called the summed
    fitted rows "monoculture replicate(s)" and the capacity rows "curve(s)" where growth_rates.csv said 5;
    and it dropped the lag's method, the plateau's fall and its media, which a genus of one strain kept."""
    from grownet.model import InteractionNetwork
    from grownet.report import report_text
    net = _net([dict(_arc("blautia", "roseburia", 1.0), source_name="Blautia", target_name="Roseburia",
                     source_identity="genus", target_identity="genus")])
    strain = {"rate": 0.3, "unit": "1/h", "n": 1, "n_label": "fitted row(s)", "studies": ["S1"],
              "lag": 0.5, "lag_method": "baranyi", "capacity": 1e8, "capacity_unit": "Cells/mL", "capacity_n": 1,
              "capacity_curves": 3, "replicates": 3, "capacity_fall": 2.0, "capacity_media": ["WC"],
              "capacity_medium": "WC", "capacity_source": "fitted from the monoculture time courses"}
    rates = {"ncbi:1": {**strain, "name": "Blautia hydrogenotrophica"},
             "ncbi:2": {**strain, "name": "Blautia wexlerae", "capacity_curves": 2, "replicates": 2,
                        "capacity_fall": 4.0}}
    row = matrix.for_nodes(net, rates)["blautia"]
    assert row["n_label"] == "fitted row(s)" and row["lag_method"] == "baranyi"
    assert row["capacity_fall"] == 3.0 and row["capacity_media"] == ["WC"]       # median of 2 and 4
    csv_row = dict(zip(*[line.split(",") for line in matrix.rates_csv({"blautia": row}).splitlines()[:2]],
                       strict=True))
    assert csv_row["lag_method"] == "baranyi" and csv_row["capacity_fall_from_peak"] == "3"
    shown = InteractionNetwork()
    shown.meta["growth_rates"] = {"rule": "r", "organisms": {"blautia": row}}
    text = report_text({"network": shown, "resolved": [], "unresolved": [], "studies": [], "errors": [],
                        "skipped": [], "entries": []})
    assert "median of 2 fitted row(s)" in text and "monoculture replicate(s)" not in text, text
    assert "from 2 row(s)" in text, text
    # a strain with no capacity and no medium neither makes the medium "mixed" nor adds a fall
    bare = {**strain, "name": "Blautia obeum", "capacity": None, "capacity_medium": "", "capacity_media": [],
            "capacity_fall": 9.0, "capacity_curves": None}       # whatever it carries, it is not behind the capacity
    partial = matrix.for_nodes(net, {"ncbi:1": rates["ncbi:1"], "ncbi:3": bare})["blautia"]
    assert partial["capacity_medium"] == "WC" and partial["capacity_fall"] == 2.0
