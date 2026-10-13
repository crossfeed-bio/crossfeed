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
from .rates import doubling_time

# The -1 a package used to carry on its diagonal by convention (Karoline, 2026-10-03). No output holds it
# since #119: the package fits the diagonal from the data and the plain adjacency matrix leaves it at 0.
# It is kept because `rows` takes a diagonal, and because a reader of a 0.2.0 package met this number.
DIAGONAL = -1.0
RATE_UNIT = "1/h"
# An obligate comparison (the target's without-set did not grow there) and an abolished one (its
# with-set did not grow), both scoped to that comparison rather than to the organism,
# have no log2 ratio at all, because one side did not grow, while the interaction they report is the
# strongest there is. Karoline, 2026-10-03: "obligate and abolished arcs need to carry numbers reflecting
# the strong effect, how about 10 with the appropriate sign?" So such an arc used to enter a matrix as
# +10 or -10, a stated convention rather than a measurement. **No output holds that number since #129
# settled** (Karoline, 2026-10-08): the plain matrix leaves such a cell `NA` and the measured bound
# travels on the arc. It survives here as the gate that says an arc reports an effect it has no ratio
# for, and as the number a reader of a 0.2.0 package met.
EXTREME = 10.0


def _label(node) -> str:
    return node.name or node.id


def labels(net: InteractionNetwork) -> list:
    """The organisms of the matrix, in a stable order: by label, so two runs line up."""
    return [nid for nid, _ in sorted(net.nodes.items(), key=lambda item: (_label(item[1]).lower(), item[0]))]


def _reports_an_extreme(edge) -> bool:
    """Whether the **gLV coefficient path** counts this arc as a comparison where one side did not grow.

    It governs `_metrics` and `_pair_values`, which build the package's coefficients. It does **not**
    govern the plain adjacency matrix: `_censored` governs that, and such a cell holds `NA` (#129). Both
    functions ask "does this arc report an effect it has no ratio for", for different purposes, so they
    name each other rather than leaving a maintainer to find out which output each one is about.

    It is **built on `_censored`** so that the two can differ in one place only, by construction. They
    did not at first: this one tested `strength_bound` before it ever looked at the outcome, so an arc
    carrying a bound with an outcome that produces no bound counted here and not there, and the gLV path
    built a coefficient for a pair whose adjacency cell held a number instead of `NA`. Nothing derives
    that shape, since `interaction.py` attaches a bound only to an obligate or abolished comparison, but
    nothing refuses it either: `Edge.validate` checks the outcome against its vocabulary and never relates
    two fields, and both constructors that turn records into edges (`mgrowthdb.records_to_network`, the
    public shape for supplied records, and `InteractionNetwork.from_dict`) read the two independently
    (Craig's agent's fifth shape, #174, 2026-10-08). Such an arc is now named in the package rather than
    counted: see `_pair_values`.

    The five shapes the no-growth rule and a supplied record can produce:

      1. a measured bound                     `_censored` yes, this yes
      2. the rule bounds nothing              `_censored` yes, this **no**
      3. older than the bound                 `_censored` yes, this yes
      4. quantified                           both no
      5. a bound without a censoring outcome  both no, and the package names it

    Shape 2 is the arc whose bound does not separate the effect from zero, which needs a metric that
    carries the inoculum of a culture that did not grow. With `auc` it happens: a flat culture still has
    the area of its own start. Over the whole live corpus on the growth rate, **the only metric a package
    can be built from**, it happens not at all: 10 censored arcs, every one shape 1 (measured 2026-10-08).
    The divergence therefore changes no package today. It stays because the two paths decide different
    things: whether a cell can hold a number, and whether a pair has a coefficient to fit at all.

    The bound itself is on the arc (`strength_bound`, with `bound_rule`), and `EXTREME` is no longer
    returned anywhere: it is kept as the number a reader of a 0.2.0 package met.
    """
    if not _censored(edge):
        return False
    if getattr(edge, "strength_bound", None) is not None:
        return True
    if getattr(edge, "bound_rule", ""):
        return False       # shape 2: the rule was applied and bounds nothing away from zero
    return True


def _censored(edge) -> bool:
    """Whether this arc reports an effect it has no ratio for, because one side did not grow.

    Such an arc takes a cell without giving it a number. **#129 settled as `NA`** (Karoline, 2026-10-08,
    choosing it over printing the measured bound there): the matrix is a lossy projection of the arcs, the
    one output whose cells cannot say what kind of number they hold, so a bound printed in a cell is
    indistinguishable from a ratio, which is the objection that retired +/-10 in the first place. The
    bound stays where it can state itself, on the arc (`strength_bound`, `bound_rule`), and the matrix
    says `NA`, which R reads as not a number rather than as no interaction. That also gives the three
    arcs whose rule bounds nothing away from zero the same cell as the rest, instead of a 0 that says no
    interaction about the strongest effect in the set.

    The gLV coefficient path asks the same question for its own reason and answers it in
    `_reports_an_extreme`, which differs from this one on the arcs whose rule bounds nothing away from
    zero. That function says which output each of the two governs.
    """
    if edge.strength is not None or edge.status == "absent":
        return False
    return edge.outcome in (OBLIGATE, ABOLISHED)


def cells(net: InteractionNetwork) -> tuple:
    """({(affected, actor): value}, conflicts): one value per ordered pair, and the pairs left at 0.

    Arcs of a pair are merged by their median. An obligate or abolished arc has no ratio, so it carries
    its direction and no number, and does not enter the median of the arcs that do have one (register
    item 14: such arcs "join their direction and count without entering the median"); it decides a cell
    only when no arc of the pair was quantified, and then the value is **None**, which the CSV writes as
    `NA` (#129, see `_censored`). A pair whose arcs disagree in sign is not merged (item 14 again): it
    stays 0 and is returned in `conflicts`, so the README can name it. The direction of a censored arc
    still counts in that disagreement, which is why it is kept rather than dropped.
    """
    measured, censored = {}, {}
    for edge in net.edges:
        pair = (edge.target, edge.source)
        if edge.status != "absent" and edge.strength is not None:
            measured.setdefault(pair, []).append(edge.strength)
        elif _censored(edge):
            censored.setdefault(pair, []).append(1.0 if edge.outcome == OBLIGATE else -1.0)
    values, conflicts = {}, []
    for pair in list(measured) + [p for p in censored if p not in measured]:
        directions = measured.get(pair, []) + censored.get(pair, [])
        if any(v > 0 for v in directions) and any(v < 0 for v in directions):
            conflicts.append(pair)
            continue
        numbers = measured.get(pair)
        values[pair] = statistics.median(numbers) if numbers else None
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
    """{"arcs", "cells", "organisms", "within_one_organism"}: how many arcs reach the matrix, how many
    cells they make, how many organisms the matrix has, and how many arcs are a pair with itself and so
    have no cell of their own. A matrix holds one cell per ordered pair, so a network with several arcs
    for one pair has fewer cells than arcs; the page and the README say so, rather than leaving two counts
    to disagree (the lesson of the hidden arcs, Karoline, 2026-10-03). A censored arc reaches the matrix
    and its cell holds `NA` rather than a number (#129), so it is counted here: a cell a reader sees is a
    cell, whatever it holds."""
    values, _ = cells(net)
    in_a_cell = sum(1 for e in net.edges
                    if (e.status != "absent" and e.strength is not None) or _censored(e))
    # A SELF pair has no cell of its own in the plain adjacency matrix: `rows` writes the diagonal
    # there, 0.0 when no diagonal is supplied. `--merge-genera` produces within-genus arcs by design
    # (Karoline, on `derive.merge_genus`: "interactions within one genus stay, as an arc from the genus
    # to itself"), so counting them here promised 45 cells where the CSV held 44, and the arc the JSON
    # reported printed as 0, which in that file means no interaction (#248). They are counted apart so
    # the two numbers agree and the page can say what has no cell.
    self_pairs = sum(1 for a, b in values if a == b)
    # the ARCS from an organism to itself, counted directly: counting self pairs in `values` missed the
    # ones a sign conflict dropped from it, so a sidecar said 1 where the file held 5 (found in review)
    self_arcs = sum(1 for e in net.edges if e.source == e.target
                    and ((e.status != "absent" and e.strength is not None) or _censored(e)))
    return {"arcs": in_a_cell, "cells": len(values) - self_pairs, "organisms": len(net.nodes),
            "within_one_organism": self_arcs}


def bounded_cells(net: InteractionNetwork) -> list:
    """The cells the matrix leaves `NA`, as (affected, actor, bound) labels, the bound or None.

    These are the pairs whose only arcs are obligate or abolished: no ratio exists, so the cell holds no
    number (#129). `bound` is the measured bound the no-growth rule put on the side that did not grow,
    the median over the arcs of that pair, and None where the rule bounds nothing away from zero or there
    was no start to multiply. Since the cell cannot say it is censored, this listing is how a reader of
    the matrix learns which `NA`s are a comparison where one side did not grow, and how strong the effect
    is at least: the page names them beside the download and the report prints each bound with its rule.
    """
    values, _ = cells(net)
    bounds: dict = {}
    for edge in net.edges:
        pair = (edge.target, edge.source)
        if _censored(edge) and values.get(pair, 0.0) is None:
            size = getattr(edge, "strength_bound", None)
            bounds.setdefault(pair, []).append(size)
    out = []
    for (a, b), sizes in bounds.items():
        got = [s for s in sizes if s is not None]
        out.append((_label(net.nodes[a]), _label(net.nodes[b]),
                    statistics.median(got) if got else None))
    return out


def rows(net: InteractionNetwork, diagonal: float | None = None) -> tuple:
    """(names, matrix, conflicts): the square matrix, row by row, with `diagonal` on the diagonal.

    `diagonal` None leaves the diagonal at 0, which is the plain adjacency matrix. The gLV package does
    not come through here: it fits its own diagonal (`coefficients`). A censored cell holds **None**, not
    a number, and the CSV writes it as `NA` (#129); `bounded_cells` names those cells.
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


class NodeRates(dict):
    """The rates `for_nodes` returns, by node id, with `no_rate`: {label: why} for a node with no rate where
    the reason is known (a genus whose strains' rates are in time units that are not converted, or an
    organism, or a genus of them, whose every study's rates were left out for their starting spread, #81),
    which `rate_meta` records beside `without_a_rate`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.no_rate: dict = {}


def for_nodes(net: InteractionNetwork, rates: dict, current: dict | None = None) -> dict:
    """The growth rates keyed by this network's own node ids.

    A rate belongs to a strain, as a monoculture does, while a network merged to the genus level
    (`derive.merge_genus`) has one node per genus. Such a node takes the median of the rates of the
    strains of its genus, with their replicates counted and their studies kept, so a genus network can be
    simulated too.

    `current` maps a taxon id to its current name (#24), as `derive.merge_genus` takes it: a strain's rate
    carries the name its study used, so it joined its genus, and was listed in `merged_from`, by that name
    while the arcs used the current one, and a strain moved to another genus left that genus with no rate
    (found in review).
    """
    current = current or {}
    # why an organism whose monocultures were read has no rate, by node id (`derive.OrganismRates`)
    refused = dict(getattr(rates, "no_rate", {}))

    def current_name(key, rate):
        taxon = key.removeprefix("ncbi:")
        return current.get(int(taxon), rate.get("name", "")) if key.startswith("ncbi:") and taxon.isdigit() \
            else rate.get("name", "")
    rates = {key: {**rate, "name": current_name(key, rate)} for key, rate in rates.items()}
    out = NodeRates()
    for nid, node in net.nodes.items():
        if nid not in rates and nid in refused:
            out.no_rate[_label(node)] = refused[nid][1]
        if nid in rates:
            # the node's own name, which is the strain's current one (#24), so the rates file, the report
            # and the network all call it the same thing
            out[nid] = {**rates[nid], "name": _label(node)}
            continue
        label = _label(node)
        members = [r for r in rates.values() if genus_name(r.get("name", "")) == genus_name(label)]
        if node.identity == "genus" and not members:
            # a genus whose strains' rates were all refused says whose and why, as a strain does (found in
            # review: keyed by strain id, the reason never reached the genus node)
            whose = [f"{current_name(key, {'name': name})}: {why}" for key, (name, why) in sorted(refused.items())
                     if genus_name(current_name(key, {"name": name})) == genus_name(label)]
            if whose:
                out.no_rate[label] = "; ".join(whose)
        if node.identity != "genus" or not members:
            continue
        # a genus of one strain IS that strain: its row is the strain's, whole, which the merge below
        # turned into fitted-row counts and dropped the capacity's provenance from (found in review)
        if len(members) == 1:
            out[nid] = {**members[0], "name": label, "merged_from": [members[0].get("name", "")]}
            continue

        capacity = _merged_capacity(members)
        if capacity["capacity"] is None and capacity["other_capacity_units"]:
            # the strains plateaued in units that are not converted, so every plateau they reached is left
            # out, one entry per curve or row as everywhere else, and no strain's "taken from <medium>"
            # stands beside a genus with no capacity (found in review)
            units = ", ".join(capacity["other_capacity_units"])
            why = f"this genus's strains plateaued in different units ({units}), which are not converted, so it " \
                  "has no capacity"
            # a strain's plateaus in other media keep their own names, with this reason in place of "taken
            # from": their unit is their medium's, which the strain row does not carry (found in review)
            kept = [(what, why if "capacity is taken from" in reason else reason)
                    for r in members for what, reason in r.get("capacity_left_out") or []]
            plateaus = []
            for r in members:
                if r.get("capacity") is None:
                    continue
                # `capacity_n` counts what the plateau rests on, curves or fitted rows, in the capacity's
                # own unit; `capacity_curves` is monoculture replicates in gLV mode (found in review)
                n = r.get("capacity_n", 0)
                plateaus += [(f"{r.get('name', '')}: plateau {k + 1} of {n} ({r.get('capacity_unit', '')})", why)
                             for k in range(n)]
            capacity["capacity_left_out"] = kept + plateaus
        # the strains whose plateau the merged capacity is the median of; with none, every strain says why
        behind = [r for r in members if r.get("capacity") is not None
                  and r.get("capacity_unit") == capacity["capacity_unit"]] if capacity["capacity"] is not None \
            else members

        def total(rows, key):
            values = [r.get(key) for r in rows]
            return sum(values) if all(isinstance(v, int) for v in values) else None

        def same(rows, key):
            values = {r.get(key) or "" for r in rows}
            return values.pop() if len(values) == 1 else "mixed: " + "; ".join(sorted(v for v in values if v))
        falls = [r["capacity_fall"] for r in behind if r.get("capacity_fall") is not None]
        media = sorted({m for r in behind for m in r.get("capacity_media") or ()}) \
            if capacity["capacity"] is not None else []
        units = {r["unit"] for r in members}
        if len(units) > 1:
            # strains whose rates are in different time units have no median: it was taken across them,
            # with the unit "", and the matrix read it in its own unit (found in review). Which unit should
            # win is not decided here, so the genus has no rate and is listed among those without one, with
            # the reason
            out.no_rate[label] = ("its strains' growth rates are in different time units ("
                                  + "; ".join(f"{r.get('name', '')} {r['unit']}" for r in members)
                                  + "), which are not converted")
            continue
        out[nid] = {"name": label, "rate": statistics.median(r["rate"] for r in members),
                    "unit": members[0]["unit"],
                    "n": sum(r.get("n", 0) for r in members),
                    "studies": sorted({s for r in members for s in r.get("studies", ())}),
                    # the strains' own rates left out in another time unit, which the report prints
                    "per_study": {}, "other_units": [f"{r.get('name', '')}: {u}" for r in members
                                                     for u in r.get("other_units") or ()],
                    "method": members[0].get("method", ""),
                    **capacity,
                    # replicates and plateau curves are counted, and the capacity's provenance kept, as a
                    # strain row has them, rather than the fitted-row counts `n` stands for
                    # a measured strain row counts its replicates in `n` and has no `replicates`, which made
                    # this None and the payload send null beside the csv's count (found in review)
                    "replicates": total([{"replicates": r["replicates"] if r.get("replicates") is not None
                                          else r.get("n")} for r in members], "replicates"),
                    "capacity_curves": total(behind, "capacity_curves") if capacity["capacity"] is not None
                    else None,
                    "capacity_source": same(behind, "capacity_source"),
                    # no capacity, no medium for it: plateaus in two units gave none, and the medium survived
                    # beside an empty capacity in the report and the payload (found in review)
                    "capacity_medium": same(behind, "capacity_medium") if capacity["capacity"] is not None else "",
                    # the strains the capacity is the median of, so the report does not call one strain's
                    # plateau "the median of the strains' capacities" (found in review)
                    "capacity_from": sorted(r["name"] for r in behind) if capacity["capacity"] is not None else [],
                    # what a strain row says beside its numbers, which a merged row dropped while a genus
                    # of one strain kept it (found in review): the count's unit when the rows are fitted
                    # ones, so the report does not call them monoculture replicates; the lag's method; the
                    # plateau's fall (Karoline, 2026-10-07: it travels with the plateau) and its media
                    **({"n_label": same(members, "n_label")} if any(r.get("n_label") for r in members) else {}),
                    "lag_method": same([r for r in members if r.get("lag") is not None], "lag_method")
                    if capacity["lag"] is not None else "",
                    "capacity_fall": statistics.median(falls) if capacity["capacity"] is not None and falls
                    else None,
                    "capacity_media": media,
                    # and every other medium a plateau of these strains is in, and the spellings the alias
                    # table read as the medium, which the report names (found in review)
                    "capacity_other_media": sorted({m for r in behind for m in r.get("capacity_other_media") or ()}
                                                   - set(media)) if capacity["capacity"] is not None else [],
                    "capacity_medium_spellings": sorted({m for r in behind
                                                         for m in r.get("capacity_medium_spellings") or ()})
                    if capacity["capacity"] is not None else [],
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
            # the rows or curves of the strains the median is of, as `capacity_curves` counts them
            "capacity_n": sum(r.get("capacity_n", 0) for r in members
                              if r.get("capacity") is not None and r.get("capacity_unit") == unit) if sizes else 0,
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


# The study-level tripwire of #173 (Craig's agent's framing, built on Karoline's 2026-10-12 decision): a
# study whose rates are ALL this many times slower than the median rate of the other studies in the same
# run is named. A flag and never a refusal, since slow is not wrong; and an internal comparison, so it
# carries no citation burden. Five is the low end of the gap that motivated it: SMGDB00000018's four fits
# sat five to fifteen times below the corpus median of 0.2245 /h, together, while the next slowest study's
# fastest fit was within it.
SLOW_FACTOR = 5.0
# fewer other studies than this and their median is not a reference worth comparing a study with
SLOW_MIN_OTHER_STUDIES = 3


def slow_studies(rates: dict) -> list:
    """[{"study", "rates", "fastest", "others_median", "factor"}]: studies every rate of which is more than
    `SLOW_FACTOR` times slower than the median rate of the other studies (#173).

    Read from each organism's `per_study`, so a study enters with every rate it gave, whichever organism
    it went to, and an organism's merged rate that rests partly on such a study is visible as such.
    """
    by_study: dict = {}
    for rate in rates.values():
        for sid, value in (rate.get("per_study") or {}).items():
            if value is not None and value > 0:
                by_study.setdefault(sid, []).append(value)
    out = []
    # one study, one vote: the reference is the median of the other studies' OWN medians, not of their
    # pooled rates, so a study that gave twenty rates cannot set every other study's test. Pooling read
    # the same as this while every study gave two or three, and would have drifted as they diverged
    # (Craig's agent, on #287); it is what "slow as a block" against "the other studies" means.
    medians = {sid: statistics.median(vs) for sid, vs in by_study.items()}
    for sid, values in sorted(by_study.items()):
        others = [m for other, m in medians.items() if other != sid]
        if len(others) < SLOW_MIN_OTHER_STUDIES:
            continue
        reference = statistics.median(others)
        if max(values) * SLOW_FACTOR < reference:
            out.append({"study": sid, "rates": len(values), "fastest": max(values),
                        "others_median": reference, "factor": reference / max(values)})
    return out


def genus_rule(rates: dict) -> str:
    """What the rule adds when a genus of several strains is among `rates`: its rate is the median of its
    strains' rates, not of their pooled replicates or rows, which the rule alone said. One clause for the
    network's rule and the package README, which said the old words after the rule was fixed (found in
    review)."""
    several = any(len(rate.get("merged_from") or ()) > 1 for rate in rates.values())
    return ("; a genus of several strains: the median of its strains' rates, and its capacity the median of "
            "the capacities of those of its strains that have one, in one unit" if several else "")


def rate_meta(net: InteractionNetwork, rates: dict, method: str) -> str:
    """The `growth_rates` block of a network's meta: the rule, a rate per organism, and the organisms that
    have none, so a downloaded network carries the rates it was reported with and says what is missing."""
    return {"rule": rate_rule(method) + genus_rule(rates),
            "organisms": {nid: dict(rate) for nid, rate in rates.items()},
            "without_a_rate": sorted(_label(node) for nid, node in net.nodes.items() if nid not in rates),
            # why, where one is known: strains whose rates are in time units not converted, or rates all
            # left out for their starting spread (#81)
            "why_without_a_rate": dict(getattr(rates, "no_rate", {})),
            "slow_studies": slow_studies(rates)}


def _number(value: float | None) -> str:
    """A cell as the CSV writes it. None is a cell with no number, printed `NA` rather than 0: R reads
    `NA` as not a number and propagates it, while 0 would say no interaction about a pair where one side
    did not grow at all (#129)."""
    if value is None:
        return "NA"
    if value == 0:
        return "0"
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    # four decimal places print any |value| below 5e-5 as `0` or `-0`, and `0` is documented as no
    # interaction; four significant digits there instead, as `_coefficient` writes them (#211)
    return f"{value:.4g}" if text in ("0", "-0") else text


def matrix_csv(net: InteractionNetwork, diagonal: float | None = None) -> str:
    """The matrix as CSV: the header row and the first column are the organisms."""
    names, matrix, _ = rows(net, diagonal)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["", *names])
    for name, row in zip(names, matrix, strict=True):
        writer.writerow([name, *(_number(v) for v in row)])
    return out.getvalue()


# The file written beside the adjacency matrix CSV (Karoline, 2026-10-12, on #212: "Sidecar file").
ABOUT_SUFFIX = ".about.txt"


def about_name(csv_name: str) -> str:
    """The sidecar's name for a matrix file: `x.csv` gives `x.about.txt`."""
    stem = csv_name[:-4] if csv_name.lower().endswith(".csv") else csv_name
    return stem + ABOUT_SUFFIX


def matrix_about(net: InteractionNetwork, csv_name: str = "grownet_matrix.csv") -> str:
    """What the adjacency matrix CSV is, for the file written beside it (#212).

    The CSV is a bare grid: no tool, version, date, derivation, metric or threshold, nothing saying rows are
    the affected organism, and no key for `0` or `NA`, while changing a setting changes every number and
    the file looks the same. A comment header would sit inside the grid, and R's `read.csv` does not skip
    `#` lines unless told to, so the description travels beside the grid instead. It also names the
    pairs `matrix_csv` leaves at 0 for disagreeing in sign, which the CSV used to drop silently.
    """
    import json
    import textwrap

    from . import brand
    from .help import EDGE_ATTRIBUTES

    meta = net.meta
    names, _, conflicts = rows(net)
    k = (meta.get("absence") or {}).get("k")
    metrics = sorted({e.metric for e in net.edges if e.metric})

    def para(text, indent="  "):
        return textwrap.wrap(text, 106, initial_indent=indent, subsequent_indent=indent + "    ")

    lines = [f"{brand.NAME} {meta.get('tool_version', '')}: adjacency matrix",
             f"derived {meta.get('derived_at', '')} from {meta.get('source_db', 'mGrowthDB')}",
             f"describes {csv_name}, {len(names)} x {len(names)}. Keep this file beside it: the CSV alone "
             "does not say how it was made.",
             ""]
    # an incomplete run's 0 cells include pairs from studies that were never read (#247; found in review)
    if meta.get("complete") is False:
        errors = meta.get("errors") or []
        # a failure while the growth rates were read touches no cell of this matrix (found in review)
        if errors and all("while reading growth rates" in e for e in errors):
            lines.append("INCOMPLETE: some growth rates could not be read; the cells below are not affected:")
        else:
            lines.append("INCOMPLETE: this run could not read everything it asked for, so a 0 below can be a "
                         "pair")
            lines.append("  from a study or curve that was never read:")
        lines += [f"  {error}" for error in errors]
        lines.append("")
    lines.append("READING IT")
    lines += para("Rows are the affected organism and columns the actor: the cell in row i, column j is the "
                  "effect of j on i. The diagonal is 0, since this is the plain adjacency matrix; the gLV "
                  "package is where a diagonal is fitted.")
    lines += para(f"A cell is the median strength of the arcs of that ordered pair. Strength is "
                  f"{EDGE_ATTRIBUTES['strength']}.")
    lines += para(f"Derivation: {derivation_of(net)}. Metric: {', '.join(metrics) or 'not recorded'}. "
                  "Both change every number here, and the file looks the same either way.")
    lines += para("0 is no arc in this network for the pair: none was derived, the comparison fell below "
                  "the absence threshold" + (f" (k = {k})" if k not in (None, "") else "")
                  + ", it was hidden as low quality, or the pair's arcs disagree in sign (listed below).")
    lines += para("NA is a comparison where one side did not grow, so no ratio exists: those cells are "
                  "listed below with the bound the network's arcs carry.")
    within = counts(net).get("within_one_organism")
    if within:
        # a within-genus arc has no cell of its own: the diagonal is written there, as the page says (#248)
        lines += para(f"{within} arc(s) are from one organism to itself, which --merge-genera produces, and "
                      "have no cell in this matrix: the diagonal is written there.")
    lines += para("In R: read.csv(file, row.names = 1, check.names = FALSE). Without check.names = FALSE, R "
                  "rewrites the organism names in the header and they no longer match the row names.")
    lines.append("")
    settings = meta.get("settings") or {}
    lines.append("SETTINGS" if settings else "SETTINGS: none recorded; these records were already derived")
    lines += [f"  {key}: {json.dumps(settings[key], default=str)}" for key in sorted(settings)]
    lines.append("")
    # a pair of an organism with itself has no cell, so it is not "left at 0": the within-one-organism line
    # covers it (found in review)
    conflicts = [(affected, actor) for affected, actor in conflicts if affected != actor]
    if conflicts:
        # Which designs disagree, per pair: across a biculture and a drop-out is the pairwise effect and
        # the in-community effect pulling opposite ways, which the report names as a result (#207);
        # within one design it is condition or replicate scatter, a different thing to tell a reader.
        # Listed under one heading they read as one cause (Craig's agent, reading #278 and #280 together).
        _, conflicting = cells(net)
        designs = {}
        for affected_id, actor_id in conflicting:
            kinds = sorted({e.evidence or "unknown" for e in net.edges
                            if e.target == affected_id and e.source == actor_id})
            designs[(_label(net.nodes[affected_id]), _label(net.nodes[actor_id]))] = (
                "across designs: " + " and ".join(kinds) if len(kinds) > 1
                else f"within one design: every arc {kinds[0] if kinds else 'unknown'}")
        lines.append("LEFT AT 0 BECAUSE THE ARCS OF THE PAIR DISAGREE IN SIGN (actor on affected). Some disagree")
        lines.append("  between designs and some within one; each says which:")
        lines += [f"  {actor} on {affected} ({designs.get((affected, actor), 'design not recorded')})"
                  for affected, actor in dict.fromkeys(conflicts)]
        lines.append("")
    bounded = bounded_cells(net)
    if bounded:
        lines.append("NA CELLS (actor on affected, and the bound where the rule set one)")
        # an obligate arc's bound is a lower one (at least this much facilitation), an abolished arc's an
        # upper one (at most this much inhibition), as `derive.bounded_strength` says; this said "at
        # least" for both (found in review)
        lines += [f"  {actor} on {affected}" + ("" if bound is None else
                                                f": {'at least' if bound > 0 else 'at most'} {bound:+.4g}")
                  for affected, actor, bound in bounded]
        lines.append("")
    found = media(net)
    if found:
        lines.append("MEDIA THE ARCS COME FROM")
        lines += [f"  {m}" for m in found]
        lines.append("")
    lines.append("SOURCES (cite the studies behind the arcs you use)")
    lines += [f"  {sid}: {study.citation or 'no citation recorded'}"
              + (f" [{study.license}]" if study.license else "") + (f" {study.url}" if study.url else "")
              for sid, study in sorted(net.studies.items())] or ["  none"]
    return "\n".join(lines) + "\n"


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


# What the diagonal is, in each derivation's own words. The specified comparison measures a plateau and
# divides: K_i is the thing observed and A_ii is derived from it. The integrated form fits A_ii as a
# parameter of the row and K_i = -r_i / A_ii is the plateau that fit implies, which is the opposite
# direction, and an organism whose fit implies none has a measured plateau put in instead.
DIAGONAL_PROSE = {
    "replicate": [
        "  The diagonal is A[i][i] = -r_i / K_i, with K_i the organism's own monoculture carrying",
        "      capacity, the plateau of the curves that reached stationary phase. An organism on its own",
        "      therefore settles at K_i. Where no monoculture of it reached a certified plateau, its own",
        "      plateau beside its partners fits the same balance, 0 = r_i + A[i][i] x_i + sum_j A[i][j] x_j",
        "      there, and the organism is named under SELF-LIMITATION FITTED AT A CO-CULTURE PLATEAU.",
    ],
    "integrated": [
        "  The diagonal is FITTED, not divided: A[i][i] is a parameter of the same least squares that",
        "      gave r_i and the off-diagonals, so it is what the monoculture time courses imply about the",
        "      organism's own limitation. The carrying capacity in growth_rates.csv is derived from it,",
        "      K_i = -r_i / A[i][i], and is the plateau that fit implies rather than one a curve was",
        "      observed to hold; capacity_source in that file says so for each organism.",
        "      A fit whose A[i][i] is not negative implies no plateau at all. Then the measured plateau of",
        "      the monocultures is put in its place where they certified one, which capacity_source also",
        "      states and which the section DIAGONALS THAT ARE NOT A FIT below names.",
    ],
}

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
        "      from the co-cultures with those held fixed. Every arc of the NETWORK carries the coefficient,",
        "      the condition number of its fit, its R2 and the R2 of the same row with every interaction set",
        "      to zero. Those are on the arcs in the network file, not in this package: a cell here is traced",
        "      to its fit through the network the package was built from.",
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

# One line each, for the `caveats` block that travels into the R object and any other consumer. This
# was a single unbranched string saying "fitted: -r_i / K_i, with K_i the organism's own plateau", which
# is the comparison's direction: under the integrated form A[i][i] IS the fitted parameter and K_i is
# derived from it, which the same module says twelve lines from here is "the opposite direction" (#231).
DIAGONAL_CAVEAT = {
    "replicate": "fitted: -r_i / K_i, with K_i the organism's own observed plateau",
    "integrated": ("fitted directly: A[i][i] is a parameter of the same least squares that gave r_i, and "
                   "K_i = -r_i / A[i][i] is the plateau that fit implies, which is the opposite "
                   "direction; carrying_capacity_source says so per organism"),
}

CAVEAT_COEFFICIENTS = {
    "replicate": ("every cell is a fitted per-capita coefficient: the diagonal is -r_i / K_i "
                  "and an off-diagonal cell is (r_with - r_without) / x_j, so nothing here is "
                  "a convention and nothing needs scaling to match the rest"),
    "integrated": ("every cell is a fitted per-capita coefficient: the diagonal A[i][i] is fitted "
                   "directly, with K_i = -r_i / A[i][i] derived from it, and an "
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

    The last column is the **doubling time**, ln(2) / rate in the time unit of the rate (#173). It is
    derived from the column beside it and adds no measurement: a rate nothing in the derivation judges for
    plausibility is at least printed in the form a reader judges at a glance. It is appended rather than
    placed beside the rate so that a reader parsing this file by column index is unaffected.
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["organism", "growth_rate", "unit", "replicates", "studies", "method", "lag",
                     "lag_method", "carrying_capacity", "capacity_unit", "capacity_curves",
                     "capacity_curves_left_out", "capacity_fall_from_peak", "capacity_medium",
                     "capacity_source", "doubling_time"])
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
                         # 0 is a count, and a blank is what R reads as NA, which is the cell the
                         # column exists to tell apart from "no capacity at all" (#211 item 5); blank
                         # only where the derivation did not record the curves at all
                         "" if "capacity_left_out" not in rate else len(rate.get("capacity_left_out") or ()),
                         # a plateau is the peak of a curve that may have declined after it, so what the
                         # curves held at their last measurement travels with it (Karoline, 2026-10-07)
                         "" if rate.get("capacity_fall") is None else f"{rate['capacity_fall']:.4g}",
                         # one medium, never pooled: the diagonal and the cells beside it are of one
                         # environment (Karoline, 2026-10-07)
                         rate.get("capacity_medium", "") if capacity is not None else "",
                         # fitted with the partners, or -r/K at a measured plateau (#142 item 7)
                         rate.get("capacity_source", ""),
                         # ln(2) / rate, in the time unit of the rate: the same number in the form a
                         # reader rejects at a glance (#173)
                         ("" if (double := doubling_time(rate["rate"], rate.get("unit", RATE_UNIT)))
                          is None else f"{double:.4g}")])
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
        if edge.status == "absent" or (edge.strength is None and not _reports_an_extreme(edge)):
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
    # a merged arc is the median of several comparisons and carries no single one's two rates: its fitted
    # coefficient is the median of its members' where it has one, and otherwise its cell is taken from its
    # median log2 ratio, which the README says under its own heading, NOT as a network saved before the
    # rates were recorded (found in review: the merge fix had sent merged arcs to that wrong label)
    if edge.merged_arcs:
        if edge.coefficient is not None:
            return edge.coefficient, "rates"
        if edge.strength is not None and fallback_rate:
            return fallback_rate * (2 ** edge.strength - 1) / edge.partner_abundance, "merged"
        return None, ""
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
        censored = _reports_an_extreme(edge)
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
                                           "how": set(), "media": [], "directions": []})
        # every arc's direction counts in the sign check, converted or not, as `cells` counts it: an
        # obligate arc that could not be converted beside an inhibition left the inhibition's number in the
        # cell, where main named the pair's sign conflict (found in review)
        if edge.strength is not None:
            entry["directions"].append(edge.strength)
        elif _censored(edge):
            entry["directions"].append(1.0 if edge.outcome == OBLIGATE else -1.0)
        # a bound without an outcome that produces one: the no-growth rule never ran on this comparison,
        # so the bound is not its own and nothing here can say what the cell should hold. Nothing derives
        # it and nothing refuses it either, so it is named rather than guessed at, which is the standard
        # the capacity unit invariant below sets (Craig's agent's fifth shape, #174)
        if (edge.strength is None and getattr(edge, "strength_bound", None) is not None
                and not _censored(edge)):
            entry["reasons"].append(
                f"this arc carries a bound ({edge.strength_bound:+.4g}) with outcome "
                f"{edge.outcome!r}, which the no-growth rule does not produce a bound for, so neither "
                "the bound nor a cell can be read from it")
            continue
        for name in (edge.medium or "").split("; "):
            if name and name not in entry["media"]:
                entry["media"].append(name)
        if value is None:
            actor, affected = _label(net.nodes[edge.source]), _label(net.nodes[edge.target])
            own_rate = ((rates or {}).get(edge.target) or {}).get("rate")
            entry["reasons"].append(
                f"no abundance for {actor} over {affected}'s growth window"
                if edge.partner_abundance in (None, 0) else
                # a merged arc is converted with the affected organism's own rate, and the arcs behind it did
                # record theirs: "not recorded" was false of it (found in review)
                f"a merged arc is converted with {affected}'s own growth rate, which it has none of"
                if getattr(edge, "merged_arcs", None) and own_rate is None and edge.strength is not None else
                # its members compared their rates; merged without a median ratio (some did not grow on
                # one side) it has no number to convert (found in review)
                "a merged arc whose members do not all have a ratio carries no median ratio and no "
                "coefficient (derive without merging for one per comparison)"
                if getattr(edge, "merged_arcs", None) and edge.strength is None else
                f"the rates behind this arc were not recorded (metric {edge.metric or 'unknown'})")
            continue
        entry["by_unit"].setdefault(unit, []).append(value)
        entry["censored"] = entry["censored"] or censored
        entry["how"].add(how)
    values, conflicts, unfitted = {}, [], []
    for pair, entry in per_pair.items():
        if any(v > 0 for v in entry["directions"]) and any(v < 0 for v in entry["directions"]):
            conflicts.append(pair)
            continue
        if not entry["by_unit"]:
            unfitted.append((pair, "; ".join(dict.fromkeys(entry["reasons"]))))
            continue
        unit = max(entry["by_unit"], key=lambda u: len(entry["by_unit"][u]))
        numbers = entry["by_unit"][unit]
        # an arc that gave no number beside arcs that did was left out of the median without a word (found
        # in review)
        if entry["reasons"]:
            unfitted.append((pair, f"{len(entry['reasons'])} arc(s) of this pair give no number ("
                                   + "; ".join(dict.fromkeys(entry["reasons"])) + "), so they are left out of "
                                   "this pair's median"))
        # the arcs of this pair counted in another unit are not merged into it and are not converted, so
        # they are named here. They used to disappear, against the README's promise that a pair outside a
        # matrix's unit is named (found 2026-10-06)
        for other, dropped in entry["by_unit"].items():
            if other != unit:
                unfitted.append((pair, f"{len(dropped)} arc(s) of this pair measure the actor in {other} "
                                       f"and the rest in {unit}; abundances are never converted, so they "
                                       "are left out of this pair's median"))
        if any(v > 0 for v in numbers) and any(v < 0 for v in numbers):
            conflicts.append(pair)
            continue
        values[pair] = {"value": statistics.median(numbers), "unit": unit,
                        "censored": entry["censored"], "arcs": len(numbers),
                        # the media behind this cell: arcs of a pair are merged by their median whatever
                        # medium each was measured in, and a cell that pools two environments is named
                        # rather than reading as one measurement (found 2026-10-06)
                        "media": list(entry["media"]),
                        "how": ("ratio" if "ratio" in entry["how"] else
                                "merged" if "merged" in entry["how"] else "rates")}
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


def _block_media(net: InteractionNetwork, ids) -> list:
    """The media of the arcs between the organisms of one matrix, or the network's when none joins them."""
    here, found = set(ids), []
    for edge in net.edges:
        if edge.status == "absent" or edge.source not in here or edge.target not in here:
            continue
        for name in (edge.medium or "").split("; "):
            if name and name not in found:
                found.append(name)
    return found or media(net)


def coefficients(net: InteractionNetwork, rates: dict) -> dict:
    """The network and its rates as fitted gLV coefficients, one matrix per abundance unit (#119).

    {"matrices": [{"abundance_unit", "unit", "organisms", "ids", "matrix", "cells", "conflicts"}],
     "left_out": [(organism, why)], "pairs_left_out": [(affected, actor, why)],
     "across_units": [(affected, actor, why)], "arcs_left_out": [(affected, actor, why)],
     "obligate_rows": [(organism, partner)],
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
            # and why it has no rate of its own, where that is known: R reads only these reasons (found in
            # review: Agrobacterium's #81 refusal reached the report and not the package)
            known = (getattr(rates, "no_rate", {}) or {}).get(name) if rate.get("rate") is None else None
            left_out.append((name, "it grows only with a partner and reached no certified plateau beside "
                                   "one, in the same abundance unit as that partner, so its "
                                   "self-limitation cannot be fitted" + (f"; it has no growth rate: {known}"
                                                                         if known else "")))
        elif rate.get("rate") is None and name in getattr(rates, "no_rate", {}):
            # its strains have rates, in units that are not converted: the README said it had none at all
            # (found in review)
            left_out.append((name, rates.no_rate[name] + ", so it has no growth rate and nothing on it can be "
                                   "fitted"))
        elif rate.get("rate") is None:
            left_out.append((name, "no growth rate, and no arc saying it grows only with a partner, so "
                                   "neither its own limitation nor the effect of anything on it can be "
                                   "fitted"))
        elif len(rate.get("other_capacity_units") or []) > 1:
            # a genus whose strains plateaued in different units: its curves DID reach a plateau, and the
            # README and the payload said none had (found in review). Empty on every strain row without one.
            left_out.append((name, "its strains' plateaus are in different units ("
                                   + ", ".join(rate["other_capacity_units"]) + "), which are not converted, "
                                   "so its self-limitation is not fitted"))
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
        table, filled = [], []
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
                filled.append((affected, actor))
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
        matrices.append({"abundance_unit": abundance_unit, "media": _block_media(net, keep),
                         "unit": coefficient_unit(rate_unit, abundance_unit),
                         "rate_unit": rate_unit, "organisms": names, "ids": keep, "matrix": table,
                         "cells": len(filled), "filled": filled, "pooled_media": pooled, "conflicts": [],
                         "file": f"interaction_matrix.{unit_file(abundance_unit)}.csv"})

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
                # and its cells and pooled media with it: the README counted cells the matrix no longer
                # holds (found in review)
                block["filled"] = [(a, b) for a, b in block["filled"] if a in block["ids"] and b in block["ids"]]
                block["cells"] = len(block["filled"])
                block["pooled_media"] = [row for row in block["pooled_media"]
                                         if row[0] in block["organisms"] and row[1] in block["organisms"]]
                block["media"] = _block_media(net, block["ids"])
    # a pair whose two organisms sit in different matrices has no cell in either; worked out after the
    # unusable organisms left theirs, whose effects are then named as in no matrix (found in review)
    where = {nid: block["abundance_unit"] for block in matrices for nid in block["ids"]}
    # a pair whose arcs disagree in sign is named in the matrix that holds both its organisms, worked out
    # after the unusable organisms left theirs: before, one that left was still named there as left at 0
    # (found in review)
    for block in matrices:
        here = set(block["ids"])
        block["conflicts"] = [(_label(net.nodes[a]), _label(net.nodes[b]))
                              for a, b in conflicts if a in here and b in here]
    # one row per pair, so that a pair with several reasons is one effect, and is counted once as one
    # (found in review: a cross-unit pair with arcs in two partner units read as two effects)
    across_at: dict = {}
    for (affected, actor), conflict in [(pair, False) for pair in values] + [(pair, True) for pair in conflicts]:
        if affected in where and actor in where and where[affected] == where[actor]:
            continue
        sign = "its arcs disagree in sign, so they are not merged; " if conflict else ""
        if affected in where and actor in where:
            why = (f"{_label(net.nodes[actor])} is counted in {where[actor]} and "
                   f"{_label(net.nodes[affected])} in {where[affected]}, so this effect is in neither matrix")
        else:
            missing = [_label(net.nodes[nid]) for nid in (affected, actor)
                       if nid not in where and nid in net.nodes]
            if not missing:
                continue
            why = f"{' and '.join(missing)} could not be fitted, so this effect is in no matrix"
        # a conflict between organisms in no common matrix was named nowhere (found in review)
        across_at[(affected, actor)] = len(across)
        across.append((_label(net.nodes[affected]), _label(net.nodes[actor]), sign + why))
    # an effect on or by an organism that is in no matrix is not "left at 0" in one: it is in none (found
    # in review: the genus package listed such a pair as a 0); routed after the unusable organisms left
    # their matrices, which are in none either. Arcs left out of a cell that still holds a value (the pair's
    # other arcs, in another unit) are named apart: the effect is fitted, those arcs are not in it.
    outside = {name for name, _ in left_out}
    arcs_left_out = []
    for (affected, actor), why in unfitted:
        names = (_label(net.nodes[affected]), _label(net.nodes[actor]))
        missing = [n for n in names if n in outside]
        if (affected, actor) in across_at:
            at = across_at[(affected, actor)]
            across[at] = (*names, f"{across[at][2]}; {why}")
        elif missing:
            across_at[(affected, actor)] = len(across)
            across.append((*names, f"{why}; {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                                   "in no matrix"))
        elif affected in where and actor in where and where[affected] != where[actor]:
            # two organisms in different matrices: no cell to leave at 0 (found in review)
            across_at[(affected, actor)] = len(across)
            across.append((*names, f"{why}; {names[1]} is counted in {where[actor]} and {names[0]} in "
                                   f"{where[affected]}, so this effect is in neither matrix"))
        elif ((affected, actor) in values and affected in where and actor in where
              and values[(affected, actor)]["unit"] == where[affected]):
            # the pair's cell holds the median of its other arcs, which is what this list says of it
            at = next((k for k, row in enumerate(arcs_left_out) if row[:2] == names), None)
            if at is None:
                arcs_left_out.append((*names, why))
            else:
                arcs_left_out[at] = (*names, f"{arcs_left_out[at][2]}; {why}")
        elif (affected, actor) in values or (affected, actor) in conflicts:
            # its cell is 0, for its other arcs' unit or their signs, so these arcs are not beside a median
            # either (found in review: they were said to be)
            at = next((k for k, row in enumerate(pairs_left_out) if row[:2] == names), None)
            if at is not None:
                pairs_left_out[at] = (*names, f"{pairs_left_out[at][2]}; {why}")
            else:
                pairs_left_out.append((*names, f"{why}; its other arcs disagree in sign, so its cell is left "
                                               "at 0"))
        else:
            pairs_left_out.append((*names, f"{why}, so the per-capita effect cannot be fitted"))
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
            "across_units": across, "arcs_left_out": arcs_left_out, "floors": [],
            "from_absolute_rates": all(entry["how"] == "rates" for entry in values.values()),
            "from_the_ratio": [(_label(net.nodes[a]), _label(net.nodes[b]))
                               for (a, b), entry in values.items() if entry["how"] == "ratio"],
            "from_merged_ratio": [(_label(net.nodes[a]), _label(net.nodes[b]))
                                  for (a, b), entry in values.items() if entry["how"] == "merged"],
            "obligate_rows": list(rows_fitted), "plateau_rows": list(plateau_rows),
            # only cells that are in a matrix: an organism left out of every block took its censored
            # cells with it, and the README named them as entering the median of their pair while
            # WHAT IS NOT IN HERE listed the same organisms as excluded (#211 item 2)
            "censored_cells": [(_label(net.nodes[a]), _label(net.nodes[b]))
                               for (a, b), entry in values.items()
                               if entry["censored"] and any(a in block["ids"] and b in block["ids"]
                                                            for block in matrices)],
            "metric": metrics[0] if metrics else "",
            # the integrated path's equivalent of `plateau_rows`: an organism whose fit implied no
            # plateau, so a measured one was put in its place. `plateau_rows` is populated from
            # `edge.target_capacity`, which that derivation never sets, so the one diagonal in the
            # package that is NOT a fit appeared in no section at all (#155 item 11)
            "substituted_rows": sorted((rate.get("name") or nid, rate.get("capacity_source", ""))
                                       for nid, rate in rates.items()
                                       if "measured plateau" in (rate.get("capacity_source") or "")),
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


def _rate_method_lines(got: dict, derivation: str = "replicate", rates: dict | None = None) -> list:
    """What the README says about the estimator behind r, and what choosing another one would move.

    Per derivation, as `DIAGONAL_PROSE` and `OFF_DIAGONAL` are: a package built in gLV mode said, nineteen
    lines below its own integrated description, that "each off-diagonal uses its own comparison's two
    rates" and that the Growth rate method setting chooses the estimator, which the integrated form does
    not read (#211 item 1).
    """
    methods = got["rate_methods"]
    named = ", ".join(methods) if methods else "not recorded"
    merge = ("the median over the fitted rows, each row's rate the median over that organism's "
             "monoculture replicates" if any(str(m).startswith("integrated") for m in methods)
             else "median over replicates and studies") + genus_rule(rates or {})
    if derivation == "integrated":
        lines = [f"  Growth rates: {named}, {merge}, batch monocultures only.",
                 "      r_i is fitted together with A[i][i] from the organism's monoculture time courses,",
                 "      and its row's off-diagonals from the co-cultures with those held fixed, so no",
                 "      separate estimator is chosen: the Growth rate method setting is not read by this",
                 "      derivation. The equilibrium below belongs to that fit.",
                 ]
    else:
        lines = [f"  Growth rates: {named}, {merge}, batch monocultures only.",
                 "      The estimator sets where this matrix settles as well as how fast a simulation",
                 "      runs. The diagonal's r_i is that merged rate, while each",
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
        "                          monoculture carrying capacity behind it, and the doubling time the",
        "                          rate implies, ln(2) / r, in the time unit of the rate",
        "  MATCH THE TWO BY THE ORGANISM COLUMN, NEVER BY POSITION. growth_rates.csv holds every",
        "      organism with a rate, in one order; each matrix holds only its own unit's organisms, in",
        "      its own order. Rows 1 to n of the rates file are not the rates of an n x n matrix, and a",
        "      simulation built that way runs without an error and settles somewhere else. In R:",
        "      r <- rates$growth_rate[match(rownames(A), rates$organism)]",
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
        # the diagonal in the derivation's own words too: it was unbranched and described the comparison's
        # route, so the default's README said K_i is a plateau the curves reached when on that path A_ii
        # is what the fit produced and K is derived from it (#155 item 11)
        *DIAGONAL_PROSE[derivation_of(net)],
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
        *_rate_method_lines(got, derivation_of(net), rates),
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
    if got.get("substituted_rows"):
        lines += ["DIAGONALS THAT ARE NOT A FIT",
                  "  The fit of these organisms implies no plateau: its A[i][i] came out at or above zero,",
                  "  which is no self-limitation and no bounded state. The measured plateau of their",
                  "  monocultures was put in its place, so their diagonal is -r_i / K_i with a K_i that was",
                  "  observed, while every other diagonal here is a parameter the fit produced."]
        lines += [f"      {who}: {why}" for who, why in got["substituted_rows"]]
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
    if got.get("from_merged_ratio"):
        lines += ["CELLS FROM MERGED ARCS, TAKEN FROM THEIR MEDIAN LOG2 RATIO",
                  "  Each of these is a merged arc, the median of several comparisons, so it carries no one",
                  "  comparison's two rates: its cell uses r_i (2^L - 1) / x_j with L the arcs' median log2",
                  "  ratio and the organism's reported rate. Derive without merging to have a cell per",
                  "  comparison (actor on affected):"]
        lines += [f"      {actor} on {affected}" for affected, actor in got["from_merged_ratio"]]
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
        # only the pairs inside a matrix: a pair outside every matrix whose arcs disagree is named with the
        # effects in no matrix, below, and "no pair disagreed" was false beside it (found in review)
        lines.append("  No pair in a matrix has arcs of opposite sign.")
    if got["left_out"]:
        lines.append("  These organisms are in no matrix, because a coefficient of theirs cannot be fitted:")
        lines += [f"      {name}: {why}" for name, why in got["left_out"]]
    else:
        lines.append("  Every organism of the network is in a matrix.")
    if got["pairs_left_out"]:
        lines.append("  These effects are left at 0 (actor on affected):")
        lines += [f"      {actor} on {affected}: {why}"
                  for affected, actor, why in dict.fromkeys(got["pairs_left_out"])]
    if got.get("arcs_left_out"):
        lines.append("  These pairs have arcs left out of their cell, which is the median of the pair's other"
                     " arcs (actor on affected):")
        lines += [f"      {actor} on {affected}: {why}" for affected, actor, why in dict.fromkeys(got["arcs_left_out"])]
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
             "unit": rates[nid].get("unit", RATE_UNIT),
             # `replicates` means monoculture replicates, which is the rule stated over `rates_csv`,
             # and the CSV follows it. This published `n` under that name, so under the integrated form,
             # the one gLV mode selects, the payload reported its FITTED ROW count as the replicate
             # count: 1 or 2 against the zip's 3 on a live corpus run, where `glv_payload` promises "the
             # same numbers as the zip" and the README allows a difference in the fifth significant
             # digit (#259). The row count is deliberately not added beside it: `grownet.glv/v1` is a
             # released format with `PREVIOUS_GLV_FORMATS` beside it, so a new field moves that id,
             # which is a decision about the package rather than a fix to it. Anyone who wants the row
             # count has it in the network's own `meta.growth_rates`, as `n` with `n_label`.
             # as growth_rates.csv writes it: `n` where the count is missing OR empty (found in review)
             "replicates": rates[nid]["replicates"] if rates[nid].get("replicates") is not None
             else rates[nid].get("n"),
             "studies": list(rates[nid].get("studies", ())),
             "per_study": dict(rates[nid].get("per_study", {})),
             "method": rates[nid].get("method", ""), "lag": rates[nid].get("lag"),
             "lag_method": rates[nid].get("lag_method", ""),
             "carrying_capacity": rates[nid].get("capacity"),
             "carrying_capacity_unit": rates[nid].get("capacity_unit", ""),
             # the curves the plateau rests on, as growth_rates.csv writes it: under the integrated form
             # `capacity_n` counts fitted ROWS, so the payload said 1 where the zip said 3, the same slip #259
             # fixed for `replicates` (found loading the payload into R in review)
             # and, as there, nothing where there is no capacity: the fallback sent 0 where the zip's
             # csv is empty (found in review)
             "carrying_capacity_curves": None if rates[nid].get("capacity") is None else (
                 rates[nid].get("capacity_curves") if rates[nid].get("capacity_curves") is not None
                 else rates[nid].get("capacity_n")),
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
            "diagonal": DIAGONAL_CAVEAT[derivation_of(net)],
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
            # what was measured between organisms counted differently, from this package's own rows: it
            # said none was whatever the rows held (found in review)
            "units": ("one matrix per abundance unit: abundances are never converted between units, since "
                      "a cell mass conversion would have to be invented, and "
                      + (f"{between} effect(s) between organisms counted differently were measured and are "
                         "in no matrix (across_units names them)" if (between := sum(
                             "neither matrix" in row[2] for row in got["across_units"])) else
                         "no effect between organisms counted differently was measured")),
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
            "arcs_left_out": [list(row) for row in got.get("arcs_left_out", [])],
            "obligate_rows": [list(row) for row in got.get("obligate_rows", [])],
            "plateau_rows": [list(row) for row in got.get("plateau_rows", [])],
            "substituted_rows": [list(row) for row in got.get("substituted_rows", [])],
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
