"""The interaction matrix as an image (#341), on hand-built networks.

Karoline, 2026-11-14: "provide the interaction matrix as an image, with a hover function that says from
which studies/experiments each entry is derived. the image can be downloaded. the image would need a legend
to know the colors of negative and positive entries". Her choices: both matrices (the adjacency matrix, and
in gLV mode each matrix of coefficients), on the local page's result, as SVG only.

Every expected number is computed by hand in the test that uses it.
"""
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
             for g in root.iter(f"{SVG}g")}
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
    assert len(list(root.iter(f"{SVG}g"))) == 9


def test_a_species_name_is_in_italics_and_its_strain_is_not():
    label = matrix_image._label_svg("Bacteroides thetaiotaomicron VPI-5482")
    assert label == '<tspan font-style="italic">Bacteroides thetaiotaomicron</tspan> VPI-5482'
    assert matrix_image._label_svg("Blautia") == '<tspan font-style="italic">Blautia</tspan>'
    assert matrix_image._label_svg("strain 7") == "strain 7"


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
    assert "Matrix image" in page and "<svg" in page and "Download the image (.svg)" in page
    assert "Hover a cell" in page
    with urllib.request.urlopen(f"{base}/matrix.svg?token={token}&which=0", timeout=10) as r:
        assert r.headers["Content-Type"].startswith("image/svg+xml")
        assert "attachment" in r.headers["Content-Disposition"] and ".svg" in r.headers["Content-Disposition"]
        root = ET.fromstring(r.read().decode("utf-8"))
    assert root.find(f"{SVG}title").text == "Adjacency matrix"
    assert any(g.find(f"{SVG}title").text.startswith("Effect of") for g in root.iter(f"{SVG}g"))
    with pytest.raises(urllib.error.HTTPError):
        _get(f"{base}/matrix.svg?token={token}&which=9")

