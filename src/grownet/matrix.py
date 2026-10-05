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
             "per_study": dict(rates[nid].get("per_study", {}))}
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


def glv_package(net: InteractionNetwork, rates: dict) -> bytes:
    """The zip a simulator is handed: the matrix, the rates and the README."""
    order = labels(net)
    names, _, conflicts = rows(net, DIAGONAL)
    missing = [_label(net.nodes[nid]) for nid in order if nid not in rates]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("interaction_matrix.csv", matrix_csv(net, DIAGONAL))
        archive.writestr("growth_rates.csv", rates_csv(rates, net))
        archive.writestr("README.txt", readme(net, rates, conflicts, missing, by_convention(net)))
    return buffer.getvalue()
