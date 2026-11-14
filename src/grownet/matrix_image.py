"""The interaction matrix as an image: one colored cell per ordered pair, a legend for the sign, and a hover
that names the studies and experiments each cell is derived from (#341).

Karoline, 2026-11-14: "provide the interaction matrix as an image, with a hover function that says from
which studies/experiments each entry is derived. the image can be downloaded. the image would need a legend
to know the colors of negative and positive entries". Her choices on the same day: both matrices (the
adjacency matrix for every search, and in gLV mode each matrix of fitted coefficients), on the local page's
result, as SVG only, since the page has no JavaScript and the standard library cannot draw the text a PNG
would need.

The image is SVG, written as text. The hover is each cell's `<title>`, which a browser shows on the page
and in the downloaded file alike, so the file keeps what the page shows. Rows are the affected organism and
columns the actor, as in the CSV and the package: `A[i][j]` is the effect of j on i.

Color carries the sign with the two signal colors of the legend and the Cytoscape style (`brand.GROWTH`
for positive, `brand.INHIBITION` for negative), stronger with the size of the value on a scale symmetric
about 0, so the two ends of the legend are one number with two signs. A cell that holds no number says so
by pattern, not by a color that could read as a sign: `NA` is hatched, a pair whose arcs disagree in sign is
cross-hatched, and a pair with no arc is left white.
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
GAP = 2                       # px of page color between cells
NUMBER_FORMATS = {"log2": "{:+.3g}", "coefficient": "{:+.3g}"}
MAX_CITATION = 80             # characters of a study's citation in a hover

# what each kind of cell means, in the legend's order; a value cell is the color scale above these
KINDS = {
    "zero": "0: every arc of the pair was judged absent",
    "na": "NA: one side did not grow, so there is no ratio",
    "conflict": "arcs disagree in sign, so not merged (0 in the file)",
    "empty": "no arc in this search",
    "diagonal": "the diagonal, not part of this matrix (0 in the file)",
}


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _mix(color: str, share: float) -> str:
    """`color` mixed into NEUTRAL by `share` (0 is NEUTRAL, 1 is the color itself)."""
    a = [int(NEUTRAL[k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(color[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * share):02X}" for x, y in zip(a, b, strict=True))


def color_of(value: float, scale: float) -> str:
    """The fill of a value cell: NEUTRAL at 0, the signal color of its sign at the end of the scale. The
    smallest nonzero value still takes a fifth of the color, so a weak effect does not read as none."""
    if not value or not scale:
        return NEUTRAL
    share = 0.2 + 0.8 * min(abs(value) / scale, 1.0)
    return _mix(brand.GROWTH if value > 0 else brand.INHIBITION, share)


_BINOMIAL = re.compile(r"^([A-Z][a-z]+)(?: ([a-z][a-z-]+))?(.*)$")


def _label_svg(name: str) -> str:
    """A label with the genus and species in italics and a strain designation upright, as the help writes
    species names (Karoline, 2026-11-06: "please put species names in italics")."""
    found = _BINOMIAL.match(name)
    if not found:
        return _esc(name)
    genus, species, rest = found.groups()
    taxon = genus + (f" {species}" if species else "")
    return f'<tspan font-style="italic">{_esc(taxon)}</tspan>{_esc(rest)}'


def _cell(n: int) -> float:
    """The cell size: 44 px for a matrix of up to eight organisms, shrinking to CELL for a large one, so a
    pair is not two small squares and the All network still fits a screen's width."""
    return max(CELL, min(44.0, 360.0 / max(n, 1)))


def _lines(text: str, width: int) -> list:
    """`text` broken at spaces into lines of at most `width` characters."""
    out, line = [], ""
    for word in text.split():
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


def adjacency_cells(net: InteractionNetwork) -> tuple:
    """(names, {(row, column): cell}) for the adjacency matrix, one cell per ordered pair of the network.

    A cell is {"kind", "value", "hover"}; its value is the one `matrix.cells` writes in the CSV, the median
    log2 ratio of the pair's arcs, and its hover names every arc behind it.
    """
    from . import matrix
    order = matrix.labels(net)
    names = [matrix._label(net.nodes[nid]) for nid in order]
    values, conflicts = matrix.cells(net)
    arcs: dict = {}
    for edge in net.edges:
        arcs.setdefault((edge.target, edge.source), []).append(edge)
    grid = {}
    for i, affected in enumerate(order):
        for j, actor in enumerate(order):
            head = f"Effect of {names[j]} on {names[i]}"
            if i == j:
                grid[(i, j)] = {"kind": "diagonal", "value": None,
                                "hover": f"{names[i]}: the diagonal is not part of the adjacency matrix "
                                         "(0 in the file)"}
                continue
            pair = (affected, actor)
            present = [e for e in arcs.get(pair, []) if e.status != "absent"]
            absent = [e for e in arcs.get(pair, []) if e.status == "absent"]
            if pair in conflicts:
                lines = [head, f"Not merged: the {_arcs(len(present))} of this pair disagree in sign, so the "
                               "file holds 0", *provenance(present, net)]
                grid[(i, j)] = {"kind": "conflict", "value": 0.0, "hover": "\n".join(lines)}
            elif pair in values and values[pair] is None:
                lines = [head, "NA: one side did not grow, so no ratio exists; the arc carries the measured "
                               "bound", *provenance(present, net)]
                grid[(i, j)] = {"kind": "na", "value": None, "hover": "\n".join(lines)}
            elif pair in values:
                value = values[pair]
                quantified = [e for e in present if e.strength is not None]
                how = (f"the median of {_arcs(len(quantified))}" if len(quantified) > 1 else "from 1 arc")
                lines = [head, f"log2 strength {value:+.3g} ({how})", *provenance(present, net)]
                if absent:
                    lines.append(f"{_arcs(len(absent))} of this pair judged absent, not in the value")
                grid[(i, j)] = {"kind": "value", "value": value, "hover": "\n".join(lines)}
            elif absent:
                lines = [head, f"0: judged no interaction ({_arcs(len(absent))}, absent)",
                         *provenance(absent, net)]
                grid[(i, j)] = {"kind": "zero", "value": 0.0, "hover": "\n".join(lines)}
            else:
                grid[(i, j)] = {"kind": "empty", "value": None, "hover": f"{head}\nNo arc in this search"}
    return names, grid


def glv_cells(net: InteractionNetwork, rates: dict, block: dict, got: dict) -> tuple:
    """(names, {(row, column): cell}) for one matrix of fitted gLV coefficients (`matrix.coefficients`).

    An off-diagonal cell names the arcs its coefficient is the median of; a diagonal names the studies of
    the organism's own growth rate, which with its carrying capacity gives `-r_i / K_i`, or says it came
    from the plateau balance beside its partners. An empty cell gives the reason the package states, when
    there is one.
    """
    names, ids, unit = block["organisms"], block["ids"], block["unit"]
    behind = block.get("behind") or {}
    why_not = {}
    for key in ("pairs_left_out", "arcs_left_out", "across_units"):
        for affected, actor, why in got.get(key) or ():
            why_not.setdefault((affected, actor), why)
    grid = {}
    for i, affected in enumerate(ids):
        for j, actor in enumerate(ids):
            value = block["matrix"][i][j]
            if i == j:
                rate = rates.get(affected) or {}
                if rate.get("rate") is not None and rate.get("capacity"):
                    source = (f"-r / K from its monoculture: r = {rate['rate']:.3g} {rate.get('unit', '1/h')}, "
                              f"K = {rate['capacity']:.3g} {rate.get('capacity_unit', '')}".rstrip())
                else:
                    source = "from its plateau beside its partners (the plateau balance)"
                lines = [f"Self-limitation of {names[i]}", f"{value:+.3g} {unit}", source,
                         _studies_line(rate.get("studies") or (), net, "Studies of its growth rate")]
                grid[(i, j)] = {"kind": "value", "value": value, "hover": "\n".join(lines)}
                continue
            head = f"Effect of {names[j]} on {names[i]}"
            edges = behind.get((affected, actor))
            if edges:
                how = f"the median of {_arcs(len(edges))}" if len(edges) > 1 else "from 1 arc"
                lines = [head, f"{value:+.3g} {unit} ({how})", *provenance(edges, net)]
                grid[(i, j)] = {"kind": "value", "value": value, "hover": "\n".join(lines)}
            else:
                why = why_not.get((names[i], names[j]))
                grid[(i, j)] = {"kind": "empty", "value": None,
                                "hover": f"{head}\nNo coefficient" + (f": {why}" if why else ": no arc fitted")}
    return names, grid


def svg(names: list, grid: dict, title: str, subtitle: str, value_name: str, slug: str = "m") -> str:
    """The matrix as a standalone SVG: title, column labels, row labels, the cells with their hover, and a
    legend with the scale's two ends and every kind of cell that occurs. `slug` keeps the pattern ids of
    two images on one page apart.

    The hover is drawn in the image itself: a panel under the legend shows the hovered cell's text, by a
    CSS `:hover` rule inside the SVG, so it needs no script and works on the page and in the downloaded
    file alike. A `<title>` alone was not enough: a browser's native tooltip for it does not appear in
    every browser (Karoline, 2026-11-14: "the hover does not work"). The `<title>` stays, for screen
    readers and for the browsers that do show it."""
    n = len(names)
    size = _cell(n)
    finite = [abs(c["value"]) for c in grid.values() if c["kind"] == "value" and c["value"] is not None
              and math.isfinite(c["value"])]
    scale = max(finite, default=0.0)
    longest = max((len(s) for s in names), default=4)
    left = 12 + longest * CHAR
    top_labels = longest * CHAR * math.sin(math.radians(50)) + 14
    width = max(left + n * size + 24, 720)
    sub = _lines(subtitle, int((width - 24) / CHAR))
    top = 40 + 16 * len(sub) + top_labels
    kinds = [k for k in KINDS if any(c["kind"] == k for c in grid.values())]
    legend_h = 64 + 20 * len(kinds)
    ly = top + n * size + 40
    # the hover panel, under the legend, as tall as the longest hover text wrapped to its width
    per_line = int((width - 48) / CHAR)
    wrapped = {key: [piece for line in cell["hover"].splitlines() for piece in (_lines(line, per_line) or [""])]
               for key, cell in grid.items()}
    panel_y = ly + legend_h - 4
    panel_h = 24 + 16 * max((len(lines) for lines in wrapped.values()), default=1)
    height = panel_y + panel_h + 12
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
           f'<linearGradient id="{slug}-scale" x1="0" x2="1" y1="0" y2="0">'
           f'<stop offset="0" stop-color="{brand.INHIBITION}"/><stop offset="0.5" stop-color="{NEUTRAL}"/>'
           f'<stop offset="1" stop-color="{brand.GROWTH}"/></linearGradient>'
           "</defs>",
           "<style>.tip{visibility:hidden}.cell:hover .tip{visibility:visible}"
           f".cell:hover>rect{{stroke:{brand.INK};stroke-width:2}}</style>",
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
    # the panel's frame and its resting text, drawn before the cells so a hovered cell's text covers it
    out += [f'<rect x="12" y="{panel_y:.1f}" width="{width - 24:.0f}" height="{panel_h}" rx="4" '
            f'fill="{brand.PANEL}" stroke="{brand.LINE}"/>',
            f'<text x="24" y="{panel_y + 20:.1f}" font-size="12" fill="{brand.MUTED}">Hover a cell: its value '
            "and the studies and experiments behind it appear here.</text>"]
    fills = {"zero": NEUTRAL, "na": f"url(#{slug}-na)", "conflict": f"url(#{slug}-conflict)", "empty": EMPTY,
             "diagonal": brand.LINE}
    for (i, j), cell in sorted(grid.items()):
        fill = (color_of(cell["value"], scale) if cell["kind"] == "value" and cell["value"] is not None
                else fills.get(cell["kind"], EMPTY))
        x, y = left + j * size, top + i * size
        # the first line names the pair, in bold, as a heading for the rest
        tip = "".join(f'<text x="24" y="{panel_y + 20 + 16 * k:.1f}" font-size="12" fill="{brand.INK}"'
                      + (' font-weight="600"' if k == 0 else "") + f">{_esc(line)}</text>"
                      for k, line in enumerate(wrapped[(i, j)]))
        out.append(f'<g class="cell"><title>{_esc(cell["hover"])}</title>'
                   f'<rect x="{x + GAP / 2:.1f}" y="{y + GAP / 2:.1f}" '
                   f'width="{size - GAP:.1f}" height="{size - GAP:.1f}" '
                   f'rx="2" fill="{fill}" stroke="{brand.LINE}" stroke-width="0.6"/>'
                   f'<g class="tip"><rect x="13" y="{panel_y + 1:.1f}" width="{width - 26:.0f}" '
                   f'height="{panel_h - 2}" rx="4" fill="{brand.PANEL}"/>{tip}</g></g>')
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
    out.append("</svg>")
    return "\n".join(out) + "\n"


def adjacency_svg(net: InteractionNetwork) -> str:
    names, grid = adjacency_cells(net)
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
