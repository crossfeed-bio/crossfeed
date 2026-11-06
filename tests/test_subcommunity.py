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
from grownet.subcommunity import UNIT_ROW, fit, leave_one_out_predictions

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
