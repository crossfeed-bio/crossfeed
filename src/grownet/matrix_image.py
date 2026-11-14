"""The interaction matrix as an image: one colored cell per ordered pair, a legend for the sign, and a hover
that names the studies and experiments each cell is derived from (#341).

Karoline, 2026-11-14: "provide the interaction matrix as an image, with a hover function that says from
which studies/experiments each entry is derived. the image can be downloaded. the image would need a legend
to know the colors of negative and positive entries". Her choices on the same day: both matrices (the
adjacency matrix for every search, and in gLV mode each matrix of fitted coefficients), on the local page's
result, as SVG only, since the page has no JavaScript and the standard library cannot draw the text a PNG
would need.

The image is SVG, written as text. Rows are the affected organism and columns the actor, as in the CSV and
the package: `A[i][j]` is the effect of j on i. The hover is drawn in the image itself, a box beside the
hovered cell shown by a CSS rule inside the SVG, so it needs no script and the downloaded file keeps it. A
`<title>` alone was the first build and did not show in the app's browser pane (Karoline: "the hover does
not work"); each cell keeps its `<title>` for screen readers.

Color carries the sign with the two signal colors of the legend and the Cytoscape style (`brand.GROWTH`
for positive, `brand.INHIBITION` for negative), stronger with the size of the value on a scale symmetric
about 0, so the two ends of the legend are one number with two signs, and the legend's gradient is built
from the same mix as the cells, so a cell's color reads off it at its own value. A cell that holds no number
says so by pattern, not by a color that could read as a sign: `NA` is hatched, a pair whose arcs disagree in
sign is cross-hatched, a pair with arcs and no coefficient is dotted, and a pair with no arc is left white.
"""
from __future__ import annotations

import html
import math
import re

from . import brand
from .model import InteractionNetwork

NEUTRAL = "#F3F4F1"           # a value of 0, judged no interaction
EMPTY = "#FFFFFF"             # no arc between the two in this search
CELL = 26                     # px per cell for a large matrix; a small one gets larger cells (`_cell`)
FONT = 12                     # px, labels
CHAR = 6.6                    # px per character of a label at FONT, for the label margins
TIP_CHAR = 7.2                # px per character of hover text at FONT: ids and digits run wider than prose
TIP_WIDTH = 560               # px, the widest a hover box gets
GAP = 2                       # px of page color between cells
MAX_CITATION = 80             # characters of a study's citation in a hover
FLOOR = 0.2                   # the share of its signal color the smallest nonzero value takes

# what each kind of cell means, in the legend's order; a value cell is the color scale above these
KINDS = {
    "zero": "0: compared, and judged no interaction (absent)",
    "na": "NA: one side did not grow, so there is no ratio",
    "conflict": "arcs disagree in sign, so not merged (0 in the file)",
    "unfitted": "arcs exist, but no coefficient was fitted (the hover says why)",
    "nonfinite": "not a finite number (the hover gives it)",
    "empty": "no arc in this search",
    "diagonal": "the diagonal, not part of this matrix (0 in the file)",
}

_CONTROL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _esc(text) -> str:
    """Escaped for SVG text and attributes, with the C0 control characters XML forbids removed, so a name
    carrying one cannot make the downloaded file unreadable."""
    return html.escape(_CONTROL.sub("", str(text)), quote=True)


def _mix(color: str, share: float) -> str:
    """`color` mixed into NEUTRAL by `share` (0 is NEUTRAL, 1 is the color itself)."""
    a = [int(NEUTRAL[k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(color[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * share):02X}" for x, y in zip(a, b, strict=True))


def color_of(value: float, scale: float) -> str:
    """The fill of a value cell: NEUTRAL at 0, the signal color of its sign at the end of the scale. The
    smallest nonzero value still takes FLOOR of the color, so a weak effect does not read as none."""
    if not value or not scale or not math.isfinite(value):
        return NEUTRAL
    share = FLOOR + (1 - FLOOR) * min(abs(value) / scale, 1.0)
    return _mix(brand.GROWTH if value > 0 else brand.INHIBITION, share)


# a genus (in brackets where it is a misplaced one, "[Clostridium]"), a species epithet, and the epithet
# after a rank such as "subsp." or "var.", which is italic while the rank is not
_GENUS = re.compile(r"^(\[?[A-Z][a-z]+\]?)( [a-z][a-z-]+)?")
_RANK = re.compile(r"^( (?:subsp|var|pv|serovar)\.)( [a-z][a-z-]+)")


def _label_svg(name: str) -> str:
    """A label with the genus, species and subspecies epithets in italics and the rest upright (a strain
    designation, a rank), as the help writes species names (Karoline, 2026-11-06: "please put species
    names in italics")."""
    found = _GENUS.match(name)
    if not found:
        return _esc(name)
    italic = lambda s: f'<tspan font-style="italic">{_esc(s)}</tspan>'  # noqa: E731
    out = italic(found.group(1) + (found.group(2) or ""))
    rest = name[found.end():]
    rank = _RANK.match(rest)
    if rank:
        out += _esc(rank.group(1)) + italic(rank.group(2))
        rest = rest[rank.end():]
    return out + _esc(rest)


def _cell(n: int) -> float:
    """The cell size: 44 px for a matrix of up to eight organisms, shrinking to CELL for a large one, so a
    pair is not two small squares and the All network still fits a screen's width."""
    return max(CELL, min(44.0, 360.0 / max(n, 1)))


def _lines(text: str, width: int) -> list:
    """`text` broken at spaces into lines of at most `width` characters; a word longer than a line is cut."""
    out, line = [], ""
    for word in text.split():
        while len(word) > width:
            if line:
                out.append(line)
                line = ""
            out.append(word[:width])
            word = word[width:]
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    return out + ([line] if line else [])


def _studies_line(study_ids, net: InteractionNetwork, label: str = "Studies") -> str:
    named = []
    for sid in study_ids:
        citation = (net.studies.get(sid).citation if net.studies.get(sid) else "") or ""
        if len(citation) > MAX_CITATION:
            citation = citation[:MAX_CITATION - 1].rstrip() + "…"
        named.append(f"{sid} ({citation})" if citation else sid)
    return f"{label}: " + ("; ".join(named) if named else "not recorded")


def provenance(edges, net: InteractionNetwork) -> list:
    """The hover lines that name the studies and the experiments behind `edges`, each once, in order."""
    studies = list(dict.fromkeys(s for e in edges for s in (e.study_ids or ())))
    experiments = list(dict.fromkeys(x for e in edges for x in (getattr(e, "experiments", None) or ())))
    return [_studies_line(studies, net),
            "Experiments: " + (", ".join(experiments) if experiments else "not recorded")]


def _arcs(n: int) -> str:
    return "1 arc" if n == 1 else f"{n} arcs"


def _how(edges) -> str:
    """What a cell's number is over `edges`: one arc, the median of several, and which of them are merged
    arcs (Merge parallel arcs, Merge to genus), each itself the median of the comparisons it joined."""
    merged = [e for e in edges if getattr(e, "merged_arcs", None)]
    if len(edges) == 1 and merged:
        return f"from 1 merged arc, the median of {merged[0].merged_arcs} comparisons"
    base = "from 1 arc" if len(edges) == 1 else f"the median of {_arcs(len(edges))}"
    return base + (f", {len(merged)} of them merged arcs" if merged else "")


def _absent_lines(edges, net: InteractionNetwork) -> list:
    """The arcs of a pair judged absent beside a value or a conflict: not in the number, named with theirs."""
    if not edges:
        return []
    return [f"Also {_arcs(len(edges))} judged absent, not in the value", *provenance(edges, net)]


def _bound_line(bound) -> str:
    if bound is None:
        return "The no-growth rule bounds nothing away from zero here, so no bound is given"
    return f"Measured bound: log2 at {'least' if bound > 0 else 'most'} {bound:+.3g}"


def adjacency_cells(net: InteractionNetwork, absent: InteractionNetwork | None = None) -> tuple:
    """(names, {(row, column): cell}) for the adjacency matrix, one cell per ordered pair of the network.

    A cell is {"kind", "value", "hover"}; its value is the one `matrix.cells` writes in the CSV, and its
    hover names the arcs that value is taken over, then any other arc of the pair that is not in it.
    `absent` is the network of arcs below the absence threshold that the search left out of the file
    (`result["absent"]`), so a pair that was compared and judged absent is drawn as 0, as the file's own
    description of a 0 says, rather than as a pair never compared.
    """
    from . import matrix
    order = matrix.labels(net)
    names = [matrix._label(net.nodes[nid]) for nid in order]
    values, conflicts = matrix.cells(net)
    bounds = {(a, b): size for a, b, size in matrix.bounded_cells(net)}
    arcs: dict = {}
    for edge in [*net.edges, *(absent.edges if absent else ())]:
        arcs.setdefault((edge.target, edge.source), []).append(edge)
    grid = {}
    for i, affected in enumerate(order):
        for j, actor in enumerate(order):
            head = f"Effect of {names[j]} on {names[i]}"
            pair = (affected, actor)
            if i == j:
                # an arc of an organism on itself (Merge to genus joins strains of one genus) has no cell:
                # the diagonal is written there, so its hover names those arcs
                own = [e for e in arcs.get(pair, []) if e.status != "absent"]
                lines = [f"{names[i]}: the diagonal is not part of the adjacency matrix (0 in the file)"]
                if own:
                    lines += [f"{_arcs(len(own))} from {names[i]} to itself, which have no cell: "
                              + ", ".join("NA" if e.strength is None else f"{e.strength:+.3g}" for e in own),
                              *provenance(own, net)]
                grid[(i, j)] = {"kind": "diagonal", "value": None, "hover": "\n".join(lines)}
                continue
            present = [e for e in arcs.get(pair, []) if e.status != "absent"]
            judged_absent = [e for e in arcs.get(pair, []) if e.status == "absent"]
            quantified = [e for e in present if e.strength is not None]
            censored = [e for e in present if matrix._censored(e)]
            if pair in conflicts:
                lines = [head, f"Not merged: the {_arcs(len(present))} of this pair disagree in sign, so the "
                               "file holds 0", *provenance(present, net), *_absent_lines(judged_absent, net)]
                grid[(i, j)] = {"kind": "conflict", "value": 0.0, "hover": "\n".join(lines)}
            elif pair in values and values[pair] is None:
                lines = [head, f"NA: one side did not grow, so no ratio exists ({_arcs(len(censored))})",
                         _bound_line(bounds.get((names[i], names[j]))), *provenance(censored, net)]
                grid[(i, j)] = {"kind": "na", "value": None, "hover": "\n".join(lines)}
            elif pair in values:
                value = values[pair]
                kind = "value" if math.isfinite(value) else "nonfinite"
                lines = [head, f"log2 strength {value:+.3g} ({_how(quantified)})", *provenance(quantified, net)]
                if censored:
                    # obligate or abolished arcs of the same direction count in the sign check and stay out
                    # of the median (register item 14), so they are named apart from the number
                    lines += [f"Also {_arcs(len(censored))} where one side did not grow, same direction, not "
                              "in the value", *provenance(censored, net)]
                lines += _absent_lines(judged_absent, net)
                grid[(i, j)] = {"kind": kind, "value": value, "hover": "\n".join(lines)}
            elif judged_absent:
                lines = [head, f"0: compared, and judged no interaction ({_arcs(len(judged_absent))}, absent)",
                         *provenance(judged_absent, net)]
                grid[(i, j)] = {"kind": "zero", "value": 0.0, "hover": "\n".join(lines)}
            else:
                grid[(i, j)] = {"kind": "empty", "value": None, "hover": f"{head}\nNo arc in this search"}
    return names, grid


def _diagonal_source(derivation: str, rate: dict) -> list:
    """How a gLV diagonal was made, in the words of the package's own README (`matrix.DIAGONAL_CAVEAT`),
    with the numbers that went into it. Under the integrated form the diagonal is fitted and the plateau
    follows from it, the opposite direction to -r/K; under the steady-state form the rate is r - D."""
    r, cap = rate.get("rate"), rate.get("capacity")
    unit, cap_unit = rate.get("unit", "1/h"), rate.get("capacity_unit", "")
    if derivation == "steady":
        lines = ["Fitted from chemostat steady states with the rest of its row: A_ii = (r - D) B_ii, and "
                 "K = -1 / B_ii is its steady state alone"]
        if r is not None:
            lines.append(f"r - D = {r:.3g} {unit}" + (f", K = {cap:.3g} {cap_unit}".rstrip() if cap else ""))
    elif derivation == "integrated":
        lines = ["Fitted directly with its growth rate from the monoculture time courses; K = -r / A_ii is "
                 "the plateau that fit implies"]
        if r is not None:
            lines.append(f"r = {r:.3g} {unit}" + (f", K = {cap:.3g} {cap_unit}".rstrip() if cap else ""))
    elif r is not None and cap:
        lines = [f"-r / K from its monoculture: r = {r:.3g} {unit}, K = {cap:.3g} {cap_unit}".rstrip()]
    else:
        lines = ["From its plateau beside its partners (the plateau balance)"]
    if rate.get("capacity_source"):
        lines.append(f"Carrying capacity: {rate['capacity_source']}")
    return lines


def glv_cells(net: InteractionNetwork, rates: dict, block: dict, got: dict) -> tuple:
    """(names, {(row, column): cell}) for one matrix of fitted gLV coefficients (`matrix.coefficients`).

    An off-diagonal cell names the arcs its coefficient is the median of, and any arc of the pair the
    package left out with why; a diagonal says how it was fitted under this network's derivation and names
    the studies of the organism's own growth rate. A pair with arcs and no coefficient says why, and a pair
    whose arcs disagree in sign says so, as the package's README does.
    """
    from . import matrix
    derivation = matrix.derivation_of(net)
    names, ids, unit = block["organisms"], block["ids"], block["unit"]
    behind = block.get("behind") or {}
    conflicts = {tuple(pair) for pair in block.get("conflicts") or ()}
    why_not, left_out = {}, {}
    for key in ("pairs_left_out", "across_units"):
        for affected, actor, why in got.get(key) or ():
            why_not.setdefault((affected, actor), why)
    for affected, actor, why in got.get("arcs_left_out") or ():
        left_out.setdefault((affected, actor), why)
    arcs: dict = {}
    for edge in net.edges:
        if edge.status != "absent":
            arcs.setdefault((edge.target, edge.source), []).append(edge)
    grid = {}
    for i, affected in enumerate(ids):
        for j, actor in enumerate(ids):
            value = block["matrix"][i][j]
            if i == j:
                rate = rates.get(affected) or {}
                lines = [f"Self-limitation of {names[i]}", f"{value:+.3g} {unit}",
                         *_diagonal_source(derivation, rate),
                         _studies_line(rate.get("studies") or (), net, "Studies of its growth rate")]
                grid[(i, j)] = {"kind": "value" if math.isfinite(value) else "nonfinite", "value": value,
                                "hover": "\n".join(lines)}
                continue
            head = f"Effect of {names[j]} on {names[i]}"
            label_pair = (names[i], names[j])
            edges = behind.get((affected, actor))
            pair_arcs = arcs.get((affected, actor), [])
            if edges:
                lines = [head, f"{value:+.3g} {unit} ({_how(edges)})", *provenance(edges, net)]
                if label_pair in left_out:
                    lines.append(f"Left out of it: {left_out[label_pair]}")
                grid[(i, j)] = {"kind": "value" if math.isfinite(value) else "nonfinite", "value": value,
                                "hover": "\n".join(lines)}
            elif label_pair in conflicts:
                lines = [head, f"Not merged: the {_arcs(len(pair_arcs))} of this pair disagree in sign, so the "
                               "file holds 0", *provenance(pair_arcs, net)]
                grid[(i, j)] = {"kind": "conflict", "value": 0.0, "hover": "\n".join(lines)}
            elif pair_arcs:
                why = why_not.get(label_pair) or left_out.get(label_pair) or "no arc of this pair gave a number"
                lines = [head, f"No coefficient: {why}", *provenance(pair_arcs, net)]
                grid[(i, j)] = {"kind": "unfitted", "value": None, "hover": "\n".join(lines)}
            else:
                grid[(i, j)] = {"kind": "empty", "value": None, "hover": f"{head}\nNo arc in this search"}
    return names, grid


def svg(names: list, grid: dict, title: str, subtitle: str, value_name: str, slug: str = "m") -> str:
    """The matrix as a standalone SVG: title, column labels, row labels, the cells, and a legend with the
    scale's two ends and every kind of cell that occurs. `slug` keeps the ids of two images on one page
    apart.

    Each cell's hover is a box drawn beside the cell in a layer above every cell, hidden until that cell is
    hovered by a `:has()` rule inside the SVG. Beside the cell, it is in view wherever the cell is, which a
    panel under the legend was not on a large matrix; above every cell, no later cell covers it."""
    n = len(names)
    size = _cell(n)
    finite = [abs(c["value"]) for c in grid.values() if c["kind"] == "value" and c["value"] is not None
              and math.isfinite(c["value"])]
    scale = max(finite, default=0.0)
    longest = max((len(s) for s in names), default=4)
    left = 12 + longest * CHAR
    slant = math.radians(50)
    top_labels = longest * CHAR * math.sin(slant) + 14
    # the slanted column labels reach right of their column by their length's horizontal extent
    width = max(left + n * size + longest * CHAR * math.cos(slant) + 24, 720)
    sub = _lines(subtitle, int((width - 24) / CHAR))
    top = 40 + 16 * len(sub) + top_labels
    kinds = [k for k in KINDS if any(c["kind"] == k for c in grid.values())]
    ly = top + n * size + 40
    tip_w = min(TIP_WIDTH, width - 24)
    per_line = int((tip_w - 20) / TIP_CHAR)
    wrapped = {key: [piece for line in cell["hover"].splitlines() for piece in (_lines(line, per_line) or [""])]
               for key, cell in grid.items()}
    tallest = 16 + 16 * max((len(lines) for lines in wrapped.values()), default=1)
    height = max(ly + 64 + 20 * len(kinds), tallest + 16)
    stops = [(0, brand.INHIBITION), (0.4999, _mix(brand.INHIBITION, FLOOR)), (0.5, NEUTRAL),
             (0.5001, _mix(brand.GROWTH, FLOOR)), (1, brand.GROWTH)]
    rules = "".join(f"svg:has(#{slug}-c{i}-{j}:hover) #{slug}-t{i}-{j}{{visibility:visible}}" for i, j in grid)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="system-ui, -apple-system, Segoe UI, sans-serif" '
           f'role="img" aria-label="{_esc(title)}">',
           f"<title>{_esc(title)}</title>",
           "<defs>"
           f'<pattern id="{slug}-na" width="6" height="6" patternUnits="userSpaceOnUse" '
           'patternTransform="rotate(45)"><rect width="6" height="6" fill="#FFFFFF"/>'
           f'<line x1="0" y1="0" x2="0" y2="6" stroke="{brand.MUTED}" stroke-width="1.6"/></pattern>'
           f'<pattern id="{slug}-conflict" width="6" height="6" patternUnits="userSpaceOnUse" '
           'patternTransform="rotate(45)"><rect width="6" height="6" fill="#FFFFFF"/>'
           f'<line x1="0" y1="0" x2="0" y2="6" stroke="{brand.MUTED}" stroke-width="1.2"/>'
           f'<line x1="0" y1="3" x2="6" y2="3" stroke="{brand.MUTED}" stroke-width="1.2"/></pattern>'
           f'<pattern id="{slug}-unfitted" width="6" height="6" patternUnits="userSpaceOnUse">'
           f'<rect width="6" height="6" fill="#FFFFFF"/><circle cx="3" cy="3" r="1.1" fill="{brand.MUTED}"/>'
           "</pattern>"
           f'<pattern id="{slug}-nonfinite" width="8" height="8" patternUnits="userSpaceOnUse">'
           f'<rect width="8" height="8" fill="{brand.PANEL}"/><text x="1" y="7" font-size="7" '
           f'fill="{brand.MUTED}">?</text></pattern>'
           f'<linearGradient id="{slug}-scale" x1="0" x2="1" y1="0" y2="0">'
           + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops) +
           "</linearGradient></defs>",
           f"<style>.tip{{visibility:hidden;pointer-events:none}}.cell:hover>rect{{stroke:{brand.INK};stroke-width:2}}{rules}</style>",
           f'<rect width="{width:.0f}" height="{height:.0f}" fill="#FFFFFF"/>',
           f'<text x="12" y="24" font-size="15" font-weight="600" fill="{brand.INK}">{_esc(title)}</text>',
           *(f'<text x="12" y="{44 + 16 * k}" font-size="12" fill="{brand.MUTED}">{_esc(line)}</text>'
             for k, line in enumerate(sub))]
    # column labels: the actor, slanted so long names fit
    for j, name in enumerate(names):
        x, y = left + j * size + size / 2, top - 6
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{FONT}" fill="{brand.INK}" '
                   f'transform="rotate(-50 {x:.1f} {y:.1f})">{_label_svg(name)}</text>')
    for i, name in enumerate(names):
        y = top + i * size + size / 2 + FONT * 0.35
        out.append(f'<text x="{left - 8:.1f}" y="{y:.1f}" font-size="{FONT}" text-anchor="end" '
                   f'fill="{brand.INK}">{_label_svg(name)}</text>')
    fills = {"zero": NEUTRAL, "na": f"url(#{slug}-na)", "conflict": f"url(#{slug}-conflict)",
             "unfitted": f"url(#{slug}-unfitted)", "nonfinite": f"url(#{slug}-nonfinite)", "empty": EMPTY,
             "diagonal": brand.LINE}
    tips = []
    for (i, j), cell in sorted(grid.items()):
        fill = (color_of(cell["value"], scale) if cell["kind"] == "value" and cell["value"] is not None
                else fills.get(cell["kind"], EMPTY))
        x, y = left + j * size, top + i * size
        out.append(f'<g class="cell" id="{slug}-c{i}-{j}"><title>{_esc(cell["hover"])}</title>'
                   f'<rect x="{x + GAP / 2:.1f}" y="{y + GAP / 2:.1f}" '
                   f'width="{size - GAP:.1f}" height="{size - GAP:.1f}" '
                   f'rx="2" fill="{fill}" stroke="{brand.LINE}" stroke-width="0.6"/></g>')
        # the box beside the cell, never over it: to its right where it fits, else to its left, else below
        # its row (above it at the bottom edge). A box clamped over its own cell took the pointer from the
        # cell, hid, gave it back and flickered (found reviewing in the pane).
        lines = wrapped[(i, j)]
        box_h = 16 + 16 * len(lines)
        if x + size + 6 + tip_w <= width - 4:
            bx, by = x + size + 6, min(max(y, 4), height - box_h - 4)
        elif x - 6 - tip_w >= 4:
            bx, by = x - 6 - tip_w, min(max(y, 4), height - box_h - 4)
        else:
            bx = min(max(x + size / 2 - tip_w / 2, 4), width - tip_w - 4)
            by = y + size + 6 if y + size + 6 + box_h <= height - 4 else max(y - 6 - box_h, 4)
        text = "".join(f'<text x="{bx + 10:.1f}" y="{by + 20 + 16 * k:.1f}" font-size="12" fill="{brand.INK}"'
                       + (' font-weight="600"' if k == 0 else "") + f">{_esc(line)}</text>"
                       for k, line in enumerate(lines))
        tips.append(f'<g class="tip" id="{slug}-t{i}-{j}"><rect x="{bx:.1f}" y="{by:.1f}" width="{tip_w:.0f}" '
                    f'height="{box_h}" rx="4" fill="#FFFFFF" stroke="{brand.INK}" stroke-width="0.8"/>{text}</g>')
    # axis captions
    out.append(f'<text x="{left:.1f}" y="{top + n * size + 18:.1f}" font-size="11" fill="{brand.MUTED}">'
               "rows: the affected organism; columns: the actor</text>")
    # the legend: the scale with its two ends, then each kind of cell that occurs here
    bar = 220
    number = (lambda v: f"{v:+.3g}") if scale else (lambda v: "0")
    out += [f'<text x="12" y="{ly:.1f}" font-size="12" font-weight="600" fill="{brand.INK}">{_esc(value_name)}</text>',
            f'<rect x="12" y="{ly + 8:.1f}" width="{bar}" height="12" rx="2" fill="url(#{slug}-scale)" '
            f'stroke="{brand.LINE}" stroke-width="0.6"/>',
            f'<text x="12" y="{ly + 34:.1f}" font-size="11" fill="{brand.INK}">{number(-scale)} negative</text>',
            f'<text x="{12 + bar / 2:.1f}" y="{ly + 34:.1f}" font-size="11" text-anchor="middle" '
            f'fill="{brand.INK}">0</text>',
            f'<text x="{12 + bar:.1f}" y="{ly + 34:.1f}" font-size="11" text-anchor="end" '
            f'fill="{brand.INK}">positive {number(scale)}</text>']
    for k, kind in enumerate(kinds):
        y = ly + 50 + 20 * k
        out.append(f'<rect x="12" y="{y:.1f}" width="14" height="14" rx="2" fill="{fills[kind]}" '
                   f'stroke="{brand.LINE}" stroke-width="0.6"/>'
                   f'<text x="34" y="{y + 11:.1f}" font-size="11" fill="{brand.INK}">{_esc(KINDS[kind])}</text>')
    # the hover boxes last, so each is drawn above every cell
    out += tips
    out.append("</svg>")
    return "\n".join(out) + "\n"


def adjacency_svg(net: InteractionNetwork, absent: InteractionNetwork | None = None) -> str:
    names, grid = adjacency_cells(net, absent)
    return svg(names, grid, "Adjacency matrix",
               "Each cell is the log2 effect of the column organism on the row organism; hover a cell for "
               "the studies and experiments behind it.", "log2 strength", slug="adj")


def glv_svgs(net: InteractionNetwork, rates: dict) -> list:
    """[(abundance unit, file name, SVG)]: one image per matrix of the gLV package. Raises
    `matrix.CannotConvert` as the package does, when the arcs do not compare growth rates."""
    from . import matrix
    got = matrix.coefficients(net, rates)
    out = []
    for k, block in enumerate(got["matrices"]):
        names, grid = glv_cells(net, rates, block, got)
        out.append((block["abundance_unit"], f"glv_matrix.{matrix.unit_file(block['abundance_unit'])}.svg",
                    svg(names, grid, f"gLV coefficients in {block['abundance_unit']}",
                        f"A[i, j], the per-capita effect of the column organism j on the row organism i, in "
                        f"{block['unit']}; hover a cell for the studies and experiments behind it.",
                        f"coefficient ({block['unit']})", slug=f"glv{k}")))
    return out
