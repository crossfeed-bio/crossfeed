"""The network as a matrix, and the parameters a generalized Lotka-Volterra simulator takes (#108).

Karoline, 2026-10-03: "supporting another network export format: the adjacency matrix. In addition,
grownet should be able to provide parameters for generalized Lotka-Volterra (gLV) simulation tools ...
building an adjacency matrix with negative (-1) entries on the diagonal in which each strain (or species
or genus) only appears once (so merge across studies) and where the same is true for the growth rates that
are delivered together with the interaction matrix."

The conventions, decided with her:

  * **A cell holds the log2 mean as it is**, the effect size the comparison measured. It is not a fitted
    gLV coefficient, which would be a per-capita effect in absolute units, and the README says so. The
    diagonal is -1 by convention (self-limitation), not a normalization of the rest.
  * **Rows are affected, columns are the actor**: `A[i][j]` is the effect of j on i, which is the order
    dx_i/dt = x_i (r_i + sum_j A[i][j] x_j) reads in. An arc from source to target is `A[target][source]`.
  * **An empty cell is 0**, and so is an absent arc: the absence threshold judged it no interaction.
  * **Each organism appears once.** Arcs of one ordered pair are merged across conditions and studies by
    their median, which is her merge rule (register item 14). That rule refuses to merge arcs of opposite
    sign, so such a pair gets 0 and is named in the README: a simulator should not be handed a number no
    one stands behind.
  * **A growth rate is the maximum specific growth rate in monoculture**, median over the replicates and
    studies that have one (see `derive.growth_rates`).

Standard library only: the matrix is text, and the package is a zip of text files.
"""
from __future__ import annotations

import csv
import io
import statistics
import zipfile

from . import brand
from .interaction import ABOLISHED, OBLIGATE
from .model import InteractionNetwork, genus_name

# The -1 a package used to carry on its diagonal by convention (Karoline, 2026-10-03). No output holds it
# since #119: the package fits the diagonal from the data and the plain adjacency matrix leaves it at 0.
# It is kept because `rows` takes a diagonal, and because a reader of a 0.2.0 package met this number.
DIAGONAL = -1.0
RATE_UNIT = "1/h"
# An obligate comparison (the target grows only with the source) and an abolished one (only without it)
# have no log2 ratio at all, because one side did not grow, while the interaction they report is the
# strongest there is. Karoline, 2026-10-03: "obligate and abolished arcs need to carry numbers reflecting
# the strong effect, how about 10 with the appropriate sign?" So such an arc enters a matrix as +10
# (obligate, the extreme of facilitation) or -10 (abolished, the extreme of inhibition). It is a stated
# convention, not a measurement: as a log2 mean, 10 is a thousandfold difference, past anything the
# quantified arcs reach, and the files say so.
EXTREME = 10.0


def _label(node) -> str:
    return node.name or node.id


def labels(net: InteractionNetwork) -> list:
    """The organisms of the matrix, in a stable order: by label, so two runs line up."""
    return [nid for nid, _ in sorted(net.nodes.items(), key=lambda item: (_label(item[1]).lower(), item[0]))]


def _extreme(edge):
    """The value of an arc that has no ratio, or None.

    Since #129 that is the **measured bound** the no-growth rule puts on the side that did not grow: at
    least this much facilitation for an obligate comparison, at most this much inhibition for an abolished
    one (`interaction.no_growth_bound`, carried as `strength_bound`). A network derived before that change
    has no bound, and falls back to `EXTREME` so its censored arcs still show rather than reading as 0,
    which would say no interaction about the strongest effect there is; the README names those cells.
    """
    if edge.strength is not None or edge.status == "absent":
        return None
    if getattr(edge, "strength_bound", None) is not None:
        return edge.strength_bound
    if getattr(edge, "bound_rule", ""):
        return None        # the rule was applied and bounds nothing away from zero: the cell stays 0
    if edge.outcome == OBLIGATE:
        return EXTREME
    return -EXTREME if edge.outcome == ABOLISHED else None


def cells(net: InteractionNetwork) -> tuple:
    """({(affected, actor): value}, conflicts): one value per ordered pair, and the pairs left at 0.

    Arcs of a pair are merged by their median. An obligate or abolished arc has no ratio, so it carries
    `EXTREME` with its sign and does not enter the median of the arcs that do have one (register item 14:
    such arcs "join their direction and count without entering the median"); it decides a cell only when
    no arc of the pair was quantified. A pair whose arcs disagree in sign is not merged (item 14 again):
    it stays 0 and is returned in `conflicts`, so the README can name it.
    """
    measured, extreme = {}, {}
    for edge in net.edges:
        pair = (edge.target, edge.source)
        if edge.status != "absent" and edge.strength is not None:
            measured.setdefault(pair, []).append(edge.strength)
        elif (value := _extreme(edge)) is not None:
            extreme.setdefault(pair, []).append(value)
    values, conflicts = {}, []
    for pair in list(measured) + [p for p in extreme if p not in measured]:
        numbers = measured.get(pair, []) + extreme.get(pair, [])
        if any(v > 0 for v in numbers) and any(v < 0 for v in numbers):
            conflicts.append(pair)
            continue
        values[pair] = statistics.median(measured.get(pair) or extreme[pair])
    return values, conflicts


def media(net: InteractionNetwork) -> list:
    """The media the arcs of this matrix come from, in order, as mGrowthDB names them.

    A gLV simulation is of one environment, so a matrix built from several media mixes things that were
    never measured together (Karoline, 2026-10-04, on why she now wants environment filtering: "it's one
    thing to export a network of known interactions and another to do a gLV simulation"). The files say
    which media they hold, and the page's second box is how a reader keeps one.
    """
    seen = []
    for edge in net.edges:
        for name in (edge.medium or "").split("; "):
            if name and name not in seen:
                seen.append(name)
    return seen


def dropout_arcs(net: InteractionNetwork) -> int:
    """How many arcs of this matrix come from a drop-out design.

    Such an arc compares a community with the same community without one member, so the effect may run
    through a third species, while a gLV coefficient is meant to be the direct effect of one organism on
    another (Karoline, 2026-10-04: "for gLV, including drop-out communities are not a good idea"). They are
    derived by default, so the files say how many are in them and which switch leaves them out.
    """
    return sum(1 for e in net.edges
               if (e.evidence == "dropout" or "dropout" in (e.evidence or "")) and e.status != "absent")


def counts(net: InteractionNetwork) -> dict:
    """{"arcs", "cells", "organisms"}: how many arcs carry a number, how many cells they make, and how many
    organisms the matrix has. A matrix holds one cell per ordered pair, so a network with several arcs for
    one pair has fewer cells than arcs; the page and the README say so, rather than leaving two counts to
    disagree (the lesson of the hidden arcs, Karoline, 2026-10-03)."""
    values, _ = cells(net)
    in_a_cell = sum(1 for e in net.edges
                    if (e.status != "absent" and e.strength is not None) or _extreme(e) is not None)
    return {"arcs": in_a_cell, "cells": len(values), "organisms": len(net.nodes)}


def bounded_cells(net: InteractionNetwork) -> list:
    """The cells that hold a measured bound rather than a ratio, as (affected, actor, value) labels.

    These are the pairs whose only arcs are obligate or abolished: no ratio exists, so the cell carries
    the bound the no-growth rule puts on the side that did not grow (#129). A reader has to know which
    numbers are bounds, so the report and the README name them.
    """
    return [row for row in _censored_cells(net) if row[2] not in (EXTREME, -EXTREME)]


def by_convention(net: InteractionNetwork) -> list:
    """The censored cells of a network old enough to have no bound, which fall back to `EXTREME`."""
    return [row for row in _censored_cells(net) if row[2] in (EXTREME, -EXTREME)]


def _censored_cells(net: InteractionNetwork) -> list:
    """Every cell whose value comes from a comparison where one side did not grow."""
    values, _ = cells(net)
    measured = {(e.target, e.source) for e in net.edges if e.status != "absent" and e.strength is not None}
    pairs = []
    for edge in net.edges:
        pair = (edge.target, edge.source)
        if _extreme(edge) is not None and pair not in measured and pair in values and pair not in pairs:
            pairs.append(pair)
    return [(_label(net.nodes[a]), _label(net.nodes[b]), values[(a, b)]) for a, b in pairs]


def rows(net: InteractionNetwork, diagonal: float | None = None) -> tuple:
    """(names, matrix, conflicts): the square matrix, row by row, with `diagonal` on the diagonal.

    `diagonal` None leaves the diagonal at 0, which is the plain adjacency matrix. The gLV package does
    not come through here: it fits its own diagonal (`coefficients`).
    """
    order = labels(net)
    values, conflicts = cells(net)
    names = [_label(net.nodes[nid]) for nid in order]
    matrix = []
    for affected in order:
        row = []
        for actor in order:
            if affected == actor:
                row.append(0.0 if diagonal is None else diagonal)
            else:
                row.append(values.get((affected, actor), 0.0))
        matrix.append(row)
    return names, matrix, [(net.nodes[a].name or a, net.nodes[b].name or b) for a, b in conflicts]


def for_nodes(net: InteractionNetwork, rates: dict) -> dict:
    """The growth rates keyed by this network's own node ids.

    A rate belongs to a strain, as a monoculture does, while a network merged to the genus level
    (`derive.merge_genus`) has one node per genus. Such a node takes the median of the rates of the
    strains of its genus, with their replicates counted and their studies kept, so a genus network can be
    simulated too.
    """
    out = {}
    for nid, node in net.nodes.items():
        if nid in rates:
            # the node's own name, which is the strain's current one (#24), so the rates file, the report
            # and the network all call it the same thing
            out[nid] = {**rates[nid], "name": _label(node)}
            continue
        label = _label(node)
        members = [r for r in rates.values() if genus_name(r.get("name", "")) == genus_name(label)]
        if node.identity != "genus" or not members:
            continue
        units = {r["unit"] for r in members}
        out[nid] = {"name": label, "rate": statistics.median(r["rate"] for r in members),
                    "unit": members[0]["unit"] if len(units) == 1 else "",
                    "n": sum(r.get("n", 0) for r in members),
                    "studies": sorted({s for r in members for s in r.get("studies", ())}),
                    "per_study": {}, "other_units": [],
                    "method": members[0].get("method", ""),
                    **_merged_capacity(members),
                    "merged_from": sorted(r["name"] for r in members)}
    return out


def _merged_capacity(members: list) -> dict:
    """The capacity and the lag of a genus node, merged over the species behind it (#118): the median of
    the ones that have a capacity, and only within one abundance unit."""
    units = {r.get("capacity_unit") for r in members if r.get("capacity") is not None and r.get("capacity_unit")}
    unit = units.pop() if len(units) == 1 else ""
    sizes = [r["capacity"] for r in members
             if r.get("capacity") is not None and r.get("capacity_unit") == unit] if unit else []
    lags = [r["lag"] for r in members if r.get("lag") is not None]
    return {"capacity": statistics.median(sizes) if sizes else None,
            "capacity_unit": unit if sizes else "",
            "capacity_n": sum(r.get("capacity_n", 0) for r in members) if sizes else 0,
            "capacity_per_study": {}, "other_capacity_units": sorted(units) if not unit else [],
            "capacity_left_out": [x for r in members for x in r.get("capacity_left_out") or []],
            "lag": statistics.median(lags) if lags else None, "lag_n": len(lags)}


def rate_rule(method: str) -> str:
    """How a reported rate was obtained, recorded in every network that carries rates.

    The integrated form does not merge replicate sets: each fitted row already holds a rate that stage 1
    took as the median over that organism's monoculture replicates, and the published rate is the median
    over the rows. Saying "median over replicates" of it put one merge where there are two (#155 item 13).
    """
    if str(method).startswith("integrated"):
        return (f"{method} in monoculture, the median over the fitted rows, each row's own rate the "
                "median over that organism's monoculture replicates; batch experiments only")
    return f"{method} in monoculture, median over replicates and studies; batch experiments only"


def rate_meta(net: InteractionNetwork, rates: dict, method: str) -> str:
    """The `growth_rates` block of a network's meta: the rule, a rate per organism, and the organisms that
    have none, so a downloaded network carries the rates it was reported with and says what is missing."""
    return {"rule": rate_rule(method), "organisms": {nid: dict(rate) for nid, rate in rates.items()},
            "without_a_rate": sorted(_label(node) for nid, node in net.nodes.items() if nid not in rates)}


def _number(value: float) -> str:
    return "0" if value == 0 else f"{value:.4f}".rstrip("0").rstrip(".")


def matrix_csv(net: InteractionNetwork, diagonal: float | None = None) -> str:
    """The matrix as CSV: the header row and the first column are the organisms."""
    names, matrix, _ = rows(net, diagonal)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["", *names])
    for name, row in zip(names, matrix, strict=True):
        writer.writerow([name, *(_number(v) for v in row)])
    return out.getvalue()


def derivation_of(net: InteractionNetwork | None) -> str:
    """"integrated" or "replicate": whose formula this network's cells follow.

    The prose a package carries has to match the derivation that made it, and a reader meets that prose
    in README.txt, in the payload's caveats and in the R package (#142 item 6). The settings say it;
    where they do not, the arcs do, since an integrated arc records its own metric.
    """
    said = ((net.meta.get("settings") if net is not None else None) or {}).get("derivation")
    if said in ("integrated", "replicate"):
        return said
    if net is not None and any(str(e.metric or "").startswith("integrated") for e in net.edges):
        return "integrated"
    return "replicate"


# What an off-diagonal cell is, in each derivation's own words. The specified comparison takes a
# difference of two separately fitted rates; the integrated form fits the whole row from the time course
# and the cell is a parameter of that fit, so the comparison's formula is not what it holds.
OFF_DIAGONAL = {
    "replicate": [
        "  An off-diagonal cell is A[i][j] = (r_with - r_without) / x_j, the difference between i's own",
        "      growth rate with j and without it, over x_j, the partner's abundance averaged over the",
        "      window i's rate was fitted in, which keeps the rate and the abundance in one interval",
        "      rather than pairing a rate with an abundance the organism reached at another time. Both",
        "      rates come from the same comparison, and the two rates",
        "      behind every arc are in the report beside this file, so every cell can be rebuilt by hand.",
        "      Where one of them is 0, measured, because i grew only with j or only without it, the cell",
        "      is still that difference: no floor and no stated extreme enters this package.",
    ],
    "integrated": [
        "  An off-diagonal cell is A[i][j] fitted from the whole measured time course, not a difference of",
        "      two rates: integrating dx_i/dt = x_i (r_i + sum_j A[i][j] x_j) over a replicate's span gives",
        "      ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j dt), which is linear in r_i and in",
        "      every A[i][j], so one least-squares fit per organism gives its whole row. r_i and A[i][i]",
        "      come from that organism's monocultures under the same conditions, then the partners' effects",
        "      from the co-cultures with those held fixed. Every arc carries the coefficient, the condition",
        "      number and the residual of the fit behind it, so every cell can be traced to its fit.",
    ],
}

# The two assumptions of the generalized Lotka-Volterra form itself, which no amount of care in the
# fitting removes (Karoline, 2026-10-07: "let's add some caveats about the assumptions of gLV, especially
# the higher-order interactions and constant interaction coefficients. In batch, the medium changes, so
# the environment changes, and with it the species interactions"). They belong beside the parameters
# rather than only in the help, because the zip and the R object travel without the page.
MODEL_ASSUMPTIONS = (
    "  EVERY COEFFICIENT IS CONSTANT IN TIME. One number stands for the effect of j on i over the whole",
    "      run. In a batch culture the medium is consumed, the pH moves and metabolites accumulate, so a",
    "      pair that competes for a resource while it is plentiful can cross-feed on what is left once it",
    "      is gone: the effect can change in size and in sign along the growth curve. A cell here is the",
    "      average that best described the interval that was fitted, not a property of the pair. Each arc",
    "      reports fit_window_share, the share of the measured course its rows cover, and carries the",
    "      window_partial caution below a half; an effect that appears only in late stationary phase is",
    "      outside that window rather than averaged into it.",
    "  INTERACTIONS ARE PAIRWISE AND ADD UP. The effect of j on i is the same whoever else is present,",
    "      and a community is the sum of its pairs. A higher-order interaction, where a third organism",
    "      changes how the first two affect each other, has no term in this model and cannot be fitted",
    "      into one. Every cell here was measured between two organisms and is carried into a simulation",
    "      of any community as though it still held there.",
    "  So read a simulation against the measurement it came from rather than against itself, and treat",
    "      these numbers as a description of the organisms under the conditions that were fitted. The",
    "      medium travels with every arc and with every carrying capacity for that reason.",
)

CAVEAT_COEFFICIENTS = {
    "replicate": ("every cell is a fitted per-capita coefficient: the diagonal is -r_i / K_i "
                  "and an off-diagonal cell is (r_with - r_without) / x_j, so nothing here is "
                  "a convention and nothing needs scaling to match the rest"),
    "integrated": ("every cell is a fitted per-capita coefficient: the diagonal is -r_i / K_i and an "
                   "off-diagonal cell is fitted from the whole time course, as a parameter of "
                   "ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j dt), so nothing here is a "
                   "convention and nothing needs scaling to match the rest"),
}


def rates_csv(rates: dict, net: InteractionNetwork | None = None) -> str:
    """The growth rates as CSV: one row per organism, with how many values the median rests on.

    Beside the rate come the quantities a gLV coefficient is made of (#118): the estimator, the lag it
    fitted (empty for an estimator with none), and the monoculture carrying capacity with its unit and
    how many curves it rests on (empty where no curve reached a certified plateau), and how many curves
    gave none, so an empty capacity does not read as absence.
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["organism", "growth_rate", "unit", "replicates", "studies", "method", "lag",
                     "lag_method", "carrying_capacity", "capacity_unit", "capacity_curves",
                     "capacity_curves_left_out", "capacity_fall_from_peak", "capacity_medium",
                     "capacity_source"])
    order = labels(net) if net is not None else sorted(rates)
    for nid in order:
        rate = rates.get(nid)
        if rate is None:
            continue
        name = _label(net.nodes[nid]) if net is not None else nid
        capacity = rate.get("capacity")
        lag = rate.get("lag")
        # `replicates` means monoculture replicates, as it has since 0.2.0. A derivation that merges
        # fitted rows rather than replicate sets says how many replicates its rate stage had in
        # `replicates` and keeps the row count in `n`, which the report prints with `n_label`.
        replicates = rate.get("replicates")
        writer.writerow([name, _number(rate["rate"]), rate.get("unit", RATE_UNIT),
                         rate.get("n", "") if replicates is None else replicates,
                         " ".join(rate.get("studies", ())),
                         rate.get("method", ""), "" if lag is None else _number(lag),
                         rate.get("lag_method", "") if lag is not None else "",
                         "" if capacity is None else f"{capacity:g}",
                         rate.get("capacity_unit", "") if capacity is not None else "",
                         (rate.get("capacity_curves") if rate.get("capacity_curves") is not None
                          else rate.get("capacity_n", "")) if capacity is not None else "",
                         # an empty capacity reads as absence unless the curves that gave none are
                         # counted where the capacity itself is read (found 2026-10-06)
                         len(rate.get("capacity_left_out") or "") or "",
                         # a plateau is the peak of a curve that may have declined after it, so what the
                         # curves held at their last measurement travels with it (Karoline, 2026-10-07)
                         "" if rate.get("capacity_fall") is None else f"{rate['capacity_fall']:.4g}",
                         # one medium, never pooled: the diagonal and the cells beside it are of one
                         # environment (Karoline, 2026-10-07)
                         rate.get("capacity_medium", "") if capacity is not None else "",
                         # fitted with the partners, or -r/K at a measured plateau (#142 item 7)
                         rate.get("capacity_source", "")])
    return out.getvalue()


def _dropout_lines(net: InteractionNetwork) -> list:
    """What the README says about arcs that may act through a third species."""
    n = dropout_arcs(net)
    if not n:
        return ["  Every arc compares two organisms directly; none comes from a drop-out design."]
    return [f"  {n} ARC(S) COME FROM DROP-OUT DESIGNS, a community against the same community without one",
            "      member, so the effect may run through a third species, which a gLV coefficient is not",
            "      meant to include. Press gLV mode on the page, or untick Include drop-out communities in",
            "      Advanced settings, and derive again to leave them out."]


def _media_lines(net: InteractionNetwork) -> list:
    """What the README says about the environments behind the numbers."""
    names = media(net)
    if not names:
        return ["  The media these arcs were measured in are not recorded in this network."]
    if len(names) == 1:
        return [f"  Every arc was measured in one medium: {names[0]}."]
    return [f"  THESE ARCS COME FROM {len(names)} MEDIA, and a gLV simulation is of one environment:",
            *[f"      {name}" for name in names],
            "      Select one in grownet's second box (media, experiments or studies) and derive again to",
            "      keep a single environment."]


# ---- fitted gLV coefficients (#119) ----------------------------------------------------------------
#
# Karoline settled the entries on #116, from Craig's derivation and the math: the package stops holding
# effect sizes and holds coefficients in 1/(time x abundance).
#
#     A_ii = -r_i / K_i                     K_i: the monoculture carrying capacity (#118)
#     A_ij = r_i * (2^L - 1) / x_j_star     L: the log2 ratio of i's GROWTH RATE with j over without it
#                                           x_j_star: j's abundance over i's growth window (#118)
#
# So a package can only be built from a network derived with a growth rate as the growth property: `auc`
# and `max` cannot produce L. Abundances are never converted between units (Craig's partition, which she
# took): a cell mass conversion would have to be invented, while the dynamics are invariant to the unit,
# so the zip holds one matrix per abundance unit and says which pairs fell outside it.


class CannotConvert(ValueError):
    """The network cannot become coefficients: its arcs do not compare growth rates."""


RATE_METRIC_PREFIX = "growth_rate"
# a derivation that fits the coefficient itself rather than a ratio of a growth property (#127): its arcs
# already carry the quantity the package holds, so they need no ratio of rates
FITTED_METRIC_PREFIX = "integrated"


def _metrics(net: InteractionNetwork) -> list:
    """The growth properties the arcs of this network were compared on, in order."""
    seen = []
    for edge in net.edges:
        if edge.status == "absent" or (edge.strength is None and _extreme(edge) is None):
            continue
        name = edge.metric or ""
        if name not in seen:
            seen.append(name)
    return seen


def _per_arc(edge, fallback_rate: float | None = None) -> tuple:
    """(the coefficient one biculture arc gives, how it was obtained), or (None, "").

    `A_ij = (r_with - r_without) / x_j_star`, Karoline's formula written as a difference rather than a
    ratio (#123). Both rates are the arc's own, from the same comparison, and a set that did not grow
    carries 0, so an obligate or abolished pair is a measurement here rather than a floor or a stated
    extreme.

    A network saved before #123 carries no absolute rates, only the log2 ratio, so such an arc falls back
    to `r_i (2^L - 1) / x_j_star` with the organism's reported rate, which is the same number whenever
    that rate is the arc's own without-set rate. The README says when a package holds such a cell.
    """
    if edge.partner_abundance in (None, 0):
        return None, ""
    if edge.metric_with is not None and edge.metric_without is not None:
        return (edge.metric_with - edge.metric_without) / edge.partner_abundance, "rates"
    if edge.strength is not None and fallback_rate:
        return fallback_rate * (2 ** edge.strength - 1) / edge.partner_abundance, "ratio"
    return None, ""


def _pair_values(net: InteractionNetwork, rates: dict = None) -> tuple:
    """({pair: {"value", "unit", "censored", "arcs"}}, conflicts, unfitted).

    One entry per ordered pair: the median of the coefficients its arcs give, which is Karoline's merge
    rule (register item 14) applied to the converted numbers, and only within one abundance unit. A pair
    whose arcs disagree in sign is not merged and is returned in `conflicts`; a pair no arc could convert
    is returned in `unfitted` with the reason.
    """
    per_pair: dict = {}
    for edge in net.edges:
        if edge.status == "absent":
            continue
        quantified = edge.strength is not None
        censored = _extreme(edge) is not None
        # an arc can carry both its rates and no strength: the integrated form leaves `strength` None
        # whenever the fitted inhibition at least cancels the organism's own rate (log2 of a non-positive
        # number), which is the washout regime, so gating on `strength` alone dropped the strongest
        # inhibitions out of the matrix without naming them (found 2026-10-06).
        has_rates = edge.metric_with is not None and edge.metric_without is not None
        if not quantified and not censored and not has_rates:
            continue
        pair = (edge.target, edge.source)
        unit = edge.partner_abundance_unit or ""
        value, how = _per_arc(edge, ((rates or {}).get(edge.target) or {}).get("rate"))
        entry = per_pair.setdefault(pair, {"by_unit": {}, "reasons": [], "censored": False,
                                           "how": set(), "media": []})
        for name in (edge.medium or "").split("; "):
            if name and name not in entry["media"]:
                entry["media"].append(name)
        if value is None:
            actor, affected = _label(net.nodes[edge.source]), _label(net.nodes[edge.target])
            entry["reasons"].append(
                f"no abundance for {actor} over {affected}'s growth window"
                if edge.partner_abundance in (None, 0) else
                f"the rates behind this arc were not recorded (metric {edge.metric or 'unknown'})")
            continue
        entry["by_unit"].setdefault(unit, []).append(value)
        entry["censored"] = entry["censored"] or censored
        entry["how"].add(how)
    values, conflicts, unfitted = {}, [], []
    for pair, entry in per_pair.items():
        if not entry["by_unit"]:
            unfitted.append((pair, "; ".join(dict.fromkeys(entry["reasons"]))))
            continue
        unit = max(entry["by_unit"], key=lambda u: len(entry["by_unit"][u]))
        numbers = entry["by_unit"][unit]
        # the arcs of this pair counted in another unit are not merged into it and are not converted, so
        # they are named here. They used to disappear, against the README's promise that a pair outside a
        # matrix's unit is named (found 2026-10-06)
        for other, dropped in entry["by_unit"].items():
            if other != unit:
                unfitted.append((pair, f"{len(dropped)} arc(s) of this pair measure the actor in {other} "
                                       f"and the rest in {unit}; abundances are never converted, so they "
                                       "are left out of this cell"))
        if any(v > 0 for v in numbers) and any(v < 0 for v in numbers):
            conflicts.append(pair)
            continue
        values[pair] = {"value": statistics.median(numbers), "unit": unit,
                        "censored": entry["censored"], "arcs": len(numbers),
                        # the media behind this cell: arcs of a pair are merged by their median whatever
                        # medium each was measured in, and a cell that pools two environments is named
                        # rather than reading as one measurement (found 2026-10-06)
                        "media": list(entry["media"]),
                        "how": "ratio" if "ratio" in entry["how"] else "rates"}
    return values, conflicts, unfitted


def plateaus(net: InteractionNetwork) -> dict:
    """{organism: {"mine": its own plateau in co-culture, "unit": ..., "partners": {partner: its plateau}}}.

    The plateau balance of #123, which fits a self-limitation where a monoculture gave no certified
    plateau: at an organism's plateau beside its partners, `0 = r_i + A_ii x_i + sum_j A_ij x_j`, so
    `A_ii = -(r_i + sum_j A_ij x_j) / x_i`. Every abundance here is the measured plateau of a co-culture,
    the organism's own from its arcs and each partner's from the reverse arc, which a biculture always
    derives both of. Only plateaus in one abundance unit are put together.
    """
    plateau = {(e.target, e.source): (e.target_capacity, e.target_capacity_unit)
               for e in net.edges if e.status != "absent" and e.target_capacity is not None}
    out: dict = {}
    left_out: list = []
    for (target, source), (mine, unit) in sorted(plateau.items()):
        theirs, their_unit = plateau.get((source, target), (None, ""))
        if theirs is None:
            continue
        if their_unit != unit:
            left_out.append((f"{target} beside {source}",
                             f"its plateau is in {unit} and {source}'s in {their_unit}, so the balance "
                             "cannot be formed: abundances are never converted"))
            continue
        entry = out.setdefault(target, {"unit": unit, "partners": {}, "left_out": []})
        if entry["unit"] != unit:
            # the organism's first plateau fixed the unit, and this one is in another: named rather than
            # dropped on a bare `continue`, which lost it in silence while the partner still carried the
            # arc from its own side (Craig's agent on #133, #142 item 14)
            entry["left_out"].append(
                (f"{target} beside {source}",
                 f"this plateau is in {unit} and this organism's others in {entry['unit']}; left out "
                 "rather than converted"))
            continue
        # both plateaus of this co-culture, kept together: an organism beside two partners has a
        # different plateau of its own beside each, so a single "mine" taken from whichever arc came
        # first made the fitted diagonal depend on arc order (found 2026-10-06, Craig's agent on #128)
        entry["partners"][source] = {"mine": mine, "theirs": theirs}
    for entry in out.values():
        entry["left_out"] = sorted(entry["left_out"]) + left_out
    return out


def obligate_partners(net: InteractionNetwork) -> dict:
    """{organism: [(partner, its plateau beside the organism, the organism's own plateau)]}.

    The arcs that say an organism grows only with a partner: it did not grow in that comparison without
    it (`metric_without` is 0). Such an organism has no monoculture rate or capacity, and a gLV model
    says so with `r_i = 0` and a self-limitation fitted at the plateau it does reach beside the partner
    (#123). The partner's own plateau in the same co-culture is the reverse arc's, which a biculture
    always derives both of.
    """
    plateau = {(e.target, e.source): (e.target_capacity, e.target_capacity_unit)
               for e in net.edges if e.target_capacity is not None}
    out: dict = {}
    for edge in net.edges:
        if edge.status == "absent" or edge.metric_without != 0 or edge.metric_with in (None, 0):
            continue
        mine, unit = plateau.get((edge.target, edge.source), (None, ""))
        theirs, their_unit = plateau.get((edge.source, edge.target), (None, ""))
        if mine is None or theirs is None or unit != their_unit:
            continue
        out.setdefault(edge.target, []).append((edge.source, theirs, mine))
    return out


def abundance_units(net: InteractionNetwork, rates: dict = None) -> list:
    """The abundance units a package of this network would partition by, in order (#130).

    The units the organisms' own carrying capacities were measured in, and the units their partners were
    counted in, which are the two numbers a coefficient divides by. More than one means the package holds
    one matrix per unit, which the page says before a reader downloads it, since nothing is ever
    converted between them.
    """
    units = {rate.get("capacity_unit") for rate in (rates or {}).values() if rate.get("capacity")}
    units |= {edge.partner_abundance_unit for edge in net.edges
              if edge.partner_abundance is not None and edge.partner_abundance_unit}
    return sorted(u for u in units if u)


def coefficient_unit(rate_unit: str, abundance_unit: str) -> str:
    """The unit of a coefficient: 1/(time x abundance), from the rate's "1/h" and the abundance unit."""
    time = (rate_unit or RATE_UNIT).removeprefix("1/") or "h"
    return f"1/({time} x {abundance_unit})"


def unit_file(abundance_unit: str) -> str:
    """The abundance unit as part of a file name: "Cells/mL" becomes "Cells_per_mL"."""
    safe = abundance_unit.replace("/", "_per_")
    return "".join(c if c.isalnum() or c in "_-." else "_" for c in safe)


def coefficients(net: InteractionNetwork, rates: dict) -> dict:
    """The network and its rates as fitted gLV coefficients, one matrix per abundance unit (#119).

    {"matrices": [{"abundance_unit", "unit", "organisms", "ids", "matrix", "cells", "conflicts"}],
     "left_out": [(organism, why)], "pairs_left_out": [(affected, actor, why)],
     "across_units": [(affected, actor, why)], "obligate_rows": [(organism, partner)],
     "censored_cells": [(affected, actor)], "rate_methods", "lag_methods", "metric"}

    **Every number is a measurement** (#123): a cell is `(r_with - r_without) / x_j_star` from one arc's
    own rates, merged across the arcs of a pair by their median, and a diagonal is `-r_i / K_i` from the
    monoculture. An organism that grows only with a partner has `r_i = 0` by measurement and its
    self-limitation from the plateau it reaches beside that partner, so an obligate pair needs no floor
    and no stated extreme. An organism or pair that still cannot be fitted is named rather than given a
    number. Raises `CannotConvert` when the arcs do not compare growth rates.
    """
    metrics = _metrics(net)
    not_rates = [m for m in metrics
                 if not (m or "").startswith((RATE_METRIC_PREFIX, FITTED_METRIC_PREFIX))]
    if not_rates:
        raise CannotConvert(
            f"these arcs compare {', '.join(repr(m) for m in not_rates)}, and a gLV coefficient needs the "
            f"log2 ratio of a growth rate: derive with the {RATE_METRIC_PREFIX} growth property (gLV mode "
            "on the page, or --metric growth_rate) and build the package again")
    values, conflicts, unfitted = _pair_values(net, rates)
    obligate = obligate_partners(net)
    plateau_of = plateaus(net)
    # the organisms an arc says grow only with a partner, whether or not a plateau was certified for them
    only_with = {e.target for e in net.edges if e.status != "absent" and e.metric_without == 0
                 and e.metric_with not in (None, 0)}
    left_out, pairs_left_out, across, rows_fitted = [], [], [], []
    unusable, plateau_rows = [], []

    # an organism belongs to the matrix of the unit its own abundance was measured in: its monoculture
    # carrying capacity, or, for one that grows only with a partner, its plateau beside that partner
    blocks: dict = {}
    for nid in labels(net):
        name = _label(net.nodes[nid])
        rate = rates.get(nid) or {}
        if rate.get("rate") is not None and rate.get("capacity") is not None:
            blocks.setdefault(rate.get("capacity_unit", ""), []).append(nid)
            continue
        if rate.get("rate") is not None and nid in plateau_of:
            blocks.setdefault(plateau_of[nid]["unit"], []).append(nid)
            plateau_rows.append((name, "its co-culture plateau"))
            continue
        if nid in obligate:
            # r_i = 0 by measurement: it did not grow alone. Its unit is the one its plateau beside the
            # partner was measured in.
            #
            # The invariant this relies on, one capacity unit per organism, is enforced upstream in
            # `derive._collect_capacity`, which pins an organism's unit on the first plateau and names
            # every later one in another unit as left out rather than converted. It is NOT enforced by
            # `obligate_partners`, which the comment here used to credit: that function matches units
            # within a pair and never compares one partner against another (Craig's agent on #133).
            #
            # A network does not always come from a fresh derivation: `from_dict` reads one from a
            # published artifact and drops fields it does not know, so a file could carry plateaus of one
            # organism in two units. This used to pick a unit by edge order and say nothing, so it now
            # refuses and names it, as everything else here refuses rather than guesses (#142 item 14).
            units = sorted({e.target_capacity_unit for e in net.edges
                            if e.target == nid and e.target_capacity is not None
                            and e.target_capacity_unit})
            if len(units) > 1:
                left_out.append((name, f"its plateaus are in {', '.join(units)}: one organism's "
                                       "capacity has one unit, and this network carries two, so which "
                                       "matrix it belongs in is not known and none is guessed"))
                continue
            blocks.setdefault(units[0] if units else "", []).append(nid)
            rows_fitted.append((name, _label(net.nodes[obligate[nid][0][0]])))
            continue
        if nid in only_with:
            left_out.append((name, "it grows only with a partner and reached no certified plateau beside "
                                   "one, in the same abundance unit as that partner, so its "
                                   "self-limitation cannot be fitted"))
        elif rate.get("rate") is None:
            left_out.append((name, "no growth rate, and no arc saying it grows only with a partner, so "
                                   "neither its own limitation nor the effect of anything on it can be "
                                   "fitted"))
        else:
            left_out.append((name, "no carrying capacity from a curve that reached stationary phase, so "
                                   "its self-limitation is not fitted"))

    matrices = []
    for abundance_unit, ids in sorted(blocks.items()):
        times = {(rates[nid].get("unit") or RATE_UNIT) for nid in ids if nid in rates} or {RATE_UNIT}
        rate_unit = sorted(times)[0]
        keep = []
        for nid in ids:
            own = (rates.get(nid) or {}).get("unit")
            if own and own != rate_unit:
                left_out.append((_label(net.nodes[nid]),
                                 f"its growth rate is in {own}, and this matrix in {rate_unit}; left out "
                                 "rather than converted"))
                continue
            keep.append(nid)
        names = [_label(net.nodes[nid]) for nid in keep]
        table, filled = [], 0
        pooled: list = []
        for i, affected in enumerate(keep):
            rate = rates.get(affected) or {}
            row = []
            for j, actor in enumerate(keep):
                if i == j:
                    row.append(0.0)        # set below, once the row's partners are known
                    continue
                entry = values.get((affected, actor))
                if entry is None:
                    row.append(0.0)
                    continue
                label_pair = (_label(net.nodes[affected]), _label(net.nodes[actor]))
                if entry["unit"] != abundance_unit:
                    pairs_left_out.append((*label_pair,
                                           f"{label_pair[1]}'s abundance beside {label_pair[0]} is in "
                                           f"{entry['unit']}, and this matrix is in {abundance_unit}; "
                                           "left out rather than converted"))
                    row.append(0.0)
                    continue
                row.append(entry["value"])
                filled += 1
                if len(entry.get("media") or ()) > 1:
                    pooled.append((*label_pair, ", ".join(entry["media"])))
            if rate.get("rate") is not None and rate.get("capacity"):
                row[i] = -rate["rate"] / rate["capacity"]
            else:
                # the plateau balance: at the organism's plateau beside its partners,
                # 0 = r_i + A_ii x_i + sum_j A_ij x_j, so A_ii = -(r_i + sum_j A_ij x_j) / x_i. For one
                # that grows only with a partner r_i is 0, measured (#123); for one with a rate and no
                # certified monoculture plateau it is its own rate (#124 item 2).
                balance = plateau_of.get(affected) or {}
                own_rate = rate.get("rate") or 0.0
                # one equation per co-culture, each from that co-culture's own two plateaus, merged by
                # their median as a pair's arcs are (register item 14)
                fitted = []
                for partner, both in (balance.get("partners") or {}).items():
                    mine, theirs = both["mine"], both["theirs"]
                    if not mine:
                        continue
                    effect = next((row[k] for k, other in enumerate(keep) if other == partner), 0.0)
                    fitted.append(-(own_rate + effect * theirs) / mine)
                row[i] = statistics.median(fitted) if fitted else 0.0
                if row[i] >= 0:
                    unusable.append((_label(net.nodes[affected]),
                                     "its self-limitation comes out at or above zero at its co-culture "
                                     "plateau, where its partners' effect outweighs its own rate, so no "
                                     "limitation can be fitted for it"))
            table.append(row)
        here = set(keep)
        block_media = []
        for edge in net.edges:
            if edge.status == "absent" or edge.source not in here or edge.target not in here:
                continue
            for name in (edge.medium or "").split("; "):
                if name and name not in block_media:
                    block_media.append(name)
        matrices.append({"abundance_unit": abundance_unit, "media": block_media or media(net),
                         "unit": coefficient_unit(rate_unit, abundance_unit),
                         "rate_unit": rate_unit, "organisms": names, "ids": keep, "matrix": table,
                         "cells": filled, "pooled_media": pooled,
                         "conflicts": [(_label(net.nodes[a]), _label(net.nodes[b]))
                                       for a, b in conflicts if a in keep and b in keep],
                         "file": f"interaction_matrix.{unit_file(abundance_unit)}.csv"})

    # a pair whose two organisms sit in different matrices has no cell in either
    where = {nid: block["abundance_unit"] for block in matrices for nid in block["ids"]}
    for affected, actor in values:
        if affected in where and actor in where and where[affected] != where[actor]:
            across.append((_label(net.nodes[affected]), _label(net.nodes[actor]),
                           f"{_label(net.nodes[actor])} is counted in {where[actor]} and "
                           f"{_label(net.nodes[affected])} in {where[affected]}, so this effect is in "
                           "neither matrix"))
        elif affected not in where or actor not in where:
            missing = [_label(net.nodes[nid]) for nid in (affected, actor)
                       if nid not in where and nid in net.nodes]
            if missing:
                across.append((_label(net.nodes[affected]), _label(net.nodes[actor]),
                               f"{' and '.join(missing)} could not be fitted, so this effect is in no "
                               "matrix"))
    for (affected, actor), why in unfitted:
        pairs_left_out.append((_label(net.nodes[affected]), _label(net.nodes[actor]),
                               f"{why}, so the per-capita effect cannot be fitted"))
    # an organism whose plateau balance gave no usable limitation leaves the matrix it was put in
    for name, why in unusable:
        left_out.append((name, why))
        plateau_rows[:] = [row for row in plateau_rows if row[0] != name]
        rows_fitted[:] = [row for row in rows_fitted if row[0] != name]
        for block in matrices:
            if name in block["organisms"]:
                keep_at = [k for k, other in enumerate(block["organisms"]) if other != name]
                block["organisms"] = [block["organisms"][k] for k in keep_at]
                block["ids"] = [block["ids"][k] for k in keep_at]
                block["matrix"] = [[block["matrix"][i][j] for j in keep_at] for i in keep_at]
    matrices = [block for block in matrices if block["organisms"]]
    # the equilibrium each block implies, which the package defines as its own meaning and used to leave
    # the reader to compute. It is worked out here, after every organism that leaves a matrix has left it:
    # computed inside the loop above it described the block before the removal, so a block that dropped a
    # row carried an equilibrium of the wrong length, which named an organism it does not hold and raised
    # on the package's own README (found 2026-10-06, round 2 of the review).
    from .steady import MAX_EQUILIBRIUM_CONDITION, condition_of, solve
    for block in matrices:
        rate_of = [(rates.get(nid) or {}).get("rate") for nid in block["ids"]]
        block["equilibrium"], block["not_above_zero"], block["equilibrium_why_not"] = None, [], ""
        block["equilibrium_condition"] = None
        if not all(r is not None for r in rate_of):
            block["equilibrium_why_not"] = "not every organism in this matrix has a growth rate"
            continue
        # how well the system is conditioned decides whether its solution is worth printing at all: a
        # near-singular block used to return a number like 1e24 and have it reported as a steady state,
        # and a change of 0.05 percent in one coefficient flipped the verdict (#142 item 9)
        condition = condition_of(block["matrix"])
        block["equilibrium_condition"] = None if condition == float("inf") else condition
        if condition > MAX_EQUILIBRIUM_CONDITION:
            block["equilibrium_why_not"] = (
                f"this matrix is too ill-conditioned to solve: its condition number is "
                f"{'infinite' if condition == float('inf') else format(condition, '.3g')}, above the "
                f"{MAX_EQUILIBRIUM_CONDITION:.0e} this tool will stand behind, so an equilibrium computed "
                "from it would carry fewer digits than it printed")
            continue
        answer = solve([row[:] for row in block["matrix"]], [-r for r in rate_of])
        if answer is None:
            block["equilibrium_why_not"] = "this matrix is singular, so it has no single equilibrium"
            continue
        block["equilibrium"] = answer
        block["not_above_zero"] = [name for name, value
                                   in zip(block["organisms"], answer, strict=True) if value <= 0]
    return {"matrices": matrices, "left_out": left_out, "pairs_left_out": pairs_left_out,
            "across_units": across, "floors": [],
            "from_absolute_rates": all(entry["how"] == "rates" for entry in values.values()),
            "from_the_ratio": [(_label(net.nodes[a]), _label(net.nodes[b]))
                               for (a, b), entry in values.items() if entry["how"] == "ratio"],
            "obligate_rows": list(rows_fitted), "plateau_rows": list(plateau_rows),
            "censored_cells": [(_label(net.nodes[a]), _label(net.nodes[b]))
                               for (a, b), entry in values.items() if entry["censored"]],
            "metric": metrics[0] if metrics else "",
            "rate_methods": sorted({r.get("method", "") for r in rates.values() if r.get("method")}),
            "lag_methods": sorted({r.get("lag_method", "") for r in rates.values()
                                   if r.get("lag") is not None and r.get("lag_method")})}


def _coefficient(value: float) -> str:
    """A coefficient as text: these are small numbers, so they keep four significant digits."""
    return "0" if value == 0 else f"{value:.4g}"


def coefficient_csv(block: dict) -> str:
    """One matrix of coefficients as CSV: the header row and the first column are the organisms."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["", *block["organisms"]])
    for name, row in zip(block["organisms"], block["matrix"], strict=True):
        writer.writerow([name, *(_coefficient(v) for v in row)])
    return out.getvalue()


def _rate_method_lines(got: dict) -> list:
    """What the README says about the estimator behind r, and what choosing another one would move."""
    methods = got["rate_methods"]
    named = ", ".join(methods) if methods else "not recorded"
    merge = ("the median over the fitted rows, each row's rate the median over that organism's "
             "monoculture replicates" if any(str(m).startswith("integrated") for m in methods)
             else "median over replicates and studies")
    lines = [f"  Growth rates: {named}, {merge}, batch monocultures only.",
             "      The estimator sets where this matrix settles as well as how fast a simulation",
             f"      runs. The diagonal's r_i is {merge} while each",
             "      off-diagonal uses its own comparison's two rates; x_j_star is the mean over the",
             "      window that estimator fitted in; and the rate guards reject different curves. So",
             "      the equilibrium below belongs to this estimator. The Growth rate method setting",
             "      chooses it.",
             ]
    if got["lag_methods"]:
        lines.append(f"  Lag: {', '.join(got['lag_methods'])}, reported beside each rate in "
                     "growth_rates.csv. A gLV model has no lag term, so a simulation that should start "
                     "after it")
        lines.append("      starts at that time rather than at 0.")
    return lines


def readme_from(got: dict, net: InteractionNetwork, rates: dict) -> str:
    """What a reader has to know before feeding the converted files to a simulator (#119)."""
    meta = net.meta
    absence = meta.get("absence", {})
    units = [block["unit"] for block in got["matrices"]]
    lines = [
        f"{brand.NAME} {meta.get('tool_version', '')}: fitted parameters for a generalized "
        "Lotka-Volterra simulation",
        f"derived {meta.get('derived_at', '')} from {meta.get('source_db', 'mGrowthDB')}",
        "",
        "FILES",
        "  interaction_matrix.<unit>.csv  one matrix per abundance unit, named after it; the header row",
        "                          and the first column are the organisms",
        "  growth_rates.csv        one growth rate per organism, with the estimator, the lag and the",
        "                          monoculture carrying capacity behind it",
        "",
        "THE COEFFICIENTS",
        "  A[i][j] is the effect of j on i, so rows are affected and columns are the actor:",
        "      dx_i/dt = x_i * ( r_i + sum_j A[i][j] * x_j )",
        "  EVERY CELL IS A PER-CAPITA COEFFICIENT, in " + (", ".join(units) if units else "1/(time x "
        "abundance)") + ". Nothing here is a",
        "      convention, and nothing needs scaling to be in the same units as the rest.",
        "  A simulation of these numbers can still grow without bound, and a solver then returns NA: it",
        "      happens when two organisms are fitted as facilitating each other more strongly than each",
        "      limits itself, which these measurements then say, rather than a convention. Scaling the",
        "      cells would hide that rather than settle it; the equilibrium of the fit is the solution of",
        "      A x = -r, and a negative entry there means this fit has no steady state with every",
        "      organism above zero. A simulation can still settle with fewer of them.",
        "  The diagonal is fitted: A[i][i] = -r_i / K_i, with K_i the organism's own monoculture carrying",
        "      capacity, the plateau of the curves that reached stationary phase. An organism on its own",
        "      therefore settles at K_i. Where no monoculture of it reached a certified plateau, its own",
        "      plateau beside its partners fits the same balance, 0 = r_i + A[i][i] x_i + sum_j A[i][j] x_j",
        "      there, and the organism is named under SELF-LIMITATION FITTED AT A CO-CULTURE PLATEAU.",
        # in the derivation's own words: the comparison's formula is not what an integrated cell holds
        *OFF_DIAGONAL[derivation_of(net)],
        "  ABUNDANCES ARE NEVER CONVERTED BETWEEN UNITS: a cell mass conversion would have to be",
        "      invented, while the dynamics are the same in any unit, so each unit has its own matrix and",
        "      the pairs that fall outside it are named below.",
        f"  An empty cell is 0. An arc below the absence threshold (k = {absence.get('k', '')}) is also 0:",
        "      the threshold judged it no interaction.",
        "  Arcs of one ordered pair are merged across conditions and studies by their median; a pair whose",
        "      arcs disagree in sign is left at 0 and named below.",
        *_media_lines(net),
        *_dropout_lines(net),
        *_rate_method_lines(got),
        "",
        "WHAT THIS MODEL ASSUMES",
        *MODEL_ASSUMPTIONS,
        "",
        "MATRICES",
    ]
    for block in got["matrices"]:
        lines.append(f"  {block['file']}: {len(block['organisms'])} organism(s), "
                     f"{block['cells']} fitted cell(s), every cell in {block['unit']}"
                     + (f", measured in {', '.join(block['media'])}" if block.get("media") else ""))
        # the equilibrium of this matrix, worked out here rather than left to the reader
        if block.get("equilibrium") is None:
            # the reason, not a bare "not computed": too ill-conditioned, singular, or a missing rate
            lines.append("      where it settles: NOT COMPUTED. "
                         + (block.get("equilibrium_why_not")
                            or "an organism here has no rate"))
        elif block.get("not_above_zero"):
            lines.append("      where it settles: NOWHERE WITH EVERY ORGANISM ABOVE ZERO. The solution of "
                         "A x = -r puts")
            lines.append("          " + ", ".join(block["not_above_zero"]) + " at or below zero, so a "
                         "simulation of this matrix")
            lines.append("          settles with fewer organisms than it holds, or grows without bound.")
        else:
            condition = block.get("equilibrium_condition")
            lines.append("      where it settles (the solution of A x = -r, in "
                         f"{block['abundance_unit']}): "
                         + ", ".join(f"{name} {value:.4g}" for name, value
                                     in zip(block["organisms"], block["equilibrium"], strict=True))
                         + (f" [condition number {condition:.3g}: a relative change in the "
                            "coefficients moves these numbers by up to that factor]"
                            if condition else ""))
    if not got["matrices"]:
        lines.append("  NONE: no organism had both a growth rate and a carrying capacity (see below).")
    lines.append("")
    pooled = [row for block in got["matrices"] for row in (block.get("pooled_media") or ())]
    if pooled:
        lines += ["CELLS MERGED ACROSS MEDIA",
                  "  A pair's arcs are merged by their median whatever medium each was measured in, so",
                  "  these cells pool more than one environment. A gLV simulation is of one environment:",
                  "  hold the search to one medium with the second box to keep them apart."]
        lines += [f"      {actor} on {affected}: {media}" for affected, actor, media in pooled]
        lines.append("")
    if got.get("plateau_rows"):
        lines += ["SELF-LIMITATION FITTED AT A CO-CULTURE PLATEAU",
                  "  These organisms reached no certified plateau in monoculture, so -r_i / K_i has no K_i",
                  "  for them. Their own plateau beside their partners fits the same balance instead:",
                  "  0 = r_i + A[i][i] x_i + sum_j A[i][j] x_j there, with every abundance measured."]
        lines += [f"      {who}: {why}" for who, why in got["plateau_rows"]]
        lines.append("")
    if got.get("obligate_rows"):
        lines += ["ORGANISMS THAT GROW ONLY WITH A PARTNER",
                  "  These did not grow alone in the comparisons behind this package, so their own rate is",
                  "  0 by measurement and their self-limitation is fitted at the plateau they reach beside",
                  "  the partner: 0 = A[i][i] x_i + sum_j A[i][j] x_j there."]
        lines += [f"      {who} grows only with {partner}" for who, partner in got["obligate_rows"]]
        lines.append("")
    if got.get("from_the_ratio"):
        lines += ["CELLS TAKEN FROM THE LOG2 RATIO, NOT FROM TWO RATES",
                  "  These arcs come from a network derived before the two absolute rates were recorded,",
                  "  so their cells use r_i (2^L - 1) / x_j with the organism's reported rate, which is",
                  "  the same number whenever that rate is the arc's own rate without the actor. Derive",
                  "  again to have them from the measurements themselves (actor on affected):"]
        lines += [f"      {actor} on {affected}" for affected, actor in got["from_the_ratio"]]
        lines.append("")
    if got.get("censored_cells"):
        lines += ["CELLS FROM A COMPARISON WHERE ONE SIDE DID NOT GROW",
                  "  One of the two rates behind these cells is 0, measured: the affected organism grew",
                  "  only with the actor, or only without it. The formula takes that as it is, so these",
                  "  are measurements and not floors or stated extremes, and they enter the median of",
                  "  their pair like any other measurement, which register item 14 kept them out of while",
                  "  they were conventions (actor on affected):"]
        lines += [f"      {actor} on {affected}" for affected, actor in got["censored_cells"]]
        lines.append("")
    lines.append("WHAT IS NOT IN HERE")
    conflicts = [pair for block in got["matrices"] for pair in block["conflicts"]]
    if conflicts:
        lines.append("  These pairs have arcs of opposite sign, in different conditions or studies, so they")
        lines.append("  are left at 0 rather than averaged (actor on affected):")
        lines += [f"      {actor} on {affected}" for affected, actor in dict.fromkeys(conflicts)]
    else:
        lines.append("  No pair had arcs of opposite sign.")
    if got["left_out"]:
        lines.append("  These organisms are in no matrix, because a coefficient of theirs cannot be fitted:")
        lines += [f"      {name}: {why}" for name, why in got["left_out"]]
    else:
        lines.append("  Every organism of the network is in a matrix.")
    if got["pairs_left_out"]:
        lines.append("  These effects are left at 0 (actor on affected):")
        lines += [f"      {actor} on {affected}: {why}"
                  for affected, actor, why in dict.fromkeys(got["pairs_left_out"])]
    if got["across_units"]:
        lines.append("  These effects are in no matrix:")
        lines += [f"      {actor} on {affected}: {why}"
                  for affected, actor, why in dict.fromkeys(got["across_units"])]
    lines += ["", "Interactions are derived, not measured: see the report beside this file for what was",
              "skipped and why."]
    return "\n".join(lines) + "\n"


# The same parameters as the zip, for a program rather than a reader: the caveats travel as data beside
# the numbers, so code can act on them instead of a person having to read the README first (Karoline,
# 2026-10-03: "The problem is the README: caveats such as the placeholders for obligates/abolished taxa
# have to reach the user"). The README text travels with it, so nothing is lost either way.
# The payload moved to v1 with #120: `matrices` replaced `interactions`, one per abundance unit, and the
# numbers became fitted coefficients rather than log2 means, so the fields changed meaning and a version
# is a promise about content (Craig's rule, #71).
GLV_FORMAT = "grownet.glv/v1"
PREVIOUS_GLV_FORMATS = ("grownet.glv/v0",)


def glv_payload(net: InteractionNetwork, rates: dict, extra: dict = None) -> dict:
    """The gLV parameters as one JSON-ready document (`GLV_FORMAT`), the same numbers as the zip (#120).

    `matrices` holds one matrix per abundance unit, each with its `organisms`, its `interactions` (rows
    affected, columns the actor, the fitted diagonal), its unit and the media its arcs came from, because
    nothing is converted between abundance units. `growth_rate_detail` carries each rate with what a
    coefficient is made of beside it: the estimator, the lag and the carrying capacity. `caveats` holds,
    as data, everything the README says in prose: the cells from a comparison where one side did not grow,
    the pairs left at 0 for disagreeing in sign, the organisms and effects that could not be fitted at
    all, the rows fitted at a plateau, the absence threshold, the media, the drop-out count, and the
    standing note that a fit can still have no bounded state. The README travels too, so neither route
    loses what the other carries.

    `extra` is {name: text} the caller computed, which is how the steady-state check of #125 travels here
    as it does in the zip. Raises `CannotConvert` when the arcs cannot give coefficients.
    """
    got = coefficients(net, rates)
    meta = net.meta
    order = labels(net)
    missing = [_label(net.nodes[nid]) for nid in order if nid not in rates
               or (rates[nid] or {}).get("rate") is None]
    units = {rates[nid].get("unit", RATE_UNIT) for nid in order if nid in rates}
    return {
        "format": GLV_FORMAT,
        "tool": meta.get("tool", brand.NAME),
        "tool_version": meta.get("tool_version", ""),
        "derived_at": meta.get("derived_at", ""),
        "source_db": meta.get("source_db", "mGrowthDB"),
        "matrices": [{"abundance_unit": block["abundance_unit"], "unit": block["unit"],
                      "organisms": list(block["organisms"]), "interactions": block["matrix"],
                      "media": list(block["media"]), "cells": block["cells"], "file": block["file"],
                      # where this matrix settles, so a reader does not have to solve it to find out
                      # that it settles nowhere with every organism above zero
                      "equilibrium": (list(block["equilibrium"])
                                      if block.get("equilibrium") is not None else None),
                      "equilibrium_condition": block.get("equilibrium_condition"),
                      "equilibrium_why_not": block.get("equilibrium_why_not", ""),
                      "not_above_zero": list(block.get("not_above_zero") or []),
                      "pooled_media": [list(row) for row in (block.get("pooled_media") or ())]}
                     for block in got["matrices"]],
        "growth_rate_unit": units.pop() if len(units) == 1 else "",
        "growth_rate_detail": [
            {"organism": _label(net.nodes[nid]), "rate": rates[nid]["rate"],
             "unit": rates[nid].get("unit", RATE_UNIT), "replicates": rates[nid].get("n"),
             "studies": list(rates[nid].get("studies", ())),
             "per_study": dict(rates[nid].get("per_study", {})),
             "method": rates[nid].get("method", ""), "lag": rates[nid].get("lag"),
             "lag_method": rates[nid].get("lag_method", ""),
             "carrying_capacity": rates[nid].get("capacity"),
             "carrying_capacity_unit": rates[nid].get("capacity_unit", ""),
             "carrying_capacity_curves": rates[nid].get("capacity_n"),
             "carrying_capacity_left_out": [list(row) for row in
                                            (rates[nid].get("capacity_left_out") or [])],
             "carrying_capacity_media": list(rates[nid].get("capacity_media") or ()),
             "carrying_capacity_medium": rates[nid].get("capacity_medium", ""),
             "carrying_capacity_other_media": list(rates[nid].get("capacity_other_media") or ()),
             "carrying_capacity_fall_from_peak": rates[nid].get("capacity_fall"),
             "carrying_capacity_source": rates[nid].get("capacity_source", "")}
            for nid in order if nid in rates and (rates[nid] or {}).get("rate") is not None],
        "caveats": {
            # in the derivation's own words (#142 item 6): the comparison's formula is not what an
            # integrated cell holds, and the R package prints this text rather than one of its own
            "coefficients": CAVEAT_COEFFICIENTS[derivation_of(net)],
            "derivation": derivation_of(net),
            "diagonal": "fitted: -r_i / K_i, with K_i the organism's own plateau",
            # the assumptions of the form itself, so the R object and any other consumer carry them too
            "model_assumptions": {
                "constant_coefficients": (
                    "every coefficient is constant in time. In batch culture the medium is consumed and "
                    "metabolites accumulate, so the effect one organism has on another can change in "
                    "size and in sign along the growth curve; a cell is the average over the interval "
                    "that was fitted, and each arc's fit_window_share says what share of the measured "
                    "course that interval covers"),
                "pairwise_only": (
                    "interactions are pairwise and add up: the effect of j on i is taken to be the same "
                    "whoever else is present. A higher-order interaction, where a third organism changes "
                    "how the first two affect each other, has no term in this model, and every cell here "
                    "was measured between two organisms"),
            },
            "units": ("one matrix per abundance unit: abundances are never converted between units, since "
                      "a cell mass conversion would have to be invented, and no effect between organisms "
                      "counted differently was measured"),
            "abundance_units": sorted({block["abundance_unit"] for block in got["matrices"]}),
            "unbounded": ("a fit can have no bounded state: when two organisms are fitted as facilitating "
                          "each other more than each limits itself, a simulation grows without bound and "
                          "a solver returns NA. The equilibrium of a fit is the solution of A x = -r, and "
                          "a negative entry there means there is no steady state with every organism "
                          "above zero, although a simulation can settle with fewer of them"),
            "censored": ("one of the two rates behind these cells is 0, measured: the affected organism "
                         "grew only with the actor, or only without it. The formula takes that as it is, "
                         "so they are measurements and not floors or stated extremes"),
            "censored_cells": [{"affected": affected, "actor": actor}
                               for affected, actor in got["censored_cells"]],
            "sign_conflicts": [{"affected": affected, "actor": actor}
                               for block in got["matrices"] for affected, actor in block["conflicts"]],
            "left_out": [list(row) for row in got["left_out"]],
            "pairs_left_out": [list(row) for row in got["pairs_left_out"]],
            "across_units": [list(row) for row in got["across_units"]],
            "obligate_rows": [list(row) for row in got.get("obligate_rows", [])],
            "plateau_rows": [list(row) for row in got.get("plateau_rows", [])],
            "from_the_ratio": [list(row) for row in got.get("from_the_ratio", [])],
            "media": media(net),
            "dropout_arcs": dropout_arcs(net),
            "absence_k": meta.get("absence", {}).get("k"),
            "without_a_rate": missing,
            "rate_methods": got["rate_methods"],
            "lag_methods": got["lag_methods"],
            "counts": counts(net),
        },
        "readme": readme_from(got, net, rates),
        "files": dict(extra or {}),
        "studies": [{"id": sid, "citation": study.citation or sid, "url": study.url,
                     "license": study.license} for sid, study in sorted(net.studies.items())],
        "settings": dict(meta.get("settings", {})),
    }


def glv_package(net: InteractionNetwork, rates: dict, extra: dict = None) -> bytes:
    """The zip a simulator is handed: one matrix of coefficients per abundance unit, the rates and the
    README (#119). Raises `CannotConvert` when the arcs do not compare growth rates.

    `extra` is {file name: text} the caller computed, which is how the steady-state check of #125 travels
    in the package without this module having to read a chemostat.
    """
    got = coefficients(net, rates)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for block in got["matrices"]:
            archive.writestr(block["file"], coefficient_csv(block))
        archive.writestr("growth_rates.csv", rates_csv(rates, net))
        archive.writestr("README.txt", readme_from(got, net, rates))
        for name, text in (extra or {}).items():
            archive.writestr(name, text)
    return buffer.getvalue()
