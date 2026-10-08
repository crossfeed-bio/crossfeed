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
        r"function graphmlValue\(attr,v,ty\)\{.*?\n\}\n",
        # the graph-level resolver: flat key names over a nested meta (#155 item 4)
        r"const GRAPH_META=\{.*?\};\n", r"function graphMeta\(meta,nm\)\{.*?\}\n",
        r"function toGraphML\(net\)\{.*?\n\}\n"))
    # Every key this release added has to be carried by the fixture, or the two writers agree about
    # nothing. The test used to build its network with no `meta` at all and a record holding none of the
    # fitted fields, so each new key was skipped on both sides and the equality held vacuously: that is
    # how the viewer came to write four graph-level attributes as nothing and one as "[object Object]"
    # while this test passed (#155 item 4).
    record = {"source": "ncbi:1", "target": "ncbi:2", "source_name": "Blautia a", "target_name": "Roseburia b",
              "source_taxon_id": "1", "effect": "inhibition", "strength": -1.25, "weight": 1.25, "sd": 0.5,
              "se": 0.25, "status": "present", "quality": ["single_replicate"], "notes": ["one note", "two"],
              "cautions": ["two_replicates", "window_partial"], "experiments": ["E1", "E2"],
              "study_id": "S1", "strength_range": [-2, -0.5], "merged_arcs": 2, "n_with": 3,
              # what the integrated derivation adds, including this release's own fields
              "coefficient": -4.351e-10, "coefficient_unit": "1/(h x Cells/mL)",
              "coefficient_sd": 1.2e-10, "coefficient_n": 3,
              "coefficient_sd_from_rate_stage": 3.4e-11,
              "se_replicates": 0.2, "se_rate_stage": 0.15,
              "rate_stage_method": "bootstrap of 3 monoculture replicate(s), 200 resamples",
              "rate_stage_n": 3, "fit_r2": 0.9994, "fit_null_r2": 0.9879, "fit_condition": 227.6,
              "fit_window_share": 0.2667, "rate_mismatch_to_zero": -0.1498,
              "partner_abundance": 2.4e8, "partner_abundance_unit": "Cells/mL", "partner_abundance_n": 3,
              "metric_with": 0.52, "metric_without": 0.8, "target_capacity": 9.13e8,
              "target_capacity_unit": "Cells/mL", "target_capacity_n": 3,
              "strength_bound": -1.5, "bound_rule": "no-growth rule",
              "medium": "Wilkins-Chalgren Anaerobe Broth (WC)", "cultivation_mode": "batch",
              "outcome": "quantified", "metric": "integrated:two_stage", "evidence": "biculture",
              "community": ["ncbi:1", "ncbi:2"], "p_value": 0.0042, "q_value": 0.0068,
              "significance": 2.1675, "effect_over_sd": 2.5, "n_without": 3,
              "supporting_pairs": 1, "merged_pairs": ["Blautia a -> Roseburia b"]}
    # and the graph-level meta the viewer was reading at the wrong depth
    meta = {"absence": {"rule": "|log2 mean| < k sd", "k": 1.0, "absent": 7},
            "hidden": {"low_quality": 2, "absent": 7},
            "statistics": {"test": "two-sided t-test of the fitted log2 strength against no effect"}}
    net = records_to_network([record], meta)
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


def test_the_viewer_accepts_every_network_the_tool_writes():
    """gui/index.html once rejected every file grownet writes: its guard tested the schema id against
    `crossfeed.interaction_network` after the rename, so "unexpected schema" came out of a file the tool
    had just produced (found 2026-10-06, fixed on #141). Nothing pinned the guard, so this runs the line
    itself with Node against every id a reader may meet, including the gLV payload's, which belongs to the
    other download and must still be refused."""
    import json
    import re
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    from grownet.model import KNOWN_SCHEMAS
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    page = (Path(__file__).resolve().parents[1] / "gui" / "index.html").read_text(encoding="utf-8")
    guard = re.search(r"^.*unexpected schema.*$", page, re.M).group(0).strip()
    accept = [*KNOWN_SCHEMAS, "crossfeed.interaction_network/v0"]   # the id before the rename stays valid
    refuse = ["grownet.glv/v1", "grownet.all_result/v1", "other/v1"]
    js = ("function check(s){const d={schema:s};try{" + guard + "return 'yes';}catch(e){return 'no';}}"
          "console.log(JSON.stringify(" + json.dumps(accept + refuse) + ".map(check)));")
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert got == ["yes"] * len(accept) + ["no"] * len(refuse)
