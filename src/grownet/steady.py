"""Scoring a gLV package against a chemostat steady state (#125, from #124 item 4a).

Karoline, 2026-10-06: "you can check accuracy of fit using study 7 for mono-cultures and pairs with study
5's controls, which are steady state community abundances (without perturbation, ignoring the extra
species, which are at small abundance)", and then "go ahead with ... the chemostat validation".

A package is built from batch co-cultures and never sees a chemostat, so a chemostat is an independent
test of it. A continuous culture holds

    dx_i/dt = x_i ( r_i + sum_j A_ij x_j ) - D x_i

so at steady state `A x* = -(r - D)`, with D the dilution rate mGrowthDB records on the compartment. This
module reads the observed steady states, finds the stable state the package's own numbers settle in
(`settled`: the organisms it keeps satisfy that system, and none it loses can grow back in), and reports
both with their ratio. It only reports: no coefficient, rate or network changes because of a check.

The rules it applies, stated once:
  * **the observed steady state** of a vessel is the mean of its measurements over the last quarter of the
    run, and an organism's steady state is the median over the vessels, with every vessel and organism it
    could not read named with the reason;
  * **a perturbed run is named**, not used, since what Karoline asked for is the unperturbed state, and a
    run whose records say neither way is scored with that said;
  * **nothing is compared across abundance units or media**, as nothing is converted anywhere else;
  * **an organism the package loses**, observed at or near zero, agrees in direction, and
    the check says so rather than printing a ratio.
"""
from __future__ import annotations

import math
import re
import statistics

from .adapter import replicates_for_experiment
from .growth import SPIKE_FACTOR, cut

# the share of the run that counts as the end of it, where a chemostat is at its steady state
TAIL = 0.25
MIN_POINTS = 2          # fewer measurements in that window than this, and no steady state is read
# an organism observed below this share of the largest steady state of its run counts as washed out
WASHED_OUT = 0.01
# Whether a run was perturbed is in free text only: mGrowthDB has no field for it (the notes of #62 say
# so), and the two unperturbed runs are called "No perturbations" and "Control vessels ... but no
# perturbations", so a search for the word alone would mark exactly the wrong ones. These two patterns are
# read in order: a denial first, then the words the perturbed runs use ("The pH of the feed was changed
# from 6.4 to 3.7 and the feed was stopped for 12 hrs", "a feed perturbation as well as addition of fresh
# medium"). Neither matching leaves it unknown, which is reported rather than guessed.
_NOT_PERTURBED = re.compile(r"\b(no|without|not)\s+(further\s+|any\s+)?perturb", re.I)
_PERTURBED = re.compile(r"perturb|pulse[ds]?\b|was stopped|were stopped|changed from|decreased from"
                        r"|increased from|addition of fresh|wash[- ]?out", re.I)


def _dilution(exp: dict):
    """The dilution rate of an experiment's compartments, or None when none is recorded."""
    for comp in exp.get("compartments") or []:
        value = comp.get("dilutionRate")
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _medium(exp: dict) -> str:
    """The medium this run was in, by the strict rule: the name with every alteration its description
    states (`media.identity`), which is what an arc records too, so the two are comparable."""
    from .media import identity
    return identity(exp)["label"]


def same_medium(a: str, b: str) -> bool:
    """Whether two recorded media are the same medium, by `media.identity`'s key.

    Karoline, 2026-10-07: "foodnet's strict medium rule should be applied in general ... because such
    changes alter interactions". Both sides are labels, one from the package's arcs and one from the
    chemostat run, so the key is reconstructed from each (`media.key_from_label`) and the two keys are
    compared for equality. An empty label matches nothing: a run whose medium is unrecorded is not scored
    against a package, since a coefficient is specific to its environment.

    This replaced a subset rule over the names' words, which had two faults the live names exposed. It
    was not transitive: "Wilkins-Chalgren" reached all three long spellings, while the two correct long
    ones did not reach the misspelled "Anerobe" (#142 item 10). And it matched a composite name to one of
    its own compartments, because `medium_of` joins one name per compartment, so a capacity from the WC
    side of SMGDB00000002 and one from its WC-plus-Mucin design were called the same environment (#142
    item 13). Keying is stricter in both directions: of the 7 pairs the subset rule called one medium on
    the live names it keeps the one the validation needs, SMGDB00000009 and 16's "Wilkins-Chalgren
    Anaerobe Broth" against SMGDB00000002, 7 and 11's "...Anaerobe Broth (WC)", and drops the three
    composite matches and three against the bare short name. The cost is SMGDB00000001, whose chemostat
    is recorded under the "Anerobe" misspelling and now matches nothing; only an alias table recovers
    that, and Craig's agent recommends against widening the matching, since a missed comparison costs
    validation while a false merge produces a wrong number carrying a scientific claim.
    """
    from .media import key_from_label
    first, second = key_from_label(a), key_from_label(b)
    return bool(first and second and first == second)


def _perturbed(exp: dict):
    """True, False, or None when the records say neither way."""
    text = " ".join(str(exp.get(key) or "") for key in ("name", "description"))
    # mGrowthDB serves no perturbations field today (its experiment records hold name, description,
    # cultivationMode, compartments, communityStrains and bioreplicates), so the free-text rules below are
    # the whole rule. This reads one if the API ever adds it.
    if exp.get("perturbations"):
        return True
    if _NOT_PERTURBED.search(text):
        return False
    return True if _PERTURBED.search(text) else None


def _tail_mean(curve, tail: float = TAIL):
    """(value, window, points): the mean over the end of the run, and the window it was taken over.

    The window is the last `tail` of the curve's span, widened to the last `MIN_POINTS` measurements when
    it holds fewer than that: SMGDB00000005's chemostats have nine points over 400 h, so a quarter of the
    run holds one measurement, and a mean of one point is the point. The window is returned either way,
    so what was averaged is on the record.
    """
    times, values = cut(curve, None)
    if len(values) < MIN_POINTS:
        return None, (times[0], times[-1]), len(values)
    span = times[-1] - times[0]
    start = times[-1] - tail * span if span > 0 else times[0]
    inside = [(t, v) for t, v in zip(times, values, strict=True) if t >= start - 1e-9]
    if len(inside) < MIN_POINTS:
        inside = list(zip(times, values, strict=True))[-MIN_POINTS:]
        start = inside[0][0]
    return sum(v for _, v in inside) / len(inside), (start, times[-1]), len(inside)


def observed(client, exps: list, spike_factor: float = SPIKE_FACTOR) -> list:
    """The steady states of the continuous cultures among `exps`, one entry per experiment.

    {"study_id", "experiment", "name", "medium", "dilution", "unit", "window", "vessels", "perturbed",
     "why_not", "organisms": {name: {"value", "vessels", "spread"}}, "left_out": [(what, why)]}

    `why_not` is empty when the run can be scored, and otherwise says why it cannot: a missing dilution
    rate, perturbations, or no organism read. Nothing is derived here and nothing is cached beyond what
    the client already caches, so a check costs the curves of these experiments and nothing else.
    """
    out = []
    for exp in exps:
        if (exp.get("cultivationMode") or "").lower() == "batch":
            continue
        name = exp.get("name") or exp.get("id") or "experiment"
        reps, skipped = replicates_for_experiment(client, exp, spike_factor)
        entry = {"study_id": exp.get("studyId", ""), "experiment": exp.get("id", ""), "name": name,
                 "medium": _medium(exp), "dilution": _dilution(exp), "unit": "", "window": None,
                 "vessels": len(reps), "perturbed": _perturbed(exp), "why_not": "",
                 "organisms": {}, "left_out": [(what, why) for what, why in skipped]}
        if entry["perturbed"] is None:
            entry["left_out"].append((name, "mGrowthDB records no perturbations field and this run's "
                                            "description says neither way, so whether its end is an "
                                            "unperturbed steady state is not known from the records"))
        windows = []
        for strain in exp.get("communityStrains") or []:
            species = strain.get("name")
            values, points, per_vessel = [], 0, {}
            for i, rep in enumerate(reps):
                curve = rep.curve(species)
                if curve is None:
                    entry["left_out"].append((f"{name}: {species}, vessel {rep.name or i}",
                                              "no curve for this organism in this vessel"))
                    continue
                value, window, points = _tail_mean(curve)
                if value is None:
                    entry["left_out"].append((f"{name}: {species}, vessel {rep.name or i}",
                                              f"{points} measurement(s) over the last quarter of the "
                                              "run, too few for a steady state"))
                    continue
                if not entry["unit"]:
                    entry["unit"] = curve.abundance_unit
                if curve.abundance_unit != entry["unit"]:
                    entry["left_out"].append((f"{name}: {species}, vessel {rep.name or i}",
                                              f"measured in {curve.abundance_unit}, and this run in "
                                              f"{entry['unit']}; left out rather than converted"))
                    continue
                values.append(value)
                per_vessel[i] = value
                windows.append(window)
            if values:
                # `per_vessel` by vessel index, for the steady-state derivation's bootstrap over vessels
                # (#312); `check` reads only the median
                entry["organisms"][species] = {"value": statistics.median(values), "vessels": len(values),
                                               "spread": (min(values), max(values)), "per_vessel": per_vessel}
        if windows:
            entry["window"] = (min(w[0] for w in windows), max(w[1] for w in windows))
        reasons = []
        if entry["dilution"] is None:
            reasons.append("no dilution rate is recorded on its compartments, and a steady state cannot "
                           "be predicted without one")
        if entry["perturbed"] is True:
            reasons.append("the run carries perturbations, so its end is not an unperturbed steady state")
        if not entry["organisms"]:
            reasons.append("no organism of it could be read")
        entry["why_not"] = "; ".join(reasons)
        out.append(entry)
    return out


class Found(list):
    """Observed steady states, and `why_not`: why none could be looked up at all, which is not the same
    as mGrowthDB holding none (found in review: a genus package and a failed search both read as "holds no
    continuous culture of these organisms")."""
    why_not = ""
    unread: tuple = ()


def _found(items=(), why_not: str = "", unread=()) -> Found:
    out = Found(items)
    out.why_not, out.unread = why_not, tuple(unread)
    return out


def find(client, net, progress=None) -> list:
    """The observed steady states of every continuous culture mGrowthDB holds for this network's
    organisms, including studies the search itself never read.

    The organisms are looked up by taxon id through the API's own search, so this costs one search, the
    studies it names, and the curves of their continuous cultures. A study that cannot be read is skipped
    rather than losing the others.
    """
    taxa = sorted({node.taxon_id for node in net.nodes.values() if node.taxon_id})
    if not taxa:
        return _found(why_not="no organism of this network has a taxon id to look chemostats up by (a genus "
                              "node has none, and a chemostat holds strains): derive without merging genera "
                              "to check the strains")
    try:
        found = client.search(strain_ncbi_ids=",".join(str(t) for t in taxa))
    except Exception as e:       # noqa: BLE001 - a check that cannot look studies up says so
        return _found(why_not=f"the search for chemostats of these organisms failed ({e})")
    studies = list(found.get("studies", []))
    out, unread = [], []
    for i, sid in enumerate(studies):
        if progress:
            progress(i, len(studies), f"Reading the chemostats of {sid}")
        try:
            exps = client.study_experiments(sid)
        except Exception as e:   # noqa: BLE001 - same reason, one unreadable study at a time, named
            unread.append(f"{sid} ({e})")
            continue
        for entry in observed(client, exps):
            entry["study_id"] = entry["study_id"] or sid
            out.append(entry)
    # a study that could not be read is named; with none read, nothing was looked at, which is not
    # mGrowthDB holding no chemostat (found in review)
    if unread and len(unread) == len(studies):
        return _found(why_not=f"none of the {len(studies)} studies the search named could be read: "
                              + "; ".join(unread), unread=unread)
    return _found(out, unread=unread)


# How ill-conditioned a matrix may be and still have an equilibrium printed. A condition number of 1e8
# means the solution can lose about eight of the sixteen digits a float carries, so a number printed to
# four significant digits is then not a prediction of anything: constructed at the project's own scale, a
# change of 0.05 percent in one coefficient flipped the categorical verdict, against a stated relative
# spread of 0.33, and a near-singular block returned 1e24 reported as a steady state (#142 item 9).
MAX_EQUILIBRIUM_CONDITION = 1.0e8


def condition_of(rows: list) -> float:
    """A condition number of a square matrix: the 1-norm of the matrix times the 1-norm of its inverse.

    Infinity when it is singular. This is the standard library's own arithmetic throughout, like the rest
    of the module, and the matrices are as small as a community is.
    """
    n = len(rows)
    if not n:
        return float("inf")
    norm = max((sum(abs(rows[i][j]) for i in range(n)) for j in range(n)), default=0.0)
    columns = []
    for j in range(n):
        unit = [1.0 if i == j else 0.0 for i in range(n)]
        got = solve([row[:] for row in rows], unit)
        if got is None:
            return float("inf")
        columns.append(got)
    inverse_norm = max((sum(abs(c) for c in column) for column in columns), default=0.0)
    return norm * inverse_norm if norm and inverse_norm else float("inf")


def solve(rows: list, rhs: list):
    """The solution of `rows x = rhs` by Gaussian elimination with partial pivoting, or None if singular.

    Standard library only, like everything else here, and the systems are as small as the matrices are.
    The caller checks `condition_of` before standing behind a solution: an absolute pivot above 1e-300 is
    the only thing this refuses, and a matrix can be far too ill-conditioned for its answer to mean
    anything while every pivot clears that.
    """
    n = len(rhs)
    work = [list(row) + [rhs[i]] for i, row in enumerate(rows)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(work[r][col]))
        if abs(work[pivot][col]) < 1e-300:
            return None
        work[col], work[pivot] = work[pivot], work[col]
        for r in range(n):
            if r == col:
                continue
            factor = work[r][col] / work[col][col]
            for k in range(col, n + 1):
                work[r][k] -= factor * work[col][k]
    return [work[i][n] / work[i][i] for i in range(n)]


# How many organisms `settled` searches by trying every sub-community: 2^12 = 4096 small solves take about a
# second in pure Python, and a chemostat or a package matrix holds far fewer organisms than that.
MAX_SETTLED = 12
# A value this share of the largest of its kind, or less, is zero to rounding: an organism of a candidate
# state at that size is not above zero, and an outsider growing at that rate does not grow back in. The
# same share on both boundaries, so a state on the edge is found once (Craig's agent, reviewing).
SETTLED_TOLERANCE = 1e-9


def _determinant(rows: list) -> float:
    """The determinant by Gaussian elimination with partial pivoting."""
    n, work, sign = len(rows), [list(row) for row in rows], 1.0
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(work[r][col]))
        if work[pivot][col] == 0.0:
            return 0.0
        if pivot != col:
            work[col], work[pivot], sign = work[pivot], work[col], -sign
        for r in range(col + 1, n):
            factor = work[r][col] / work[col][col]
            for k in range(col, n):
                work[r][k] -= factor * work[col][k]
    product = sign
    for i in range(n):
        product *= work[i][i]
    return product


def _sign(a, b):
    return abs(a) if b >= 0 else -abs(a)


def _eigenvalues(rows: list) -> list:
    """[(real, imaginary)]: the eigenvalues of a real square matrix, by reduction to upper Hessenberg form
    with stabilized elementary similarity transformations and then the shifted QR algorithm, after
    balancing (EISPACK's balanc, elmhes and hqr, as Numerical Recipes, 2nd ed., sections 11.5 and 11.6, write
    them, with the iteration limit raised from 30 to 60 and an exceptional shift every 10). Standard library
    only. Raises ArithmeticError if the iteration does not converge."""
    n = len(rows)
    if n == 0:
        return []
    # 1-indexed copy, as the published algorithm is written
    a = [[0.0] * (n + 1)] + [[0.0] + [float(v) for v in row] for row in rows]
    # balanc: scale rows and columns by powers of 2 so each row and its column have similar norms, without
    # rounding, as Numerical Recipes and LAPACK do before the reduction. A state's Jacobian diag(x) A is
    # graded (x from 1e3 to 1e9 gives entries from 1e-7 to 1e9), and without this the eigenvalues were off by
    # up to 6e-6 of the largest, more than STABLE_MARGIN, so an unstable state was judged stable (found in
    # review: 20 verdicts of 6000 near-edge states differed from R's eigen(), none with it)
    radix, converged = 2.0, False
    while not converged:
        converged = True
        for i in range(1, n + 1):
            c = sum(abs(a[j][i]) for j in range(1, n + 1) if j != i)
            r = sum(abs(a[i][j]) for j in range(1, n + 1) if j != i)
            if c and r:
                g, f, s = r / radix, 1.0, c + r
                while c < g:
                    f *= radix
                    c *= radix * radix
                g = r * radix
                while c > g:
                    f /= radix
                    c /= radix * radix
                if (c + r) / f < 0.95 * s:
                    converged = False
                    for j in range(1, n + 1):
                        a[i][j] /= f
                    for j in range(1, n + 1):
                        a[j][i] *= f
    # elmhes: Gaussian elimination with pivoting to upper Hessenberg form
    for m in range(2, n):
        x, i = 0.0, m
        for j in range(m, n + 1):
            if abs(a[j][m - 1]) > abs(x):
                x, i = a[j][m - 1], j
        if i != m:
            for j in range(m - 1, n + 1):
                a[i][j], a[m][j] = a[m][j], a[i][j]
            for j in range(1, n + 1):
                a[j][i], a[j][m] = a[j][m], a[j][i]
        if x != 0.0:
            for i in range(m + 1, n + 1):
                y = a[i][m - 1]
                if y != 0.0:
                    y /= x
                    a[i][m - 1] = y
                    for j in range(m, n + 1):
                        a[i][j] -= y * a[m][j]
                    for j in range(1, n + 1):
                        a[j][m] += y * a[j][i]
    for i in range(3, n + 1):              # the multipliers left below the subdiagonal are not part of it
        for j in range(1, i - 1):
            a[i][j] = 0.0
    # hqr
    wr, wi = [0.0] * (n + 1), [0.0] * (n + 1)
    anorm = sum(abs(a[i][j]) for i in range(1, n + 1) for j in range(max(i - 1, 1), n + 1))
    nn, t = n, 0.0
    while nn >= 1:
        its = 0
        while True:
            low = nn
            while low >= 2:
                s = abs(a[low - 1][low - 1]) + abs(a[low][low])
                if s == 0.0:
                    s = anorm
                if abs(a[low][low - 1]) + s == s:
                    a[low][low - 1] = 0.0
                    break
                low -= 1
            x = a[nn][nn]
            if low == nn:
                wr[nn], wi[nn] = x + t, 0.0
                nn -= 1
            else:
                y = a[nn - 1][nn - 1]
                w = a[nn][nn - 1] * a[nn - 1][nn]
                if low == nn - 1:
                    p = 0.5 * (y - x)
                    q = p * p + w
                    z = math.sqrt(abs(q))
                    x += t
                    if q >= 0.0:
                        z = p + _sign(z, p)
                        wr[nn - 1] = wr[nn] = x + z
                        if z:
                            wr[nn] = x - w / z
                        wi[nn - 1] = wi[nn] = 0.0
                    else:
                        wr[nn - 1] = wr[nn] = x + p
                        wi[nn - 1], wi[nn] = -z, z
                    nn -= 2
                else:
                    if its == 60:
                        raise ArithmeticError("the QR iteration did not converge")
                    if its in (10, 20, 30, 40, 50):
                        t += x
                        for i in range(1, nn + 1):
                            a[i][i] -= x
                        s = abs(a[nn][nn - 1]) + abs(a[nn - 1][nn - 2])
                        y = x = 0.75 * s
                        w = -0.4375 * s * s
                    its += 1
                    m = nn - 2
                    while m >= low:
                        z = a[m][m]
                        r = x - z
                        s = y - z
                        p = (r * s - w) / a[m + 1][m] + a[m][m + 1]
                        q = a[m + 1][m + 1] - z - r - s
                        r = a[m + 2][m + 1]
                        s = abs(p) + abs(q) + abs(r)
                        p, q, r = p / s, q / s, r / s
                        if m == low:
                            break
                        u = abs(a[m][m - 1]) * (abs(q) + abs(r))
                        v = abs(p) * (abs(a[m - 1][m - 1]) + abs(z) + abs(a[m + 1][m + 1]))
                        if u + v == v:
                            break
                        m -= 1
                    for i in range(m + 2, nn + 1):
                        a[i][i - 2] = 0.0
                        if i != m + 2:
                            a[i][i - 3] = 0.0
                    k = m
                    while k <= nn - 1:
                        if k != m:
                            p = a[k][k - 1]
                            q = a[k + 1][k - 1]
                            r = a[k + 2][k - 1] if k != nn - 1 else 0.0
                            x = abs(p) + abs(q) + abs(r)
                            if x != 0.0:
                                p, q, r = p / x, q / x, r / x
                        s = _sign(math.sqrt(p * p + q * q + r * r), p)
                        if s != 0.0:
                            if k == m:
                                if low != m:
                                    a[k][k - 1] = -a[k][k - 1]
                            else:
                                a[k][k - 1] = -s * x
                            p += s
                            x, y, z = p / s, q / s, r / s
                            q, r = q / p, r / p
                            for j in range(k, nn + 1):
                                p = a[k][j] + q * a[k + 1][j]
                                if k != nn - 1:
                                    p += r * a[k + 2][j]
                                    a[k + 2][j] -= p * z
                                a[k + 1][j] -= p * y
                                a[k][j] -= p * x
                            for i in range(low, min(nn, k + 3) + 1):
                                p = x * a[i][k] + y * a[i][k + 1]
                                if k != nn - 1:
                                    p += z * a[i][k + 2]
                                    a[i][k + 2] -= p * r
                                a[i][k + 1] -= p * q
                                a[i][k] -= p
                        k += 1
            if not low < nn - 1:
                break
    return [(wr[i], wi[i]) for i in range(1, n + 1)]


STABLE_MARGIN = 1e-10   # a real part above -1e-10 of the largest eigenvalue's size is not counted as negative


def _stable(rows: list) -> bool:
    """Whether every eigenvalue of `rows` has a negative real part, at least STABLE_MARGIN of the largest
    eigenvalue's size below zero, so an eigenvalue that is zero to rounding does not count as stable.

    The eigenvalues are computed directly. A Routh-Hurwitz test on the characteristic polynomial from the
    Faddeev-LeVerrier recursion did this before and lost its digits where a state's abundances span many
    orders: on 3000 random states with abundances from 1e3 to 3e9 it judged 23 wrongly against R's eigen()
    (22 stable states refused, 1 unstable accepted), with condition numbers of 19 to 536, so the
    conditioning gate did not catch them; this routine judges all 3000 as R does. Without balancing it still
    differed from R on 20 of 6000 states whose rightmost eigenvalue sits within 3e-7 of zero, where diag(x) A
    is graded; balanced, on none (both found in review).
    """
    values = _eigenvalues(rows)
    if not values:
        return True
    size = max(math.hypot(re, im) for re, im in values)
    return all(re < -STABLE_MARGIN * size for re, _ in values)


def settled(matrix: list, growth: list) -> dict:
    """Where dx_i/dt = x_i (g_i + sum_j A_ij x_j) settles: the state a simulation ends in.

    The solution of `A x = -g` with every organism present is only that state when all of it is above zero.
    When it is not, the system settles on a sub-community, and solving with everyone present says nothing
    about which: on study 7's package at a dilution of 0.04 /h the full solution puts two of its three
    organisms below zero, while the system settles with one of those two present (2026-11-13). So every
    sub-community S is tried, and a state is one where
      * every organism of S is above zero at the solution of `A_SS x_S = -g_S`,
      * no organism outside S can grow back in: its rate there, g_j + sum_k A_jk x_k, is not positive, and
      * it is stable: every eigenvalue of diag(x_S) A_SS has a negative real part.
    Those are the eigenvalues of the whole Jacobian at that state together with the outsiders' rates.

    Two rules keep the search from deciding on numbers it cannot stand behind (Craig's agent, reviewing):
      * **one tolerance on both boundaries.** A value within `SETTLED_TOLERANCE` of the largest of its kind
        counts as zero: an organism of S at that size is not above zero, and an outsider growing at that
        rate does not grow back in. So a state on the edge between S and S without k is found once, as the
        smaller community, rather than once on each side of a rounding error.
      * **every candidate's conditioning is checked before its stability is judged**, since the
        eigenvalues of an ill-conditioned `A_SS` carry fewer digits than the verdict needs. One such
        candidate is enough to refuse: it could be a state or not, and either way the verdict over all
        candidates would rest on it.

    {"state": [x_i] or None, "kept": [i], "lost": [i], "invasion": {i: rate of a lost organism},
     "states": every such state, "why_not": ""}. Exactly one state gives `state`; none, several (where it
    settles then depends on where it starts), an ill-conditioned candidate, or a system too large to search
    gives `why_not`, which says what the search established and no more.
    """
    n = len(growth)
    out = {"state": None, "kept": [], "lost": [], "invasion": {}, "states": [], "why_not": ""}
    if n > MAX_SETTLED:
        out["why_not"] = (f"it holds {n} organisms, and this tool finds where a system settles by trying "
                          f"every sub-community of at most {MAX_SETTLED}")
        return out
    scale = max((abs(g) for g in growth), default=0.0) or 1.0
    found, unjudged, unconverged = [], [], []
    for mask in range(1 << n):
        kept = [i for i in range(n) if mask >> i & 1]
        x = [0.0] * n
        if kept:
            part = solve([[matrix[i][j] for j in kept] for i in kept], [-growth[i] for i in kept])
            if part is None:
                continue
            size = max(abs(value) for value in part) or 1.0
            if any(value <= SETTLED_TOLERANCE * size for value in part):
                continue
            for i, value in zip(kept, part, strict=True):
                x[i] = value
        invasion = {j: growth[j] + sum(matrix[j][k] * x[k] for k in kept) for j in range(n) if j not in kept}
        if any(rate > SETTLED_TOLERANCE * scale for rate in invasion.values()):
            continue
        if kept:
            condition = condition_of([[matrix[i][j] for j in kept] for i in kept])
            if condition > MAX_EQUILIBRIUM_CONDITION:
                unjudged.append((len(kept), condition))
                continue
        try:
            stable = _stable([[x[i] * matrix[i][j] for j in kept] for i in kept])
        except ArithmeticError:            # the QR iteration did not converge: not judged, never a verdict
            unconverged.append(len(kept))
            continue
        if not stable:
            continue
        found.append({"state": x, "kept": kept, "lost": [j for j in range(n) if j not in kept],
                      "invasion": invasion})
    out["states"] = found
    if unjudged:
        members, worst = max(unjudged, key=lambda item: item[1])
        worst_text = "infinite" if worst == float("inf") else format(worst, ".3g")
        out["why_not"] = (f"{len(unjudged)} sub-community(ies) it could settle on are too ill-conditioned to "
                          f"judge (the worst, of {members} organism(s), has a condition number of "
                          f"{worst_text}, above the {MAX_EQUILIBRIUM_CONDITION:.0e} this tool will stand "
                          "behind), so no state is named")
    elif unconverged:
        # its own sentence: such a candidate passed the conditioning gate, and was reported as having an
        # infinite condition number (found in review)
        out["why_not"] = (f"the stability of {len(unconverged)} sub-community(ies) it could settle on could not "
                          "be computed (the eigenvalue iteration did not converge), so no state is named")
    elif len(found) == 1:
        out.update(found[0])
    elif found:
        out["why_not"] = (f"it has {len(found)} stable steady states, so where it settles depends on where it "
                          "starts")
    else:
        out["why_not"] = ("no sub-community of it has a stable steady state this check can stand behind")
    return out


def predicted(block: dict, rates: dict, dilution: float, organisms: list = None) -> dict:
    """The steady state the package predicts: where `dx/dt = x (r - D + A x)` settles (`settled`).

    {"values": {organism: x}, "notes": {organism: why it is lost}, "lost": [organisms],
     "interior": {organism: x}, "why_not": ""}. An organism the package loses has the value 0, and its
    note says what it cannot grow back into. `interior` is the solution of `A x = -(r - D)` with every
    organism present, which is only the state when nothing is lost. `organisms` restricts the system to a
    sub-community, which is what a chemostat holding some of the matrix's organisms needs; the others are
    reported rather than silently set to anything.
    """
    names, ids = block["organisms"], block["ids"]
    keep = [i for i, name in enumerate(names) if organisms is None or name in organisms]
    if not keep:
        return {"values": {}, "notes": {}, "why_not": "no organism in common"}
    rows = [[block["matrix"][i][j] for j in keep] for i in keep]
    # an organism with no growth rate is refused, as the package README refuses it ("not every organism in
    # this matrix has a growth rate"): it used to enter as r = 0 without a word, so the check scored a
    # package whose README said its equilibrium was not computed (found in review)
    missing = [names[i] for i in keep if (rates.get(ids[i]) or {}).get("rate") is None]
    if missing:
        return {"values": {}, "notes": {}, "lost": [], "interior": {},
                "why_not": "not every organism in it has a growth rate (" + ", ".join(missing) + ")"}
    rhs = [-((rates.get(ids[i]) or {})["rate"] - dilution) for i in keep]
    # the full solution only where it is worth printing, as the README decides it: on an ill-conditioned
    # system it printed numbers like -5e+20 that the README refused (found in review)
    answer = (solve([row[:] for row in rows], rhs) if condition_of(rows) <= MAX_EQUILIBRIUM_CONDITION
              else None)
    interior = {names[i]: answer[k] for k, i in enumerate(keep)} if answer is not None else {}
    where = settled(rows, [-value for value in rhs])
    if where["state"] is None:
        return {"values": {}, "notes": {}, "lost": [], "interior": interior,
                "why_not": f"the package has no single state to compare here: {where['why_not']}"}
    values = {names[i]: where["state"][k] for k, i in enumerate(keep)}
    lost = [names[keep[k]] for k in where["lost"]]
    held = ", ".join(names[keep[k]] for k in where["kept"]) or "no organism"
    notes = {names[keep[k]]: (f"it cannot grow back in where the package settles, with {held}: a few cells "
                              f"of it added there grow at {where['invasion'][k]:.2g} /h")
             for k in where["lost"]}
    # the same prediction with every off-diagonal set to 0, which is each organism on its own at
    # -r_i / A_ii. It says how much of the prediction the fitted interactions are responsible for, and
    # without it a check of the whole package reads as a check of the interactions (found 2026-10-06)
    alone = solve([[rows[a][b] if a == b else 0.0 for b in range(len(keep))] for a in range(len(keep))],
                  list(rhs))
    without = {names[i]: alone[k] for k, i in enumerate(keep)} if alone is not None else {}
    return {"values": values, "notes": notes, "lost": lost, "interior": interior, "why_not": "",
            "without_interactions": without}


def _environment(block: dict) -> list:
    """The media a matrix stands for: its cells' (`media`) when it holds a cell, which are the effects a
    chemostat is scored with; the arcs' between its organisms (`arc_media`) when it holds none, so that it
    still has an environment (found in review, both ways: a matrix of no cell matched a chemostat in any
    medium, and then arcs in no cell matched one in a medium no cell was measured in)."""
    named = block.get("media") if block.get("cells") or "arc_media" not in block else block["arc_media"]
    return [name for name in (named or []) if name]


def _fits(block: dict, unit: str, medium: str, organisms: set) -> bool:
    """Whether this matrix can be compared with a run in `unit` and `medium`: same abundance unit, at
    least one organism in common, and the same medium where the package records one at all."""
    named = _environment(block)
    return bool(block["abundance_unit"] == unit and organisms.intersection(block["organisms"])
                and (not named or any(same_medium(name, medium) for name in named)))


def _washed_out(value: float, biggest: float) -> bool:
    """Whether the chemostat lost this organism: nothing left, or under a hundredth of the largest steady
    state of the same run (SMGDB00000011's Faecalibacterium duncaniae is zero in every vessel while the
    others hold 1e8)."""
    return value <= 0 or (biggest > 0 and value <= WASHED_OUT * biggest)


def check(coefficients: dict, rates: dict, seen: list) -> list:
    """Score a package against each observed steady state: one entry per observation.

    {"name", "study_id", "experiment", "medium", "dilution", "used", "why_not", "rows": [...]} , where a
    row is {"organism", "predicted", "observed", "ratio", "note"}. A matrix is matched to an observation
    by abundance unit, by medium and by sharing at least one organism; `used` False always carries the
    reason, so a reader never has to guess why a chemostat was not scored.
    """
    out = []
    for entry in seen:
        result = {"name": entry["name"], "study_id": entry["study_id"],
                  "experiment": entry["experiment"], "medium": entry["medium"],
                  "dilution": entry["dilution"], "vessels": entry["vessels"],
                  "window": entry["window"], "used": False, "why_not": entry["why_not"], "rows": []}
        if result["why_not"]:
            out.append(result)
            continue
        here = set(entry["organisms"])
        block = next((b for b in coefficients["matrices"]
                      if _fits(b, entry["unit"], entry["medium"], here)), None)
        if block is None:
            units = sorted({b["abundance_unit"] for b in coefficients["matrices"]})
            media_names = sorted({name for b in coefficients["matrices"] for name in _environment(b)})
            theirs = ", ".join(media_names) or "an unrecorded medium"
            if not any(here.intersection(b["organisms"]) for b in coefficients["matrices"]):
                result["why_not"] = ("no organism of this run is in the package, so there is nothing to "
                                     "compare")
            elif entry["unit"] not in units:
                result["why_not"] = (f"this run measures {entry['unit']} and the package holds "
                                     f"{', '.join(units) or 'nothing'}; left out rather than converted")
            else:
                # the two media are told apart by name, and the name is a third party's: so this says the
                # names differ, and names a near miss where one word is spelled differently, rather than
                # asserting that the environments differ (Craig's agent, on #141)
                from .media import near_miss
                mine = entry["medium"] or "an unrecorded medium"
                result["why_not"] = (f"this run is recorded in {mine} and the package in {theirs}: "
                                     "mGrowthDB names them as different media, and a coefficient is "
                                     "specific to the environment it was fitted in")
                close = next(((name, near_miss(name, entry["medium"])) for name in media_names
                              if near_miss(name, entry["medium"])), None)
                if close:
                    name, (theirs_word, mine_word) = close
                    result["why_not"] += (f". {name} differs from this run's medium in one word only, "
                                          f"\"{theirs_word}\" against \"{mine_word}\": if that is one "
                                          "medium spelled two ways, the two studies record it "
                                          "differently and grownet does not merge names that disagree")
            out.append(result)
            continue
        # an alias is the one place grownet says two names that disagree are one medium, so a run scored
        # across one says which entry of the table made that happen (Karoline, 2026-10-07)
        from .media import key_from_label_with_aliases
        fired = list(key_from_label_with_aliases(entry["medium"])[1])
        for name in _environment(block):
            for pair in key_from_label_with_aliases(name)[1]:
                if pair not in fired:
                    fired.append(pair)
        result["medium_aliases"] = [list(pair) for pair in fired]
        shared = [name for name in block["organisms"] if name in here]
        got = predicted(block, rates, entry["dilution"], shared)
        if got["why_not"]:
            result["why_not"] = got["why_not"]
            out.append(result)
            continue
        biggest = max((o["value"] for o in entry["organisms"].values()), default=0.0)
        for name in shared:
            value, seen_here = got["values"][name], entry["organisms"][name]["value"]
            row = {"organism": name, "predicted": value, "observed": seen_here, "ratio": None, "note": "",
                   "without_interactions": (got.get("without_interactions") or {}).get(name),
                   "lost": name in got["lost"]}
            gone = _washed_out(seen_here, biggest)
            if name in got["lost"] and gone:
                row["note"] = ("the fit washes this organism out and the chemostat did too, so the two "
                               "agree in direction")
            elif name in got["lost"]:
                row["note"] = ("the fit washes this organism out while the chemostat holds it: "
                               + got["notes"].get(name, ""))
            elif gone:
                row["note"] = "the chemostat washed this organism out and the fit keeps it"
            else:
                row["ratio"] = value / seen_here
            result["rows"].append(row)
        result["used"] = True
        # the solution with every organism present, named only where it is not the state: a reader who
        # solves A x = -(r - D) in R finds these numbers, and is told why they are not the prediction
        result["interior_not_above_zero"] = {name: value for name, value in (got.get("interior") or {}).items()
                                             if got["lost"] and value <= 0}
        result["left_out"] = [name for name in entry["organisms"] if name not in shared]
        if not _environment(block):
            # what records no medium: this matrix's effects, or the arcs between its organisms when it holds
            # none; "the package" was said where the network's other arcs did record one (found in review)
            what = ("the effects in this matrix record" if block.get("cells") or "arc_media" not in block
                    else "the arcs between this matrix's organisms record")
            result["note"] = (f"{what} no medium, so this comparison does not know whether the two were "
                              "measured in the same environment")
        elif block.get("cells") and block.get("unrecorded"):
            # scored by the medium its other cells record, which these do not (found in review)
            result["note"] = (f"{block['unrecorded']} cell(s) of this matrix have an arc recording no medium, "
                              "so whether they were measured in this run's environment is not recorded")
        out.append(result)
    # why nothing could be looked up travels with the result, to the report and the package
    return _found(out, getattr(seen, "why_not", ""), getattr(seen, "unread", ()))


def _number(value: float) -> str:
    return f"{value:.4g}"


def summary_line(checks: list) -> str:
    """The one line the command line prints for the check (found in review: a check that did not run read as
    "0 chemostat(s) scored, 0 not")."""
    if not checks and getattr(checks, "why_not", ""):
        return f"steady-state check: not checked, because {checks.why_not}"
    scored = sum(1 for one in checks if one["used"])
    unread = len(getattr(checks, "unread", ()))
    return (f"steady-state check: {scored} chemostat(s) scored, {len(checks) - scored} not (the report says "
            "why each)" + (f"; {unread} study(ies) the search named could not be read" if unread else ""))


def as_text(checks: list) -> str:
    """The check as the report and the package print it: one block per chemostat."""
    if not checks and getattr(checks, "why_not", ""):
        return f"steady-state check: not checked, because {checks.why_not}.\n"
    unread = list(getattr(checks, "unread", ()))
    # a study the search named and that could not be read is said, so "holds none" is not claimed of it
    # (found in review)
    skipped = (f"{len(unread)} study(ies) the search named could not be read, so any chemostat of theirs is "
               f"not here: {'; '.join(unread)}.\n" if unread else "")
    if not checks:
        return ("steady-state check: mGrowthDB holds no continuous culture of these organisms"
                + (" in the studies that could be read" if unread else "")
                + ", so there is nothing to score this package against.\n" + skipped)
    lines = ["steady-state check: what this package predicts for a chemostat, against what the chemostat",
             "held. The prediction is the stable state dx/dt = x (r - D + A x) settles in: the organisms it",
             "keeps satisfy A x = -(r - D), and none it loses can grow back in. These numbers come from the",
             "package alone and the observations were never used to make it.", ""]
    for check_one in checks:
        head = f"  {check_one['name']} ({check_one['study_id'] or check_one['experiment']})"
        if not check_one["used"]:
            lines.append(f"{head}: not scored, because {check_one['why_not']}.")
            continue
        lines.append(f"{head}, dilution rate {check_one['dilution']:g} /h, "
                     f"{check_one['vessels']} vessel(s):")
        for short, full in check_one.get("medium_aliases") or []:
            lines.append(f"      scored across a medium alias: \"{short}\" is read as \"{full}\" "
                         "(grownet.media.WORD_ALIASES and NAME_ALIASES, curated by hand)")
        if check_one.get("note"):
            lines.append(f"      note: {check_one['note']}")
        lost = [row["organism"] for row in check_one["rows"] if row.get("lost")]
        if lost:
            kept = [row["organism"] for row in check_one["rows"] if row["organism"] not in lost]
            lines.append(f"      the package settles with {', '.join(kept) or 'no organism'}, and loses "
                         f"{', '.join(lost)}")
        below = check_one.get("interior_not_above_zero") or {}
        if below:
            lines.append("      (solving A x = -(r - D) with every organism present puts "
                         + ", ".join(f"{name} at {_number(value)}" for name, value in below.items())
                         + ", which is no state: the system settles with fewer organisms)")
        for row in check_one["rows"]:
            if row["ratio"] is not None:
                alone = row.get("without_interactions")
                beside = (f", and {_number(alone / row['observed'])}x with every interaction set to 0"
                          if alone and row["observed"] else "")
                lines.append(f"      {row['organism']}: predicted {_number(row['predicted'])}, "
                             f"observed {_number(row['observed'])}, "
                             f"{_number(row['ratio'])}x observed{beside}")
            else:
                lines.append(f"      {row['organism']}: predicted {_number(row['predicted'])}, "
                             f"observed {_number(row['observed'])}: {row['note']}")
        for name in check_one.get("left_out", []):
            lines.append(f"      {name}: in the chemostat and not in the package, so not scored")
    lines.append("")
    return "\n".join(lines) + "\n" + skipped
