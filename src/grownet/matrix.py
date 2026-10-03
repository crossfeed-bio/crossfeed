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
from .model import InteractionNetwork, genus_name

DIAGONAL = -1.0           # self-limitation, by convention (Karoline, 2026-10-03)
RATE_UNIT = "1/h"


def _label(node) -> str:
    return node.name or node.id


def labels(net: InteractionNetwork) -> list:
    """The organisms of the matrix, in a stable order: by label, so two runs line up."""
    return [nid for nid, _ in sorted(net.nodes.items(), key=lambda item: (_label(item[1]).lower(), item[0]))]


def cells(net: InteractionNetwork) -> tuple:
    """({(affected, actor): value}, conflicts): one value per ordered pair, and the pairs left at 0.

    Arcs of a pair are merged by their median. A pair whose arcs disagree in sign is not merged (register
    item 14): it stays 0 and is returned in `conflicts`, so the README can name it.
    """
    gathered: dict = {}
    for edge in net.edges:
        if edge.status == "absent" or edge.strength is None:
            continue                      # no interaction at this threshold, or no ratio to put in a cell
        gathered.setdefault((edge.target, edge.source), []).append(edge.strength)
    values, conflicts = {}, []
    for pair, strengths in gathered.items():
        if any(s > 0 for s in strengths) and any(s < 0 for s in strengths):
            conflicts.append(pair)
            continue
        values[pair] = statistics.median(strengths)
    return values, conflicts


def counts(net: InteractionNetwork) -> dict:
    """{"arcs", "cells", "organisms"}: how many arcs carry a number, how many cells they make, and how many
    organisms the matrix has. A matrix holds one cell per ordered pair, so a network with several arcs for
    one pair has fewer cells than arcs; the page and the README say so, rather than leaving two counts to
    disagree (the lesson of the hidden arcs, Karoline, 2026-10-03)."""
    values, _ = cells(net)
    with_a_number = sum(1 for e in net.edges if e.status != "absent" and e.strength is not None)
    return {"arcs": with_a_number, "cells": len(values), "organisms": len(net.nodes)}


def unquantified(net: InteractionNetwork) -> list:
    """The pairs that have an arc but no number for it, as (affected, actor) labels.

    An obligate or abolished comparison has no finite log2 ratio (one side did not grow), so its cell is 0
    like an empty one, while the interaction it reports is the strongest there is. The README names these
    pairs, since a matrix alone would understate them.
    """
    values, _ = cells(net)
    pairs = []
    for edge in net.edges:
        pair = (edge.target, edge.source)
        if edge.strength is None and edge.status != "absent" and pair not in values and pair not in pairs:
            pairs.append(pair)
    return [(_label(net.nodes[a]), _label(net.nodes[b])) for a, b in pairs]


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
            out[nid] = rates[nid]
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
                    "merged_from": sorted(r["name"] for r in members)}
    return out


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
    """The growth rates as CSV: one row per organism, with how many values the median rests on."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["organism", "growth_rate", "unit", "replicates", "studies"])
    order = labels(net) if net is not None else sorted(rates)
    for nid in order:
        rate = rates.get(nid)
        if rate is None:
            continue
        name = _label(net.nodes[nid]) if net is not None else nid
        writer.writerow([name, _number(rate["rate"]), rate.get("unit", RATE_UNIT),
                         rate.get("n", ""), " ".join(rate.get("studies", ()))])
    return out.getvalue()


def readme(net: InteractionNetwork, rates: dict, conflicts: list, missing: list, without_a_number=()) -> str:
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
        "  growth_rates.csv        one growth rate per organism, with how many values it rests on",
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
        f"  One cell per ordered pair: this network's {count['arcs']} arc(s) with a number make "
        f"{count['cells']} cell(s) over {count['organisms']} organism(s).",
        "  A growth rate is the maximum specific growth rate of that organism in monoculture (easylinear,",
        f"      the method mGrowthDB reports), median over replicates and studies, in {RATE_UNIT}.",
        "",
        "WHAT IS NOT IN HERE",
    ]
    if conflicts:
        lines.append("  These pairs have arcs of opposite sign in different studies, so they are left at 0")
        lines.append("  rather than averaged (actor on affected):")
        lines += [f"      {actor} on {affected}" for affected, actor in conflicts]
    else:
        lines.append("  No pair had arcs of opposite sign across studies.")
    if without_a_number:
        lines.append("  These pairs interact but have no number: one side did not grow at all (obligate or")
        lines.append("  abolished), so there is no log2 ratio and the cell is 0 (actor on affected):")
        lines += [f"      {actor} on {affected}" for affected, actor in without_a_number]
    if missing:
        lines.append("  These organisms have no growth rate, so a simulation needs one from elsewhere:")
        lines += [f"      {name}" for name in missing]
    else:
        lines.append("  Every organism in the matrix has a growth rate.")
    lines += ["", "Interactions are derived, not measured: see the report beside this file for what was",
              "skipped and why."]
    return "\n".join(lines) + "\n"


def glv_package(net: InteractionNetwork, rates: dict) -> bytes:
    """The zip a simulator is handed: the matrix, the rates and the README."""
    order = labels(net)
    names, _, conflicts = rows(net, DIAGONAL)
    missing = [_label(net.nodes[nid]) for nid in order if nid not in rates]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("interaction_matrix.csv", matrix_csv(net, DIAGONAL))
        archive.writestr("growth_rates.csv", rates_csv(rates, net))
        archive.writestr("README.txt", readme(net, rates, conflicts, missing, unquantified(net)))
    return buffer.getvalue()
