"""The diagonal from a co-culture plateau, and the media each matrix came from (#124 items 2 and 5).

Karoline, 2026-10-06: "complete #124". Item 2 asked whether a carrying capacity can come from somewhere
other than that study's own monoculture; item 5 asked whether to write one matrix per medium.

What this implements, with the reasons in the issue comment: the plateau balance already used for an
organism that grows only with a partner (#123) works for any organism, so an organism with a rate but no
certified monoculture plateau is fitted at its plateau beside its partners instead of being dropped; and
media stay together in one matrix per unit, with each matrix naming the media its own arcs came from,
since partitioning by medium would fragment the corpus into singletons while the second box already holds
a search to one environment.
"""
import pytest

from grownet import matrix
from grownet.mgrowthdb import records_to_network

METRIC = "growth_rate:easylinear:5"


def _arc(source, target, with_rate, without_rate, x_j=2.0e8, capacity=None, medium="WC", unit="Cells/mL"):
    return {"source": source, "target": target, "source_name": source.upper(),
            "target_name": target.upper(), "effect": "facilitation", "strength": 1.0, "status": "present",
            "outcome": "quantified", "study_id": "S1", "metric": METRIC, "evidence": "biculture",
            "medium": medium, "partner_abundance": x_j, "partner_abundance_unit": unit,
            "partner_abundance_n": 3, "metric_with": with_rate, "metric_without": without_rate,
            "target_capacity": capacity, "target_capacity_unit": unit if capacity else "",
            "target_capacity_n": 3 if capacity else 0}


def _rate(name, rate, capacity, unit="Cells/mL"):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"], "method": METRIC,
            "lag": 0.0, "lag_method": "baranyi", "capacity": capacity,
            "capacity_unit": unit if capacity else "", "capacity_n": 3 if capacity else 0}


def _cell(block, affected, actor):
    i, j = block["organisms"].index(affected), block["organisms"].index(actor)
    return block["matrix"][i][j]


def test_an_organism_with_no_monoculture_plateau_is_fitted_at_its_co_culture_plateau():
    """SMGDB00000004's B. hydrogenotrophica reaches no certified plateau alone, so #119 dropped it from
    the matrix. Its plateau beside its partner fits the same balance: with r_A = 0.4 /h, A_AB = (0.8 -
    0.4) / 2e8 = +2e-9, B at its own co-culture plateau of 4e8 and A at 3e8,
    A_AA = -(0.4 + 2e-9 * 4e8) / 3e8 = -(0.4 + 0.8) / 3e8 = -4e-9."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8)]
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(records_to_network(arcs), rates)
    (block,) = got["matrices"]
    assert block["organisms"] == ["A", "B"]
    assert _cell(block, "A", "B") == pytest.approx(2.0e-9)
    assert _cell(block, "A", "A") == pytest.approx(-4.0e-9)
    assert got["plateau_rows"] == [("A", "its co-culture plateau")]
    assert got["left_out"] == []
    text = matrix.readme_from(got, records_to_network(arcs), rates)
    assert "co-culture plateau" in text and "A" in text


def test_a_monoculture_plateau_is_still_preferred_when_there_is_one():
    """Nothing changes for an organism that settled alone: -r/K from its own monoculture."""
    arcs = [_arc("b", "a", 0.8, 0.4, x_j=2.0e8, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8)]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(records_to_network(arcs), rates)
    (block,) = got["matrices"]
    assert _cell(block, "A", "A") == pytest.approx(-4.0e-10)      # -0.4 / 1e9
    assert got["plateau_rows"] == []


def test_a_plateau_fit_that_comes_out_positive_is_named_not_published():
    """A self-limitation at or above zero is not a limitation. It happens when the partners suppress the
    organism harder than its own rate at the plateau: A_AB = (0.05 - 0.4) / 2e8 = -1.75e-9, so with B at
    4e8 the balance gives -(0.4 - 0.7) / 3e8 = +1e-9, which is not a limitation, and A is named."""
    arcs = [_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),   # a strong inhibition
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8)]
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(records_to_network(arcs), rates)
    assert got["matrices"][0]["organisms"] == ["B"]
    assert any(name == "A" and "above zero" in why for name, why in got["left_out"])


def test_each_matrix_names_the_media_its_own_arcs_came_from():
    """Item 5: media stay in one matrix per unit, and the README says which media each matrix holds, so a
    reader sees the mixture without the package fragmenting into one matrix per medium."""
    arcs = [_arc("b", "a", 0.8, 0.4, medium="WC"),
            _arc("d", "c", 0.8, 0.4, medium="mMCB", unit="CFUs/mL")]
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8),
             "c": _rate("C", 0.5, 1.0e8, "CFUs/mL"), "d": _rate("D", 0.5, 2.0e8, "CFUs/mL")}
    got = matrix.coefficients(records_to_network(arcs), rates)
    by_unit = {b["abundance_unit"]: b for b in got["matrices"]}
    assert by_unit["Cells/mL"]["media"] == ["WC"]
    assert by_unit["CFUs/mL"]["media"] == ["mMCB"]
    text = matrix.readme_from(got, records_to_network(arcs), rates)
    assert "in WC" in text and "in mMCB" in text


def test_the_fitted_diagonal_does_not_depend_on_the_order_the_arcs_arrive_in():
    """Found by Craig's agent on #128, 2026-10-06: the balance summed every partner's effect while
    taking the organism's own plateau from whichever arc came first, so an organism obligate on two
    partners got a diagonal that moved by the ratio of its two plateaus when the arcs were reordered.

    A grows only with B and only with C. Its own plateau is 1e8 beside B and 5e8 beside C, and each
    co-culture gives its own equation: with r_A = 0 and A_AB = 0.4 / 2e8 = +2e-9, beside B the balance is
    -(2e-9 x 2e8) / 1e8 = -4e-9; with A_AC = 0.5 / 1e9 = +5e-10, beside C it is -(5e-10 x 1e9) / 5e8 =
    -1e-9. The median of the two is -2.5e-9 whichever order they arrive in.
    """
    beside_b = _arc("b", "a", 0.4, 0.0, x_j=2.0e8, capacity=1.0e8)
    back_from_b = _arc("a", "b", 0.3, 0.2, x_j=1.0e8, capacity=2.0e8)
    beside_c = _arc("c", "a", 0.5, 0.0, x_j=1.0e9, capacity=5.0e8)
    back_from_c = _arc("a", "c", 0.3, 0.2, x_j=5.0e8, capacity=1.0e9)
    rates = {"b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.2, 5.0e8)}

    one = matrix.coefficients(records_to_network([beside_b, back_from_b, beside_c, back_from_c]), rates)
    other = matrix.coefficients(records_to_network([beside_c, back_from_c, beside_b, back_from_b]), rates)
    first, second = one["matrices"][0], other["matrices"][0]
    assert _cell(first, "A", "A") == pytest.approx(-2.5e-9, rel=1e-9)
    assert _cell(first, "A", "A") == _cell(second, "A", "A")


def test_an_effect_on_an_organism_dropped_as_unusable_is_in_no_matrix_not_left_at_0():
    """Round 17 of the review: the routing ran before the organisms whose plateau balance gave no usable
    limitation left their matrix, so the README said A is in no matrix and listed C on A as left at 0. And
    the package's sentence about sign speaks of the pairs in a matrix."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    arcs = [_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8),
            _arc("c", "a", 0.6, 0.4, x_j=None)]
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    net = records_to_network(arcs)
    got = matrix.coefficients(net, rates)
    assert "A" in [name for name, _ in got["left_out"]], got["left_out"]
    assert not [row for row in got["pairs_left_out"] if "A" in row[:2]], got["pairs_left_out"]
    assert [row[:2] for row in got["across_units"] if row[:2] == ("A", "C")] == [("A", "C")], got["across_units"]
    # and A's fitted effects, which left its matrix with it, are named as in no matrix too
    assert {("A", "B"), ("B", "A")} <= {row[:2] for row in got["across_units"]}, got["across_units"]
    assert "No pair in a matrix has arcs of opposite sign." in matrix.readme_from(got, net, rates)


def test_a_sign_conflict_of_an_organism_dropped_as_unusable_is_named_outside_its_matrix():
    """Round 18 of the review: the matrices' sign conflicts were worked out before the unusable organisms
    left them, so C on A, whose two arcs disagree (an inhibition, strength -1, and a facilitation, +0.58),
    was listed as "left at 0" in a matrix that A, dropped for an unusable self-limitation, is no longer in.
    It is now named with A's other effects as in no matrix, saying its arcs disagree, and the README no
    longer says that no pair disagreed beside it without saying it means the pairs in a matrix."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    arcs = [_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),
            _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8),
            {**_arc("c", "a", 0.2, 0.4, x_j=3.0e8), "strength": -1.0},
            {**_arc("c", "a", 0.6, 0.4, x_j=3.0e8), "strength": 0.58, "condition": "x"},
            _arc("a", "c", 0.3, 0.2, x_j=3.0e8), _arc("c", "b", 0.3, 0.2, x_j=3.0e8)]
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    net = records_to_network(arcs)
    got = matrix.coefficients(net, rates)
    assert "A" in [name for name, _ in got["left_out"]], got["left_out"]
    assert [block["conflicts"] for block in got["matrices"]] == [[]], got["matrices"]
    why = dict(((a, b), w) for a, b, w in got["across_units"])[("A", "C")]
    assert why == ("its arcs disagree in sign, so they are not merged; A could not be fitted, so this effect is "
                   "in no matrix"), why
    readme = matrix.readme_from(got, net, rates)
    assert "left at 0 rather than averaged" not in readme
    assert "No pair in a matrix has arcs of opposite sign." in readme


def _obligate_unconverted(source, target):
    # an obligate arc with no partner abundance, so it gives no number, only its direction (facilitation)
    return {**_arc(source, target, 0.3, 0.0, x_j=None), "strength": None, "outcome": "obligate",
            "effect": "facilitation"}


def test_a_sign_conflict_between_organisms_in_no_common_matrix_is_named():
    """Round 18 of the review: B on C has an inhibition (strength -1) and an obligate arc (a facilitation),
    so its arcs disagree in sign, which the plain adjacency matrix names. When C has no rate (in no matrix),
    or is counted in CFUs/mL while B is in Cells/mL (in neither matrix), the gLV package named the pair
    nowhere, since a conflict was only named inside a matrix holding both. It is now named with the effects
    in no matrix, saying the arcs disagree."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    base = [_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.5, 0.4)]
    inhibition = {**_arc("b", "c", 0.2, 0.4), "strength": -1.0, "effect": "inhibition"}
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)}
    net = records_to_network(base + [inhibition, _obligate_unconverted("b", "c")])
    got = matrix.coefficients(net, rates)
    assert matrix.rows(net)[2] == [("C", "B")]
    assert got["across_units"] == [("C", "B", "its arcs disagree in sign, so they are not merged; C could not be "
                                              "fitted, so this effect is in no matrix")]
    # across units: C and D in CFUs/mL
    net = records_to_network(base + [inhibition, _obligate_unconverted("b", "c"),
                                     _arc("d", "c", 0.8, 0.4, unit="CFUs/mL")])
    got = matrix.coefficients(net, {**rates, "c": _rate("C", 0.5, 1e8, "CFUs/mL"),
                                    "d": _rate("D", 0.5, 2e8, "CFUs/mL")})
    assert got["across_units"] == [("C", "B", "its arcs disagree in sign, so they are not merged; B is counted in "
                                              "Cells/mL and C in CFUs/mL, so this effect is in neither matrix")]
    assert [block["conflicts"] for block in got["matrices"]] == [[], []]


def test_an_effect_with_several_reasons_is_one_row_and_counted_once():
    """Round 18 of the review: C on A, with C counted in CFUs/mL and A in Cells/mL, has two arcs whose
    partner C was counted in CFUs/mL and one in Cells/mL. It got two rows in across_units (one for being
    between matrices, one for the arc in the other unit, which also spoke of "this cell" where none
    exists), and the package said 2 effects between organisms counted differently were measured for one.
    It is one row now, and 1 effect."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    arcs = [_arc("b", "a", 0.8, 0.4), _arc("d", "c", 0.8, 0.4, unit="CFUs/mL"),
            _arc("c", "a", 0.5, 0.4, unit="CFUs/mL"),
            {**_arc("c", "a", 0.5, 0.4), "condition": "x"},
            {**_arc("c", "a", 0.55, 0.4, unit="CFUs/mL"), "condition": "y"}]
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8),
             "c": _rate("C", 0.5, 1e8, "CFUs/mL"), "d": _rate("D", 0.5, 2e8, "CFUs/mL")}
    net = records_to_network(arcs)
    got = matrix.coefficients(net, rates)
    ((affected, actor, why),) = got["across_units"]
    assert (affected, actor) == ("A", "C")
    assert why == ("C is counted in CFUs/mL and A in Cells/mL, so this effect is in neither matrix; 1 arc(s) of "
                   "this pair measure the actor in Cells/mL and the rest in CFUs/mL; abundances are never "
                   "converted, so they are left out of this pair's median")
    assert "1 effect(s) between organisms counted differently were measured" in \
        matrix.glv_payload(net, rates)["caveats"]["units"]


def test_arcs_beside_a_cell_of_0_are_not_said_to_be_beside_a_median():
    """Round 18 of the review: "these arcs are not in their pair's cell, which is the median of the pair's
    other arcs" was said of arcs whose pair's cell is 0. (a) B on A has two arcs with B counted in CFUs/mL
    and one in Cells/mL, the matrix's unit; the CFUs/mL arcs are the majority, so the cell is left at 0 for
    their unit and the Cells/mL arc is not beside any median. (b) B on A's Cells/mL arcs disagree in sign
    (+0.58 and a washout inhibition) and a third is in CFUs/mL, so the cell is a conflict left at 0. Each
    pair is one row of the effects left at 0, with all its reasons."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)}
    net = records_to_network([dict(_arc("b", "a", 0.8, 0.4, unit=u), study_id=s)
                              for s, u in (("S1", "CFUs/mL"), ("S2", "CFUs/mL"), ("S3", "Cells/mL"))])
    got = matrix.coefficients(net, rates)
    assert got["arcs_left_out"] == []
    ((affected, actor, why),) = got["pairs_left_out"]
    assert (affected, actor) == ("A", "B")
    assert why == ("B's abundance beside A is in CFUs/mL, and this matrix is in Cells/mL; left out rather than "
                   "converted; 1 arc(s) of this pair measure the actor in Cells/mL and the rest in CFUs/mL; "
                   "abundances are never converted, so they are left out of this pair's median")
    net = records_to_network([dict(_arc("b", "a", 0.6, 0.4), study_id="S1"),
                              dict(_arc("b", "a", -0.1, 0.4), strength=None, effect="inhibition", study_id="S2"),
                              dict(_arc("b", "a", 0.7, 0.4, unit="CFUs/mL"), study_id="S3")])
    got = matrix.coefficients(net, rates)
    assert got["arcs_left_out"] == [] and got["matrices"][0]["conflicts"] == [("A", "B")]
    ((_, _, why),) = got["pairs_left_out"]
    assert why.endswith("; its other arcs disagree in sign, so its cell is left at 0"), why


def test_an_arc_with_no_number_beside_one_with_a_number_is_named():
    """Round 18 of the review: B on A has a converted arc (with 0.6, without 0.4, B at 2e8: (0.6 - 0.4) /
    2e8 = 1e-9) and an arc with no abundance for B, which gives no number. The cell is the first arc's
    1e-9, and the second was left out of it without a word; it is now listed beside the cell."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([dict(_arc("b", "a", 0.6, 0.4), study_id="S1"),
                              dict(_arc("b", "a", 0.8, 0.4, x_j=None), study_id="S2")])
    got = matrix.coefficients(net, {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)})
    assert _cell(got["matrices"][0], "A", "B") == pytest.approx(1e-9)
    assert got["arcs_left_out"] == [("A", "B", "1 arc(s) of this pair give no number (no abundance for B over A's "
                                               "growth window), so they are left out of this pair's median")]


def test_a_matrix_counts_only_the_cells_and_media_it_still_holds():
    """Round 18 of the review: A's self-limitation comes out unusable, so A leaves the matrix with its
    effects (B on A, measured in WC and in M2, and A on B). The README still said the B and C matrix held
    3 fitted cells, one pooling WC and M2, measured in WC and M2, and it holds one, C on B, measured in M3
    alone, and no cell of it pools media."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),
                              {**_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8, medium="M2"),
                               "study_id": "S2"},
                              _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8),
                              _arc("c", "a", 0.6, 0.4), _arc("c", "b", 0.6, 0.4, medium="M3")])
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    assert block["organisms"] == ["B", "C"] and block["cells"] == 1 and block["pooled_media"] == []
    assert block["media"] == ["M3"]
    assert "2 organism(s), 1 fitted cell(s), every cell in 1/(h x Cells/mL), measured in M3\n" in \
        matrix.readme_from(got, net, rates)
    assert matrix.glv_payload(net, rates)["matrices"][0]["pooled_media"] == []


def test_an_abolished_arc_with_no_number_still_counts_in_the_sign_check():
    """Round 18 of the review: the sign check counts an arc's direction whether or not it converts, and a
    test held that only for an obligate arc. B on A has a facilitation (with 0.6, without 0.4: (0.6 - 0.4) /
    2e8 = 1e-9) and an abolished arc (A did not grow with B) with no abundance for B, so it gives no number
    but says B inhibits A. The pair is a sign conflict, left at 0, not the facilitation's 1e-9."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    abolished = {**_arc("b", "a", 0.0, 0.4, x_j=None), "strength": None, "outcome": "abolished",
                 "effect": "inhibition", "study_id": "S2"}
    net = records_to_network([_arc("b", "a", 0.6, 0.4), abolished])
    got = matrix.coefficients(net, {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)})
    (block,) = got["matrices"]
    assert block["conflicts"] == [("A", "B")] and _cell(block, "A", "B") == 0.0


def test_an_effect_in_no_matrix_for_want_of_a_coefficient_is_not_one_between_units():
    """Round 18 of the review: a package of two matrices (A and B in Cells/mL, C and E in OD) whose only
    effect outside them is D on A, D having no rate, measured nothing between organisms counted
    differently, and says so; a mutant counting every row of across_units said 1 had been."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([_arc("b", "a", 0.6, 0.4), _arc("e", "c", 0.8, 0.4, unit="OD"),
                              _arc("d", "a", 0.6, 0.4)])
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8),
             "c": _rate("C", 0.5, 0.8, "OD"), "e": _rate("E", 0.5, 0.6, "OD")}
    got = matrix.coefficients(net, rates)
    assert len(got["matrices"]) == 2
    assert got["across_units"] == [("A", "D", "D could not be fitted, so this effect is in no matrix")]
    assert "no effect between organisms counted differently was measured" in \
        matrix.glv_payload(net, rates)["caveats"]["units"]


def test_a_pair_with_arcs_in_two_other_units_is_one_row():
    """Round 18 of the review: B on A has three arcs with B counted in Cells/mL, the matrix's unit, which
    make the cell, two in CFUs/mL and one in OD. The arcs in each other unit were a row of their own, so R
    said 2 pairs had arcs left out of their cell where one has. One row now, naming both units."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([dict(_arc("b", "a", 0.8, 0.4, unit=u), study_id=s) for s, u in
                              (("S1", "Cells/mL"), ("S2", "Cells/mL"), ("S3", "Cells/mL"), ("S4", "CFUs/mL"),
                               ("S5", "CFUs/mL"), ("S6", "OD"))])
    got = matrix.coefficients(net, {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)})
    ((affected, actor, why),) = got["arcs_left_out"]
    assert (affected, actor) == ("A", "B")
    assert "2 arc(s) of this pair measure the actor in CFUs/mL" in why
    assert "1 arc(s) of this pair measure the actor in OD" in why
