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
                   "converted, so they are left out")
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
    assert why == ("B's abundance beside A is in CFUs/mL, not in Cells/mL, the unit of the matrix they were placed "
                   "in; left out rather than converted; 1 arc(s) of this pair measure the actor in Cells/mL and "
                   "the rest in CFUs/mL; abundances are never converted, so they are left out")
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
                                               "growth window), so they are left out")]
    # two such arcs are counted as two, and their one reason is said once (round 19)
    net = records_to_network([dict(_arc("b", "a", 0.6, 0.4), study_id="S1"),
                              dict(_arc("b", "a", 0.8, 0.4, x_j=None), study_id="S2"),
                              dict(_arc("b", "a", 0.7, 0.4, x_j=None), study_id="S3")])
    got = matrix.coefficients(net, {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)})
    assert got["arcs_left_out"] == [("A", "B", "2 arc(s) of this pair give no number (no abundance for B over A's "
                                               "growth window), so they are left out")]


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
    assert block["media"] == ["M3"] and block["arc_media"] == ["M3"]
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


def test_an_effect_of_an_organism_that_left_is_not_also_left_at_0():
    """Round 19 of the review: C on A, with C's abundance in CFUs/mL beside a Cells/mL matrix, was listed
    as left at 0 in that matrix before A left it for an unusable self-limitation, and then also as in no
    matrix. It is one row now, in no matrix, with both reasons."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),
                              _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8),
                              _arc("a", "c", 0.3, 0.2, x_j=3.0e8), _arc("c", "b", 0.3, 0.2, x_j=3.0e8),
                              _arc("c", "a", 0.5, 0.4, x_j=3.0e8, unit="CFUs/mL")])
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    got = matrix.coefficients(net, rates)
    assert "A" in [name for name, _ in got["left_out"]]
    assert got["pairs_left_out"] == []
    assert dict(((a, b), w) for a, b, w in got["across_units"])[("A", "C")] == (
        "A could not be fitted, so this effect is in no matrix; C's abundance beside A is in CFUs/mL, not in "
        "Cells/mL, the unit of the matrix they were placed in; left out rather than converted")


def test_a_cell_pools_only_the_media_of_the_arcs_in_it():
    """Round 19 of the review: B on A has a converted arc in WC and an arc in LB with no abundance for B, so
    the cell is the WC arc's alone. The README said the cell pooled WC and LB, and that every cell of the
    matrix was measured in WC and LB."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    rates = {"a": _rate("A", 0.4, 6e8), "b": _rate("B", 0.2, 5.0e8)}
    net = records_to_network([_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.6, 0.4),
                              {**_arc("b", "a", 0.7, 0.4, medium="LB", x_j=None), "condition": "x"}])
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    assert block["media"] == ["WC"] and block["pooled_media"] == []
    readme = matrix.readme_from(got, net, rates)
    assert "B on A: WC, LB" not in readme and "measured in WC\n" in readme
    # nor an arc in another unit: two WC arcs with B in Cells/mL make the cell, the LB one in CFUs/mL not
    net = records_to_network([_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.6, 0.4),
                              {**_arc("b", "a", 0.6, 0.4), "condition": "y"},
                              {**_arc("b", "a", 0.7, 0.4, medium="LB", unit="CFUs/mL"), "condition": "x"}])
    (block,) = matrix.coefficients(net, rates)["matrices"]
    assert block["media"] == ["WC"] and block["pooled_media"] == []
    # control: both arcs converted, so the cell does pool the two media
    net = records_to_network([_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.6, 0.4),
                              {**_arc("b", "a", 0.7, 0.4, medium="LB"), "condition": "x"}])
    assert matrix.coefficients(net, rates)["matrices"][0]["pooled_media"] == [("A", "B", "WC, LB")]


def test_a_cell_left_at_0_is_not_described_as_a_cell():
    """Round 19 of the review: C on A is an obligate arc (C grows A from 0, censored) with C's abundance in
    CFUs/mL beside a Cells/mL matrix, so its cell is left at 0; and B on A, from an arc saved before the
    two rates were recorded, is in neither matrix, B being counted in CFUs/mL. The package still listed C
    on A as a cell from a comparison where one side did not grow, and B on A as a cell taken from the log2
    ratio."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    obligate = {**_arc("c", "a", 0.8, 0.0, unit="CFUs/mL"), "strength": None, "outcome": "obligate"}
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8), "c": _rate("C", 0.5, 1e8)}
    net = records_to_network([_arc("a", "b", 0.3, 0.2), obligate])
    got = matrix.coefficients(net, rates)
    assert _cell(got["matrices"][0], "A", "C") == 0.0 and got["censored_cells"] == []
    # control: in the matrix's unit the obligate cell is held, and listed
    net = records_to_network([_arc("a", "b", 0.3, 0.2), {**obligate, "partner_abundance_unit": "Cells/mL"}])
    assert matrix.coefficients(net, rates)["censored_cells"] == [("A", "C")]
    old = {**_arc("b", "a", 0.8, 0.4, unit="CFUs/mL"), "metric_with": None, "metric_without": None}
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8, "CFUs/mL"), "c": _rate("C", 0.2, 5e8, "CFUs/mL")}
    net = records_to_network([_arc("a", "b", 0.3, 0.2), old, _arc("c", "b", 0.3, 0.2, unit="CFUs/mL")])
    got = matrix.coefficients(net, rates)
    assert ("A", "B") in [row[:2] for row in got["across_units"]] and got["from_the_ratio"] == []
    # the cells the matrices do hold all come from two rates (round 20)
    assert got["from_absolute_rates"] is True
    assert "CELLS TAKEN FROM THE LOG2 RATIO" not in matrix.readme_from(got, net, rates)
    # a merged arc whose cell is left at 0 for its unit is not a cell from merged arcs (round 20)
    merged = {**_arc("a", "b", 0.3, 0.2, unit="CFUs/mL"), "strength": -0.5, "effect": "inhibition", "sd": 0.1,
              "merged_arcs": 2, "metric_with": None, "metric_without": None}
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.4, 1e9)}
    got = matrix.coefficients(records_to_network([merged]), rates)
    assert got["pairs_left_out"] and got["from_merged_ratio"] == []
    got = matrix.coefficients(records_to_network([{**merged, "partner_abundance_unit": "Cells/mL"}]), rates)
    assert got["from_merged_ratio"] == [("B", "A")]


def test_a_cell_is_labeled_only_by_the_arcs_in_it():
    """Round 20 of the review: B on A has two rate arcs with B counted in Cells/mL, which make the cell
    ((0.6 - 0.4) / 2e8 = 1e-9 and (0.65 - 0.4) / 2e8 = 1.25e-9, median 1.125e-9), and one arc with B in
    CFUs/mL that is not in it. When that arc was obligate the cell was listed as one from a comparison where
    one side did not grow, and when it was saved before the rates were recorded, as one taken from the
    log2 ratio."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8)}
    two = [{**_arc("b", "a", 0.6, 0.4), "condition": "x"}, {**_arc("b", "a", 0.65, 0.4), "condition": "y"}]
    obligate = {**_arc("b", "a", 0.8, 0.0, unit="CFUs/mL"), "strength": None, "outcome": "obligate",
                "condition": "o"}
    old = {**_arc("b", "a", 0.8, 0.4, unit="CFUs/mL"), "metric_with": None, "metric_without": None,
           "condition": "r"}
    merged = {**_arc("b", "a", 0.8, 0.4, unit="CFUs/mL"), "merged_arcs": 2, "metric_with": None,
              "metric_without": None, "strength": 1.0, "condition": "m"}
    for other in (obligate, old, merged):
        got = matrix.coefficients(records_to_network([_arc("a", "b", 0.3, 0.2), *two, other]), rates)
        assert _cell(got["matrices"][0], "A", "B") == pytest.approx(1.125e-9)
        assert got["censored_cells"] == [] and got["from_the_ratio"] == [] and got["from_merged_ratio"] == []
        assert got["from_absolute_rates"] is True
    # whichever comes first: an obligate or old arc before a rate arc of the same unit still labels the
    # cell (round 21: a last-arc-wins label passed every test)
    for first, listed in ((dict(obligate, partner_abundance_unit="Cells/mL"), "censored_cells"),
                          (dict(old, partner_abundance_unit="Cells/mL"), "from_the_ratio")):
        got = matrix.coefficients(records_to_network([_arc("a", "b", 0.3, 0.2), first, *two]), rates)
        assert got[listed] == [("A", "B")], (listed, got[listed])
    # control: in the cell's own unit each is in it, and labels it
    got = matrix.coefficients(records_to_network([_arc("a", "b", 0.3, 0.2),
                                                  {**obligate, "partner_abundance_unit": "Cells/mL"}]), rates)
    assert got["censored_cells"] == [("A", "B")]


def test_the_media_warning_is_about_the_cells_the_matrices_hold():
    """Round 19 of the review: the live genus package's only matrix was measured in WC, and its README and R
    warned that "these arcs come from 5 media", the other four from arcs between organisms in no matrix.
    Here A and B are in a matrix measured in WC, and C, with no rate, acts on A in LB: the package says
    every cell was measured in WC and names LB as the medium of arcs in no cell."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    rates = {"a": _rate("A", 0.4, 6e8), "b": _rate("B", 0.2, 5.0e8)}
    net = records_to_network([_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.6, 0.4),
                              _arc("c", "a", 0.6, 0.4, medium="LB")])
    got = matrix.coefficients(net, rates)
    assert got["cell_media"] == ["WC"]
    readme = matrix.readme_from(got, net, rates)
    assert "Every effect between two organisms in the matrices was measured in one medium: WC." in readme
    assert "The network's other arcs, in no cell, come from LB." in readme
    assert "THESE ARCS COME FROM" not in readme
    caveats = matrix.glv_payload(net, rates)["caveats"]
    assert caveats["cell_media"] == ["WC"] and caveats["media"] == ["WC", "LB"]
    # control: a cell that pools WC and LB is warned about, and C on A, in M3, named apart (round 20)
    net = records_to_network([_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.6, 0.4),
                              {**_arc("b", "a", 0.7, 0.4, medium="LB"), "condition": "x"},
                              _arc("c", "a", 0.6, 0.4, medium="M3")])
    got = matrix.coefficients(net, rates)
    readme = matrix.readme_from(got, net, rates)
    assert "A MATRIX'S EFFECTS COME FROM MORE THAN ONE MEDIUM" in readme and "Cells/mL matrix: WC, LB" in readme
    assert "The network's other arcs, in no cell, come from M3." in readme


def test_a_matrix_left_with_no_cell_names_no_media():
    """Round 19 of the review: A leaves the B and C matrix for an unusable self-limitation, taking B on A (in
    WC and M2) and A on B with it, and no arc joins B and C. The matrix fell back on the network's media and
    said it was measured in WC and M2, the media of the arcs that left with A. It holds no cell, so it names
    no medium."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8),
                              {**_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8, medium="M2"),
                               "study_id": "S2"},
                              _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8), _arc("c", "a", 0.6, 0.4)])
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    assert block["organisms"] == ["B", "C"] and block["cells"] == 0 and block["media"] == []
    readme = matrix.readme_from(got, net, rates)
    assert "2 organism(s), 0 fitted cell(s), every cell in 1/(h x Cells/mL)\n" in readme
    # and the package says no effect is in the matrices, rather than warning about the media of arcs in
    # none; a steady state is still matched against the network's media, no arc joining B and C (round 20)
    assert ("No effect between two organisms is in the matrices; the network's arcs, in no cell, come from "
            "WC, M2.") in readme and "THESE ARCS COME FROM" not in readme
    assert block["arc_media"] == ["WC", "M2"]


def test_cells_whose_arcs_record_no_medium_are_not_said_to_be_no_cell():
    """Round 21 of the review: A and B hold two cells from arcs that record no medium, and C on A is in LB
    with C counted in CFUs/mL. The README said no effect between two organisms is in the matrices."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8), "c": _rate("C", 0.2, 5e8)}
    net = records_to_network([{**_arc("a", "b", 0.3, 0.2), "medium": None},
                              {**_arc("b", "a", 0.6, 0.4), "medium": None},
                              _arc("c", "a", 0.6, 0.4, medium="LB", unit="CFUs/mL")])
    got = matrix.coefficients(net, rates)
    assert sum(block["cells"] for block in got["matrices"]) == 2 and got["cell_media"] == []
    readme = matrix.readme_from(got, net, rates)
    assert "No effect between two organisms is in the matrices" not in readme
    assert "The effects between organisms in the matrices record no medium." in readme
    assert "The network's other arcs, in no cell, come from LB." in readme


def test_two_matrices_of_one_medium_each_are_not_a_mix_of_environments():
    """Round 21 of the review: the live genus package held a Cells/mL matrix measured in WC and a CFUs/mL
    one measured in MM, and warned that its effects come from 2 media and to select one, while each
    matrix, which is what a simulation takes, is of one medium. Here A and B are in WC (Cells/mL) and C and
    D in LB (CFUs/mL)."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8),
             "c": _rate("C", 0.5, 1e8, "CFUs/mL"), "d": _rate("D", 0.5, 2e8, "CFUs/mL")}
    net = records_to_network([_arc("b", "a", 0.6, 0.4), _arc("d", "c", 0.8, 0.4, medium="LB", unit="CFUs/mL")])
    got = matrix.coefficients(net, rates)
    assert got["cell_media"] == ["WC", "LB"]
    readme = matrix.readme_from(got, net, rates)
    assert "Each matrix's effects between organisms were measured in one medium" in readme
    assert "      Cells/mL: WC\n" in readme and "      CFUs/mL: LB\n" in readme
    assert "MORE THAN ONE MEDIUM" not in readme
    # control: a second WC arc on C in CFUs/mL makes that matrix pool two media, which is warned about
    net = records_to_network([_arc("b", "a", 0.6, 0.4), _arc("d", "c", 0.8, 0.4, medium="LB", unit="CFUs/mL"),
                              {**_arc("d", "c", 0.7, 0.4, unit="CFUs/mL"), "condition": "x"}])
    readme = matrix.readme_from(matrix.coefficients(net, rates), net, rates)
    assert "A MATRIX'S EFFECTS COME FROM MORE THAN ONE MEDIUM" in readme
    # every matrix is named with its media, the one of a single medium too (round 22)
    assert "      CFUs/mL matrix: LB, WC\n" in readme and "      Cells/mL matrix: WC\n" in readme
    # a third matrix, in OD, whose one cell records no medium, is listed as such, not left out (round 22)
    rates = {**rates, "e": _rate("E", 0.5, 0.8, "OD"), "f": _rate("F", 0.5, 0.6, "OD")}
    net = records_to_network([_arc("b", "a", 0.6, 0.4), _arc("d", "c", 0.8, 0.4, medium="LB", unit="CFUs/mL"),
                              {**_arc("f", "e", 0.8, 0.4, unit="OD"), "medium": None}])
    readme = matrix.readme_from(matrix.coefficients(net, rates), net, rates)
    assert "Each matrix's effects between organisms were measured in one medium" in readme
    assert "      OD: no medium recorded\n" in readme and "MORE THAN ONE MEDIUM" not in readme


def test_the_model_assumption_does_not_say_every_cell_is_from_two_organisms():
    """Round 21 of the review: "Every cell here was measured between two organisms" was said of a package
    whose diagonal comes from monocultures and whose cells can come from drop-out designs."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([_arc("a", "b", 0.3, 0.2), _arc("b", "a", 0.6, 0.4)])
    rates = {"a": _rate("A", 0.4, 6e8), "b": _rate("B", 0.2, 5.0e8)}
    readme = matrix.readme_from(matrix.coefficients(net, rates), net, rates)
    assert "Every cell here was measured between two organisms" not in readme
    assert "its monoculture, or its co-culture plateau where the README says so" in readme
    assert "unless it comes from a drop-out design" in \
        matrix.glv_payload(net, rates)["caveats"]["model_assumptions"]["pairwise_only"]


def test_every_matrix_holding_a_cell_is_described_with_its_media_and_unrecorded_cells():
    """Round 22 of the review: cells whose arcs record no medium vanished from the media lines. (A) Cells/mL
    cells in WC and CFUs/mL cells recording none read as "every effect ... one medium: WC"; (A1) one
    matrix with a WC cell and a cell recording none read the same; (C) a warning about a matrix pooling WC
    and LB counted the CFUs/mL matrix's medium X and named only the pooling matrix."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network

    def none(record):
        return {**record, "medium": None}
    cfu = "CFUs/mL"
    rates = {"a": _rate("A", 0.4, 1e9), "b": _rate("B", 0.2, 5e8), "c": _rate("C", 0.4, 1e9, unit=cfu),
             "d": _rate("D", 0.2, 5e8, unit=cfu)}

    def readme(records):
        net = records_to_network(records)
        return matrix.readme_from(matrix.coefficients(net, rates), net, rates)
    text = readme([_arc("b", "a", 0.6, 0.4), none(_arc("d", "c", 0.6, 0.4, unit=cfu))])
    assert "Every effect between two organisms" not in text
    assert "      Cells/mL: WC\n" in text and "      CFUs/mL: no medium recorded\n" in text
    text = readme([_arc("b", "a", 0.6, 0.4), none(_arc("a", "b", 0.3, 0.2))])
    assert "A MATRIX'S EFFECTS COME FROM MORE THAN ONE MEDIUM" in text
    assert "      Cells/mL matrix: WC, 1 cell(s) recording no medium\n" in text
    text = readme([_arc("b", "a", 0.6, 0.4), {**_arc("b", "a", 0.7, 0.4, medium="LB"), "condition": "z"},
                   _arc("d", "c", 0.6, 0.4, unit=cfu, medium="X")])
    assert "      Cells/mL matrix: WC, LB\n" in text and "      CFUs/mL matrix: X\n" in text
    # the payload carries the count R prints
    net = records_to_network([_arc("b", "a", 0.6, 0.4), none(_arc("a", "b", 0.3, 0.2))])
    (block,) = matrix.glv_payload(net, rates)["matrices"]
    assert block["cells_without_medium"] == 1 and block["media"] == ["WC"]


def test_a_cell_recording_no_medium_leaves_the_count_with_its_organism():
    """Round 22 of the review: A leaves the matrix for an unusable self-limitation, taking B on A, whose arc
    records no medium. The B and C matrix holds C on B, in M3, alone, so it is of one medium and counts no
    cell recording none."""
    from grownet import matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([{**_arc("b", "a", 0.05, 0.4, x_j=2.0e8, capacity=3.0e8), "medium": None},
                              _arc("a", "b", 0.3, 0.2, x_j=3.0e8, capacity=4.0e8),
                              _arc("c", "a", 0.6, 0.4), _arc("c", "b", 0.6, 0.4, medium="M3")])
    rates = {"a": _rate("A", 0.4, None), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    assert block["organisms"] == ["B", "C"] and block["unrecorded"] == 0
    assert "Every effect between two organisms in the matrices was measured in one medium: M3." in \
        matrix.readme_from(got, net, rates)
