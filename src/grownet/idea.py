"""The figure of the help page's introduction: the comparison grownet makes, drawn from code.

Two species grown alone, each in its own panel, then together, and the arcs the change gives. The curves
come from the Baranyi-Roberts model the tool fits (`rates._baranyi`), and each panel marks the three
growth measures the tool can compare, computed the way the tool computes them: the area under the curve
(auc, on abundance, down to zero), the maximal abundance (max), and the growth rate (the steepest slope of
log abundance, reached in the marked stretch). The parameters are illustrative, not data.
"""
from __future__ import annotations

import math

from .brand import GROWTH, INHIBITION, INK, MUTED
from .rates import _baranyi

A_COLOR, B_COLOR = "#2A78D6", "#C98500"     # blue and amber: apart for every common color vision deficiency
T_END, Y_TOP, N0 = 24.0, 1.15, 0.02
STEPS = 96

# (maximal abundance, maximum specific growth rate per hour, lag in hours), all illustrative
ALONE = {"A": (1.00, 0.90, 3.0), "B": (0.70, 0.60, 4.0)}
TOGETHER = {"A": (0.60, 0.75, 3.0), "B": (1.00, 0.70, 3.5)}   # A does worse beside B, B better beside A

W, H = 320, 232
LEFT, TOP, BOTTOM = 34, 30, 196


def _abundance(t: float, params) -> float:
    nmax, mu, lag = params
    return math.exp(_baranyi(t, math.log(N0), mu, math.log(nmax / N0), mu * lag))


def _curve(params):
    return [(T_END * i / STEPS, _abundance(T_END * i / STEPS, params)) for i in range(STEPS + 1)]


def _steep_stretch(points, share: float = 0.9):
    """The stretch where the slope of log abundance is within `share` of its steepest: the growth rate."""
    slopes = [(math.log(b[1]) - math.log(a[1])) / (b[0] - a[0]) for a, b in zip(points[:-1], points[1:], strict=True)]
    best = max(slopes)
    steep = [i for i, s in enumerate(slopes) if s >= share * best]
    return points[min(steep):max(steep) + 2]


class _Panel:
    def __init__(self, right: float):
        self.right = right

    def x(self, t: float) -> float:
        return LEFT + (self.right - LEFT) * t / T_END

    def y(self, n: float) -> float:
        return BOTTOM - (BOTTOM - TOP) * n / Y_TOP

    def path(self, points) -> str:
        return "M " + " L ".join(f"{self.x(t):.1f} {self.y(n):.1f}" for t, n in points)

    def axes(self) -> str:
        return (f'<path d="M {LEFT} {TOP - 6} L {LEFT} {BOTTOM} L {self.right + 6} {BOTTOM}" fill="none" '
                f'stroke="{MUTED}" stroke-width="1.2"/>'
                f'<text x="{(LEFT + self.right) / 2:.0f}" y="{BOTTOM + 18}" text-anchor="middle" '
                f'class="ax">time</text>'
                f'<text x="{LEFT - 10}" y="{(TOP + BOTTOM) / 2:.0f}" text-anchor="middle" class="ax" '
                f'transform="rotate(-90 {LEFT - 10} {(TOP + BOTTOM) / 2:.0f})">abundance</text>')


def _svg(title: str, label: str, body: str) -> str:
    style = (f".ax{{font:12px system-ui,sans-serif;fill:{MUTED}}}"
             f".lb{{font:12px system-ui,sans-serif;fill:{INK}}}"
             f".hd{{font:600 13px system-ui,sans-serif;fill:{INK}}}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="{label}">'
            f"<title>{label}</title><style>{style}</style>"
            f'<text x="{LEFT}" y="16" class="hd">{title}</text>{body}</svg>')


def _alone(name: str, color: str) -> str:
    p = _Panel(W - 16)
    points = _curve(ALONE[name])
    top = max(n for _, n in points)
    stretch = _steep_stretch(points)
    area = p.path(points) + f" L {p.x(T_END):.1f} {BOTTOM} L {p.x(0):.1f} {BOTTOM} Z"
    end_t, end_n = stretch[-1]
    body = (f'<path d="{area}" fill="{color}" fill-opacity="0.14"/>'
            f'<line x1="{LEFT}" y1="{p.y(top):.1f}" x2="{p.right}" y2="{p.y(top):.1f}" stroke="{INK}" '
            f'stroke-width="1" stroke-dasharray="4 3"/>'
            f'<text x="{p.right}" y="{p.y(top) - 5:.1f}" text-anchor="end" class="lb">maximum (max)</text>'
            f'<path d="{p.path(points)}" fill="none" stroke="{color}" stroke-width="2.2"/>'
            f'<path d="{p.path(stretch)}" fill="none" stroke="{color}" stroke-width="6" stroke-opacity="0.45" '
            f'stroke-linecap="round"/>'
            f'<text x="{p.x(end_t) + 8:.1f}" y="{p.y(end_n) + 16:.1f}" class="lb">growth rate</text>'
            f'<text x="{p.x(T_END * 0.72):.1f}" y="{p.y(top * 0.35):.1f}" text-anchor="middle" '
            f'class="lb">area (auc)</text>'
            + p.axes())
    return _svg(f"{name} alone", f"Growth curve of species {name} alone, with its area, maximum and growth "
                f"rate marked", body)


def _together() -> str:
    p = _Panel(W - 90)
    body = []
    for k, (name, color) in enumerate((("A", A_COLOR), ("B", B_COLOR))):
        alone, together = _curve(ALONE[name]), _curve(TOGETHER[name])
        body.append(f'<path d="{p.path(alone)}" fill="none" stroke="{color}" stroke-width="1.4" '
                    f'stroke-dasharray="4 3" stroke-opacity="0.8"/>'
                    f'<path d="{p.path(together)}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        was, now = alone[-1][1], together[-1][1]
        x = p.right + 10 + 14 * k                             # one arrow each, side by side
        tip = p.y(now) + (6 if now < was else -6)
        head = -1 if now < was else 1                         # the arrowhead points at the value together
        body.append(f'<line x1="{x}" y1="{p.y(was):.1f}" x2="{x}" y2="{tip:.1f}" stroke="{color}" '
                    f'stroke-width="2"/>'
                    f'<path d="M {x - 4.5} {tip:.1f} L {x + 4.5} {tip:.1f} L {x} {tip - 7 * head:.1f} Z" '
                    f'fill="{color}"/>'
                    f'<text x="{p.right + 36}" y="{p.y(now) + 4:.1f}" class="lb">'
                    f'{name} {"lower" if now < was else "higher"}</text>')
    key = (f'<line x1="{LEFT + 10}" y1="{TOP + 4}" x2="{LEFT + 30}" y2="{TOP + 4}" stroke="{MUTED}" '
           f'stroke-width="1.4" stroke-dasharray="4 3"/><text x="{LEFT + 35}" y="{TOP + 8}" class="ax">alone</text>'
           f'<line x1="{LEFT + 82}" y1="{TOP + 4}" x2="{LEFT + 102}" y2="{TOP + 4}" stroke="{MUTED}" '
           f'stroke-width="2.2"/><text x="{LEFT + 107}" y="{TOP + 8}" class="ax">together</text>')
    return _svg("A and B together", "Growth curves of A and B grown together, with their curves alone dashed: "
                "A reaches less, B reaches more", "".join(body) + key + p.axes())


def _arc(start, control, end, color) -> str:
    """A quadratic arc whose arrowhead lies along its tangent at the end, touching the target node."""
    (x0, y0), (cx, cy), (x2, y2) = start, control, end
    length = math.hypot(x2 - cx, y2 - cy)
    ux, uy = (x2 - cx) / length, (y2 - cy) / length
    bx, by = x2 - 11 * ux, y2 - 11 * uy                 # the arrowhead's base; the line stops there
    return (f'<path d="M {x0} {y0} Q {cx} {cy} {bx:.1f} {by:.1f}" fill="none" stroke="{color}" '
            f'stroke-width="3"/>'
            f'<path d="M {x2} {y2} L {bx - 6 * uy:.1f} {by + 6 * ux:.1f} L {bx + 6 * uy:.1f} {by - 6 * ux:.1f} Z" '
            f'fill="{color}"/>')


def _arcs() -> str:
    """The arcs the comparison gives, in the legend's colors and with its uniform arrowheads."""
    ax, bx, y, r, o = 70, 250, 118, 20, 14             # o: where an arc meets a node, at 45 degrees
    mid = (ax + bx) / 2
    body = (_arc((ax + o, y - o), (mid, y - 72), (bx - o, y - o), GROWTH)
            + _arc((bx - o, y + o), (mid, y + 72), (ax + o, y + o), INHIBITION)
            + f'<circle cx="{ax}" cy="{y}" r="{r}" fill="{A_COLOR}"/>'
            f'<circle cx="{bx}" cy="{y}" r="{r}" fill="{B_COLOR}"/>'
            f'<text x="{ax}" y="{y + 5}" text-anchor="middle" class="hd" style="fill:#fff">A</text>'
            f'<text x="{bx}" y="{y + 5}" text-anchor="middle" class="hd" style="fill:#fff">B</text>'
            f'<text x="{mid}" y="{y - 46}" text-anchor="middle" class="lb">A facilitates B</text>'
            f'<text x="{mid}" y="{y + 56}" text-anchor="middle" class="lb">B inhibits A</text>')
    return _svg("The arcs it gives", "Two arcs: a green arc from A to B, A facilitates B, and an orange-red arc "
                "from B to A, B inhibits A", body)


def idea_figure() -> str:
    """The four panels, side by side where the page is wide and stacked where it is narrow."""
    panels = (_alone("A", A_COLOR), _alone("B", B_COLOR), _together(), _arcs())
    return '<div class="idea">' + "".join(f"<figure>{svg}</figure>" for svg in panels) + "</div>"
