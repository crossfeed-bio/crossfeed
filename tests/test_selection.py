"""The second box: media, experiments or studies (#113).

Karoline, 2026-10-04: "a second, optional, input field next to the first one with the taxa. Users can
either specify names of media or a list of experiment identifiers there (so this last item can then be
removed from the advanced options). The media will have to be string-matched against the experiment
description; they are not systematically provided by mGrowthDB."

Every experiment in mGrowthDB does carry a structured medium name today, so a medium is matched against
that first and against the description and the experiment name as well, since what tells experiments of
one study apart lives only there (study 2: BT_WC and BT_MUCIN on one medium).
"""
import pytest

from grownet import selection
from grownet.derive import select_experiments

A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"


def _exp(eid, name, members, medium="Wilkins-Chalgren Anaerobe Broth (WC)", description="", study="SMGDB00000002"):
    return {"id": eid, "name": name, "studyId": study, "cultivationMode": "batch",
            "description": description,
            "communityStrains": [{"name": m} for m in members],
            "compartments": [{"name": "C1", "mediumName": medium, "mediumUrl": "https://example/medium"}]}


def test_an_entry_is_an_id_by_its_shape_and_a_medium_otherwise():
    parsed = selection.parse(["EMGDB000000031", "smgdb00000004", "Wilkins-Chalgren", "mucin beads"])
    assert parsed["experiments"] == ["EMGDB000000031"]
    assert parsed["studies"] == ["SMGDB00000004"]        # kept as mGrowthDB writes it, whatever was typed
    assert parsed["media"] == ["Wilkins-Chalgren", "mucin beads"]
    # one per line, and at commas and semicolons, as in the first box
    assert selection.parse("mucin, wilkins\nEMGDB000000031")["media"] == ["mucin", "wilkins"]
    assert selection.empty(selection.parse([])) and not selection.empty(parsed)


def test_a_medium_matches_its_name_case_insensitively_and_as_a_substring():
    """Wilkins-Chalgren is spelled four ways in mGrowthDB, one of them misspelled (Anerobe), so typing
    part of it has to find all of them."""
    wanted = selection.parse(["wilkins"])
    for medium in ("Wilkins-Chalgren", "Wilkins-Chalgren Anaerobe Broth",
                   "Wilkins-Chalgren Anaerobe Broth (WC)", "Wilkins-Chalgren Anerobe Broth (WC)"):
        assert selection.matches(_exp("E1", "x", [A], medium=medium), wanted)
    assert not selection.matches(_exp("E1", "x", [A], medium="mMCB"), wanted)


def test_a_medium_also_matches_the_description_and_the_name():
    # study 2 runs BT_WC and BT_MUCIN on one medium, so what tells them apart is only there
    plain = _exp("E1", "BT_WC", [A], description="BT with WC for 120h")
    beads = _exp("E2", "BT_MUCIN", [A], description="BT with WC plus mucin beads for 120 h")
    mucin = selection.parse(["mucin"])
    assert selection.matches(beads, mucin) and not selection.matches(plain, mucin)
    assert selection.matches(plain, selection.parse(["BT_WC"]))      # the experiment name counts too


def test_an_experiment_or_a_study_is_picked_by_its_id():
    exp = _exp("EMGDB000000031", "co", [A, B], study="SMGDB00000004")
    assert selection.matched_by(exp, selection.parse(["EMGDB000000031"])) == "EMGDB000000031"
    assert selection.matched_by(exp, selection.parse(["smgdb00000004"])) == "SMGDB00000004"
    assert selection.matched_by(exp, selection.parse(["EMGDB000000099"])) == ""


def test_naming_a_co_culture_keeps_the_monocultures_it_is_compared_against():
    """Karoline, 2026-10-04, choosing this over a literal reading: one id alone would otherwise give no
    arc, since a comparison needs the monocultures too."""
    co = _exp("EMGDB000000031", "co", [A, B])
    mono_a, mono_b = _exp("EMGDB000000025", "A alone", [A]), _exp("EMGDB000000027", "B alone", [B])
    other = _exp("EMGDB000000040", "C alone", ["Other species"], medium="mMCB")
    skipped = []
    kept = select_experiments([co, mono_a, mono_b, other], selection.parse(["EMGDB000000031"]), skipped)
    assert [e["id"] for e in kept] == ["EMGDB000000031", "EMGDB000000025", "EMGDB000000027"]
    assert other not in kept                      # another medium, so another comparison
    # and the report says what came along, rather than quietly widening what was asked for
    assert any("monocultures kept alongside" in label for label, _ in skipped)
    assert any("EMGDB000000025, EMGDB000000027" in reason for _, reason in skipped)


def test_a_medium_selection_keeps_every_experiment_of_that_medium():
    wc = [_exp("E1", "co", [A, B]), _exp("E2", "A alone", [A]), _exp("E3", "B alone", [B])]
    mmcb = _exp("E4", "other", [A], medium="mMCB")
    kept = select_experiments([*wc, mmcb], selection.parse(["wilkins"]), [])
    assert [e["id"] for e in kept] == ["E1", "E2", "E3"]


def test_an_empty_box_looks_at_everything():
    exps = [_exp("E1", "co", [A, B]), _exp("E2", "other", [A], medium="mMCB")]
    assert select_experiments(exps, selection.parse([]), []) == exps
    assert select_experiments(exps, None, []) == exps


def test_a_selection_that_matches_nothing_says_so():
    skipped = []
    assert select_experiments([_exp("E1", "co", [A, B])], selection.parse(["nothing like this"]), skipped) == []
    assert any("no experiment of this study matches" in reason for _, reason in skipped)


def test_the_medium_of_an_experiment_is_what_mgrowthdb_records():
    exp = _exp("E1", "co", [A, B], medium="mMCB")
    assert selection.medium_of(exp) == "mMCB"
    assert selection.medium_url(exp) == "https://example/medium"
    # several compartments: both media, each once
    exp["compartments"].append({"name": "C2", "mediumName": "Mucin"})
    assert selection.medium_of(exp) == "mMCB; Mucin"
    assert selection.medium_of({"compartments": [{"name": "C1"}]}) == ""


@pytest.mark.parametrize("entry", ["EMGDB000000031", "emgdb000000031", "SMGDB00000004"])
def test_ids_are_never_read_as_media(entry):
    parsed = selection.parse([entry])
    assert parsed["media"] == []


def test_an_arc_records_the_medium_it_came_from():
    """Karoline, 2026-10-04, choosing to add the field: so a filtered network says what it was filtered
    to, and the result table, the downloads and Cytoscape can show it."""
    from grownet.mgrowthdb import records_to_network
    record = {"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0, "study_id": "S1",
              "medium": "Wilkins-Chalgren Anaerobe Broth (WC)"}
    net = records_to_network([record])
    assert net.edges[0].medium == "Wilkins-Chalgren Anaerobe Broth (WC)"
    assert net.validate() == []
    assert net.to_dict()["edges"][0]["medium"] == "Wilkins-Chalgren Anaerobe Broth (WC)"
    # and it travels in GraphML, which is what Cytoscape and Gephi read
    from grownet.export import to_graphml
    assert 'attr.name="medium"' in to_graphml(net)
