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


def floor_magnitude(net: InteractionNetwork) -> float | None:
    """The |log2 ratio| an obligate or abolished pair enters a coefficient with, or None.

    Karoline's choice on Craig's censored argument (#116): such a pair is not a stated extreme but a
    measurement cut off at the detection limit, so it takes a floor. mGrowthDB records no detection limit
    for a growth rate, so the floor is the largest magnitude measured in the same run: the strongest
    effect the data shows, which is the least the censored one can be. A run with no quantified arc has
    no floor to take, and such pairs are then named instead.
    """
    sizes = [abs(e.strength) for e in net.edges if e.status != "absent" and e.strength is not None]
    return max(sizes) if sizes else None


def _pair_values(net: InteractionNetwork, floor: float | None) -> tuple:
    """({pair: {"log2", "floor", "abundance", "unit"}}, conflicts, no_floor).

    One entry per ordered pair, merged the way the matrix merges (median of the quantified arcs, signs
    that disagree left out). `floor` is the magnitude a censored pair enters with; `abundance` is the
    median of the partner abundances of the arcs behind the entry, in the one unit they agree on.
    """
    measured, censored, abundances, units = {}, {}, {}, {}
    for edge in net.edges:
        pair = (edge.target, edge.source)
        quantified = edge.status != "absent" and edge.strength is not None
        extreme = _extreme(edge)
        if not quantified and extreme is None:
            continue
        if quantified:
            measured.setdefault(pair, []).append(edge.strength)
        else:
            censored.setdefault(pair, []).append(1.0 if extreme > 0 else -1.0)
        if edge.partner_abundance is not None:
            abundances.setdefault(pair, {}).setdefault(edge.partner_abundance_unit or "", []) \
                .append(edge.partner_abundance)
    values, conflicts, no_floor = {}, [], []
    for pair in list(measured) + [p for p in censored if p not in measured]:
        signs = measured.get(pair, []) + censored.get(pair, [])
        if any(v > 0 for v in signs) and any(v < 0 for v in signs):
            conflicts.append(pair)
            continue
        if pair in measured:
            log2, is_floor = statistics.median(measured[pair]), False
        elif floor is None:
            no_floor.append(pair)
            continue
        else:
            log2, is_floor = floor * censored[pair][0], True
        by_unit = abundances.get(pair, {})
        unit = max(by_unit, key=lambda u: len(by_unit[u])) if by_unit else ""
        values[pair] = {"log2": log2, "floor": is_floor,
                        "abundance": statistics.median(by_unit[unit]) if unit else None,
                        "unit": unit}
        units[pair] = unit
    return values, conflicts, no_floor


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
     "across_units": [(affected, actor, why)], "floors": [(affected, actor, log2)],
     "floor_rule", "rate_methods", "metric"}

    Every number is a measurement or a floor taken from one: no diagonal by convention, no stated
    extreme. An organism whose rate or carrying capacity is missing, and a pair whose partner abundance
    is missing or in another unit, are named rather than given a number. Raises `CannotConvert` when the
    arcs do not compare growth rates, since L is a ratio of rates.
    """
    metrics = _metrics(net)
    not_rates = [m for m in metrics if not (m or "").startswith(RATE_METRIC_PREFIX)]
    if not_rates:
        raise CannotConvert(
            f"these arcs compare {', '.join(repr(m) for m in not_rates)}, and a gLV coefficient needs the "
            f"log2 ratio of a growth rate: derive with the {RATE_METRIC_PREFIX} growth property (gLV mode "
            "on the page, or --metric growth_rate) and build the package again")
    floor = floor_magnitude(net)
    values, conflicts, no_floor = _pair_values(net, floor)
    left_out, pairs_left_out, across, floors = [], [], [], []

    # an organism belongs to the matrix of the unit its own carrying capacity was measured in
    blocks: dict = {}
    for nid in labels(net):
        name = _label(net.nodes[nid])
        rate = rates.get(nid)
        if rate is None or rate.get("rate") is None:
            left_out.append((name, "no growth rate, so neither its own limitation nor the effect of "
                                   "anything on it can be fitted"))
            continue
        if rate.get("capacity") is None:
            left_out.append((name, "no carrying capacity from a curve that reached stationary phase, so "
                                   "its self-limitation is not fitted"))
            continue
        blocks.setdefault(rate.get("capacity_unit", ""), []).append(nid)

    matrices = []
    for abundance_unit, ids in sorted(blocks.items()):
        times = {(rates[nid].get("unit") or RATE_UNIT) for nid in ids}
        rate_unit = sorted(times)[0]
        keep = []
        for nid in ids:
            if (rates[nid].get("unit") or RATE_UNIT) != rate_unit:
                left_out.append((_label(net.nodes[nid]),
                                 f"its growth rate is in {rates[nid].get('unit')}, and this matrix in "
                                 f"{rate_unit}; left out rather than converted"))
                continue
            keep.append(nid)
        names = [_label(net.nodes[nid]) for nid in keep]
        table, filled = [], 0
        for i, affected in enumerate(keep):
            rate = rates[affected]
            row = []
            for j, actor in enumerate(keep):
                if i == j:
                    row.append(-rate["rate"] / rate["capacity"])
                    continue
                entry = values.get((affected, actor))
                if entry is None:
                    row.append(0.0)
                    continue
                label_pair = (_label(net.nodes[affected]), _label(net.nodes[actor]))
                if entry["abundance"] is None:
                    pairs_left_out.append((*label_pair, f"no abundance for {label_pair[1]} over "
                                                        f"{label_pair[0]}'s growth window, so the "
                                                        "per-capita effect cannot be fitted"))
                    row.append(0.0)
                    continue
                if entry["unit"] != abundance_unit:
                    pairs_left_out.append((*label_pair,
                                           f"{label_pair[1]}'s abundance beside {label_pair[0]} is in "
                                           f"{entry['unit']}, and this matrix is in {abundance_unit}; "
                                           "left out rather than converted"))
                    row.append(0.0)
                    continue
                row.append(rate["rate"] * (2 ** entry["log2"] - 1) / entry["abundance"])
                filled += 1
                if entry["floor"]:
                    floors.append((*label_pair, entry["log2"]))
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
    for affected, actor in no_floor:
        if affected in where:
            across.append((_label(net.nodes[affected]), _label(net.nodes[actor]),
                           "the pair is obligate or abolished and no arc of this run was quantified, so "
                           "there is no floor to take"))
    rule = ("a floor, not a measurement: the largest magnitude measured in this run "
            f"(log2 {_number(floor)}) with the sign of the outcome, because one side did not grow and "
            "mGrowthDB records no detection limit for a growth rate") if floor is not None else (
            "no floor was available: this run has no quantified arc to take one from")
    return {"matrices": matrices, "left_out": left_out, "pairs_left_out": pairs_left_out,
            "across_units": across, "floors": floors, "floor_rule": rule, "floor": floor,
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
        "  An off-diagonal cell is A[i][j] = r_i * (2^L - 1) / x_j, with L the log2 ratio of i's growth",
        "      rate with j over without it, and x_j the partner's own abundance averaged over the window",
        "      i's rate was fitted in.",
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
    if got["floors"]:
        lines += ["FLOORS, NOT MEASUREMENTS",
                  f"  {got['floor_rule']}.",
                  "  These cells rest on a floor (actor on affected, as log2 of the rate ratio):"]
        lines += [f"      {actor} on {affected}: log2 {_number(value)}"
                  for affected, actor, value in got["floors"]]
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
