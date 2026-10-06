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

DIAGONAL = -1.0           # self-limitation, by convention (Karoline, 2026-10-03)
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
    """+EXTREME, -EXTREME, or None: the convention value of an arc that has no ratio."""
    if edge.strength is not None or edge.status == "absent":
        return None
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


def by_convention(net: InteractionNetwork) -> list:
    """The cells that hold `EXTREME` rather than a measured value, as (affected, actor, value) labels.

    These are the pairs whose only arcs are obligate or abolished: no ratio exists, so the cell carries
    the convention. The README names them, since a reader has to know which numbers were measured.
    """
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

    `diagonal` None leaves the diagonal at 0, which is the plain adjacency matrix; the gLV package passes
    DIAGONAL.
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
    """How a reported rate was obtained, recorded in every network that carries rates."""
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


def rates_csv(rates: dict, net: InteractionNetwork | None = None) -> str:
    """The growth rates as CSV: one row per organism, with how many values the median rests on.

    Beside the rate come the quantities a gLV coefficient is made of (#118): the estimator, the lag it
    fitted (empty for an estimator with none), and the monoculture carrying capacity with its unit and
    how many curves it rests on (empty where no curve reached a certified plateau).
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["organism", "growth_rate", "unit", "replicates", "studies", "method", "lag",
                     "lag_method", "carrying_capacity", "capacity_unit", "capacity_curves"])
    order = labels(net) if net is not None else sorted(rates)
    for nid in order:
        rate = rates.get(nid)
        if rate is None:
            continue
        name = _label(net.nodes[nid]) if net is not None else nid
        capacity = rate.get("capacity")
        lag = rate.get("lag")
        writer.writerow([name, _number(rate["rate"]), rate.get("unit", RATE_UNIT),
                         rate.get("n", ""), " ".join(rate.get("studies", ())),
                         rate.get("method", ""), "" if lag is None else _number(lag),
                         rate.get("lag_method", "") if lag is not None else "",
                         "" if capacity is None else f"{capacity:g}",
                         rate.get("capacity_unit", "") if capacity is not None else "",
                         rate.get("capacity_n", "") if capacity is not None else ""])
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


def readme(net: InteractionNetwork, rates: dict, conflicts: list, missing: list, convention=()) -> str:
    """What a reader has to know before feeding these two files to a simulator."""
    meta = net.meta
    absence = meta.get("absence", {})
    count = counts(net)
    lines = [
        f"{brand.NAME} {meta.get('tool_version', '')}: parameters for a generalized Lotka-Volterra "
        "simulation",
        f"derived {meta.get('derived_at', '')} from {meta.get('source_db', 'mGrowthDB')}",
        "",
        "FILES",
        "  interaction_matrix.csv  a square matrix; the header row and the first column are the organisms",
        "  growth_rates.csv        one growth rate per organism, with how many values it rests on, and",
        "                          beside it the estimator, the lag it fitted, and the monoculture",
        "                          carrying capacity with its unit",
        "",
        "CONVENTIONS",
        "  A[i][j] is the effect of j on i, so rows are affected and columns are the actor:",
        "      dx_i/dt = x_i * ( r_i + sum_j A[i][j] * x_j )",
        f"  The diagonal is {_number(DIAGONAL)} by convention (self-limitation). It is not a scale for the",
        "      rest of the matrix.",
        "  A cell holds the log2 mean of the growth comparison: log2(growth with the actor) minus",
        "      log2(growth without it), merged across conditions and studies by its median.",
        "      IT IS AN EFFECT SIZE, NOT A FITTED gLV COEFFICIENT. A gLV coefficient is a per-capita effect",
        "      in absolute units; scale these numbers for your model rather than using them unchanged.",
        f"  An empty cell is 0. An arc below the absence threshold (k = {absence.get('k', '')}) is also 0:",
        "      the threshold judged it no interaction.",
        f"  One cell per ordered pair: this network's {count['arcs']} arc(s) make {count['cells']} cell(s) "
        f"over {count['organisms']} organism(s).",
        *_media_lines(net),
        *_dropout_lines(net),
        f"  An obligate interaction (the affected organism grows only with the actor) is {_number(EXTREME)} "
        "and an abolished",
        f"      one (it grows only without the actor) is {_number(-EXTREME)}: no ratio exists for them, "
        "because one side did not",
        "      grow at all, so these are stated extremes, not measurements. They do not enter the median "
        "of the",
        "      arcs that do have a ratio; they set a cell only when no arc of that pair was quantified.",
        f"  Cells are often stronger than the {_number(DIAGONAL)} on the diagonal, a partner outweighing "
        "an organism's own",
        "      self-limitation. A simulation run on them unchanged can grow without bound (deSolve returns",
        "      NA). Scale the off-diagonal cells for your model; the R companion package has glv_scale().",
        "  A growth rate is the maximum specific growth rate of that organism in monoculture (easylinear,",
        f"      the method mGrowthDB reports), median over replicates and studies, in {RATE_UNIT}.",
        "  The carrying capacity beside it is the plateau of that organism's monoculture, median over the",
        "      curves that reached a certified stationary phase, in the abundance unit they were measured",
        "      in (never converted); it is empty where no curve plateaued. The lag is the Baranyi fit's,",
        "      empty for an estimator that fits none. These are reported quantities, not applied to the",
        "      matrix above: the diagonal is still the convention.",
        "",
    ]
    if convention:
        lines += ["NUMBERS THAT ARE CONVENTIONS, NOT MEASUREMENTS",
                  "  These cells hold the stated extreme above, because one side did not grow at all and no",
                  "  ratio exists (actor on affected):"]
        lines += [f"      {actor} on {affected}: {_number(value)}" for affected, actor, value in convention]
        lines.append("")
    lines.append("WHAT IS NOT IN HERE")
    if conflicts:
        lines.append("  These pairs have arcs of opposite sign, in different conditions or studies, so they")
        lines.append("  are left at 0 rather than averaged (actor on affected):")
        lines += [f"      {actor} on {affected}" for affected, actor in conflicts]
    else:
        lines.append("  No pair had arcs of opposite sign.")
    if missing:
        lines.append("  These organisms have no growth rate, so a simulation needs one from elsewhere:")
        lines += [f"      {name}" for name in missing]
    else:
        lines.append("  Every organism in the matrix has a growth rate.")
    lines += ["", "Interactions are derived, not measured: see the report beside this file for what was",
              "skipped and why."]
    return "\n".join(lines) + "\n"


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
        if not quantified and not censored:
            continue
        pair = (edge.target, edge.source)
        unit = edge.partner_abundance_unit or ""
        value, how = _per_arc(edge, ((rates or {}).get(edge.target) or {}).get("rate"))
        entry = per_pair.setdefault(pair, {"by_unit": {}, "reasons": [], "censored": False,
                                           "how": set()})
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
        if any(v > 0 for v in numbers) and any(v < 0 for v in numbers):
            conflicts.append(pair)
            continue
        values[pair] = {"value": statistics.median(numbers), "unit": unit,
                        "censored": entry["censored"], "arcs": len(numbers),
                        "how": "ratio" if "ratio" in entry["how"] else "rates"}
    return values, conflicts, unfitted


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
    not_rates = [m for m in metrics if not (m or "").startswith(RATE_METRIC_PREFIX)]
    if not_rates:
        raise CannotConvert(
            f"these arcs compare {', '.join(repr(m) for m in not_rates)}, and a gLV coefficient needs the "
            f"log2 ratio of a growth rate: derive with the {RATE_METRIC_PREFIX} growth property (gLV mode "
            "on the page, or --metric growth_rate) and build the package again")
    values, conflicts, unfitted = _pair_values(net, rates)
    obligate = obligate_partners(net)
    # the organisms an arc says grow only with a partner, whether or not a plateau was certified for them
    only_with = {e.target for e in net.edges if e.status != "absent" and e.metric_without == 0
                 and e.metric_with not in (None, 0)}
    left_out, pairs_left_out, across, rows_fitted = [], [], [], []

    # an organism belongs to the matrix of the unit its own abundance was measured in: its monoculture
    # carrying capacity, or, for one that grows only with a partner, its plateau beside that partner
    blocks: dict = {}
    for nid in labels(net):
        name = _label(net.nodes[nid])
        rate = rates.get(nid) or {}
        if rate.get("rate") is not None and rate.get("capacity") is not None:
            blocks.setdefault(rate.get("capacity_unit", ""), []).append(nid)
            continue
        if nid in obligate:
            # r_i = 0 by measurement: it did not grow alone. Its unit is the one its plateau beside the
            # partner was measured in, which obligate_partners already matched between the two.
            unit = next((e.target_capacity_unit for e in net.edges
                         if e.target == nid and e.target_capacity is not None), "")
            blocks.setdefault(unit, []).append(nid)
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
            if rate.get("rate") is not None and rate.get("capacity"):
                row[i] = -rate["rate"] / rate["capacity"]
            else:
                # the plateau balance of an organism that grows only with its partner: with r_i = 0,
                # 0 = A_ii x_i + sum_j A_ij x_j, so A_ii = -(sum_j A_ij x_j) / x_i (#123)
                mine = next((mine for _, _, mine in obligate.get(affected, [])), None)
                held_up = sum(row[k] * theirs
                              for partner, theirs, _ in obligate.get(affected, [])
                              for k, other in enumerate(keep) if other == partner)
                row[i] = -held_up / mine if mine else 0.0
            table.append(row)
        matrices.append({"abundance_unit": abundance_unit, "media": media(net),
                         "unit": coefficient_unit(rate_unit, abundance_unit),
                         "rate_unit": rate_unit, "organisms": names, "ids": keep, "matrix": table,
                         "cells": filled,
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
    return {"matrices": matrices, "left_out": left_out, "pairs_left_out": pairs_left_out,
            "across_units": across, "floors": [],
            "from_absolute_rates": all(entry["how"] == "rates" for entry in values.values()),
            "from_the_ratio": [(_label(net.nodes[a]), _label(net.nodes[b]))
                               for (a, b), entry in values.items() if entry["how"] == "ratio"],
            "obligate_rows": list(rows_fitted),
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
    lines = [f"  Growth rates: {named}, median over replicates and studies, batch monocultures only.",
             "      Every cell of a row carries the factor r_i, so the row divides by it: the estimator",
             "      sets how fast a simulation moves and nothing about where it settles, which is the",
             "      solution of A x = -r (measured on #116). The Growth rate method setting chooses it.",
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
        "      A x = -r, and a negative entry there means this fit has no positive steady state.",
        "  The diagonal is fitted: A[i][i] = -r_i / K_i, with K_i the organism's own monoculture carrying",
        "      capacity, the plateau of the curves that reached stationary phase. An organism on its own",
        "      therefore settles at K_i.",
        "  An off-diagonal cell is A[i][j] = (r_with - r_without) / x_j, the difference between i's own",
        "      growth rate with j and without it, over x_j, the partner's abundance averaged over the",
        "      window i's rate was fitted in. Both rates come from the same comparison, and the two rates",
        "      behind every arc are in the report beside this file, so every cell can be rebuilt by hand.",
        "      Where one of them is 0, measured, because i grew only with j or only without it, the cell",
        "      is still that difference: no floor and no stated extreme enters this package.",
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
        "MATRICES",
    ]
    for block in got["matrices"]:
        lines.append(f"  {block['file']}: {len(block['organisms'])} organism(s), "
                     f"{block['cells']} fitted cell(s), every cell in {block['unit']}")
    if not got["matrices"]:
        lines.append("  NONE: no organism had both a growth rate and a carrying capacity (see below).")
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
GLV_FORMAT = "grownet.glv/v0"


def glv_payload(net: InteractionNetwork, rates: dict) -> dict:
    """The gLV parameters as one JSON-ready document (`GLV_FORMAT`).

    `organisms` names the rows and the columns of `interactions` (-1 on the diagonal), and
    `growth_rates` runs in the same order, with null where an organism has none. `caveats` holds, as
    data: the cells that carry the stated extreme rather than a measured ratio, the pairs left at 0 for
    disagreeing in sign, the organisms without a rate, the absence threshold, and the standing note that
    a cell is an effect size and not a fitted coefficient.
    """
    order = labels(net)
    names, matrix, conflicts = rows(net, DIAGONAL)
    missing = [_label(net.nodes[nid]) for nid in order if nid not in rates]
    units = {rates[nid].get("unit", RATE_UNIT) for nid in order if nid in rates}
    meta = net.meta
    return {
        "format": GLV_FORMAT,
        "tool": meta.get("tool", brand.NAME),
        "tool_version": meta.get("tool_version", ""),
        "derived_at": meta.get("derived_at", ""),
        "source_db": meta.get("source_db", "mGrowthDB"),
        "organisms": names,
        "interactions": matrix,
        "growth_rates": [rates[nid]["rate"] if nid in rates else None for nid in order],
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
             "carrying_capacity_curves": rates[nid].get("capacity_n")}
            for nid in order if nid in rates],
        "caveats": {
            "media": media(net),
            "dropout_arcs": dropout_arcs(net),
            "diagonal": DIAGONAL,
            "extreme": EXTREME,
            "absence_k": meta.get("absence", {}).get("k"),
            "placeholders": [{"affected": affected, "actor": actor, "value": value,
                              "outcome": "obligate" if value > 0 else "abolished"}
                             for affected, actor, value in by_convention(net)],
            "sign_conflicts": [{"affected": affected, "actor": actor} for affected, actor in conflicts],
            "without_a_rate": missing,
            "effect_size": "a cell is the log2 mean of a growth comparison, an effect size, not a fitted "
                           "gLV coefficient (a per-capita effect in absolute units); scale these numbers "
                           "for your model rather than using them unchanged",
            "counts": counts(net),
        },
        "readme": readme(net, rates, conflicts, missing, by_convention(net)),
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
