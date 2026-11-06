"""The steady-state estimator of #310 (task #311): gLV rows from the steady states of sub-communities.

Karoline, 2026-11-06: "can we have a third inference method just for gLV mode and chemostat, off by default
... The idea here is to parameterize the gLV from steady-state abundances of sub-communities", and, on EPICS
(Ansari et al. 2021) using only the leave-one-out communities: "could we have something more flexible that
would try parameterisation on all available sub-communities?"

At a steady state every member i present satisfies 1 + sum_j B_ij N_j = 0, with B = A / s and s the row's
scale (r_i - D in a chemostat). Every coefficient here is invented: nothing of any study is in a fixture.
"""
import pytest

from grownet.integrated import _solve
from grownet.subcommunity import UNIT_ROW, _resample, _row_reasons, fit, leave_one_out_predictions, pool

# Two species, by hand. B = [[-1, -0.25], [-0.1, -0.5]]: a alone settles at 1 (1 - 1*1 = 0), b alone at 2
# (1 - 0.5*2 = 0). Together: -x_a - 0.25 x_b = -1 and -0.1 x_a - 0.5 x_b = -1. The first gives
# x_a = 1 - 0.25 x_b; into the second, -0.1 + 0.025 x_b - 0.5 x_b = -1, so x_b = 0.9 / 0.475 = 1.894737
# and x_a = 1 - 0.25 * 1.894737 = 0.526316.
PAIR = {"a": 0.9 / 0.475 * -0.25 + 1, "b": 0.9 / 0.475}
TWO = [{"name": "a alone", "abundance": {"a": 1.0}},
       {"name": "b alone", "abundance": {"b": 2.0}},
       {"name": "a with b", "abundance": PAIR}]


def test_two_species_by_hand():
    got = fit(TWO)
    assert got["rows"]["a"]["values"] == pytest.approx({"a": -1.0, "b": -0.25}, abs=1e-12)
    assert got["rows"]["b"]["values"] == pytest.approx({"a": -0.1, "b": -0.5}, abs=1e-12)
    assert got["rows"]["a"]["status"] == got["rows"]["b"]["status"] == "identified"
    assert got["rows"]["a"]["equations"] == 2                  # a alone, and a with b


# Three species, generated: an invented B whose communities all coexist. The steady state of a community is
# the solution of B[present] x = -1, which is what the estimator has to invert.
B3 = {"a": {"a": -1.0, "b": -0.2, "c": 0.1},
      "b": {"a": -0.3, "b": -0.5, "c": -0.1},
      "c": {"a": 0.2, "b": -0.4, "c": -0.8}}


def _steady(members, B=B3):
    x = _solve([[B[i][j] for j in members] for i in members], [-1.0] * len(members))
    assert all(v > 0 for v in x), "an invented community that coexists"
    return dict(zip(members, x, strict=True))


def _community(*members, B=B3, vessels=None):
    extra = {"vessels": vessels} if vessels else {}
    return {"name": "+".join(members), "abundance": _steady(list(members), B), **extra}


def test_the_epics_design_recovers_every_coefficient_exactly():
    """Monocultures and the leave-one-out communities of {a, b, c}, which for three species are its pairs:
    the design of Ansari et al., 2n = 6 experiments, gives all nine coefficients."""
    design = [_community("a"), _community("b"), _community("c"),
              _community("b", "c"), _community("a", "c"), _community("a", "b")]
    got = fit(design)
    for i, row in B3.items():
        assert got["rows"][i]["status"] == "identified"
        assert got["rows"][i]["values"] == pytest.approx(row, abs=1e-10)


def test_any_mix_of_sub_communities_that_determines_a_row_is_used():
    """Not only leave-one-out: monocultures, one pair and the full community also determine every row."""
    design = [_community("a"), _community("b"), _community("c"), _community("a", "b"), _community("a", "b", "c")]
    got = fit(design)
    # c meets a and b only in the full community, and has its monoculture: two equations, three unknowns
    assert got["rows"]["c"]["status"] == "underdetermined"
    assert ("c", "a") in got["unidentified"] and ("c", "b") in got["unidentified"]
    # a and b each have three equations (alone, the pair, the full) for three unknowns
    for i in ("a", "b"):
        assert got["rows"][i]["status"] == "identified"
        assert got["rows"][i]["values"] == pytest.approx(B3[i], abs=1e-10)


def test_a_washed_out_member_gives_no_equation_and_counts_as_absent():
    """A member whose steady state is 0 washed out: its own equation does not hold (it is not at an interior
    steady state) and it contributes nothing to the others'. Here c is inoculated into a+b+c and washes out,
    so that community is the pair a+b as far as the equations go."""
    washed = {"name": "a+b+c", "abundance": {**_steady(["a", "b"]), "c": 0.0}}
    design = [_community("a"), _community("b"), _community("c"), washed]
    got = fit(design)
    assert ("a+b+c", "c") in got["washed_out"]
    assert got["rows"]["c"]["equations"] == 1
    assert got["rows"]["a"]["values"] == pytest.approx({"a": -1.0, "b": -0.2}, abs=1e-10)


def test_a_species_never_present_with_another_leaves_that_coefficient_unidentified():
    got = fit([_community("a"), _community("b")])
    assert got["rows"]["a"]["values"] == pytest.approx({"a": -1.0}, abs=1e-12)
    assert ("a", "b") in got["unidentified"] and ("b", "a") in got["unidentified"]
    assert "no community holds both" in got["why"][("a", "b")]


def test_each_community_is_predicted_by_a_fit_made_without_it():
    """For a system that is pairwise, removing one community from an over-determined design still identifies
    every row, so its prediction is exact; that is the check against context dependence."""
    design = [_community("a"), _community("b"), _community("c"),
              _community("b", "c"), _community("a", "c"), _community("a", "b"), _community("a", "b", "c")]
    predictions = leave_one_out_predictions(design)
    full = next(p for p in predictions if p["community"] == "a+b+c")
    assert full["status"] == "predicted"
    for species, observed in _steady(["a", "b", "c"]).items():
        assert full["predicted"][species] == pytest.approx(observed, rel=1e-9)
    # a monoculture too: without "a" alone, a's row still rests on its pairs and the full community
    alone = next(p for p in predictions if p["community"] == "a")
    assert alone["status"] == "predicted" and alone["predicted"]["a"] == pytest.approx(1.0, rel=1e-9)


def test_the_spread_comes_from_vessels_and_is_none_without_two():
    """A bootstrap over vessels, where every community a row rests on has two or more; otherwise the row has
    no spread and its arcs are undetermined (decision 5 of #310)."""
    import random
    rng = random.Random(1)

    def noisy(*members):
        steady = _steady(list(members))
        vessels = [{k: v * (1 + rng.gauss(0, 0.05)) for k, v in steady.items()} for _ in range(3)]
        mean = {k: sum(v[k] for v in vessels) / 3 for k in steady}
        return {"name": "+".join(members), "abundance": mean, "vessels": vessels}

    design = [noisy("a"), noisy("b"), noisy("c"), noisy("b", "c"), noisy("a", "c"), noisy("a", "b")]
    got = fit(design, draws=200)
    assert all(sd > 0 for sd in got["rows"]["a"]["sd"].values())
    # one community of row a with a single vessel: the row has no spread
    design[0] = {"name": "a", "abundance": {"a": 1.0}, "vessels": [{"a": 1.0}]}
    assert fit(design, draws=50)["rows"]["a"]["sd"] is None


def test_the_rows_are_in_units_of_the_row_scale():
    assert UNIT_ROW == "1/abundance, in units of the row scale s_i (r_i - D in a chemostat)"


def test_a_row_whose_own_term_is_not_negative_is_named_not_given_a_sign():
    """An obligate cross-feeder X: r_X = 0.1 below D = 0.2, so it washes out alone and lives on J's and K's
    products (A_XJ = 0.6, A_XK = 0.5 above zero). Its row is B_X = A_X / (r_X - D) = A_X / -0.1, so
    {X: 10, J: -6, K: -5}: every sign flipped by the negative scale. Reported, J and K were called its
    inhibitors (found in review). B_XX = 10 is not negative, which a self-limited organism's never is unless
    r_X < D, so the row cannot say which way its partners act, and it is named instead."""
    B = {"X": {"X": 10.0, "J": -6.0, "K": -5.0},
         "J": {"X": -0.1 / 0.6, "J": -1.0 / 0.6, "K": -0.2 / 0.6},
         "K": {"X": 0.0, "J": -0.3 / 0.5, "K": -1.0 / 0.5}}
    x_alone = {"name": "X", "abundance": {"X": 0.0}}                    # 1 + 10 x = 0 has no positive root
    design = [x_alone, _community("J", B=B), _community("K", B=B), _community("J", "K", B=B),
              _community("X", "J", B=B), _community("X", "K", B=B), _community("X", "J", "K", B=B)]
    got = fit(design, draws=0)
    assert got["rows"]["X"]["status"] == "no self-limitation" and got["rows"]["X"]["values"] == {}
    assert got["rows"]["X"]["own"] == pytest.approx(10.0, rel=1e-9)
    assert ("X", "J") in got["unidentified"] and "decides the sign" in got["why"][("X", "J")]
    assert any(i == "X" and "cannot hold alone at this dilution rate" in why for i, why in _row_reasons(got))
    # the others are untouched: J's and K's rows are exact
    assert got["rows"]["J"]["values"] == pytest.approx(B["J"], abs=1e-9)


def test_runs_of_the_same_members_are_one_equation_not_two():
    """Two runs of the pair a+b and nothing else: one set of members has one steady state, so this is one
    equation per row, with two unknowns, and no row is determined. Kept apart, the runs' noise made two
    equations, and the rows were "identified" from noise alone, more often the noisier the runs (found in
    review). Pooled, the runs are the community's vessels."""
    pair = _steady(["a", "b"])
    one = {"name": "a+b", "abundance": {k: v * 1.03 for k, v in pair.items()}}
    two = {"name": "a+b again", "abundance": {"a": pair["a"] * 0.96, "b": pair["b"] * 1.05}}
    got = fit([one, two], draws=0)
    assert got["rows"]["a"]["status"] == got["rows"]["b"]["status"] == "underdetermined"
    assert got["rows"]["a"]["equations"] == 1
    (pooled,) = pool([one, two])
    assert len(pooled["vessels"]) == 2 and pooled["runs"] == ["a+b", "a+b again"]
    assert pooled["abundance"]["a"] == pytest.approx(pair["a"] * (1.03 + 0.96) / 2, rel=1e-12)


def test_a_community_left_out_is_not_in_the_fit_that_predicts_it():
    """The EPICS design of three species without the full community: leave out the pair a+b and a never
    meets b, so its effect on a is not determined and a+b cannot be predicted. A fit that kept the community
    it predicts would always predict it exactly."""
    design = [_community("a"), _community("b"), _community("c"),
              _community("b", "c"), _community("a", "c"), _community("a", "b")]
    pair = next(p for p in leave_one_out_predictions(design) if p["community"] == "a+b")
    assert pair["status"].startswith("not predicted") and "a on b" in pair["status"]


def test_partners_in_the_same_proportions_everywhere_leave_the_row_undetermined():
    """b and c are always together, at 1 : 1.000001, in every community holding a, so a's equations cannot
    tell b's effect from c's: six communities, six equations for a's five unknowns (a to e), and still not
    determined, because two columns are all but equal: past the condition limit."""
    e = 1.000001
    design = [{"name": "abc", "abundance": {"a": 1.0, "b": 1.0, "c": e}},
              {"name": "abcd", "abundance": {"a": 2.0, "b": 0.5, "c": 0.5 * e, "d": 1.0}},
              {"name": "abce", "abundance": {"a": 0.5, "b": 2.0, "c": 2.0 * e, "e": 1.0}},
              {"name": "ade", "abundance": {"a": 1.5, "d": 0.7, "e": 0.4}},
              {"name": "ad", "abundance": {"a": 1.2, "d": 0.9}},
              {"name": "ae", "abundance": {"a": 0.8, "e": 1.3}}]
    got = fit(design, draws=0)
    assert got["rows"]["a"]["status"] == "underdetermined" and got["rows"]["a"]["equations"] == 6
    assert len(got["rows"]["a"]["columns"]) == 5
    assert any(i == "a" and "too alike to tell apart" in why for i, why in _row_reasons(got))
    # and with c at a proportion of its own in one community, the same design passes the limit (these
    # abundances are invented, not steady states of one B, so only the condition is the point here)
    from grownet.integrated import MAX_CONDITION
    design[0] = {"name": "abc", "abundance": {"a": 1.0, "b": 1.0, "c": 3.0}}
    assert fit(design, draws=0)["rows"]["a"]["condition"] <= MAX_CONDITION


def test_runs_are_pooled_by_the_members_present_not_by_what_was_inoculated():
    """a+b, and a+b+c where c washed out, end with the same members: one steady state, one community. a+b
    run twice where one run lost b ends with different members: two. The wash-out is reported under the run
    that lost it, not under the pool's name (found in a second review)."""
    pair = _steady(["a", "b"])
    lost_c = {"name": "a+b+c", "abundance": {**pair, "c": 0.0}}
    assert len(pool([{"name": "a+b", "abundance": dict(pair)}, lost_c])) == 1
    lost_b = {"name": "a+b, b lost", "abundance": {"a": 1.0, "b": 0.0}}
    assert len(pool([{"name": "a+b", "abundance": dict(pair)}, lost_b])) == 2
    got = fit([{"name": "a+b", "abundance": dict(pair)}, lost_c, _community("a"), _community("b")], draws=0)
    assert got["washed_out"] == [("a+b+c", "c")]
    (pooled,) = [c for c in pool([{"name": "a+b", "abundance": dict(pair)}, lost_c]) if "runs" in c]
    assert "c" not in pooled["abundance"]


def test_the_bootstrap_spreads_as_far_as_the_mean_and_keeps_a_member_present():
    """Three vessels at 1, 2 and 6: the mean 3 has a standard error s / sqrt(3) = 2.646 / 1.732 = 1.528. A
    plain bootstrap of the mean spreads sqrt(2 / 3) of that, 1.247; widened by sqrt(3 / 2) it spreads 1.528
    (found in review). And two vessels at 1 and 100: a draw of the 1 twice, widened, would fall below 0,
    which would read the member as washed out; it stays present."""
    import random
    import statistics
    rng = random.Random(0)
    c = {"name": "x", "abundance": {"a": 3.0}, "vessels": [{"a": 1.0}, {"a": 2.0}, {"a": 6.0}]}
    draws = [_resample([c], rng)[0]["abundance"]["a"] for _ in range(4000)]
    assert statistics.pstdev(draws) == pytest.approx(statistics.stdev([1.0, 2.0, 6.0]) / 3 ** 0.5, rel=0.05)
    wide = {"name": "y", "abundance": {"a": 50.5}, "vessels": [{"a": 1.0}, {"a": 100.0}]}
    assert all(_resample([wide], rng)[0]["abundance"]["a"] > 0 for _ in range(200))


def test_a_left_out_run_takes_its_twin_runs_with_it():
    """Called on runs as they come, two runs of a+b are one community: leaving it out leaves both out, so a
    never meets b and the pair is not predicted, instead of being predicted exactly by its own twin."""
    pair = _steady(["a", "b"])
    runs = [_community("a"), _community("b"), {"name": "a+b", "abundance": dict(pair)},
            {"name": "a+b again", "abundance": dict(pair)}]
    (twins,) = [p for p in leave_one_out_predictions(runs) if p["community"].startswith("a+b")]
    assert twins["community"] == "a+b (2 runs)" and twins["status"].startswith("not predicted")
