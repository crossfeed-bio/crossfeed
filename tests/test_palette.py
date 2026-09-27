"""The two signal colors stay apart for a reader with a color vision deficiency.

The arc tips are uniform (Karoline, 2026-09-27), so the color is the only cue for the sign of an
interaction. Green against red, the pair the tool used first, is the hardest one to tell apart: roughly
eight percent of men see little difference. This simulates the two common dichromacies and requires the
colors to stay far apart under both, so the palette cannot drift back to a pair that only works for
readers with typical color vision.

The simulation is Vienot, Brettel and Mollon (1999): sRGB to linear light, to LMS cone responses, with the
missing cone's response replaced by what the remaining two predict, and back. It is the standard
approximation, and exact enough to separate a pair that works from one that does not.
"""
import math

import pytest

from crossfeed.cytoscape import FACILITATION as CY_FACILITATION
from crossfeed.cytoscape import INHIBITION as CY_INHIBITION
from crossfeed.cytoscape import MUTED as CY_MUTED
from crossfeed.legend import FACILITATION, INHIBITION, MUTED

_RGB_TO_LMS = ((0.31399, 0.63951, 0.04649), (0.15537, 0.75789, 0.08670), (0.01775, 0.10945, 0.87262))
_LMS_TO_RGB = ((5.47221, -4.64196, 0.16963), (-1.12524, 2.29317, -0.16789), (0.02980, -0.19318, 1.16364))
_DICHROMACY = {
    "protanopia": ((0, 1.05118294, -0.05116099), (0, 1, 0), (0, 0, 1)),
    "deuteranopia": ((1, 0, 0), (0.9513092, 0, 0.04866992), (0, 0, 1)),
}
APART = 70.0        # sRGB units between the two colors after simulation; green and red managed only 58


def _channels(color: str) -> tuple:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _to_linear(value: float) -> float:
    value /= 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _apply(matrix, vector) -> list:
    return [sum(row[i] * vector[i] for i in range(3)) for row in matrix]


def simulate(color: str, kind: str) -> tuple:
    """`color` as a reader with that dichromacy sees it, as sRGB channels."""
    linear = [_to_linear(c) for c in _channels(color)]
    seen = _apply(_LMS_TO_RGB, _apply(_DICHROMACY[kind], _apply(_RGB_TO_LMS, linear)))
    out = []
    for value in seen:
        value = min(1.0, max(0.0, value))
        value = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
        out.append(round(value * 255))
    return tuple(out)


def luminance(color: str) -> float:
    r, g, b = (_to_linear(c) for c in _channels(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(color: str, against: str = "#ffffff") -> float:
    high, low = sorted((luminance(color), luminance(against)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("kind", sorted(_DICHROMACY))
def test_facilitation_and_inhibition_stay_apart(kind):
    apart = math.dist(simulate(FACILITATION, kind), simulate(INHIBITION, kind))
    assert apart > APART, f"{FACILITATION} and {INHIBITION} are {apart:.0f} apart under {kind}"


def test_an_absent_edge_is_told_apart_by_lightness_not_by_hue():
    # simulated, the gray of an absent edge sits near the green (about 60 units): hue does not separate
    # them. Lightness does, and an absent edge is also thinner and hidden by default, so the color is
    # never its only cue.
    for signal in (FACILITATION, INHIBITION):
        assert luminance(MUTED) > luminance(signal) * 1.4


def test_the_legend_and_the_cytoscape_style_use_the_same_colors():
    # one vocabulary: a screenshot of the page and a Cytoscape network have to agree
    assert (FACILITATION.lower(), INHIBITION.lower(), MUTED.lower()) == \
        (CY_FACILITATION.lower(), CY_INHIBITION.lower(), CY_MUTED.lower())


@pytest.mark.parametrize("color", [FACILITATION, INHIBITION])
def test_the_signal_colors_are_readable_as_text_on_white(color):
    # they label directions in the page's table, so they meet the 4.5:1 rule for body text
    assert contrast(color) >= 4.5


@pytest.mark.parametrize("kind", sorted(_DICHROMACY))
@pytest.mark.parametrize("color", ["#ff0000", "#00ff00", "#1a7f5a", "#c2410c", "#8a8a8a"])
def test_the_simulation_lands_on_the_dichromatic_plane(color, kind):
    # a check on the check: a reader missing the long or medium cone cannot separate red from green, so
    # every simulated color comes back with its red and green channels nearly equal. If this fails, the
    # matrices are wrong and the distances above mean nothing.
    red, green, _ = simulate(color, kind)
    assert abs(red - green) <= 12
