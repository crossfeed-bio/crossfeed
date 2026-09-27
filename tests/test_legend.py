"""The legend: it stays in step with the vocabulary it explains, and with the file the docs link to."""
import os
import re
from xml.etree import ElementTree as ET

import pytest

from crossfeed.legend import ARCS, LEFT, TEXT_X, WIDTH, legend_page, legend_svg
from crossfeed.model import CAUTIONS, EFFECTS, EVIDENCE, OUTCOMES, QUALITY_FLAGS, STATUSES

SVG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "legend.svg")
CHAR = 0.56 * 13        # a generous width per character at the 13px meaning size


def _words(svg: str) -> str:
    return " ".join(re.findall(r">([^<]*)</text>", svg))


def test_the_legend_is_well_formed_svg():
    root = ET.fromstring(legend_svg())
    assert root.tag.endswith("svg") and root.get("viewBox").startswith("0 0 ")
    assert root.get("aria-label") == "interaction network legend"
    # the name of the tool is not in the picture: species interact for many reasons, not only cross-feeding
    # (Karoline, 2026-09-27), and the tool is being renamed
    assert "crossfeed" not in legend_svg()


@pytest.mark.parametrize("value", [*EFFECTS, *OUTCOMES, *QUALITY_FLAGS, *CAUTIONS, *EVIDENCE, *STATUSES])
def test_every_value_a_reader_can_meet_is_explained(value):
    # a value the legend does not name is a value a reader cannot look up (as in the viewer's guard, #57)
    assert value.replace("_", " ") in _words(legend_svg()) or value in _words(legend_svg())


def test_nothing_is_drawn_outside_the_canvas():
    svg = legend_svg()
    height = int(re.search(r'viewBox="0 0 \d+ (\d+)"', svg).group(1))
    texts = [(float(x), float(y), len(t))
             for x, y, t in re.findall(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)</text>', svg)]
    assert texts and max(x + CHAR * n for x, _, n in texts) <= WIDTH
    assert max(y for _, y, _ in texts) <= height - 10
    assert LEFT < TEXT_X < WIDTH


def test_the_shipped_file_is_what_the_code_draws():
    # docs/legend.svg is linked from the README, so it cannot drift: regenerate it with `make legend`
    with open(SVG_FILE, encoding="utf-8") as f:
        assert f.read() == legend_svg()


def test_the_page_carries_the_drawing_and_a_way_back():
    page = legend_page("tok&1")
    assert "<svg" in page and 'href="/?token=tok&amp;1"' in page
    assert "<svg" in legend_page() and "Back to crossfeed" not in legend_page()


def test_every_arc_ends_in_the_same_head():
    # Karoline, 2026-09-27: uniform tips, the color carries the sign. A bar head would be a line, not a
    # path, so counting the heads catches a row that goes its own way
    svg = legend_svg()
    heads = re.findall(r'<path d="M [\d.]+ [\d.]+ l -15 -7\.5 l 0 15 z" fill="(#[0-9A-Fa-f]{6})"/>', svg)
    assert len(heads) == len(ARCS)
    assert len(set(heads)) > 1                       # they differ in color, which is the whole point
