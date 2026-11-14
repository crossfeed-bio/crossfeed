"""The interaction matrix as an image (#341), on hand-built networks.

Karoline, 2026-11-14: "provide the interaction matrix as an image, with a hover function that says from
which studies/experiments each entry is derived. the image can be downloaded. the image would need a legend
to know the colors of negative and positive entries". Her choices: both matrices (the adjacency matrix, and
in gLV mode each matrix of coefficients), on the local page's result, as SVG only.

Every expected number is computed by hand in the test that uses it.
"""
import math
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import pytest
from test_glv_coefficients import _arc as _glv_arc
from test_glv_coefficients import _net as _glv_net
from test_glv_coefficients import _rate
from test_gui import _get, server  # noqa: F401 - `server` is the fixture the page test uses

from grownet import brand, matrix, matrix_image
from grownet.mgrowthdb import records_to_network

SVG = "{http://www.w3.org/2000/svg}"


def _arc(source, target, strength, study, experiments, **extra):
    return {"source": source, "target": target, "source_name": source.upper(), "target_name": target.upper(),
            "effect": "facilitation" if (strength or 0) > 0 else "inhibition", "strength": strength,
            "weight": abs(strength or 0), "status": "present", "outcome": "quantified", "study_id": study,
            "study_citation": {"S1": "Study one", "S2": "Study two"}.get(study, ""),
            "experiments": experiments, **extra}


# Three organisms, A, B and C, and one pair of each kind a cell can be (rows affected, columns the actor):
#   a on b: +1 (S1, E1) and +3 (S2, E2 E3), the median is +2, the largest value, so the scale is 2
#   c on a: -0.5 (S1, E4), a quarter of the scale
#   b on c: judged absent (S3, E5), so 0
#   a on c: obligate, no ratio (S1, E6), so NA
#   c on b: +1 (S1, E7) and -1 (S2, E8) disagree in sign, so not merged
#   b on a: no arc
NET = records_to_network([
    _arc("a", "b", 1.0, "S1", ["E1"]), _arc("a", "b", 3.0, "S2", ["E2", "E3"]),
    _arc("c", "a", -0.5, "S1", ["E4"]),
    {**_arc("b", "c", 0.1, "S3", ["E5"]), "status": "absent", "effect": "neutral"},
    {**_arc("a", "c", None, "S1", ["E6"]), "outcome": "obligate", "effect": "facilitation"},
    _arc("c", "b", 1.0, "S1", ["E7"]), _arc("c", "b", -1.0, "S2", ["E8"]),
])


def _cells(root):
    """The groups that are cells: each holds its square, its `<title>` and its hover panel."""
    return [g for g in root.iter(f"{SVG}g") if g.get("class") == "cell"]


def test_each_cell_is_the_kind_and_value_the_csv_holds():
    names, grid = matrix_image.adjacency_cells(NET)
    assert names == ["A", "B", "C"]
    a, b, c = 0, 1, 2
    kinds = {(i, j): (cell["kind"], cell["value"]) for (i, j), cell in grid.items()}
    assert kinds[(b, a)] == ("value", 2.0)          # row B, column A: a on b, the median of +1 and +3
    assert kinds[(a, c)] == ("value", -0.5)         # c on a
    assert kinds[(c, b)] == ("zero", 0.0)           # b on c, judged absent
    assert kinds[(c, a)] == ("na", None)            # a on c, obligate: no ratio
    assert kinds[(b, c)] == ("conflict", 0.0)       # c on b, the signs disagree
    assert kinds[(a, b)] == ("empty", None)         # b on a, no arc
    assert {kinds[(k, k)][0] for k in (a, b, c)} == {"diagonal"}
    # and the image agrees with the file: every value cell holds what the CSV writes there
    _, rows, _ = matrix.rows(NET)
    assert rows[b][a] == 2.0 and rows[a][c] == -0.5


def test_the_hover_names_every_study_and_experiment_behind_a_cell():
    _, grid = matrix_image.adjacency_cells(NET)
    merged = grid[(1, 0)]["hover"]
    assert merged.splitlines() == [
        "Effect of A on B",
        "log2 strength +2 (the median of 2 arcs)",
        "Studies: S1 (Study one); S2 (Study two)",
        "Experiments: E1, E2, E3",
    ]
    assert "S3" in grid[(2, 1)]["hover"] and "E5" in grid[(2, 1)]["hover"]         # the absent pair
    assert "E6" in grid[(2, 0)]["hover"] and grid[(2, 0)]["hover"].count("NA") == 1
    assert "disagree in sign" in grid[(1, 2)]["hover"] and "E7, E8" in grid[(1, 2)]["hover"]
    assert grid[(0, 1)]["hover"] == "Effect of B on A\nNo arc in this search"


def test_the_colors_carry_the_sign_and_the_legend_says_which_is_which():
    image = matrix_image.adjacency_svg(NET)
    root = ET.fromstring(image)
    cells = {g.find(f"{SVG}title").text.splitlines()[0]: g.find(f"{SVG}rect").get("fill")
             for g in _cells(root)}
    # +2 is the end of the scale, so the full signal color
    assert cells["Effect of A on B"] == brand.GROWTH == "#1A7F5A"
    # -0.5 is a quarter of the scale: a share of 0.2 + 0.8 x 0.25 = 0.4 of #C2410C mixed into #F3F4F1,
    # (243 + (194 - 243) x 0.4, 244 + (65 - 244) x 0.4, 241 + (12 - 241) x 0.4) = (223, 172, 149)
    assert cells["Effect of C on A"] == "#DFAC95"
    assert cells["Effect of B on C"] == matrix_image.NEUTRAL                 # absent: 0
    assert cells["Effect of A on C"].startswith("url(#adj-na)")
    assert cells["Effect of C on B"].startswith("url(#adj-conflict)")
    assert cells["Effect of B on A"] == matrix_image.EMPTY
    text = " ".join("".join(t.itertext()) for t in root.iter(f"{SVG}text"))
    # the legend: the scale's two ends with their sign, and each kind of cell that occurs
    assert "-2 negative" in text and "positive +2" in text
    for kind in ("zero", "na", "conflict", "empty", "diagonal"):
        assert matrix_image.KINDS[kind] in text, kind
    # one hover per cell, nine cells
    assert len(list(_cells(root))) == 9


def _tips(root):
    return {g.get("id"): g for g in root.iter(f"{SVG}g") if g.get("class") == "tip"}


def test_the_hover_shows_in_the_image_itself_without_a_script():
    """Karoline, 2026-11-14: "the hover does not work". A `<title>` is shown only by browsers that draw its
    native tooltip, which the app's browser pane does not. So each cell has a box of its own beside it, drawn
    above every cell and hidden until that cell is hovered by a rule inside the SVG: no script, the same on
    the page and in the downloaded file. Beside the cell, it is in view wherever the cell is (a panel under
    the legend was off screen for a third of the All network's cells)."""
    image = matrix_image.adjacency_svg(NET)
    root = ET.fromstring(image)
    assert "<script" not in image
    style = root.find(f"{SVG}style").text
    assert ".tip{visibility:hidden}" in style
    cells, tips = _cells(root), _tips(root)
    width, height = float(root.get("width")), float(root.get("height"))
    children = list(root)
    for g in cells:
        i, j = g.get("id").split("-c")[1].split("-")
        tip = tips[f"adj-t{i}-{j}"]
        # the rule that shows this cell's box: the cell hovered or focused, or the box itself hovered
        assert (f"svg:has(#adj-c{i}-{j}:hover,#adj-c{i}-{j}:focus,#adj-t{i}-{j}:hover) "
                f"#adj-t{i}-{j}{{visibility:visible}}") in style
        assert g.get("tabindex") == "0"
        # the box holds the title's words, every line fits the box at the widest hover character width, and
        # the box lies inside the image
        shown = ["".join(x.itertext()) for x in tip.iter(f"{SVG}text")]
        assert " ".join(shown).split() == g.find(f"{SVG}title").text.split()
        box = tip.find(f"{SVG}rect")
        bx, by, bw, bh = (float(box.get(k)) for k in ("x", "y", "width", "height"))
        assert all(len(line) * matrix_image.TIP_CHAR <= bw - 20 for line in shown), shown
        assert 0 <= bx and bx + bw <= width and 0 <= by and by + bh <= height
        # drawn after every cell, so no cell covers it
        assert children.index(tip) > max(children.index(c) for c in cells)
        # and never over its own cell, where it would take the pointer from the cell and flicker
        cell = g.find(f"{SVG}rect")
        cx, cy, cw = (float(cell.get(k)) for k in ("x", "y", "width"))
        assert bx >= cx + cw or bx + bw <= cx or by >= cy + cw or by + bh <= cy, (g.get("id"), bx, by)
    assert root.get("role") == "group"           # an img's children are presentational, so its titles hidden


def test_no_box_covers_its_own_cell_in_a_wide_matrix():
    """In a 14-organism matrix the middle columns have room for the box on neither side; it was clamped over
    its own cell. Every box now lies clear of its cell, in a matrix wide enough to force the fallback."""
    names = [f"Organism{k:02d} strain CC55_001C" for k in range(14)]
    grid = {(i, j): {"kind": "empty", "value": None, "hover": "x " * 120} for i in range(14) for j in range(14)}
    root = ET.fromstring(matrix_image.svg(names, grid, "t", "s", "v"))
    tips = {g.get("id"): g.find(f"{SVG}rect") for g in root.iter(f"{SVG}g") if g.get("class") == "tip"}
    below = 0
    for g in _cells(root):
        cell, box = g.find(f"{SVG}rect"), tips[g.get("id").replace("-c", "-t")]
        cx, cy, cw = (float(cell.get(k)) for k in ("x", "y", "width"))
        bx, by, bw, bh = (float(box.get(k)) for k in ("x", "y", "width", "height"))
        assert bx >= cx + cw or bx + bw <= cx or by >= cy + cw or by + bh <= cy, g.get("id")
        below += by >= cy + cw or by + bh <= cy
    assert below > 0                  # the fallback ran: some boxes sit above or below their cell


def test_the_legend_gradient_reads_each_cell_color_at_its_own_value():
    """A cell's color is FLOOR + (1 - FLOOR) |v| / scale of its signal color; the gradient used to run
    straight from NEUTRAL, so -0.5 of a scale of 2 sat on the legend at -0.8. Interpolating the legend's own
    stops at the offset of the value, 0.5 + 0.5 v / scale, gives the cell's color back, to rounding."""
    root = ET.fromstring(matrix_image.adjacency_svg(NET))
    stops = [(float(s.get("offset")), s.get("stop-color")) for s in root.iter(f"{SVG}stop")]
    rgb = lambda c: [int(c[k:k + 2], 16) for k in (1, 3, 5)]  # noqa: E731

    def at(offset):
        for (o1, c1), (o2, c2) in zip(stops, stops[1:], strict=False):
            if o1 <= offset <= o2:
                f = 0 if o2 == o1 else (offset - o1) / (o2 - o1)
                return [a + (b - a) * f for a, b in zip(rgb(c1), rgb(c2), strict=True)]
    for value in (-2.0, -0.5, -0.01, 0.01, 0.7, 2.0):
        drawn = rgb(matrix_image.color_of(value, 2.0))
        legend = at(0.5 + 0.5 * value / 2.0)
        assert all(abs(a - b) <= 1.5 for a, b in zip(drawn, legend, strict=True)), (value, drawn, legend)


def test_the_slanted_column_labels_fit_in_the_image():
    """The width counted the grid and not how far right a slanted label reaches: a 14-organism study cut
    two labels at the right edge. The last label's end, len x CHAR x cos 50 right of its column, is inside."""
    names = [f"Organism{k} with a long strain designation CC55_001C" for k in range(14)]
    grid = {(i, j): {"kind": "empty", "value": None, "hover": "x"} for i in range(14) for j in range(14)}
    root = ET.fromstring(matrix_image.svg(names, grid, "t", "s", "v"))
    width = float(root.get("width"))
    labels = [x for x in root.iter(f"{SVG}text") if (x.get("transform") or "").startswith("rotate(-50")]
    assert len(labels) == 14
    last = labels[-1]
    reach = float(last.get("x")) + len(names[-1]) * matrix_image.CHAR * math.cos(math.radians(50))
    assert reach <= width


def test_a_name_with_markup_or_a_control_character_leaves_the_file_readable():
    """A name with `<`, `&`, quotes or a C0 control character: the downloaded file still parses, and the
    page's prose filter leaves the inline image alone (it put markup inside a `<text>`, which closes the SVG
    early in an HTML page, when a citation named the tool)."""
    net = records_to_network([_arc("a", "b", 1.0, "S1", ["E<1>&\"x\""], target_name="B\x0b<b>",
                                   study_citation="measured with grownet & co")])
    image = matrix_image.adjacency_svg(net)
    root = ET.fromstring(image)                     # raises on a control character or bad escaping
    assert any("E<1>&" in (g.find(f"{SVG}title").text or "") for g in _cells(root))
    assert brand.in_prose(f"<p>grownet</p>{image}").endswith(image)


def test_a_value_that_is_not_finite_is_drawn_as_such_not_as_0():
    """A NaN strength crashed the result page (`round` of NaN in the color) and, alone, was drawn as 0."""
    net = records_to_network([_arc("a", "b", float("nan"), "S1", ["E1"]), _arc("c", "b", 1.0, "S1", ["E2"])])
    _, grid = matrix_image.adjacency_cells(net)
    kinds = {cell["kind"] for cell in grid.values()}
    assert "nonfinite" in kinds
    root = ET.fromstring(matrix_image.adjacency_svg(net))
    text = " ".join("".join(x.itertext()) for x in root.iter(f"{SVG}text"))
    assert matrix_image.KINDS["nonfinite"] in text


def test_a_pair_judged_absent_and_left_out_of_the_file_is_drawn_as_0():
    """By default the arcs below the absence threshold are left out of the file and kept on the result as
    `absent`; those pairs were compared, so the image draws them as 0 with their studies, as the file's own
    description of a 0 says, not as white cells never compared."""
    present = records_to_network([_arc("a", "b", 1.0, "S1", ["E1"]), _arc("c", "b", 1.0, "S1", ["E2"])])
    absent = records_to_network([{**_arc("c", "a", 0.1, "S3", ["E5"]), "status": "absent",
                                  "effect": "neutral"}])
    names, grid = matrix_image.adjacency_cells(present, absent)
    a, c = names.index("A"), names.index("C")
    assert grid[(a, c)]["kind"] == "zero" and "E5" in grid[(a, c)]["hover"]
    assert matrix_image.adjacency_cells(present)[1][(a, c)]["kind"] == "empty"


def test_a_value_names_only_the_arcs_in_it_and_the_rest_apart():
    """The median is over the quantified arcs; an obligate arc of the same pair counts in the sign check and
    stays out of the median, so it is named apart, with its own experiments, and a merged arc says it is a
    median of comparisons."""
    net = records_to_network([
        _arc("a", "b", 0.9, "S1", ["E1"], merged_arcs=3),
        {**_arc("a", "b", None, "S2", ["E9"]), "outcome": "obligate", "effect": "facilitation"}])
    _, grid = matrix_image.adjacency_cells(net)
    lines = grid[(1, 0)]["hover"].splitlines()
    assert lines[1] == "log2 strength +0.9 (from 1 merged arc, the median of 3 comparisons)"
    assert lines[3] == "Experiments: E1"
    assert lines[4].startswith("Also 1 arc where one side did not grow") and lines[6] == "Experiments: E9"


def test_an_na_cell_gives_its_measured_bound_or_says_there_is_none():
    with_bound = records_to_network([{**_arc("a", "b", None, "S1", ["E1"]), "outcome": "obligate",
                                      "effect": "facilitation", "strength_bound": 0.663,
                                      "bound_rule": "the no-growth factor"}])
    without = records_to_network([{**_arc("a", "b", None, "S1", ["E1"]), "outcome": "obligate",
                                   "effect": "facilitation"}])
    assert "Measured bound: log2 at least +0.663" in matrix_image.adjacency_cells(with_bound)[1][(1, 0)]["hover"]
    assert "bounds nothing away from zero" in matrix_image.adjacency_cells(without)[1][(1, 0)]["hover"]


def test_an_arc_of_an_organism_on_itself_is_named_on_its_diagonal():
    net = records_to_network([_arc("a", "a", -1.5, "S1", ["E1"]), _arc("a", "b", 1.0, "S1", ["E2"])])
    _, grid = matrix_image.adjacency_cells(net)
    assert "1 arc from A to itself, which have no cell: -1.5" in grid[(0, 0)]["hover"]
    assert "Experiments: E1" in grid[(0, 0)]["hover"]


def test_a_species_name_is_in_italics_and_its_strain_is_not():
    label = matrix_image._label_svg("Bacteroides thetaiotaomicron VPI-5482")
    assert label == '<tspan font-style="italic">Bacteroides thetaiotaomicron</tspan> VPI-5482'
    assert matrix_image._label_svg("Blautia") == '<tspan font-style="italic">Blautia</tspan>'
    assert matrix_image._label_svg("strain 7") == "strain 7"
    sub = matrix_image._label_svg("Lactobacillus delbrueckii subsp. bulgaricus ATCC BAA-365")
    assert sub == ('<tspan font-style="italic">Lactobacillus delbrueckii</tspan> subsp.'
                   '<tspan font-style="italic"> bulgaricus</tspan> ATCC BAA-365')
    assert matrix_image._label_svg("[Clostridium] scindens") == \
        '<tspan font-style="italic">[Clostridium] scindens</tspan>'


def test_a_glv_image_holds_the_coefficients_and_names_their_sources():
    # the package's own pair (tests/test_glv_coefficients.py), with experiments on its arcs:
    #   b on a, L = +1, x_b = 2e8: A_ab = 0.4 x (2^1 - 1) / 2e8 = 2e-9
    #   a on b, L = -1, x_a = 4e8: A_ba = 0.2 x (2^-1 - 1) / 4e8 = -2.5e-10
    #   diagonals -r / K: A_aa = -0.4 / 1e9 = -4e-10, A_bb = -0.2 / 5e8 = -4e-10
    net = _glv_net([_glv_arc("b", "a", 1.0, x_j=2.0e8, experiments=["E1"]),
                    _glv_arc("a", "b", -1.0, x_j=4.0e8, experiments=["E2"], study_id="S2")])
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    names, grid = matrix_image.glv_cells(net, rates, block, got)
    assert names == ["A", "B"]
    assert grid[(0, 1)]["value"] == pytest.approx(2.0e-9)
    assert grid[(1, 0)]["value"] == pytest.approx(-2.5e-10)
    assert grid[(0, 0)]["value"] == pytest.approx(-4.0e-10) == grid[(1, 1)]["value"]
    assert grid[(0, 1)]["hover"].splitlines()[2:] == ["Studies: S1", "Experiments: E1"]
    assert grid[(1, 0)]["hover"].splitlines()[2:] == ["Studies: S2", "Experiments: E2"]
    diagonal = grid[(0, 0)]["hover"]
    assert "Self-limitation of A" in diagonal and "r = 0.4 1/h, K = 1e+09 Cells/mL" in diagonal
    assert "Studies of its growth rate: S1" in diagonal
    ((unit, name, image),) = matrix_image.glv_svgs(net, rates)
    assert unit == "Cells/mL" and name == "glv_matrix.Cells_per_mL.svg"
    assert ET.fromstring(image).find(f"{SVG}title").text == "gLV coefficients in Cells/mL"


def test_the_page_shows_the_image_and_serves_it_as_a_file(server):  # noqa: F811
    base, token = server
    data = urllib.parse.urlencode({"species": "Faecalibacterium prausnitzii\nBlautia hydrogenotrophica",
                                   "metric": "growthRate", "deadband": "0.25", "only_entered": "1",
                                   "derivation": "replicate"}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10) as r:
        page = r.read().decode("utf-8")
    assert "Matrix image" in page and "Download the adjacency matrix (.svg)" in page
    # the image itself, inside its box: "<svg" alone also matches the page's logo, and the hint paragraph
    # holds "Hover a cell", so those two assertions passed with no image on the page
    found = re.search(r'<div class="matrix-image"[^>]*>(<svg.*?</svg>)', page, re.S)
    assert found, "no image inside the matrix-image box"
    inline = ET.fromstring(found.group(1))
    assert inline.find(f"{SVG}title").text == "Adjacency matrix" and _cells(inline)
    with urllib.request.urlopen(f"{base}/matrix.svg?token={token}&which=0", timeout=10) as r:
        assert r.headers["Content-Type"].startswith("image/svg+xml")
        assert "attachment" in r.headers["Content-Disposition"] and ".svg" in r.headers["Content-Disposition"]
        root = ET.fromstring(r.read().decode("utf-8"))
    assert root.find(f"{SVG}title").text == "Adjacency matrix"
    assert any(g.find(f"{SVG}title").text.startswith("Effect of") for g in _cells(root))
    for which in ("9", "-1", "x"):          # out of range, negative (served the last image) and not a number
        with pytest.raises(urllib.error.HTTPError):
            _get(f"{base}/matrix.svg?token={token}&which={which}")



def _glv(arcs, derivation=None, **rate_extra):
    net = _glv_net(arcs)
    if derivation:
        net.meta.setdefault("settings", {})["derivation"] = derivation
    rates = {"a": _rate("A", 0.4, 1.0e9, **rate_extra), "b": _rate("B", 0.2, 5.0e8, **rate_extra)}
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    return matrix_image.glv_cells(net, rates, block, got)


def test_a_glv_diagonal_says_how_it_was_fitted_under_each_derivation():
    """The image is drawn in gLV mode, which runs the integrated or the steady-state derivation, and every
    diagonal said "-r / K from its monoculture", the replicate form's wording. Under the integrated form the
    diagonal is fitted and K follows from it, the opposite direction; under the steady-state form the rate is
    r - D. Each now says what `matrix.DIAGONAL_CAVEAT` says for its derivation."""
    pair = [_glv_arc("b", "a", 1.0, x_j=2.0e8), _glv_arc("a", "b", -1.0, x_j=4.0e8)]
    replicate = _glv(pair)[1][(0, 0)]["hover"]
    integrated = _glv(pair, "integrated", capacity_source="fitted from the monoculture time courses")[1][(0, 0)]
    steady = _glv(pair, "steady")[1][(0, 0)]["hover"]
    assert "-r / K from its monoculture: r = 0.4 1/h, K = 1e+09 Cells/mL" in replicate
    assert "Fitted directly" in integrated["hover"] and "-r / K from its monoculture" not in integrated["hover"]
    assert "Carrying capacity: fitted from the monoculture time courses" in integrated["hover"]
    assert "(r - D) B_ii" in steady and "r - D = 0.4 1/h" in steady
    assert "-r / K from its monoculture" not in steady


def test_a_glv_pair_whose_arcs_disagree_in_sign_is_not_drawn_as_no_arc():
    """Two arcs of b on a, +1 and -1: the package names the pair in its conflicts and leaves 0; the image
    drew it white with "No coefficient: no arc fitted" and the legend "no arc in this search"."""
    names, grid = _glv([_glv_arc("b", "a", 1.0, experiments=["E1"]),
                        _glv_arc("b", "a", -1.0, experiments=["E2"], study_id="S2"),
                        _glv_arc("a", "b", -1.0, x_j=4.0e8)])
    cell = grid[(0, 1)]
    assert cell["kind"] == "conflict" and "disagree in sign" in cell["hover"] and "E1, E2" in cell["hover"]


def test_a_glv_pair_with_arcs_and_no_coefficient_says_why_and_is_not_no_arc():
    """An arc with no partner abundance gives no coefficient: the cell says the package's reason, names the
    arc, and the legend says arcs exist, not "no arc in this search"."""
    names, grid = _glv([_glv_arc("b", "a", 1.0, x_j=None, experiments=["E1"]),
                        _glv_arc("a", "b", -1.0, x_j=4.0e8)])
    cell = grid[(0, 1)]
    assert cell["kind"] == "unfitted" and "No coefficient: no abundance" in cell["hover"]
    assert "E1" in cell["hover"]


def test_a_long_hover_wraps_inside_its_box():
    """Experiment ids run wider per character than prose, and a line wrapped for 6.6 px per character ran
    past the box's edge. Thirty real-format ids wrap so that every line fits at TIP_CHAR per character."""
    ids = [f"EMGDB{k:09d}" for k in range(30)]
    net = records_to_network([_arc("a", "b", 1.0, "S1", ids)])
    root = ET.fromstring(matrix_image.adjacency_svg(net))
    tip = _tips(root)["adj-t1-0"]
    width = float(tip.find(f"{SVG}rect").get("width"))
    lines = ["".join(x.itertext()) for x in tip.iter(f"{SVG}text")]
    assert len(lines) > 3
    assert all(len(line) * matrix_image.TIP_CHAR <= width - 20 for line in lines)


def test_glv_mode_puts_each_coefficient_matrix_on_the_page_after_the_adjacency_matrix():
    """The page's list of images: the adjacency matrix, and in gLV mode one image per matrix of the package,
    in the order `/matrix.svg?which=` serves them. Out of gLV mode, or where no coefficient can be fitted,
    the adjacency matrix alone."""
    from grownet import gui
    net = _glv_net([_glv_arc("b", "a", 1.0, x_j=2.0e8), _glv_arc("a", "b", -1.0, x_j=4.0e8)])
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8)}
    on = gui.glv_mode(dict(gui.DEFAULTS))
    images = gui.matrix_images({"network": net, "rates": rates, "settings": on})
    assert [heading for heading, _, _ in images] == ["Adjacency matrix", "gLV coefficients in Cells/mL"]
    assert images[1][1].endswith("glv_matrix.Cells_per_mL.svg")
    assert ET.fromstring(images[1][2]).find(f"{SVG}title").text == "gLV coefficients in Cells/mL"
    off = gui.matrix_images({"network": net, "rates": rates, "settings": dict(gui.DEFAULTS)})
    assert [heading for heading, _, _ in off] == ["Adjacency matrix"]


def test_each_legend_swatch_is_the_fill_of_the_cells_it_names():
    """Each legend line's swatch has the fill of the cells of that kind, read off the drawn cells by their
    kind in the grid, so a swatch in the wrong pattern or color fails (white alone would match "no arc")."""
    _, grid = matrix_image.adjacency_cells(NET)
    root = ET.fromstring(matrix_image.adjacency_svg(NET))
    by_kind = {}
    for g in _cells(root):
        i, j = (int(k) for k in g.get("id").split("-c")[1].split("-"))
        by_kind.setdefault(grid[(i, j)]["kind"], set()).add(g.find(f"{SVG}rect").get("fill"))
    children = list(root)
    checked = 0
    for kind, sentence in matrix_image.KINDS.items():
        label = [x for x in children if x.tag == f"{SVG}text" and x.text == sentence]
        if kind not in by_kind:
            assert not label, kind                  # the legend lists only kinds that occur
            continue
        before = children[:children.index(label[0])]
        swatch = next(x for x in reversed(before) if x.tag == f"{SVG}rect")
        assert by_kind[kind] == {swatch.get("fill")}, (kind, swatch.get("fill"))
        checked += 1
    assert checked == 5                             # zero, na, conflict, empty, diagonal in NET
    stops = [s.get("stop-color") for s in root.iter(f"{SVG}stop")]
    assert stops[0] == brand.INHIBITION and stops[-1] == brand.GROWTH and matrix_image.NEUTRAL in stops


def test_the_drawn_labels_set_species_in_italics():
    net = records_to_network([{**_arc("a", "b", 1.0, "S1", ["E1"]), "source_name": "Bacteroides fragilis NCTC 9343",
                               "target_name": "Escherichia coli LF82"}])
    root = ET.fromstring(matrix_image.adjacency_svg(net))
    italic = ["".join(s.itertext()) for s in root.iter(f"{SVG}tspan") if s.get("font-style") == "italic"]
    # each name twice, as a row label and as a column label
    assert italic.count("Bacteroides fragilis") == 2 and italic.count("Escherichia coli") == 2


def test_arcs_judged_absent_beside_a_value_are_named_with_their_sources():
    net = records_to_network([_arc("a", "b", 1.0, "S1", ["E1"]),
                              {**_arc("a", "b", 0.1, "S3", ["E5"]), "status": "absent", "effect": "neutral"}])
    lines = matrix_image.adjacency_cells(net)[1][(1, 0)]["hover"].splitlines()
    assert lines[1] == "log2 strength +1 (from 1 arc)" and lines[3] == "Experiments: E1"
    assert lines[4] == "Also 1 arc judged absent, not in the value"
    assert lines[5] == "Studies: S3" and lines[6] == "Experiments: E5"


def test_cells_carry_marks_besides_color():
    """A judged-absent cell and a cell with no arc were 1.1:1 apart in contrast, and the sign was carried by
    hue alone, the two signal colors being of equal lightness. So a judged-absent cell holds 0, a negative
    value a minus sign, and a value that is not finite a question mark; a positive value, no arc and the
    others hold none."""
    net = records_to_network([_arc("a", "b", 1.0, "S1", ["E1"]), _arc("c", "a", -0.5, "S1", ["E4"]),
                              {**_arc("b", "c", 0.1, "S3", ["E5"]), "status": "absent", "effect": "neutral"},
                              _arc("c", "b", float("nan"), "S1", ["E9"])])
    _, grid = matrix_image.adjacency_cells(net)
    root = ET.fromstring(matrix_image.adjacency_svg(net))
    marks = {}
    for g in _cells(root):
        i, j = (int(k) for k in g.get("id").split("-c")[1].split("-"))
        glyph = [x.text for x in g.iter(f"{SVG}text") if x.get("class") == "mark"]
        marks[(i, j)] = glyph[0] if glyph else ""
    assert marks[(1, 0)] == "" and grid[(1, 0)]["value"] == 1.0        # positive: color only
    assert marks[(0, 2)] == "-"                                       # c on a, negative
    assert marks[(2, 1)] == "0" and grid[(2, 1)]["kind"] == "zero"    # b on c, judged absent
    assert marks[(1, 2)] == "?" and grid[(1, 2)]["kind"] == "nonfinite"
    assert marks[(0, 1)] == "" and grid[(0, 1)]["kind"] == "empty"


def test_each_box_opens_toward_the_middle_and_touches_its_cell():
    """Right of a cell in the left half and left of one in the right half, flush with the cell so the
    pointer can move onto the box; level with the cell's top in the upper half and its bottom in the lower."""
    n = 60                                       # wide enough that many cells have room on both sides
    names = [f"Organism{k:02d}" for k in range(n)]
    grid = {(i, j): {"kind": "empty", "value": None, "hover": "a\nb\nc\nd"} for i in range(n) for j in range(n)}
    root = ET.fromstring(matrix_image.svg(names, grid, "t", "s", "v"))
    width = float(root.get("width"))
    tips = {g.get("id"): g.find(f"{SVG}rect") for g in root.iter(f"{SVG}g") if g.get("class") == "tip"}
    opened = set()
    for g in _cells(root):
        i, j = (int(k) for k in g.get("id").split("-c")[1].split("-"))
        cell, box = g.find(f"{SVG}rect"), tips[f"m-t{i}-{j}"]
        x, y = float(cell.get("x")) - matrix_image.GAP / 2, float(cell.get("y")) - matrix_image.GAP / 2
        size = float(cell.get("width")) + matrix_image.GAP
        bx, by, bw, bh = (float(box.get(k)) for k in ("x", "y", "width", "height"))
        sideways = True
        room_right, room_left = x + size + bw <= width - 4, x - bw >= 4
        if bx + bw <= x + 0.05:                  # opened to the left
            assert (j >= n / 2 or not room_right) and room_left, (i, j)
            assert abs(bx + bw - x) < 0.1
        elif bx >= x + size - 0.05:              # opened to the right
            assert (j < n / 2 or not room_left) and room_right, (i, j)
            assert abs(bx - (x + size)) < 0.1
        else:                                    # no room on either side: below the row or above it
            sideways = False
            assert abs(by - (y + size)) < 0.1 or abs(by + bh - y) < 0.1, (i, j)
        opened.add("left" if sideways and bx < x else "right" if sideways else "below or above")
        height = float(root.get("height"))
        clamped = by <= 4.1 or by + bh >= height - 4.1
        if sideways and not clamped and i < n / 2:
            assert abs(by - y) < 0.1, (i, j)                 # level with the cell's top
        elif sideways and not clamped:
            assert abs(by + bh - (y + size)) < 0.1, (i, j)   # level with the cell's bottom
    # both sides occur, so each branch above was exercised (below or above is the narrow matrix's case,
    # `test_no_box_covers_its_own_cell_in_a_wide_matrix`)
    assert opened == {"left", "right"}, opened


def test_a_glv_pair_judged_absent_is_0_as_in_the_adjacency_image():
    """A pair whose only arc was judged absent and left out of the file: the adjacency image drew it as 0,
    the gLV image as "No arc in this search", while the package README says such a pair is 0."""
    net = _glv_net([_glv_arc("b", "a", 1.0, x_j=2.0e8), _glv_arc("a", "b", -1.0, x_j=4.0e8),
                    _glv_arc("c", "a", 0.5, x_j=2.0e8)])
    absent = _glv_net([{**_glv_arc("a", "c", 0.05, x_j=2.0e8, experiments=["E7"]), "status": "absent"}])
    rates = {"a": _rate("A", 0.4, 1.0e9), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.3, 5.0e8)}
    got = matrix.coefficients(net, rates)
    (block,) = got["matrices"]
    names, grid = matrix_image.glv_cells(net, rates, block, got, absent)
    cell = grid[(names.index("C"), names.index("A"))]
    assert cell["kind"] == "zero" and "judged no interaction" in cell["hover"] and "E7" in cell["hover"]
    assert matrix_image.glv_cells(net, rates, block, got)[1][(names.index("C"), names.index("A"))]["kind"] == "empty"


def test_the_command_line_writes_the_same_image_as_the_page(tmp_path, capsys):
    """The README says the command line does everything the page does; the Matrix image was the page's
    alone. `--matrix-image FILE` writes the adjacency matrix as the page draws it, hovers included."""
    import json

    from grownet.__main__ import main
    records = [_arc("a", "b", 1.0, "S1", ["E1"]), _arc("c", "a", -0.5, "S1", ["E4"])]
    fixture, image, net_file = tmp_path / "records.json", tmp_path / "m.svg", tmp_path / "net.json"
    fixture.write_text(json.dumps(records), encoding="utf-8")
    assert main(["derive", "S1", "--fixture", str(fixture), "--out", str(net_file),
                 "--matrix-image", str(image)]) == 0
    assert "as an image to" in capsys.readouterr().err
    root = ET.fromstring(image.read_text(encoding="utf-8"))
    assert root.find(f"{SVG}title").text == "Adjacency matrix"
    hovers = [g.find(f"{SVG}title").text for g in _cells(root)]
    assert any("Experiments: E1" in h for h in hovers) and any("Experiments: E4" in h for h in hovers)
    # the same picture the page would draw for that network
    from grownet.model import InteractionNetwork
    written = InteractionNetwork.from_dict(json.loads(net_file.read_text(encoding="utf-8")))
    assert image.read_text(encoding="utf-8") == matrix_image.adjacency_svg(written)
