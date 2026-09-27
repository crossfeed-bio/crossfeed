"""The legend: what every line, arrowhead and flag on a crossfeed network means.

A reader meets the network in Cytoscape or on the local page, where an arc carries several channels at
once (direction, width, dash pattern) and an edge carries flags that decide whether it is drawn at all.
Karoline asked for one compact picture they can open while looking at a network, as part of the help
(2026-09-21).

The picture is drawn here rather than kept as a hand-edited file, so it cannot drift from the vocabulary
it explains: `tests/test_legend.py` requires every value of `model.EFFECTS`, `OUTCOMES`, `QUALITY_FLAGS`,
`CAUTIONS`, `EVIDENCE` and `STATUSES` to appear in it, and `docs/legend.svg` to be exactly what
`legend_svg()` returns. Regenerate that file with `make legend`.

Standard library only, as everywhere else: the SVG is text, and the local page serves it as a page of its
own.
"""
from __future__ import annotations

import html
from xml.sax.saxutils import escape

from .brand import LOGO, logo_svg  # noqa: F401  (re-exported: docs/logo.svg is drawn from it)

WIDTH = 900
LEFT, TEXT_X = 40, 214          # sample arcs on the left, their meaning to the right of this
LINE, WRAP = 16, 72             # line height, and characters per line (SVG has no text flow)
# Facilitation green and inhibition orange-red. The orange replaces a plain red (Karoline, 2026-09-27):
# the arc tips are uniform, so the color is the only cue for the sign, and green against red is the hardest
# pair for a reader with a color vision deficiency. Simulated (Vienot 1999), these two stay about 90 sRGB
# units apart under protanopia and deuteranopia, where green and red were about 58. The test keeps it so.
FACILITATION, INHIBITION, MUTED, INK = "#1a7f5a", "#c2410c", "#8a8a8a", "#222222"

# (dash pattern, stroke width, color, head, label, meaning)
ARCS = [
    ("", 3, FACILITATION, "arrow", "facilitation",
     "the target grows more with the source present: log2 mean above zero, outcome quantified"),
    ("", 3, INHIBITION, "arrow", "inhibition",
     "the target grows less with the source present: log2 mean below zero. Every arc ends in the same "
     "head, so the color alone carries the sign"),
    ("", 7, FACILITATION, "arrow", "obligate",
     "the target grows only with the source present, so there is no ratio to report. Always present"),
    ("", 7, INHIBITION, "arrow", "abolished",
     "the target grows only without the source. Always present, like obligate"),
    ("11 6", 3, FACILITATION, "arrow", "dropout evidence",
     "the source was removed from a community, so its effect can run through a third member. A solid arc "
     "is biculture evidence: one species against the same species with one partner, direct"),
    ("2 5", 3, FACILITATION, "arrow", "single_replicate",
     "one replicate on a side: the comparison holds, its spread is unknown, and its status stays "
     "undetermined. Drawn, because one replicate is often all a study has"),
    ("", 2, MUTED, "arrow", "absent",
     "below the absence threshold k, that is |log2 mean| < k times sd. Exported with status absent and "
     "hidden by the Cytoscape style; everything above it has status present"),
]

NOTES = [
    ("Line width", "the edge weight, |log2 mean|: a thicker arc is a larger effect. The sign is the "
                   "color, never the width and never the shape of the head."),
    ("Node", "one organism, labeled with its name; in Cytoscape colored by genus (up to four, then gray)."),
    ("Shown, with a caution", "two_replicates: the spread rests on two values per side. The edge keeps its "
                              "status and is drawn."),
    ("Not drawn by default", "the quality flags strains_pooled, removed_member_detected and non_batch. The "
                             "comparison itself is in doubt, so such an edge is never read as an absence of "
                             "an interaction."),
    ("Not an edge at all", "the outcomes no_growth, where nothing grew in either set, and a comparison whose "
                           "set was emptied by exclusions. Both are reported with a reason instead."),
    ("neutral", "a log2 mean of exactly zero: no direction, and always absent. There is no neutral edge in "
                "the sense of a weak one."),
    ("Support, not decision", "each edge carries Welch's t-test corrected for multiple testing. Presence "
                              "follows the threshold k, never the test."),
]


SUBTITLE = ["An arc points from the source to the organism it affects. The color gives the direction,",
            "the width the size, the dashes the evidence. Every arc ends in the same arrowhead."]


# The mark (docs/logo.svg) lives in crossfeed.brand with the page palette; imported here for `make logo`.


def _wrap(text: str, width: int = WRAP) -> list:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return [*lines, line] if line else lines


def _head(x: float, y: float, kind: str, color: str) -> str:
    """The head that ends a sample arc: the same arrowhead on every arc, whatever its direction.

    Karoline, 2026-09-27, choosing the mark: the tips are uniform and the color distinguishes a positive
    from a negative effect. The Cytoscape style maps both effects to ARROW for the same reason.
    """
    if kind != "arrow":
        raise ValueError(f"unknown head {kind!r}: every arc ends in an arrow")
    return f'<path d="M {x} {y} l -15 -7.5 l 0 15 z" fill="{color}"/>'


def _text(x: float, y: float, lines, css: str) -> str:
    return "".join(f'<text x="{x}" y="{y + LINE * i}" class="{css}">{escape(part)}</text>'
                   for i, part in enumerate(lines))


def legend_svg() -> str:
    """The legend as a standalone SVG document."""
    rows, y = [], 100
    for dash, width, color, head, label, meaning in ARCS:
        dashes = f' stroke-dasharray="{dash}"' if dash else ""
        lines = _wrap(meaning)
        rows.append(f'<line x1="{LEFT}" y1="{y}" x2="{LEFT + 136}" y2="{y}" stroke="{color}" '
                    f'stroke-width="{width}"{dashes}/>{_head(LEFT + 150, y, head, color)}')
        rows.append(_text(TEXT_X, y - 4, [label], "label"))
        rows.append(_text(TEXT_X, y + 13, lines, "meaning"))
        y += 24 + LINE * len(lines)
    y += 14
    rows.append(f'<line x1="{LEFT}" y1="{y - 26}" x2="{WIDTH - LEFT}" y2="{y - 26}" stroke="#dddddd"/>')
    for title, text in NOTES:
        lines = _wrap(text)
        rows.append(_text(LEFT, y, [title], "label"))
        rows.append(_text(TEXT_X, y, lines, "meaning"))
        y += 10 + LINE * len(lines)
    height = y + 14
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" '
            f'height="{height}" role="img" aria-label="interaction network legend">'
            '<style>'
            f'text {{ font-family: system-ui, -apple-system, sans-serif; fill: {INK}; }}'
            '.title { font-size: 21px; font-weight: 600; }'
            '.subtitle { font-size: 13px; fill: #555555; }'
            '.label { font-size: 14px; font-weight: 600; }'
            '.meaning { font-size: 13px; fill: #444444; }'
            '</style>'
            f'<rect width="{WIDTH}" height="{height}" fill="#ffffff"/>'
            '<text x="40" y="40" class="title">Interaction network legend</text>'
            + _text(40, 62, SUBTITLE, "subtitle")
            + "".join(rows) + '</svg>\n')


def legend_page(token: str = "") -> str:
    """The legend as a page of the local server, with a link back to the form."""
    back = f'<p><a href="/?token={html.escape(token, quote=True)}">Back to crossfeed</a></p>' if token else ""
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Interaction network legend</title>'
            '<style>body { font: 16px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 52rem; '
            'padding: 2rem 1rem; } svg { max-width: 100%; height: auto; }</style></head><body>'
            f'{legend_svg()}{back}</body></html>\n')
