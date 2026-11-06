"""Validate the steady-state derivation (#310) on a published 12-species gLV, locally (#314).

The model is Venturelli et al. 2018 (Molecular Systems Biology 14:e8157, CC BY 4.0), whose Code EV1 holds
the gLV they fitted to their synthetic human gut community. NOTHING OF THEIRS IS IN THIS REPOSITORY
(AGENTS.md): download Code EV1 from the article's supplementary material yourself, unzip it, and pass the
path of `twelveSpeciesT4.xml`:

    uv run --no-project --with numpy --with scipy python packaging/validate_steady_state.py twelveSpeciesT4.xml

numpy and scipy simulate the chemostats and are not dependencies of grownet; the fitting is grownet's own
(`grownet.subcommunity`), read from `src/`.

What it does. The published model is taken as the truth. Chemostat steady states at dilution rate D are
simulated, dx_i/dt = x_i (u_i - D + sum_j a_ij x_j), for each design below; an organism under 1% of the
largest steady state of its run counts as washed out, the rule `chemostat_groups` applies. Each row's scale
u_i - D is read the way grownet reads it, from a monoculture chemostat's start-up with a stated 4 h batch
period (`row_scale`). Then `fit` estimates B = A / (u - D), and the script reports, per design:

  * how many of the 132 off-diagonal coefficients it identifies, and their error against the truth;
  * how well each row's scale is recovered from the start-up;
  * how the full community is predicted by the package, A = scale x B, from a fit made without it;
  * the same with 5% vessel-to-vessel noise over three vessels, and the bootstrap spread that gives.

Designs: EPICS's (monocultures, the 12 leave-one-out communities, the full one), the same with every pair,
and the classic bottom-up one (monocultures and pairs only).
"""
from __future__ import annotations

import itertools
import math
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from grownet.growth import GrowthCurve  # noqa: E402
from grownet.subcommunity import fit, leave_one_out_predictions, pool, row_scale  # noqa: E402

NAMES = ["BH", "CA", "BU", "PC", "BO", "BV", "BT", "EL", "FP", "CH", "DP", "ER"]
D = 0.05                # per hour, under every growth rate of the model (the slowest, ER, is 0.156)
WASHED_OUT = 0.01       # the chemostat check's share of the largest steady state of the run
BATCH_HOURS = 4.0


def model(path):
    params = {e.get("id"): float(e.get("value")) for e in ET.parse(path).getroot().iter()
              if e.tag.endswith("parameter")}
    u = np.array([params[f"u{a}"] for a in NAMES])
    A = np.array([[params[f"a{a}{b}"] for b in NAMES] for a in NAMES])
    return u, A


def steady(u, A, members, washed_out=WASHED_OUT):
    """(the chemostat steady state of a community with washed-out members at 0, whether it reached one).

    Some sub-communities of a fitted gLV have no steady state at all and grow without bound; a chemostat run
    like that would hold no steady state either, so it is left out, and counted."""
    x0 = np.where(members, 0.01, 0.0)
    # an organism not inoculated stays at exactly 0: left free, solver noise of 1e-14 grew into a member over
    # 20,000 h, and the "leave out BU" community ended with BU at 0.309 (found in review)
    with np.errstate(over="ignore", invalid="ignore"):
        sol = solve_ivp(lambda t, x: np.where(members, x * (u - D + A @ x), 0.0), (0, 20000.0), x0,
                        method="LSODA", rtol=1e-10, atol=1e-14)
    x = sol.y[:, -1].copy()
    if not np.all(np.isfinite(x)) or x.max() > 1e3:
        return x, False
    growth = u - D + A @ x
    settled = bool(np.all(np.abs(growth[x > 1e-9]) < 1e-6))
    x[(x < washed_out * x.max()) | (x < 1e-9)] = 0.0
    return x, settled


def startup(u, A, i):
    """A monoculture chemostat started with a 4 h batch period: the curve grownet's start-up reader sees."""
    def rate(t, x):
        return x * (u[i] - (D if t > BATCH_HOURS else 0.0) + A[i, i] * x)
    times = np.arange(0.0, 48.01, 0.5)
    sol = solve_ivp(rate, (0, 48.0), [0.001], t_eval=times, method="LSODA", rtol=1e-10, atol=1e-14)
    return GrowthCurve(NAMES[i], tuple(times), tuple(sol.y[0]), "h", "OD600", "od")


def communities(u, A, groups, vessels=1, noise=0.0, seed=0, washed_out=WASHED_OUT):
    rng = random.Random(seed)
    out, unsettled = [], 0
    for members in groups:
        mask = np.zeros(len(NAMES), bool)
        mask[list(members)] = True
        x, settled = steady(u, A, mask, washed_out)
        if not settled:
            unsettled += 1
            continue
        reps = [{NAMES[i]: float(x[i]) * (math.exp(rng.gauss(0, noise)) if x[i] > 0 else 1.0) for i in members}
                for _ in range(vessels)]
        mean = {k: sum(r[k] for r in reps) / vessels for k in reps[0]}
        out.append({"name": "+".join(NAMES[i] for i in members), "abundance": mean,
                    **({"vessels": reps} if vessels > 1 else {})})
    return out, unsettled


def startup_noise(u, A, sigma, draws=20, seed=1):
    """How the row scale read from a start-up with lognormal noise `sigma` on each point compares with the
    true u - D: the share above it, and the median ratio. The steepest window is kept, so noise pulls it up."""
    import statistics
    rng = random.Random(seed)
    ratios = []
    for i in range(len(NAMES)):
        curve = startup(u, A, i)
        for _ in range(draws):
            noisy = GrowthCurve(NAMES[i], curve.times, tuple(v * math.exp(rng.gauss(0, sigma)) for v in curve.values),
                                "h", "OD600", "od")
            got = row_scale(noisy, D, {"kind": "batch", "hours": BATCH_HOURS, "said": "a 4 h batch period"})
            if got["scale"] is not None:
                ratios.append(got["scale"] / (u[i] - D))
    high = sum(r > 1 for r in ratios) / len(ratios)
    print(f"row scales from start-ups with {sigma:.0%} noise on each point: {len(ratios)} read, above u - D in "
          f"{high:.0%}, median ratio {statistics.median(ratios):.2f}, max {max(ratios):.2f}")


def report(label, u, A, design, scales, draws=0):
    comms, unsettled = design
    n = len(NAMES)
    truth = {NAMES[i]: {NAMES[j]: A[i, j] / (u[i] - D) for j in range(n)} for i in range(n)}
    got = fit(comms, draws=draws)
    pairs = [(i, j) for i, row in got["rows"].items() for j in row["values"] if i != j]
    print(f"\n== {label}: {len(comms)} communities at a steady state, {unsettled} without one (left out)")
    print(f"   off-diagonal identified: {len(pairs)} of {n * (n - 1)}; "
          f"rows identified: {sum(r['status'] == 'identified' for r in got['rows'].values())} of {n}")
    if pairs:
        # errors on the scale of the row's own self-limitation |B_ii|: the published fit sets many a_ij to
        # exactly 0 (it was L1-regularized), where an error relative to the true value means nothing
        rel = [abs(got["rows"][i]["values"][j] - truth[i][j]) / abs(truth[i][i]) for i, j in pairs]
        nonzero = [(i, j) for i, j in pairs if abs(truth[i][j]) > 1e-12]
        signs = np.mean([np.sign(got["rows"][i]["values"][j]) == np.sign(truth[i][j]) for i, j in nonzero])
        print(f"   B error, on the scale of the row's |B_ii|: median {np.median(rel):.2g}, max {max(rel):.2g}; "
              f"signs agree on {signs:.0%} of the {len(nonzero)} true coefficients that are not 0")
        if draws:
            sds = [got["rows"][i]["sd"][j] for i, j in pairs if got["rows"][i]["sd"]]
            covered = [abs(got["rows"][i]["values"][j] - truth[i][j]) <= 2 * got["rows"][i]["sd"][j]
                       for i, j in pairs if got["rows"][i]["sd"]]
            if sds:
                print(f"   bootstrap: {len(sds)} coefficients with a spread; truth within 2 sd for "
                      f"{np.mean(covered):.0%}")
    full = next((c for c in comms if c["name"].count("+") == n - 1), None)
    if full is not None:
        # communities whose survivors are the same set are one equation (`pool`), so the full community may be
        # pooled with the leave-one-out ones that lost the same members; it is predicted as that one
        pooled = next(c for c in pool(comms) if full["name"] in (c.get("runs") or [c["name"]]))
        runs = len(pooled.get("runs") or [pooled["name"]])
        if runs > 1:
            print(f"   the full community holds the same organisms as {runs - 1} other communities, so they are "
                  "one equation")
        pred = next(p for p in leave_one_out_predictions(comms) if p["community"] == pooled["name"])
        if pred["status"] == "predicted":
            err = [abs(pred["predicted"][k] - v) / v for k, v in pred["observed"].items()]
            print(f"   the full community predicted without it: max relative error {max(err):.2g} over "
                  f"{len(err)} organisms present")
        else:
            print(f"   the full community {pred['status']}")
    # the package: A = scale x B, where the start-up gave a scale
    with_scale = [(i, j) for i, j in pairs if scales[i]["scale"] is not None]
    if with_scale:
        a_err = [abs(scales[i]["scale"] * got["rows"][i]["values"][j] - A[NAMES.index(i), NAMES.index(j)])
                 / abs(A[NAMES.index(i), NAMES.index(i)]) for i, j in with_scale]
        print(f"   package A = scale x B: {len(with_scale)} cells, error on the scale of |a_ii|: median "
              f"{np.median(a_err):.2g}, max {max(a_err):.2g}")


def main(path):
    u, A = model(path)
    n = len(NAMES)
    scales = {}
    for i in range(n):
        scales[NAMES[i]] = row_scale(startup(u, A, i), D, {"kind": "batch", "hours": BATCH_HOURS,
                                                           "said": "a 4 h batch period"})
    rel = [abs(scales[k]["scale"] - (u[NAMES.index(k)] - D)) / (u[NAMES.index(k)] - D) for k in NAMES
           if scales[k]["scale"] is not None]
    print(f"row scales from the start-up: {len(rel)} of {n}; error relative to u - D: median "
          f"{np.median(rel):.2g}, max {max(rel):.2g}")
    # the same start-ups timed in minutes and in days: the scale is per hour whatever the curve's unit, as the
    # dilution rate is (raised in review: every curve here was in hours, so the unit path went unchecked)
    period = {"kind": "batch", "hours": BATCH_HOURS, "said": "a 4 h batch period"}
    other = []
    for i in range(n):
        c = startup(u, A, i)
        for unit, per in (("min", 60.0), ("d", 1 / 24)):
            again = row_scale(GrowthCurve(c.species, tuple(t * per for t in c.times), c.values, unit, "OD600", "od"),
                              D, period)["scale"]
            if scales[NAMES[i]]["scale"] is not None:
                other.append(abs(again / scales[NAMES[i]]["scale"] - 1))
    print(f"the same start-ups in minutes and in days: scales differ from the hours' by at most {max(other):.2g}")
    print("a community counts as settled when every member present grows at under 1e-6 per h after 20,000 h of "
          "simulation; one that does not is left out and counted")
    monos = [(i,) for i in range(n)]
    loo = [tuple(j for j in range(n) if j != h) for h in range(n)]
    full = [tuple(range(n))]
    pairs = list(itertools.combinations(range(n), 2))
    alive, _ = steady(u, A, np.ones(n, bool))
    print(f"full community at D = {D}: {int((alive > 0).sum())} of {n} present: "
          f"{[NAMES[i] for i in range(n) if alive[i] > 0]}")
    report("EPICS: monocultures, leave-one-out, full", u, A, communities(u, A, monos + loo + full), scales)
    report("bottom-up: monocultures and pairs", u, A, communities(u, A, monos + pairs), scales)
    report("all: monocultures, pairs, leave-one-out, full", u, A, communities(u, A, monos + pairs + loo + full),
           scales)
    # the coverage of one noise draw is itself noisy, so six draws (found in a second review: one seed said 94%)
    for seed in range(6):
        report(f"all, 3 vessels with 5% noise, draw {seed}", u, A,
               communities(u, A, monos + pairs + loo + full, 3, 0.05, seed=seed), scales, draws=200)
    # what the 1% wash-out rule costs: an organism below it is read as gone though it is still there
    report("bottom-up, wash-out rule off", u, A, communities(u, A, monos + pairs, washed_out=0.0), scales)
    report("all, wash-out rule off", u, A, communities(u, A, monos + pairs + loo + full, washed_out=0.0), scales)
    for sigma in (0.02, 0.05, 0.10):
        startup_noise(u, A, sigma)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
