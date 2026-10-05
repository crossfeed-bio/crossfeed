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
    assert data == {"g_tool": "grownet", "g_tool_version": __version__, "g_derived_on": today,
                    "g_derived_at": net.meta["derived_at"]}
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
    assert main(["derive", "--live", "--species", *names, "--out", str(out), "--include-absent"]) == 0
    cli = json.loads(out.read_text(encoding="utf-8"))
    page = json.loads(_query(entries=names)["network"].to_json())
    assert cli["edges"] == page["edges"] and cli["nodes"] == page["nodes"]
    assert cli["meta"]["tool_version"] == __version__
    assert "studies searched: SMGDB00000001" in capsys.readouterr().err


def test_the_command_line_all_gives_the_pages_all_network(monkeypatch, capsys, tmp_path):
    # `derive --live --all` and the page's All button: the same edges, and the report says what was asked
    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    out, report = tmp_path / "all.json", tmp_path / "all.txt"
    assert main(["derive", "--live", "--all", "--merge-genera", "--out", str(out), "--report", str(report)]) == 0
    cli = json.loads(out.read_text(encoding="utf-8"))
    page = json.loads(gui.run_query(FakeClient(), [], {"merge_genera": True}, all_studies=True)["network"].to_json())
    assert cli["edges"] == page["edges"] and cli["edges"] and cli["meta"]["query"] == "all"
    assert {n["identity"] for n in cli["nodes"]} == {"genus"}
    assert "query: all of mGrowthDB" in report.read_text(encoding="utf-8")


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
    from grownet import matrix
    html = help.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    section = html[html.index("The matrix, the growth rates and gLV"):]
    section = section[section.index("<h2 id=\"glv\">"):section.index("<h2 id=\"settings\">")]
    assert "A[i][j]" in section.replace("&#x27;", "'") and "rows are affected" in section
    assert "median" in section and "disagree in sign" in section      # how arcs of one pair are merged
    assert "+10" in section and "-10" in section                      # the obligate and abolished extremes
    assert f"{matrix._number(matrix.DIAGONAL)} on the diagonal" in section or "-1" in section
    assert "monoculture" in section and "chemostat" in section        # where a rate comes from, and not
    assert "not fitted gLV coefficients" in section
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
