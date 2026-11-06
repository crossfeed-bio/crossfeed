"""The help page cannot fall behind the code, and a network says what made it and when (#78)."""
import argparse
import dataclasses
import datetime
import json
import re
from xml.etree import ElementTree as ET

import pytest
from test_gui import FakeClient, _query, visible

from grownet import __version__, gui, help, interaction, model
from grownet.__main__ import build_parser, main
from grownet.export import to_graphml
from grownet.mgrowthdb import provenance, records_to_network

PAGE = gui.render_help("tok")


@pytest.fixture(autouse=True)
def _no_growth_rule_off(monkeypatch):
    """The fake study's monocultures barely rise, so the no-growth rule (#37) would make every edge obligate.
    These tests are about the page, not the rule, which tests/test_interaction.py covers."""
    monkeypatch.setattr(interaction, "NO_GROWTH_ALPHA", 0.0)
    monkeypatch.setattr(interaction, "NO_GROWTH_FACTOR", 0.0)


def _derive_options() -> set:
    sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return {opt for action in sub.choices["derive"]._actions for opt in action.option_strings} - {"-h", "--help"}


def test_every_advanced_setting_is_explained():
    # a setting added to the page without a line on the help page fails here, and a stale line too
    assert set(help.SETTINGS) == set(gui.DEFAULTS)
    for label, _flag, _text in help.SETTINGS.values():
        assert gui.html.escape(label) in PAGE


def test_every_command_line_option_is_explained():
    # sets, not a substring search: an undocumented --all would hide inside --all-partners (Craig's agent, #79)
    documented = {flag.split()[0] for _, flag, _ in help.SETTINGS.values()} | set(help.CLI_ONLY)
    assert set(_derive_options()) - documented == set()


def test_every_edge_and_node_field_is_explained():
    assert list(help.EDGE_ATTRIBUTES) and set(help.EDGE_ATTRIBUTES) == {f.name for f in dataclasses.fields(model.Edge)}
    assert set(help.NODE_ATTRIBUTES) == {f.name for f in dataclasses.fields(model.Node)}
    for name in [*help.EDGE_ATTRIBUTES, *help.NODE_ATTRIBUTES]:
        assert f"<code>{name}</code>" in PAGE.replace("<wbr>", "")


# ---- what a merged arc carries (#302) ----------------------------------------------------------------
#
# Karoline, 2026-11-06, after asking "how is grownet currently merging arc attributes when arcs are merged
# across studies?": "please document this in the help in the context of the arc attributes".

# the fields a merged arc takes from its first arc: the four every merged arc shares, and the two only
# Merge to genus sets. Anything else the first arc would pass through unexamined.
FROM_THE_FIRST_ARC = {"source", "target", "effect", "metric", "supporting_pairs", "merged_pairs"}


def _two_arcs_that_differ_in_every_field():
    """Two arcs with a different, non-empty value in every field of the format, so any field the merge
    rewrites shows as a difference from the first arc."""
    def value(field, kind, i):
        if kind == "tuple":
            return [f"{field}-{i}"]
        if kind.startswith("float"):
            return [1.0, 3.0][i]
        if kind.startswith("int"):
            return [5, 7][i]                  # neither is 2, the count of a merge of two
        return f"{field}-{i}"
    arcs = [{f.name: value(f.name, str(f.type), i) for f in dataclasses.fields(model.Edge)} for i in (0, 1)]
    for i, arc in enumerate(arcs):
        arc.update(status=[None, "present"][i], evidence=["biculture", "dropout"][i], outcome=f"censored-{i}",
                   study_id=f"S{i}", study_citation=f"study {i}")
    return arcs


def test_the_help_says_what_every_attribute_becomes_on_a_merged_arc():
    from grownet.derive import _merged
    arcs = _two_arcs_that_differ_in_every_field()
    merged = _merged(arcs)
    fields = {f.name for f in dataclasses.fields(model.Edge)}
    changed = {k for k in fields if merged.get(k) != arcs[0].get(k)}
    if [s["id"] for s in merged["studies"]] != [arcs[0]["study_id"]]:      # `study_ids` is written from these
        changed.add("study_ids")
    named = [f for row_fields, _ in help.MERGED_ATTRIBUTES for f in row_fields]
    assert len(named) == len(set(named)), "a field is named in two rows"
    assert set(named) <= fields, set(named) - fields
    # every field the merge rewrites is in the help's table, and every field it does not is one the help
    # names as taken from the first arc, so a new arc field cannot reach a merged arc undocumented
    assert changed - set(named) == set(), changed - set(named)
    assert fields - changed == FROM_THE_FIRST_ARC, fields - changed
    section = PAGE[PAGE.index('id="merged"'):PAGE.index('id="decisions"')]
    section = section.replace("<wbr>", "")
    for field in [*named, *FROM_THE_FIRST_ARC]:
        assert f"<code>{field}</code>" in section, field


def test_two_obligate_arcs_that_agree_keep_their_outcome_and_every_field_they_share():
    """The other half of the table's rules, which arcs differing in every field cannot reach: two arcs with no
    log2 mean keep the outcome they share, and a one-comparison field all merged arcs agree on is kept, not
    emptied (Craig's agent: the ratchet above covers the fields, not both sides of each rule)."""
    from grownet.derive import COMPARISON_FIELDS, _merged
    arcs = _two_arcs_that_differ_in_every_field()
    for arc in arcs:
        arc.update(strength=None, outcome="obligate", effect="facilitation")
        for field in COMPARISON_FIELDS:
            arc[field] = arcs[0][field]
    merged = _merged(arcs)
    assert (merged["outcome"], merged["strength"], merged["merged_arcs"]) == ("obligate", None, 2)
    for field in COMPARISON_FIELDS:
        assert merged[field] == arcs[0][field], field
    assert "otherwise the outcome they all share" in dict(
        (fields, text) for fields, text in help.MERGED_ATTRIBUTES)[("outcome",)]


def test_the_consequences_the_help_states_for_a_merged_arc_hold():
    """Each claim of the help's "Reading a merged arc", checked on arcs whose answer is computed by hand."""
    from grownet.derive import merge_genus, merge_parallel, output_meta
    text = " ".join(visible(PAGE).split())                  # as read, not as the source wraps it

    def arc(strength, **kw):
        effect = "facilitation" if (strength or 1) > 0 else "inhibition"
        return {"source": "ncbi:1", "target": "ncbi:2", "source_name": "Alpha one", "target_name": "Beta two",
                "effect": effect, "strength": strength, "status": "present", "outcome": "quantified",
                "evidence": "biculture", "condition": "c", "experiments": [], "quality": [], "cautions": [],
                "notes": [], "community": [], "method": "m", "study_id": "S1", **kw}

    # unweighted: 1.0 on six replicates and 3.0 on one give the median of the two, 2.0, not 1.29
    assert "The median is unweighted" in text
    (one,), _ = merge_parallel([arc(1.0, n_with=6, n_without=6), arc(3.0, n_with=1, n_without=1)])
    assert one["strength"] == 2.0 and one["n_with"] is None
    # censored arcs count and do not enter the median: +0.2 and three obligate arcs give 0.2, of four arcs
    assert "one arc of +0.2 and three obligate arcs give a quantified arc of strength 0.2" in text
    (one,), _ = merge_parallel([arc(0.2)] + [arc(None, outcome="obligate", effect="facilitation")] * 3)
    assert (one["strength"], one["outcome"], one["merged_arcs"]) == (0.2, "quantified", 4)
    # present when any merged arc is: one present, two undetermined (empty status)
    assert "A merged arc is present when any of its arcs is" in text
    (one,), _ = merge_parallel([arc(1.0), arc(2.0, status=None), arc(4.0, status=None)])
    assert one["status"] == "present"
    # arcs below the absence threshold leave before the merge: 1.0 with sd 0.1 is present, 0.05 with sd 0.5
    # is below k = 1, so the merge sees one arc and merges nothing
    assert "arcs below the absence threshold have left before the merge" in text
    records = [arc(1.0, sd=0.1, n_with=3, n_without=3, p_value=0.01),
               arc(0.05, sd=0.5, n_with=3, n_without=3, p_value=0.9)]
    for r in records:
        r.pop("status")
    edges, meta = output_meta(records, merge_arcs=True)
    assert len(edges) == 1 and not edges[0].get("merged_arcs") and meta["hidden"]["absent"] == 1
    # both signs: five facilitation arcs and one inhibition arc give six arcs, none merged
    assert "five facilitation arcs and one inhibition arc give six arcs, none merged" in text
    edges, meta = merge_parallel([arc(1.0)] * 5 + [arc(-0.5)])
    assert len(edges) == 6 and meta["merged"] == 0 and meta["left_apart_for_disagreeing_signs"] == 1
    # Merge to genus also merges absent arcs: two absent arcs from species of one genus to another give one
    assert "also merges their absent arcs" in text
    absent = [arc(0.01, status="absent", source="ncbi:3", source_name="Alpha three"),
              arc(0.02, status="absent")]
    (one,), _ = merge_genus(absent, merge=True)
    assert (one["status"], one["merged_arcs"], one["source"]) == ("absent", 2, "Alpha")


def test_the_node_attributes_have_their_own_header_after_the_merged_arcs():
    """Karoline, 2026-11-06: "the help has a node attribute table under the header 'What a merged arc
    carries'. please introduce a new header." The order is now: arc attributes, what a merged arc
    carries, node attributes, what a merged node carries."""
    order = ['<h3 id="arc-attributes">Arc attributes</h3>', "<th>Arc attribute</th>",
             '<h3 id="merged">What a merged arc carries</h3>',
             '<h3 id="node-attributes">Node attributes</h3>', "<th>Node attribute</th>",
             '<h3 id="merged-nodes">What a merged node carries</h3>', '<h2 id="decisions">']
    at = [PAGE.index(marker) for marker in order]
    assert at == sorted(at), dict(zip(order, at, strict=True))


def _genus_arcs():
    """Two arcs from strains of one genus to another, as study 8 gives them live: the Lachnoclostridium
    strains share taxon id 1506553, so each carries the refusal of that id as its identity."""
    refused = ("mGrowthDB gives taxon id 1506553 to different strains in this study (Lachnoclostridium "
               "clostridioforme 2_1_49FAA, Lachnoclostridium symbiosum WAL-14673), so it is not a join key")
    def arc(source, name, strength):
        return {"source": source, "target": "ncbi:2", "source_name": name, "target_name": "Bacteroides ovatus",
                "source_taxon_id": "1506553", "source_species": " ".join(name.split()[:2]).lower(),
                "source_identity": "name", "source_taxon_id_refused": refused,
                "target_taxon_id": "2", "target_species": "bacteroides ovatus", "target_identity": "ncbi",
                "effect": "inhibition", "strength": strength, "status": "present", "outcome": "quantified",
                "evidence": "dropout", "community": [source, "ncbi:2", "ncbi:3"], "study_id": "S8",
                "condition": "c", "method": "m", "experiments": [], "quality": [], "cautions": [], "notes": []}
    return [arc("lachnoclostridium clostridioforme", "Lachnoclostridium clostridioforme 2_1_49FAA", -1.0),
            arc("lachnoclostridium symbiosum", "Lachnoclostridium symbiosum WAL-14673", -3.0)]


def test_a_genus_node_keeps_no_strain_id_and_says_so():
    """Karoline, 2026-11-06: "for a merged node on genus level, are strain ids kept? please document merging
    in nodes as well." They are not: a genus node is the genus, and the help says where the strains behind it
    are found instead. It also kept the first strain's taxon_id_refused, so the live Lachnoclostridium node
    said a taxon id was refused that the genus node does not carry (found answering her)."""
    from grownet.derive import merge_genus
    from grownet.mgrowthdb import records_to_network
    edges, _ = merge_genus(_genus_arcs(), merge=True)
    net = records_to_network(edges)
    node = net.nodes["Lachnoclostridium"]
    assert (node.name, node.identity, node.taxon_id, node.species, node.taxon_id_refused) == \
        ("Lachnoclostridium", "genus", "", "", "")
    # the strains it stands for are kept since #306 (Karoline: "Yes, add it"), by node id
    assert node.merged_nodes == ("lachnoclostridium clostridioforme", "lachnoclostridium symbiosum")
    (arc,) = net.edges
    # what the arc keeps instead: the pairs behind it by name, and the community members' strain ids
    assert tuple(arc.merged_pairs) == ("Lachnoclostridium clostridioforme -> Bacteroides ovatus",
                                       "Lachnoclostridium symbiosum -> Bacteroides ovatus")
    assert arc.supporting_pairs == 2 and "lachnoclostridium symbiosum" in arc.community
    # and the help says each of these about a merged node, field by field
    raw = PAGE[PAGE.index('id="merged-nodes"'):PAGE.index('id="decisions"')]
    section = visible(raw)
    # each field by its own name, as the help writes a field, so "species" is not found in "species pairs"
    # nor "taxon_id" in "taxon_id_refused" (found in review)
    for field in (f.name for f in dataclasses.fields(model.Node)):
        assert help._name(field) in raw, field
    assert "merged_nodes lists the strains it stands for" in " ".join(section.split())
    for where in ("merged_pairs", "supporting_pairs", "community"):
        assert help._name(where) in raw, where
    # a drop-out member on no arc (ncbi:3 here) is in the arc's community and in no node's merged_nodes,
    # and the help does not say otherwise
    assert "ncbi:3" in arc.community and not any("ncbi:3" in n.merged_nodes for n in net.nodes.values())
    assert "a member on no arc is named only there" in " ".join(section.split())


def test_the_attribute_list_names_every_value_an_edge_can_take():
    text = " ".join(help.EDGE_ATTRIBUTES.values())
    for value in (*model.EFFECTS, *model.OUTCOMES, *model.QUALITY_FLAGS, *model.CAUTIONS, *model.EVIDENCE,
                  *model.STATUSES):
        assert value in text, value


def test_the_page_has_every_section_its_contents_list_names():
    for key, title in help.SECTIONS:
        # a title may hold the name, which carries markup in prose, so the heading is read as text
        assert f'href="#{key}"' in PAGE
        assert re.search(rf'<h2 id="{key}">(.*?)</h2>', PAGE) and \
            title in visible(re.search(rf'<h2 id="{key}">.*?</h2>', PAGE).group(0))


def test_the_command_line_example_is_the_pages_example():
    for name in gui.EXAMPLE:
        assert f'"{name}"' in help.EXAMPLE_CLI
    assert help.EXAMPLE_CLI.startswith("grownet derive --live --species ")      # the command until #71
    assert gui.html.escape(help.EXAMPLE_CLI) in PAGE


def test_the_issue_tracker_is_linked():
    assert f'href="{help.ISSUES}"' in PAGE and f'href="{help.NEW_ISSUE}"' in PAGE


def test_the_version_is_shown_next_to_the_name():
    # the header of every page: the mark, the wordmark grow<b>net</b>, then the version (#78)
    heading = f'<span class="word">grow<b>net</b></span></h1></a><span class="version">{__version__}</span>'
    for page in (gui.render_form("tok"), gui.render_result("tok", _query()), PAGE):
        assert heading in page and "<svg" in page.split(heading)[0]
    assert f"grownet {__version__}" in visible(PAGE)


def test_every_network_records_the_tool_its_version_and_the_date():
    net = records_to_network([], meta={"source_db": "x"})
    today = datetime.date.today().isoformat()
    assert (net.meta["tool"], net.meta["tool_version"], net.meta["derived_on"]) == ("grownet", __version__, today)
    assert provenance(datetime.date(2026, 9, 27))["derived_on"] == "2026-09-27"
    graph = ET.fromstring(to_graphml(net)).find("{http://graphml.graphdrawing.org/xmlns}graph")
    data = {d.get("key"): d.text for d in graph.findall("{http://graphml.graphdrawing.org/xmlns}data")}
    # the four this test is about, asserted by VALUE rather than by an equality over the whole dict: the
    # dict grew when the GraphML started carrying its own schema id, source and citations (#216), and an
    # equality here made that a failure of a test about the tool, the version and the date
    assert {k: data[k] for k in ("g_tool", "g_tool_version", "g_derived_on", "g_derived_at")} == {
        "g_tool": "grownet", "g_tool_version": __version__, "g_derived_on": today,
        "g_derived_at": net.meta["derived_at"]}
    # and nothing is written that is not declared, which is what the equality was incidentally covering
    declared = {k.get("id") for k in ET.fromstring(to_graphml(net))
                .findall("{http://graphml.graphdrawing.org/xmlns}key")}
    assert set(data) <= declared, set(data) - declared
    assert net.meta["derived_at"].startswith(today + "T")                    # date, time and offset


def test_a_search_records_every_setting_it_ran_with():
    meta = _query(metric="max", absence_threshold=2.0)["network"].meta
    assert set(meta["settings"]) == set(gui.DEFAULTS)
    assert (meta["settings"]["metric"], meta["settings"]["absence_threshold"]) == ("max", 2.0)


def test_the_command_line_species_search_gives_the_pages_network(monkeypatch, capsys, tmp_path):
    # the same two names through `derive --species` and through the page's run_query: the same edges
    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    out = tmp_path / "net.json"
    names = ["Faecalibacterium prausnitzii", "Blautia hydrogenotrophica"]
    # both sides keep the absences, so the comparison is about the arcs, not about the new default
    assert main(["derive", "--live", "--species", *names, "--out", str(out), "--include-absent",
                 "--derivation", "replicate"]) == 0
    cli = json.loads(out.read_text(encoding="utf-8"))
    page = json.loads(_query(entries=names)["network"].to_json())
    assert cli["edges"] == page["edges"] and cli["nodes"] == page["nodes"]
    assert cli["meta"]["tool_version"] == __version__
    assert "studies searched: SMGDB00000001" in capsys.readouterr().err


def test_the_command_line_all_gives_the_pages_all_network(monkeypatch, capsys, tmp_path):
    # `derive --live --all` and the page with both boxes empty: the same edges, and the report says what was asked
    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    out, report = tmp_path / "all.json", tmp_path / "all.txt"
    assert main(["derive", "--live", "--all", "--merge-genera", "--derivation", "replicate",
                 "--out", str(out), "--report", str(report)]) == 0
    cli = json.loads(out.read_text(encoding="utf-8"))
    page = json.loads(gui.run_query(FakeClient(), [], {"merge_genera": True, "derivation": "replicate"},
                                    all_studies=True)["network"].to_json())
    assert cli["edges"] == page["edges"] and cli["edges"] and cli["meta"]["query"] == "all"
    assert {n["identity"] for n in cli["nodes"]} == {"genus"}
    assert "query: all of mGrowthDB" in report.read_text(encoding="utf-8")


def test_the_command_line_with_conditions_and_no_species_gives_the_pages_empty_species_box(monkeypatch, capsys,
                                                                                          tmp_path):
    # #300 (Karoline, 2026-11-04): the page's species box left empty with media or studies in the second
    # box searches every species in them. `--conditions` without `--species` or a study does the same, and
    # the report says what was asked, not "all of mGrowthDB"
    class InStudy(FakeClient):
        """The fake study's experiments, carrying the study id mGrowthDB gives them, which the second box
        matches a study id against."""

        def study_experiments(self, study_id):
            return [{**e, "studyId": study_id} for e in super().study_experiments(study_id)]

        def get_experiment(self, experiment_id):
            return {**super().get_experiment(experiment_id), "studyId": self.study_id}

    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", InStudy)
    out, report = tmp_path / "wc.json", tmp_path / "wc.txt"
    assert main(["derive", "--live", "--conditions", "SMGDB00000001", "--derivation", "replicate",
                 "--out", str(out), "--report", str(report)]) == 0
    cli = json.loads(out.read_text(encoding="utf-8"))
    page = json.loads(gui.run_query(InStudy(), [], {"conditions": "SMGDB00000001", "derivation": "replicate"},
                                    all_studies=True)["network"].to_json())
    assert cli["edges"] == page["edges"] and cli["edges"] and cli["meta"]["query"] == "all"
    text = report.read_text(encoding="utf-8")
    assert "all of mgrowthdb" not in text.lower() and "SMGDB00000001" in text
    # a study argument keeps its own meaning (derive that one study), and nothing at all still asks for one
    assert main(["derive", "--live"]) == 2
    assert "needs a study id" in capsys.readouterr().err


def test_species_search_needs_live_and_rejects_a_deriver(capsys, tmp_path):
    fixture = tmp_path / "records.json"
    fixture.write_text("[]", encoding="utf-8")
    assert main(["derive", "--fixture", str(fixture), "--species", "Blautia"]) == 2
    assert main(["derive", "--live", "--deriver", "m:C", "--species", "Blautia"]) == 2
    assert main(["derive", "--live"]) == 2                     # neither a study nor species
    err = capsys.readouterr().err
    assert "needs --live" in err and "--deriver applies to one study" in err and "needs a study id" in err


def test_the_page_uses_the_two_signal_colors_and_no_other_red():
    # Karoline's palette (2026-09-27): growth green and the orange-red, never the plain red it replaced
    from grownet import brand
    assert (brand.GROWTH, brand.INHIBITION) == ("#1A7F5A", "#C2410C")
    page = gui.render_form("tok")
    assert brand.GROWTH in page and brand.INHIBITION in page and "#B3352E" not in page.upper()


def test_directions_carry_their_color_and_the_legend_opens_in_the_frame():
    result = gui.render_result("tok", _query())
    assert '<td class="up">facilitation</td>' in result
    legend = gui.render_legend("tok")
    assert '<div class="app"><header>' in legend and "Interaction network legend" in legend


def test_the_introduction_cites_gause_and_shows_the_idea():
    page = help.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    intro = page[page.index('<h2 id="idea">'):page.index('<h2 id="example">')]
    assert "Gause GF (1932)" in intro and "Gause GF (1934)" in intro
    assert intro.count("<svg") == 4 and "A alone" in intro and "A and B together" in intro


def test_the_figure_marks_every_growth_measure_the_tool_can_compare():
    from grownet.idea import idea_figure
    figure = idea_figure()
    marks = {"auc": "area (auc)", "max": "maximum (max)", "growth_rate": "growth rate"}
    assert set(gui.METRICS) == set(marks)                   # a new measure needs a mark in the figure
    assert all(label in figure for label in marks.values())


def test_the_figure_shows_what_its_arcs_say():
    from grownet import brand, idea
    final = {name: {w: idea._curve(params[name])[-1][1] for w, params in
                    (("alone", idea.ALONE), ("together", idea.TOGETHER))} for name in "AB"}
    assert final["A"]["together"] < final["A"]["alone"]      # B inhibits A: the orange-red arc
    assert final["B"]["together"] > final["B"]["alone"]      # A facilitates B: the green arc
    arcs = idea._arcs()
    assert brand.GROWTH in arcs and brand.INHIBITION in arcs


def test_the_marked_stretch_holds_the_steepest_rise_of_log_abundance():
    import math

    from grownet import idea
    points = idea._curve(idea.ALONE["A"])
    slopes = [(math.log(b[1]) - math.log(a[1])) / (b[0] - a[0]) for a, b in zip(points[:-1], points[1:], strict=True)]
    steepest = points[slopes.index(max(slopes))]
    assert steepest in idea._steep_stretch(points)


def test_the_help_explains_how_a_chemostat_is_treated():
    """Karoline, 2026-10-03, after the rule changed: "please document the new way of treating chemostat
    data". The rule depends on the growth measure, so the help has to say both halves."""
    html = help.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    section = html[html.index("Chemostats and serial dilutions"):]
    section = section[:section.index("Try the example")]
    assert "with max it is derived" in section.lower()
    assert "continuous_culture" in section                 # what such an arc is marked with
    assert "left out" in section and "non_batch" in section  # and what happens with the other measures
    assert "never mixes modes" in section
    # the setting's own text says the same, so the two cannot drift apart
    setting = help.SETTINGS["include_non_batch"][2]
    assert "max" in setting and "continuous_culture" in setting and "non_batch" in setting


def test_the_help_explains_the_matrix_the_growth_rates_and_the_glv_package():
    """Karoline, 2026-10-03: "please make sure all of this is in the CLI and documented". Every convention
    a reader of those files needs is on the help page, in the words the files themselves use."""
    html = help.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    section = html[html.index("The matrix, the growth rates and gLV"):]
    section = section[section.index("<h2 id=\"glv\">"):section.index("<h2 id=\"settings\">")]
    assert "A[i][j]" in section.replace("&#x27;", "'") and "rows are affected" in section
    assert "median" in section and "disagree in sign" in section      # how arcs of one pair are merged
    assert "monoculture" in section and "chemostat" in section        # where a rate comes from, and not
    # what the package holds since #119, #123 and #129: coefficients, with no convention left in it, and
    # a measured bound where the plain matrix used to carry a stated extreme
    assert "per-capita" in section and "1/(time x abundance)" in section
    assert "measured bound" in section and "no-growth rule" in section
    # and where that bound is, since #129 settled on 2026-10-08: on the arc, with NA in the cell
    assert "NA" in section and "strength_bound" in section
    assert "-r_i / K_i" in section and "(r_with - r_without) / x_j" in section
    # the phrase survives only where the page says what replaced it
    for sentence in section.split("."):
        if "stated extreme" in sentence:
            assert "which is what was wrong with the stated extreme it used to carry" in sentence \
                or "no floor and no stated extreme" in sentence
    # the command line section shows both new outputs, so the page and the terminal say the same
    cli = html[html.index("<h2 id=\"cli\">"):]
    assert "--format matrix" in cli and "--report-rates" in cli and "--glv" in cli


def test_the_help_links_the_r_package_and_says_how_to_install_it():
    """Karoline, 2026-10-03: the R plugin "should be linked to/available from grownet's help and easy to
    install in R". One install line, one way to receive, and what the package enforces about the
    caveats."""
    from grownet import rbridge
    html = help.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    section = html[html.index("<h2 id=\"glv\">"):html.index("<h2 id=\"settings\">")]
    import html as html_module
    assert html_module.escape(rbridge.INSTALL_R, quote=True) in section   # the one install line
    assert "grownet_listen()" in section and "grownet_glv(url)" in section
    assert "miaSim" in section and "simulateGLV" in section
    # the line has to work as written: the package is not on main yet, and a stored token can hide a
    # public repository (Karoline hit both, 2026-10-04)
    # Karoline, 2026-10-04: "The help should refer to the stage the tool is in when released." So the
    # install line is the one a release's reader runs, with no branch of ours in it.
    assert "ref =" not in section and "install_github" in section
    assert "branch" not in section
    assert "404" in section and "install_local" in section       # the way out needs no GitHub access
    # Karoline, 2026-10-04: the example shows how to look at a simulation, and the help says that an
    # arrival always prints in R and that the listener takes one set at a time
    assert "matplot" in section and "legend(" in section
    # Karoline, 2026-10-04: miaSim runs with migration and stochasticity on by default, so the example
    # says how to switch them off without changing the call itself
    assert "stochastic = FALSE" in section and "migration_p = 0" in section
    assert "prints the summary" in section and "one parameter set" in section
    assert "run it\nagain before each send" in section or "again before each send" in section
    # Karoline, 2026-10-04: "Sys.setenv(GITHUB_PAT = \"\") was not necessary for me and I don't think we
    # should recommend it for users, as it alters their system settings in ways that can affect them
    # negatively." So the help never tells a reader to change their environment to install the package.
    assert "GITHUB_PAT" not in html and "Sys.setenv" not in html
    assert "glv_matrix()" in section and "as_miasim()" in section and "glv_scale()" in section
    assert "assumes no simulator" in section            # it works with other simulators and with own code


def test_the_name_is_marked_as_a_name_in_prose_but_left_alone_in_commands():
    """Karoline, 2026-10-03: "please use a special style for grownet, so sentences starting with it don't
    look strange". It is all lowercase, so in prose it carries the wordmark's two parts."""
    from grownet import brand
    assert brand.in_prose("<p>grownet reads mGrowthDB.</p>") == f"<p>{brand.NAME_HTML} reads mGrowthDB.</p>"
    for untouched in ("<code>grownet gui</code>", "<title>grownet</title>",
                      "<pre>python -m grownet gui</pre>", '<a href="/x">What grownet does</a>',
                      "<p>github.com/crossfeed-bio/grownet</p>", "<p>grownet-bio</p>"):
        assert brand.in_prose(untouched) == untouched
    # the served page carries it: the body is styled, the header's own wordmark is untouched
    page = gui.render_help("tok", "")
    assert page.count(brand.NAME_HTML) > 5 and "<code>grownet" in page.replace("</code>", "")


def test_the_help_says_the_adjusted_p_value_is_the_q_value():
    """Karoline, 2026-10-03: "make sure the reader in the help knows that the adjusted p-value is the
    q-value". The page heads that column q, so the two names have to meet somewhere."""
    text = visible(PAGE)
    decided = text[text.index("How an interaction is decided"):]
    assert "adjusted p-value, which is what a q-value is" in decided
    assert "q_value" in decided and "column is headed q" in decided
    # and the setting that filters on it says the same, since a reader may start there
    assert "the p-value adjusted for multiple testing: the two names mean the same number" in \
        help.SETTINGS["max_adjusted_p"][2]
    assert help.SETTINGS["max_adjusted_p"][0] == "Filter on the q-value"


def test_the_first_advanced_setting_is_called_growth_property():
    """Karoline, 2026-10-03: "Growth measure (the first entry) should be Growth property"."""
    assert help.SETTINGS["metric"][0] == "Growth property"
    assert "Growth property" in gui.render_form("tok") and "Growth measure" not in gui.render_form("tok")


def test_the_about_page_logs_what_each_release_brought():
    """Karoline, 2026-10-04: the About page "can have a small log of what happened in each new release".
    The newest entry is this version, so a release cannot forget its line, and the full record is linked."""
    from grownet import __version__
    from grownet.help import RELEASES, render_about
    assert RELEASES[0][0] == __version__, "the About page's log does not name this version"
    assert [v for v, _, _ in RELEASES] == sorted({v for v, _, _ in RELEASES}, reverse=True)  # newest first
    for version, date, lines in RELEASES:
        assert re.fullmatch(r"\d+\.\d+\.\d+", version) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
        assert lines and all(len(line) < 400 for line in lines)       # a summary, not the changelog

    page = render_about()
    assert "What changed" in page and "CHANGELOG.md" in page
    for version, _, lines in RELEASES:
        assert f">{version} <" in page
        assert lines[0][:40] in page


def test_the_glv_example_section_gives_every_step_of_running_it_in_miasim():
    """Karoline, 2026-10-07: "The help, while being generic, should provide all the steps to run this
    example with miaSim." Generic means the route above it, which holds for any package; this section is
    that route with one search's numbers in it, and a reader should not need anything the page does not
    say."""
    page = gui.render_help("tok")
    # the anchor is "glv-walkthrough", not "glv-example": the latter collided with the branch name this
    # work was written on, which test_release.py refuses in shipped text and rightly
    section = page[page.index('<h2 id="glv-walkthrough">'):]
    section = section[:section.index("<h2 ", 10)] if "<h2 " in section[10:] else section
    # the button, the command line that does the same, and the study it reads. The study moved from
    # SMGDB00000006 to SMGDB00000002 (#155 item 13): the yoghurt pair's package rested on one of three
    # monoculture replicates, all three of which fitted a positive self-limitation, and its equilibrium
    # inverted the co-culture it was fitted from. Her requirement is the steps, not the study.
    assert "gLV example" in section and "SMGDB00000002" in section
    # the command printed beside the button is the one the button runs: gLV mode, which sets the rates,
    # the metric, the drop-out setting and the derivation. It printed --report-rates alone until
    # 2026-10-10, which exits 2 under the default derivation (found reviewing #199)
    assert "--glv-mode" in section and "--glv " in section
    # installing miaSim is part of the steps: it is a Bioconductor package, not a CRAN one
    assert "BiocManager::install" in section and "miaSim" in section
    # the three calls a simulation needs, and the deterministic settings spelled out
    for call in ("grownet_listen()", "glv_matrix(glv)", "glv_rates(glv)", "as_miasim(glv)",
                 "miaSim::simulateGLV", "stochastic = FALSE", "migration_p = 0"):
        assert call in section, call
    # what to expect, so a reader can tell it worked, and where the numbers come from
    assert "solve(A, -r)" in section
    assert "7.323e8" in section and "3.634e8" in section
    # and the step that holds the prediction against the data, which is what a reader needs to catch a
    # package that settles somewhere the co-culture never was: agreeing with `solve(A, -r)` only says
    # the simulation and the package agree with each other
    assert "measured peaks" in section and "rate_mismatch_to_zero" in section
    # and that the numbers are of the database as it is, not a promise
    assert "mGrowthDB changes" in section


def test_the_help_states_what_a_glv_model_assumes():
    """Karoline, 2026-10-07: "let's add some caveats about the assumptions of gLV, especially the
    higher-order interactions and constant interaction coefficients. In batch, the medium changes, so the
    environment changes, and with it the species interactions."

    These are properties of the form, not defects in the fit, so they are stated as such and in the two
    places a reader meets the parameters: the page and the package the download carries.
    """
    import re

    page = gui.render_help("tok")
    section = page[page.index('<h2 id="glv-assumptions">'):]
    section = section[:section.index("<h2 ", 10)]
    section = re.sub(r"\s+", " ", section)      # the prose wraps, so the phrases below span line breaks
    assert "constant in time" in section
    assert "change in size and in sign along the growth curve" in section
    assert "Higher-order interactions" in section and "third organism" in section
    # the batch argument, in her terms: the medium changes, so the environment does
    for phrase in ("medium is consumed", "metabolites accumulate", "late stationary phase"):
        assert phrase in section, phrase
    # tied to the fields that say how much of the course a coefficient rests on
    assert "fit_window_share" in section and "window_partial" in section
    # and it is in the table of contents, so a reader meets it before the walkthrough
    assert 'href="#glv-assumptions"' in page
    assert page.index('href="#glv-assumptions"') < page.index('href="#glv-walkthrough"')


def test_every_command_the_help_page_prints_is_one_the_parser_accepts():
    """A help-page example that exits 2 has been fixed three times, in the CLI epilog, in the README and
    in the gLV walkthrough, and a fourth copy survived all three because no test ran what the help page
    prints: `test_help.py` asserted that the substrings `--format matrix`, `--report-rates` and `--glv`
    appear (#234). The surviving one was
    `derive SMGDB00000004 --live --report-rates --rates ... --glv ...`, which under the comparison needs
    `--metric growth_rate` and exits 2 with that message.

    This parses every command the page prints, which catches a flag combination the parser refuses
    without touching the network, and it reads the commands out of the rendered page rather than a list
    here, so the next example is covered when it is written.
    """
    import html
    import re
    import shlex

    from grownet.__main__ import _rate_flags, _resolve, _species_flags, build_parser
    from grownet.gui import DEFAULTS, EXAMPLE
    from grownet.help import COMMAND, render_help

    page = render_help("tok", DEFAULTS, EXAMPLE)
    commands = []
    # <code> as well as <pre>: the page prints four more commands in inline <code>, among them the gLV
    # walkthrough, which is one of the three places #234 says this bug was already fixed once. Removing
    # `--live` from that inline command left the whole suite green while the printed command exited 2
    # (found reviewing this change).
    for block in re.findall(r"<(?:pre|code)>(.*?)</(?:pre|code)>", page, re.S):
        for line in html.unescape(block).splitlines():
            line = line.strip()
            if line.startswith(COMMAND + " "):
                commands.append(line)
    # the floor is the real count, so losing a block is a failure rather than a quieter test. It was 8
    # while the <pre>-only extraction found 9, which let four commands go unchecked without the floor
    # noticing.
    assert len(commands) >= 12, f"the page printed {len(commands)} commands, so this checked less than before"

    parser = build_parser()
    for command in commands:
        argv = shlex.split(command)[1:]                 # drop the program name
        if argv and argv[0] in ("gui", "validate", "schema", "style"):
            continue                                   # no settings to check on these
        if "--help" in argv or "-h" in argv:
            continue                                   # argparse exits 0 and prints; nothing to check
        # the parsed arguments are not what runs: gLV mode sets four settings and `--derivation`
        # carries no default, so `_resolve` is what a run applies before any check. Calling the guard on
        # unresolved arguments passes everything, because it tests `a.derivation == "replicate"`; this
        # test found that on itself, which is why it uses the run's own resolver rather than a copy.
        args = _resolve(parser.parse_args(argv), announce=False)
        # EVERY pre-flight guard the run applies, not just the rate flags. `_derive` has three and the
        # first version of this called one, so a printed example could exit 2 with the suite green:
        # adding `--species` to the `--all` line, the most ordinary editorial slip for it, was not
        # caught (found reviewing this change).
        problems = [_rate_flags(args)]
        if args.species or args.all_studies:
            problems.append(_species_flags(args))
        for problem in problems:
            assert problem == "", f"{command}\n  -> {problem}"
