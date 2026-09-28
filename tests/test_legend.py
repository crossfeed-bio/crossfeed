"""The legend: it stays in step with the vocabulary it explains, and with the file the docs link to."""
import os
import re
from xml.etree import ElementTree as ET

import pytest

from grownet.legend import ARCS, LEFT, TEXT_X, WIDTH, legend_page, legend_svg
from grownet.model import CAUTIONS, EFFECTS, EVIDENCE, OUTCOMES, QUALITY_FLAGS, STATUSES

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
    assert "grownet" not in legend_svg()


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
    assert "<svg" in legend_page() and "Back to grownet" not in legend_page()


def test_every_arc_ends_in_the_same_head():
    # Karoline, 2026-09-27: uniform tips, the color carries the sign. A bar head would be a line, not a
    # path, so counting the heads catches a row that goes its own way
    svg = legend_svg()
    heads = re.findall(r'<path d="M [\d.]+ [\d.]+ l -15 -7\.5 l 0 15 z" fill="(#[0-9A-Fa-f]{6})"/>', svg)
    assert len(heads) == len(ARCS)
    assert len(set(heads)) > 1                       # they differ in color, which is the whole point


def test_the_viewer_draws_the_same_vocabulary():
    # gui/index.html, the standalone viewer, uses the legend's colors, one arrowhead for every arc (no
    # T-bar), dashes only for evidence and quality, and the genus colors of grownet.brand (2026-09-27)
    import json
    import re
    from pathlib import Path

    from grownet import brand
    page = (Path(__file__).resolve().parents[1] / "gui" / "index.html").read_text(encoding="utf-8")
    assert f"--fac:{brand.GROWTH};" in page and f"--inh:{brand.INHIBITION};" in page
    assert "M10,1 L10,11" not in page                                   # the T-bar head is gone
    assert 'inhibition:{color:()=>getVar("--inh"),dash:"",head:"inh"}' in page
    colors = json.loads(re.search(r"const GENUS_COLORS=(\[.*?\]);", page).group(1))
    assert colors == list(brand.GENUS_COLORS)


def test_the_viewer_writes_the_same_graphml_as_the_command_line(tmp_path):
    # gui/index.html's toGraphML, run with Node on a real-shaped network, gives the same graph, keys and
    # values as grownet.export.to_graphml (the viewer once wrote 9 of the 34 keys)
    import json
    import re
    import shutil
    import subprocess
    from pathlib import Path
    from xml.etree import ElementTree as ET

    import pytest

    from grownet.export import _KEYS, to_graphml
    from grownet.mgrowthdb import records_to_network
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    page = (Path(__file__).resolve().parents[1] / "gui" / "index.html").read_text(encoding="utf-8")
    assert json.loads(re.search(r"const GRAPHML_KEYS=(\[.*?\]);", page).group(1)) == [list(k) for k in _KEYS]
    js = "\n".join(re.search(pattern, page, re.S).group(0) for pattern in (
        r"function esc\(s\)\{.*?\}\n", r"function xmlClean\(s\)\{.*?\}\n", r"const GRAPHML_KEYS=\[.*?\];\n",
        # the style's columns (genus, genus_color, line_style, display_weight) and what they are computed from
        r"const flagsOf=[^\n]*\n", r"const GENUS_COLORS=[^\n]*\n", r"const GENUS_QUALIFIERS=[^\n]*\n",
        r"const cap=[^\n]*\n", r"const genusOf=.*?\};\n", r"const lineStyleOf=.*?\};\n",
        r"const displayWeightOf=[^\n]*\n", r"const pyFloat=[^\n]*\n",
        r"function graphmlValue\(attr,v\)\{.*?\n\}\n", r"function toGraphML\(net\)\{.*?\n\}\n"))
    record = {"source": "ncbi:1", "target": "ncbi:2", "source_name": "Blautia a", "target_name": "Roseburia b",
              "source_taxon_id": "1", "effect": "inhibition", "strength": -1.25, "weight": 1.25, "sd": 0.5,
              "status": "present", "quality": ["single_replicate"], "notes": ["one note", "two"],
              "cautions": ["two_replicates"], "experiments": ["E1", "E2"], "study_id": "S1",
              "strength_range": [-2, -0.5], "merged_arcs": 2, "n_with": 3}
    net = records_to_network([record])
    doc = json.loads(net.to_json())
    script = tmp_path / "run.js"
    script.write_text(js + f"\nprocess.stdout.write(toGraphML({json.dumps(doc)}));", encoding="utf-8")
    ours = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout

    def content(xml):
        root = ET.fromstring(xml)
        ns = "{http://graphml.graphdrawing.org/xmlns}"
        keys = sorted((k.get("id"), k.get("for"), k.get("attr.name"), k.get("attr.type"))
                      for k in root.iter(ns + "key"))
        data = sorted((el.tag.split("}")[1], el.get("id", ""), d.get("key"), d.text)
                      for el in root.iter() if el.tag in (ns + "graph", ns + "node", ns + "edge")
                      for d in el.findall(ns + "data"))
        return keys, data
    assert content(ours) == content(to_graphml(net))
