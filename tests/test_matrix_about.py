"""The adjacency matrix CSV travels with a description of itself (#212)."""
import os

from grownet import matrix
from grownet.__main__ import main
from grownet.mgrowthdb import records_to_network


def _arc(source, target, strength, outcome="quantified", **extra):
    return {"source": source, "target": target, "source_name": source.upper(), "target_name": target.upper(),
            "effect": "facilitation" if (strength or 0) >= 0 else "inhibition", "strength": strength,
            "status": "present", "outcome": outcome, "study_id": "S1", "metric": "auc", "medium": "WC",
            **extra}


def _net(arcs, **settings):
    return records_to_network(arcs, meta={"tool_version": "9.9.9", "derived_at": "2026-10-12T09:00:00+00:00",
                                          "source_db": "mGrowthDB (live)", "absence": {"k": 1.0},
                                          "settings": {"derivation": "replicate", "metric": "auc", **settings}})


def test_the_description_says_what_the_grid_cannot():
    """Provenance, orientation, the meaning of 0 and NA, the settings, the sources."""
    about = matrix.matrix_about(_net([_arc("a", "b", 1.5)]), "x.csv")
    for said in ("9.9.9", "2026-10-12T09:00:00+00:00", "describes x.csv, 2 x 2", "Rows are the affected organism",
                 "Derivation: replicate", "Metric: auc", "(k = 1.0)", "0 is no arc", "NA is a comparison",
                 'metric: "auc"', "SOURCES", "S1"):
        assert said in about, f"{said!r} missing"


def test_two_settings_give_the_same_looking_grid_and_different_descriptions():
    """#212: `--metric max` changes every number and the CSV looks the same. The description does not."""
    auc = matrix.matrix_about(_net([_arc("a", "b", 1.5)], metric="auc"))
    peak = matrix.matrix_about(_net([_arc("a", "b", 1.5)], metric="max"))
    assert 'metric: "auc"' in auc and 'metric: "max"' in peak


def test_the_pairs_the_grid_leaves_at_zero_for_disagreeing_are_named():
    """`matrix_csv` dropped the conflicts `rows()` returns, so such a pair printed as 0 with nothing naming it."""
    net = _net([_arc("a", "b", 1.5), _arc("a", "b", -1.2, study_id="S2")])
    assert "0" in matrix.matrix_csv(net).splitlines()[1]
    about = matrix.matrix_about(net)
    assert "DISAGREE IN SIGN" in about and "A on B (within one design: every arc unknown)" in about


def test_a_conflict_across_designs_is_told_apart_from_one_within_a_design():
    """Craig's agent, reading #278 and #280 together: of the All network's three sign conflicts one is
    biculture against drop-out, the result #278 names, and two are scatter among biculture arcs."""
    across = _net([_arc("a", "b", 1.5, evidence="biculture"), _arc("a", "b", -1.2, evidence="dropout",
                                                                    study_id="S2")])
    within = _net([_arc("a", "b", 1.5, evidence="biculture"), _arc("a", "b", -1.2, evidence="biculture",
                                                                    study_id="S2")])
    assert "A on B (across designs: biculture and dropout)" in matrix.matrix_about(across)
    assert "A on B (within one design: every arc biculture)" in matrix.matrix_about(within)


def test_an_na_cell_is_listed_with_its_bound():
    net = _net([_arc("a", "b", None, outcome="obligate", strength_bound=2.5)])
    assert "NA" in matrix.matrix_csv(net)
    about = matrix.matrix_about(net)
    assert "NA CELLS" in about and "A on B: at least +2.5" in about


def test_the_command_line_writes_it_beside_the_csv(tmp_path):
    out = tmp_path / "net.csv"
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "example_interactions.json")
    assert main(["derive", "SYNTHETIC-EXAMPLE", "--fixture", fixture, "--format", "matrix",
                 "--out", str(out)]) == 0
    about = (tmp_path / "net.about.txt").read_text(encoding="utf-8")
    assert "describes net.csv" in about and "SETTINGS: none recorded" in about
    assert matrix.about_name("a/b/grownet_matrix.csv") == "a/b/grownet_matrix.about.txt"
    assert matrix.about_name("matrix") == "matrix.about.txt"
