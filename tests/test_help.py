"""The help page cannot fall behind the code, and a network says what made it and when (#78)."""
import argparse
import dataclasses
import datetime
import json
from xml.etree import ElementTree as ET

import pytest
from test_gui import FakeClient, _query

from crossfeed import __version__, gui, help, interaction, model
from crossfeed.__main__ import build_parser, main
from crossfeed.export import to_graphml
from crossfeed.mgrowthdb import provenance, records_to_network

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


def test_the_attribute_list_names_every_value_an_edge_can_take():
    text = " ".join(help.EDGE_ATTRIBUTES.values())
    for value in (*model.EFFECTS, *model.OUTCOMES, *model.QUALITY_FLAGS, *model.CAUTIONS, *model.EVIDENCE,
                  *model.STATUSES):
        assert value in text, value


def test_the_page_has_every_section_its_contents_list_names():
    for key, title in help.SECTIONS:
        assert f'href="#{key}"' in PAGE and f'<h2 id="{key}">{title}</h2>' in PAGE


def test_the_command_line_example_is_the_pages_example():
    for name in gui.EXAMPLE:
        assert f'"{name}"' in help.EXAMPLE_CLI
    assert help.EXAMPLE_CLI.startswith("crossfeed derive --live --species ")      # the command until #71
    assert gui.html.escape(help.EXAMPLE_CLI) in PAGE


def test_the_issue_tracker_is_linked():
    assert f'href="{help.ISSUES}"' in PAGE and f'href="{help.NEW_ISSUE}"' in PAGE


def test_the_version_is_shown_next_to_the_name():
    # the header of every page: the mark, the wordmark grow<b>net</b>, then the version (#78)
    heading = f'<span class="word">grow<b>net</b></span></h1></a><span class="version">{__version__}</span>'
    for page in (gui.render_form("tok"), gui.render_result("tok", _query()), PAGE):
        assert heading in page and "<svg" in page.split(heading)[0]
    assert f"grownet {__version__}" in PAGE


def test_every_network_records_the_tool_its_version_and_the_date():
    net = records_to_network([], meta={"source_db": "x"})
    today = datetime.date.today().isoformat()
    assert (net.meta["tool"], net.meta["tool_version"], net.meta["derived_on"]) == ("grownet", __version__, today)
    assert provenance(datetime.date(2026, 9, 27))["derived_on"] == "2026-09-27"
    graph = ET.fromstring(to_graphml(net)).find("{http://graphml.graphdrawing.org/xmlns}graph")
    data = {d.get("key"): d.text for d in graph.findall("{http://graphml.graphdrawing.org/xmlns}data")}
    assert data == {"g_tool": "grownet", "g_tool_version": __version__, "g_derived_on": today,
                    "g_derived_at": net.meta["derived_at"]}
    assert net.meta["derived_at"].startswith(today + "T")                    # date, time and offset


def test_a_search_records_every_setting_it_ran_with():
    meta = _query(metric="max", absence_threshold=2.0)["network"].meta
    assert set(meta["settings"]) == set(gui.DEFAULTS)
    assert (meta["settings"]["metric"], meta["settings"]["absence_threshold"]) == ("max", 2.0)


def test_the_command_line_species_search_gives_the_pages_network(monkeypatch, capsys, tmp_path):
    # the same two names through `derive --species` and through the page's run_query: the same edges
    monkeypatch.setattr("crossfeed.mgrowthdb.MGrowthDBClient", FakeClient)
    out = tmp_path / "net.json"
    names = ["Faecalibacterium prausnitzii", "Blautia hydrogenotrophica"]
    assert main(["derive", "--live", "--species", *names, "--out", str(out)]) == 0
    cli = json.loads(out.read_text(encoding="utf-8"))
    page = json.loads(_query(entries=names)["network"].to_json())
    assert cli["edges"] == page["edges"] and cli["nodes"] == page["nodes"]
    assert cli["meta"]["tool_version"] == __version__
    assert "studies searched: SMGDB00000001" in capsys.readouterr().err


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
    from crossfeed import brand
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
    from crossfeed.idea import idea_figure
    figure = idea_figure()
    marks = {"auc": "area (auc)", "max": "maximum (max)", "growth_rate": "growth rate"}
    assert set(gui.METRICS) == set(marks)                   # a new measure needs a mark in the figure
    assert all(label in figure for label in marks.values())


def test_the_figure_shows_what_its_arcs_say():
    from crossfeed import brand, idea
    final = {name: {w: idea._curve(params[name])[-1][1] for w, params in
                    (("alone", idea.ALONE), ("together", idea.TOGETHER))} for name in "AB"}
    assert final["A"]["together"] < final["A"]["alone"]      # B inhibits A: the orange-red arc
    assert final["B"]["together"] > final["B"]["alone"]      # A facilitates B: the green arc
    arcs = idea._arcs()
    assert brand.GROWTH in arcs and brand.INHIBITION in arcs


def test_the_marked_stretch_holds_the_steepest_rise_of_log_abundance():
    import math

    from crossfeed import idea
    points = idea._curve(idea.ALONE["A"])
    slopes = [(math.log(b[1]) - math.log(a[1])) / (b[0] - a[0]) for a, b in zip(points[:-1], points[1:], strict=True)]
    steepest = points[slopes.index(max(slopes))]
    assert steepest in idea._steep_stretch(points)
