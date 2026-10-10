"""Karoline's interface requirements (#72), each checked against the running server, so none can be lost.

Her words, 2026-09-27: "there should be a progress bar to show something is going on while data are being
fetched and processed. Then, the output should be shown on the same page below the advanced settings, in
the form of three buttons: 1 to download the network, next to a menu where users can choose the network
format; 1 to send it to an open instance of Cytoscape and a last one with the detailed comments of the
search, which can also be downloaded as a text file that will also include all the settings."

And on #78: "The tool version should be also mentioned in the report accompanying each network."

And later the same day: "Now that we have an example button, please keep the input field empty. The header
above the input field should list the options (Species, strains or NCBI identifiers) and, in a row below in
smaller font size, give a few examples (but keep the input field empty)."

And on 2026-10-03: "if p & q-values were not computed, they are missing value (probably safer than empty);
not 0, as discussed. Small change in the header of the Result table: instead of Direction, use Sign, since
direction is misleading (direction of the arc)."

A test here failing means one of those requirements broke. Change the requirement with Karoline, not the
test.
"""
import http.server
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

import pytest
from test_gui import A, B, FakeClient

from grownet import __version__, gui, interaction
from grownet.help import SETTINGS

GATE = threading.Event()        # holds the slow client's first request until a test lets it go


class SlowClient(FakeClient):
    """The fake study, with a search that waits for the test, so the progress page can be seen."""

    def get_study(self, study_id):
        GATE.wait(10)
        return super().get_study(study_id)


@pytest.fixture(autouse=True)
def _no_growth_rule_off(monkeypatch):
    # the fake study's monocultures barely rise; these tests are about the page, not the rule (#37)
    monkeypatch.setattr(interaction, "NO_GROWTH_ALPHA", 0.0)
    monkeypatch.setattr(interaction, "NO_GROWTH_FACTOR", 0.0)


@pytest.fixture
def server(monkeypatch):
    """The real server with the slow client; the redirect after a search waits at most 0.05 s."""
    holder = {}
    original = gui._Server

    class Capture(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            holder["server"] = self

    monkeypatch.setattr(gui, "_Server", Capture)
    monkeypatch.setattr(gui._Handler, "wait", 0.05)
    GATE.clear()
    threading.Thread(target=gui.serve, kwargs={"open_browser": False, "client_factory": SlowClient},
                     daemon=True).start()
    while "server" not in holder:
        time.sleep(0.01)
    httpd = holder["server"]
    assert issubclass(httpd.RequestHandlerClass, http.server.BaseHTTPRequestHandler)
    yield f"http://127.0.0.1:{httpd.server_address[1]}", httpd.RequestHandlerClass.token
    GATE.set()
    httpd.shutdown()


def _open(url, data=None):
    with urllib.request.urlopen(url, data=data, timeout=10) as r:
        return r.geturl(), r.read().decode("utf-8"), r.headers


def _search(base, token, **fields):
    # `derivation` is the specified comparison: the fake study behind these tests measures two points per
    # set, which is all that comparison needs and too few for the integrated form that became the default
    # on 2026-10-06. These tests are about the interface, so they keep the derivation that the double can
    # feed; the default itself is checked in tests/test_integrated_wiring.py.
    form = {"species": f"{A}\n{B}", "only_entered": "1", "derivation": "replicate", **fields}
    return _open(f"{base}/run?token={token}", urllib.parse.urlencode(form).encode())


def _finished(base, token, **fields):
    """Search, let it finish, and return the page it ends on."""
    url, page, _ = _search(base, token, **fields)
    GATE.set()
    for _ in range(200):
        url, page, _ = _open(url)
        if "<progress" not in page:
            return page
        time.sleep(0.02)
    raise AssertionError("the search never finished")


def test_a_progress_bar_shows_while_data_are_fetched_and_the_page_updates_itself(server):
    base, token = server
    url, page, _ = _search(base, token)
    assert "job=" in url and "<progress" in page and "Searching" in page
    # the page reloads itself, without JavaScript, until the result is ready
    assert re.search(r'<meta http-equiv="refresh" content="1; url=/\?token=[^"]+&amp;job=', page)
    assert "<script" not in page
    GATE.set()
    for _ in range(200):
        _, page, _ = _open(url)
        if "<progress" not in page:
            break
        time.sleep(0.02)
    assert "interaction(s)" in page and 'http-equiv="refresh"' not in page


def test_the_output_is_on_the_same_page_below_the_advanced_settings(server):
    base, token = server
    page = _finished(base, token, metric="max")
    settings_end = page.index("</details>\n</form>")
    assert page.index('<section class="result"') > settings_end            # below the settings
    assert f">{A}\n{B}</textarea>" in page                                  # the species stay in the box
    assert '<option value="max" selected>' in page                          # and so do the settings


def test_three_outputs_download_with_a_format_menu_cytoscape_and_the_report(server):
    base, token = server
    page = _finished(base, token)
    outputs = page[page.index('<div class="bar outputs">'):]
    download = outputs.index("Download network")
    menu = outputs.index('<select name="format"')
    assert abs(menu - download) < 80                                        # the menu next to the button
    assert '<option value="json">JSON</option><option value="graphml">GraphML</option>' in outputs
    assert outputs.index("Send to Cytoscape") > menu
    assert outputs.index("<summary class=\"btn\">Report</summary>") > outputs.index("Send to Cytoscape")


def test_the_download_menu_gives_either_format(server):
    base, token = server
    _finished(base, token)
    _, as_json, headers = _open(f"{base}/download?token={token}&format=json")
    assert json.loads(as_json)["edges"] and "grownet_network.json" in headers["Content-Disposition"]
    _, as_graphml, headers = _open(f"{base}/download?token={token}&format=graphml")
    assert ET.fromstring(as_graphml).tag.endswith("graphml") and ".graphml" in headers["Content-Disposition"]


def test_send_to_cytoscape_sends_the_network_already_computed(server, monkeypatch):
    base, token = server
    _finished(base, token)
    sent = {}
    monkeypatch.setattr(gui, "send", lambda net, **kw: sent.update(edges=len(net.edges)) or {"suid": 9})
    _, page, _ = _open(f"{base}/cytoscape?token={token}", b"")
    # the page counts one interaction, and Cytoscape gets exactly that: one number (Karoline, 2026-10-03)
    assert "Sent to Cytoscape: network 9" in page and sent["edges"] == 1


def test_the_report_holds_the_comments_every_setting_and_the_version_and_downloads_as_text(server):
    base, token = server
    page = _finished(base, token, absence_threshold="2")
    _, text, headers = _open(f"{base}/report.txt?token={token}")
    assert headers["Content-Type"].startswith("text/plain") and "grownet_report.txt" in headers["Content-Disposition"]
    assert f"tool: grownet {__version__}" in text
    for label, flag, _ in SETTINGS.values():
        assert f"{label} ({flag.split()[0]}):" in text, label                # every setting, with its value
    assert "Absence threshold k (--absence-threshold): 2.0" in text
    assert "interactions:" in text and "pairs the data did not support" in text and "sources" in text
    # the page shows the same report inside the Report button
    assert gui.html.escape(text.splitlines()[1]) in page


def test_the_input_field_starts_empty_under_a_header_naming_the_options_and_a_row_of_examples():
    page = gui.render_form("tok")
    assert re.search(r'<textarea id="species" name="species" rows="\d+"></textarea>', page)   # empty
    assert "placeholder" not in page
    # Karoline (2026-09-28): "Genus to be mentioned in the title above the input box and a genus example
    # query in the sentence below"
    header = page.index('<label class="field" for="species">Species, strains, genera or NCBI taxon ids</label>')
    examples = page.index('<p class="examples">For example: ')
    assert header < examples < page.index("<textarea")            # a row below the header, above the box
    for example in gui.INPUT_EXAMPLES:                    # one species, one strain, one genus, one taxon id
        assert example in page[examples:page.index("<textarea")]
    assert "Bacteroides" in gui.INPUT_EXAMPLES
    assert ".examples {" in page and "font-size: .82rem" in page   # in a smaller font


def test_the_command_line_gives_everything_the_page_does(monkeypatch, tmp_path, capsys):
    """Every advanced setting has its option, and the page's three outputs (network in either format,
    Cytoscape, the report) are there, with the page's own report. `grownet derive --help` lists them."""
    from grownet.__main__ import build_parser, main
    derive = next(a for a in build_parser()._actions if a.dest == "cmd").choices["derive"]
    options = {o for action in derive._actions for o in action.option_strings}
    for key, (_, flag, _) in SETTINGS.items():
        assert key in ("studies",) or flag.split()[0] in options, key          # studies is the argument
    assert {"--format", "--out", "--to-cytoscape", "--report"} <= options
    help_text = derive.format_help()
    assert "examples:" in help_text and "--report FILE" in help_text and "a set " not in help_text

    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    sent = {}
    monkeypatch.setattr("grownet.cytoscape.send", lambda net, **kw: sent.update(n=len(net.edges)) or
                        {"suid": 3, "style": "grownet", "warning": ""})
    out, report = tmp_path / "net.graphml", tmp_path / "report.txt"
    # with k = 2 both arcs fall below the threshold, so --include-absent keeps them in what is written
    assert main(["derive", "--live", "--species", A, B, "--format", "graphml", "--out", str(out),
                 "--report", str(report), "--to-cytoscape", "--absence-threshold", "2",
                 "--include-absent", "--derivation", "replicate"]) == 0
    assert ET.fromstring(out.read_text(encoding="utf-8")).tag.endswith("graphml") and sent["n"] == 2
    text = report.read_text(encoding="utf-8")
    assert f"tool: grownet {__version__}" in text and "Absence threshold k (--absence-threshold): 2.0" in text
    # the report is the page's own, for the same search
    page = gui.run_query(FakeClient(), [A, B], {"absence_threshold": 2.0, "include_absent": True,
                                                "derivation": "replicate"})
    from grownet.report import report_text
    def without_times(t):                  # the two runs are seconds apart; the rest must be identical
        return [line for line in t.splitlines() if not line.startswith(("run:", "data: "))]
    assert without_times(text) == without_times(report_text(page))


def test_the_report_gives_the_run_time_the_tool_version_and_the_data_version(server):
    # Karoline, 2026-09-27: "Are the run date, tool version and data versions in the report?"
    base, token = server
    _finished(base, token)
    _, text, _ = _open(f"{base}/report.txt?token={token}")
    assert re.search(r"^run: \d{4}-\d\d-\d\d \d\d:\d\d:\d\d[+-]\d\d:\d\d$", text, re.M)
    assert f"tool: grownet {__version__}" in text
    assert "data version: mGrowthDB publishes no database version" in text
    assert "  SMGDB00000001: uploaded 2025-06-26, published 2025-06-29" in text     # each study's dates


def test_each_search_keeps_its_own_outputs(server):
    # two searches in two tabs: the first tab's download is still the first search's network
    base, token = server
    first = _finished(base, token)
    second = _finished(base, token, only_entered="")          # every partner: a different search
    job1 = re.search(r'name="job" value="([0-9a-f]+)"', first).group(1)
    job2 = re.search(r'name="job" value="([0-9a-f]+)"', second).group(1)
    assert job1 != job2 and f"/report.txt?token={token}&amp;job={job1}" in first
    _, report1, _ = _open(f"{base}/report.txt?token={token}&job={job1}")
    _, report2, _ = _open(f"{base}/report.txt?token={token}&job={job2}")
    assert "Only interactions between the species entered (--all-partners): on" in report1
    assert "Only interactions between the species entered (--all-partners): off" in report2


def test_the_page_and_the_command_line_start_from_the_same_defaults():
    # a setting whose default differs between the page and the command line gives two tools; each page
    # setting is mapped to its option here, so a new setting without a mapping fails too
    from grownet.__main__ import build_parser
    a = build_parser().parse_args(["derive", "--live", "--species", "x"])
    cli = {"metric": a.metric, "rate_method": a.rate_method, "rate_window": a.rate_window,
           "spike_factor": a.spike_factor, "capacity_max_fall": a.capacity_max_fall,
           "absence_threshold": a.absence_threshold,
           "include_low_quality": a.include_low_quality, "include_absent": a.include_absent,
           "correction": a.correction,
           "include_dropout": not a.no_dropout, "include_non_batch": a.include_non_batch,
           "conditions": " ".join(a.conditions),
           "exclude_studies": a.exclude_studies, "only_entered": not a.all_partners, "merge_arcs": a.merge_arcs,
           "min_studies": a.min_studies, "merge_genera": a.merge_genera, "no_growth_alpha": a.no_growth_alpha,
           "no_growth_factor": a.no_growth_factor, "max_adjusted_p": a.max_adjusted_p,
           "report_rates": a.report_rates, "steady_check": a.steady_check,
           "derivation": a.derivation}
    assert set(cli) == set(gui.DEFAULTS)
    assert {k: v for k, v in cli.items() if v != gui.DEFAULTS[k]} == {}


def test_all_on_the_command_line_needs_live_and_no_species(capsys):
    from grownet.__main__ import main
    assert main(["derive", "--all", "--fixture", "x.json"]) == 2
    assert "--all searches mGrowthDB, so it needs --live" in capsys.readouterr().err
    assert main(["derive", "--all", "--live", "--species", "Blautia"]) == 2
    assert "--all derives every study; leave out --species" in capsys.readouterr().err


def test_the_page_the_command_line_and_the_help_all_know_genera_and_all():
    # Karoline (2026-09-28): "please make sure that the GUI, CLI and help integrate the new options (...
    # CLI help documenting the new option; help page including the new advanced option and arc attribute)"
    from grownet import help as help_page
    from grownet.__main__ import build_parser
    derive = next(a for a in build_parser()._subparsers._actions if a.choices).choices["derive"].format_help()
    assert "--merge-genera" in derive and "--all" in derive and "--species Bacteroides" in derive
    page = help_page.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    assert "Merge to genus" in page                                     # the advanced option
    assert help_page._name("supporting_pairs") in page and help_page._name("merged_pairs") in page  # the arc fields
    assert "a genus (it stands for every species of it" in page and "The All button" in page
    form = gui.render_form("tok")
    assert 'name="merge_genera"' in form and 'name="all"' in form


def test_the_help_weighs_each_growth_measure():
    # Karoline (2026-09-28): "in the help, can you also describe briefly the advantages and disadvantages of
    # each growth curve characteristic?"
    from grownet import help as help_page
    page = help_page.render_help("tok", gui.DEFAULTS, gui.EXAMPLE)
    section = page[page.index('<h2 id="measures">'):page.index('<h2 id="example">')]
    for measure in ("auc", "max", "growth_rate"):                    # every measure the tool offers
        assert f"({measure}" in section
    assert section.count("<dd>For:") == len(gui.METRICS) and section.count("Against:") == len(gui.METRICS)


def test_the_readme_names_the_tool_grownet():
    # Karoline (2026-09-28): "readme in the repo still talks about crossfeed instead of grownet", and "The
    # README can have a subtitle or title extension that shows where the tool name comes from: Growth-curve
    # derived interaction networks." Then (2026-10-04): "the title would be more pretty when words only
    # start with lower case", and the name carries the wordmark's two parts in prose, as it does on the
    # page ("The README of the repo does not yet reflect the style change for grownet sentences").
    from pathlib import Path
    text = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
    assert text.startswith("# grownet: growth-curve derived interaction networks\n")
    assert "grow**net** turns" in text
    body = text.split("\n", 1)[1]
    prose_lines = [line for line in re.sub(r"```.*?```", "", body, flags=re.S).splitlines()
                   if not line.startswith("#")]
    for line in prose_lines:
        outside_code = re.sub(r"`[^`]*`|\(https?://[^)]*\)|https?://\S+", "", line)
        assert not re.search(r"(?<![\w/.*-])grownet(?![\w/.*-])", outside_code), line
    prose = re.sub(r"`[^`]*`|\(https?://[^)]*\)|https?://\S+|```.*?```", "", text, flags=re.S)
    # outside code and links, crossfeed appears only where the README explains the old name
    leftover = [line for line in prose.splitlines() if "crossfeed" in line]
    assert all("called crossfeed" in line or "crossfeed-bio" in line for line in leftover)


def test_help_and_back_after_a_search_keeps_the_result(monkeypatch):
    # Karoline (2026-09-28, audit step 8): "clicking help after a result was obtained and then coming back to
    # the main page causes a full loss of the result, which is problematic"
    import html as html_lib
    import threading
    import urllib.parse
    import urllib.request

    from test_gui import FakeClient
    handler = type("H", (gui._Handler,), {"token": "tok", "client_factory": staticmethod(FakeClient), "state": {},
                                          "wait": 5.0})
    server = gui._Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        form = urllib.parse.urlencode({"species": "Faecalibacterium prausnitzii\nBlautia hydrogenotrophica",
                                       "only_entered": "1"}).encode()
        with urllib.request.urlopen(f"{base}/run?token=tok", data=form, timeout=10) as r:
            result_page = r.read().decode("utf-8")
        assert "interaction(s)" in result_page
        for name in ("help", "legend", "about"):
            link = re.search(rf'href="(/{name}\?token=tok&amp;job=[0-9a-f]+)"', result_page)
            assert link, f"the {name} link does not carry the search"
            with urllib.request.urlopen(base + html_lib.unescape(link.group(1)), timeout=10) as r:
                page = r.read().decode("utf-8")
            back = re.search(r'href="(/\?token=tok&amp;job=[0-9a-f]+#result)">Back', page)
            assert back, f"{name}'s Back does not return to the search"
            # Karoline (2026-09-28): "a top button Back would help in the right upper corner of the help
            # page": a Back before the page's content (and one at its end), on Help, Legend and About alike
            top = page.index('<p class="bar backtop">')
            assert top < page.index("<main>") + 40 and page.count(">Back</a>") == 2
            # "When we click the grownet logo, we come back again to an empty page": the mark keeps the search
            mark = re.search(r'<a class="brand" href="([^"]+)"', page).group(1)
            assert "job=" in mark
            with urllib.request.urlopen(base + html_lib.unescape(back.group(1)), timeout=10) as r:
                assert "interaction(s)" in r.read().decode("utf-8")      # the result is still there
    finally:
        server.shutdown()


def test_the_help_page_offers_the_cytoscape_style_as_a_download():
    # Karoline (2026-09-28): "in the help, allow users to download the cytoscape style, so they don't have to
    # run cmdline to get it"
    import threading
    import urllib.request

    from test_gui import FakeClient
    handler = type("H", (gui._Handler,), {"token": "tok", "client_factory": staticmethod(FakeClient), "state": {}})
    server = gui._Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/help?token=tok", timeout=10) as r:
            page = r.read().decode("utf-8")
        assert page.count('href="/grownet_style.xml?token=tok"') == 2            # both Cytoscape answers
        with urllib.request.urlopen(f"{base}/grownet_style.xml?token=tok", timeout=10) as r:
            assert r.headers["Content-Disposition"] == 'attachment; filename="grownet_style.xml"'
            body = r.read().decode("utf-8")
        from grownet.cytoscape import style_xml
        assert body == style_xml()                                    # the same file `grownet style` writes
    finally:
        server.shutdown()


def test_the_result_table_says_sign_not_direction(server):
    """Karoline, 2026-10-03: "instead of Direction, use Sign, since direction is misleading (direction of
    the arc)". The arc's direction is the arrow from the source to the species it affects."""
    base, token = server
    page = _finished(base, token)
    header = re.search(r"<tr><th>source</th>.*?</tr>", page, re.S).group(0)
    assert "<th>sign</th>" in header and "direction" not in header


def test_a_number_that_was_not_computed_reads_as_missing_not_blank_or_zero(server):
    """Karoline, 2026-10-03: "if p & q-values were not computed, they are missing value (probably safer
    than empty); not 0". The fake study's obligate arc has no test and no ratio."""
    base, token = server
    _finished(base, token)
    _, as_json, _ = _open(f"{base}/download?token={token}&format=json")
    edges = json.loads(as_json)["edges"]
    for edge in edges:
        if edge.get("p_value") is None:        # missing, never zero
            assert edge["q_value"] is None and edge["significance"] is None
        else:
            assert edge["q_value"] is not None and edge["significance"] is not None
    # and the page says so in words rather than leaving the cell blank: an obligate arc has no test
    row = gui._arc_rows(*_untested_arc())
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
    mean, over_sd, q = cells[3], cells[4], cells[6]      # log2 mean, |mean| / sd, q
    assert "no ratio" in mean and "not computed" in over_sd and "not computed" in q
    assert all(cell.strip() for cell in (mean, over_sd, q))


def _untested_arc():
    """(network, edges) holding one obligate arc: no test, no ratio, nothing to put in those cells."""
    from grownet.mgrowthdb import records_to_network
    records = [{"source": "ncbi:1", "target": "ncbi:2", "source_name": "Alpha one", "target_name": "Beta two",
                "effect": "facilitation", "strength": None, "weight": None, "status": "present",
                "outcome": "obligate", "study_id": "S1"}]
    net = records_to_network(records)
    return net, net.edges


def test_the_file_holds_what_the_page_counts(server):
    """Karoline, 2026-10-03: "The arc number reported in Cytoscape is not identical to the arc number we
    see because of hidden arcs ... maybe do not export hidden arcs (in any network) and only report them
    in the results". So one number: the page, the downloads and Cytoscape agree."""
    base, token = server
    page = _finished(base, token)
    headline = int(re.search(r"<h2>(\d+) interaction\(s\)</h2>", page).group(1))
    _, as_json, _ = _open(f"{base}/download?token={token}&format=json")
    doc = json.loads(as_json)
    assert len(doc["edges"]) == headline
    assert not [e for e in doc["edges"] if e.get("status") == "absent"]
    assert doc["meta"]["filters"]["include_absent"] is False

    sent = {}
    monkeypatch_send = lambda net, **kw: sent.update(edges=len(net.edges)) or {"suid": 5}   # noqa: E731
    gui_send, gui.send = gui.send, monkeypatch_send
    try:
        _open(f"{base}/cytoscape?token={token}", b"")
    finally:
        gui.send = gui_send
    assert sent["edges"] == headline                      # Cytoscape counts what the page counts

    # the arcs below the threshold are still reported: on the page, and in the report with their number
    absent = int(re.search(r"(\d+) edge\(s\) below the absence threshold", page).group(1))
    assert absent and "left out of the network" in _open(f"{base}/report.txt?token={token}")[1]


def test_asking_for_the_absent_arcs_puts_them_in_the_file(server):
    base, token = server
    page = _finished(base, token, include_absent="1")
    headline = int(re.search(r"<h2>(\d+) interaction\(s\)</h2>", page).group(1))
    _, as_json, _ = _open(f"{base}/download?token={token}&format=json")
    doc = json.loads(as_json)
    assert len(doc["edges"]) > headline and [e for e in doc["edges"] if e["status"] == "absent"]
    assert doc["meta"]["filters"]["include_absent"] is True


# ---- the adjacency matrix, the growth rates and the gLV parameters (#108) -------------------------
#
# Karoline, 2026-10-03: "The next job is supporting another network export format: the adjacency matrix.
# In addition, grownet should be able to provide parameters for generalized Lotka-Volterra (gLV) simulation
# tools. I think this requires another input checkbox, next to the All button: report growth rates ...
# Growth rates, when enabled, should also be a separate downloadable output item. Then, in the Result
# section, we need another extra button to generate gLV parameters from the current run (when 'Report
# growth rates' was enabled)."

RATES = {"ncbi:853": {"name": A, "rate": 0.4, "unit": "1/h", "n": 4, "studies": ["SMGDB00000001"],
                      "per_study": {"SMGDB00000001": 0.4}, "other_units": [],
                      "method": "growth_rate:baranyi", "lag": 0.5, "capacity": 2.0,
                      "capacity_unit": "Cells/mL", "capacity_n": 4},
         "ncbi:53443": {"name": B, "rate": 0.2, "unit": "1/h", "n": 4, "studies": ["SMGDB00000001"],
                        "per_study": {"SMGDB00000001": 0.2}, "other_units": [],
                        "method": "growth_rate:baranyi", "lag": 0.0, "capacity": 1.5,
                        "capacity_unit": "Cells/mL", "capacity_n": 4}}


@pytest.fixture
def with_rates(monkeypatch):
    """The fake study's curves are two points long, too short for a fitted rate, so the rates themselves
    are given here; `tests/test_growth_rates.py` checks how they are computed."""
    monkeypatch.setattr(gui, "growth_rates", lambda *a, **kw: (dict(RATES), []))


def test_glv_mode_sits_next_to_all_and_sets_what_a_simulation_needs(server):
    """Karoline, 2026-10-04, after a first attempt put two checkboxes in the bar: "this is now quite
    complex. So how about moving both options back to advanced parameters, with their default settings,
    and instead introduce a button 'gLV mode' next to 'All', which will enable growth rate collection and
    disable drop-out communities? The GUI text can then be simplified somewhat."""
    base, token = server
    _, page, _ = _open(f"{base}/?token={token}")
    bar = page[page.index('<div class="bar">'):]
    bar = bar[:bar.index("</div>")]
    assert 'name="glv_mode" value="1"' in bar and ">gLV mode</button>" in bar
    assert 'class="switch"' in bar and 'aria-pressed="false"' in bar      # a switch, standing at off
    assert '<span class="track"><span class="knob">' in bar               # drawn, not described
    assert bar.index('name="glv_mode"') > bar.index('name="all"')        # next to All
    # the gLV example button sits between them: it fills the boxes and the settings for a package that
    # simulates and runs the search (Karoline, 2026-10-07)
    assert bar.index('name="all"') < bar.index('name="glv_example"') < bar.index('name="glv_mode"')
    assert not re.findall(r'<input[^>]*name="([^"]+)"', bar)             # and no checkboxes in the bar
    assert len(bar) < 720                                                # the text beside it stays short

    # pressing it ticks growth rates and unticks drop-out communities, in Advanced settings where they live
    def press(form):
        _, page, _ = _open(f"{base}/run?token={token}", urllib.parse.urlencode(form).encode())
        return page

    pressed = press({"species": A, "glv_mode": "1", "include_dropout": "1", "only_entered": "1"})
    settings = pressed[pressed.index("<details>"):]
    assert 'name="report_rates" value="1" checked' in settings
    assert 'name="include_dropout" value="1">' in settings               # off
    assert "gLV mode on: growth rates on, drop-out communities off" in pressed
    # and, since #119 turned the package into coefficients, the setting the conversion needs: L is the
    # log2 ratio of a growth rate. The rate method stays the reader's own (Karoline, 2026-10-06: the rate
    # from easylinear, the lag from Baranyi, "users can always enforce Baranyi in the advanced options")
    assert '<option value="growth_rate" selected>' in settings
    assert '<option value="baranyi" selected>' not in settings
    assert f">{A}</textarea>" in pressed                                 # and what was typed stays
    assert 'class="switch on"' in pressed and 'aria-pressed="true"' in pressed   # the switch is on

    # Karoline, 2026-10-04: "Do I click a 2nd time to switch it off?" Pressing it again restores both
    # defaults, and says so
    again = press({"species": A, "glv_mode": "1", "report_rates": "1", "only_entered": "1",
                   "metric": "growth_rate"})                            # what the page posts when on
    back = again[again.index("<details>"):]
    assert 'name="report_rates" value="1">' in back                      # off, its default
    assert 'name="include_dropout" value="1" checked' in back            # on, its default
    assert "gLV mode off" in again and 'class="switch on"' not in again
    assert 'class="switch"' in again and 'aria-pressed="false"' in again


def test_the_download_menu_offers_the_adjacency_matrix(server):
    base, token = server
    page = _finished(base, token)
    outputs = page[page.index('<div class="bar outputs">'):]
    assert '<option value="matrix">Adjacency matrix (CSV)</option>' in outputs
    _, table, headers = _open(f"{base}/download?token={token}&format=matrix")
    assert headers["Content-Type"].startswith("text/csv")
    rows = [line.split(",") for line in table.strip().splitlines()]
    names = rows[0][1:]
    assert names == sorted(names) and len(rows) == len(names) + 1     # square, one row per organism
    # the one interaction of the fake study is B facilitating A, so A's row holds it in B's column
    cell = rows[1 + names.index(A)][1 + names.index(B)]
    assert float(cell) > 0 and float(rows[1 + names.index(B)][1 + names.index(A)]) == 0


def test_without_report_growth_rates_there_are_no_rates_and_no_glv_button(server):
    base, token = server
    page = _finished(base, token)
    assert "Download the growth rates" not in page and "Get gLV parameters" not in page
    # and asking for the files anyway says what to do, rather than writing an empty one
    _, answer, _ = _open(f"{base}/rates.csv?token={token}")
    assert "tick Report growth rates" in answer


def test_the_growth_rates_are_their_own_download_and_bring_the_glv_control(server, with_rates):
    """Karoline, 2026-10-03: the growth rates are "a separate downloadable output item", and the gLV
    result is "one single drop-down menu ... where the user chooses whether to download or to send to R"."""
    base, token = server
    page = _finished(base, token, report_rates="1")
    outputs = page[page.index('<div class="bar outputs">'):]
    assert "Download the growth rates (.csv)" in outputs
    control = outputs[outputs.index(">Get gLV parameters<"):]
    control = control[:control.index("</form>")]
    assert '<option value="zip">Download (.zip)</option>' in control
    assert '<option value="r">Send to R</option>' in control
    assert control.count("<select") == 1              # one menu, not two buttons

    _, table, headers = _open(f"{base}/rates.csv?token={token}")
    assert headers["Content-Type"].startswith("text/csv")
    rows = [line.split(",") for line in table.strip().splitlines()]
    assert rows[0][:5] == ["organism", "growth_rate", "unit", "replicates", "studies"]
    # and the quantities a gLV coefficient is made of, beside them (#118), then the doubling time,
    # appended 2026-10-08 (#173, Karoline): no stage judges whether a rate is plausible, so the rate is
    # printed in the form a reader judges at a glance. Appended last, so a reader parsing by index is
    # unaffected
    assert rows[0][5:] == ["method", "lag", "lag_method", "carrying_capacity", "capacity_unit",
                           "capacity_curves", "capacity_curves_left_out", "capacity_fall_from_peak",
                           "capacity_medium", "capacity_source", "doubling_time"]
    assert [row[0] for row in rows[1:]] == sorted([A, B])
    assert dict(zip([r[0] for r in rows[1:]], [r[1] for r in rows[1:]], strict=True))[A] == "0.4"

    # the rates travel with the network too, so a downloaded network says what it was reported with
    _, as_json, _ = _open(f"{base}/download?token={token}&format=json")
    reported = json.loads(as_json)["meta"]["growth_rates"]
    assert reported["organisms"]["ncbi:853"]["rate"] == 0.4 and reported["without_a_rate"] == []
    assert "median over replicates and studies" in reported["rule"]


def test_the_glv_package_holds_fitted_coefficients_per_unit_and_the_rates(server, with_rates, monkeypatch):
    """#119: the package holds coefficients in 1/(time x abundance), one matrix per abundance unit, and
    no conventional number. The fake study's curves are two points long, so the rate itself is stubbed
    here (`tests/test_glv_coefficients.py` checks the arithmetic on hand-built numbers); what this test
    checks is the route, the files and the fitted diagonal, -r_i / K_i: A is 0.4 /h over 2.0 cells/mL and
    B is 0.2 over 1.5, so the diagonal is -0.2 and -0.1333."""
    import io
    import zipfile

    from grownet import rates as rate_module
    monkeypatch.setattr(rate_module, "easylinear", lambda times, values, *a, **kw: values[-1] / 10)
    monkeypatch.setattr(rate_module, "baranyi", lambda times, values, *a, **kw: values[-1] / 10)
    base, token = server
    _finished(base, token, report_rates="1", metric="growth_rate", rate_method="baranyi")
    with urllib.request.urlopen(f"{base}/glv.zip?token={token}", timeout=10) as r:
        assert r.headers["Content-Type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(r.read()))
    assert sorted(archive.namelist()) == ["README.txt", "growth_rates.csv",
                                          "interaction_matrix.Cells_per_mL.csv"]
    rows = [line.split(",") for line in
            archive.read("interaction_matrix.Cells_per_mL.csv").decode().strip().splitlines()]
    names = rows[0][1:]
    diagonal = {name: float(rows[1 + i][1 + i]) for i, name in enumerate(names)}
    assert diagonal[A] == pytest.approx(-0.4 / 2.0, rel=1e-3)
    assert diagonal[B] == pytest.approx(-0.2 / 1.5, rel=1e-3)
    assert A in archive.read("growth_rates.csv").decode()
    readme = archive.read("README.txt").decode()
    assert "A[i][j] is the effect of j on i" in readme
    assert "EVERY CELL IS A PER-CAPITA COEFFICIENT, in 1/(h x Cells/mL)" in readme
    assert "not a fitted" not in readme and "-1 by convention" not in readme


def test_the_page_says_which_setting_to_change_when_a_package_cannot_be_fitted(server, with_rates):
    """A coefficient needs the log2 ratio of a growth rate, so a search on the area under the curve
    cannot make one. The page says so instead of failing (#119)."""
    base, token = server
    _finished(base, token, report_rates="1")            # the default growth property is auc
    _, page, _ = _open(f"{base}/glv.zip?token={token}")
    assert "No gLV package:" in page and "growth_rate" in page and "gLV mode" in page


def test_the_command_line_writes_the_matrix_the_rates_and_the_glv_package(monkeypatch, tmp_path, capsys):
    """Karoline, 2026-10-03: "please make sure all of this is in the CLI and documented". So the page's
    new outputs have their options, they write the same files, and the report records the rates."""
    import io
    import zipfile

    from grownet import gui as gui_module
    from grownet.__main__ import build_parser, main
    derive = next(a for a in build_parser()._actions if a.dest == "cmd").choices["derive"]
    options = {o for action in derive._actions for o in action.option_strings}
    assert {"--report-rates", "--rates", "--glv"} <= options
    assert "matrix" in next(a for a in derive._actions if a.dest == "format").choices

    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    monkeypatch.setattr(gui_module, "growth_rates", lambda *a, **kw: (dict(RATES), []))
    table, rates_file, package, report = (tmp_path / n for n in
                                          ("m.csv", "rates.csv", "glv.zip", "report.txt"))
    # --glv needs the growth-rate comparison when the derivation is the specified comparison (#119),
    # and says so before anything is derived. The default derivation fits the coefficients themselves, so
    # it needs no growth property set, which is checked below (2026-10-06).
    assert main(["derive", "--live", "--species", A, B, "--report-rates", "--format", "matrix",
                 "--derivation", "replicate", "--out", str(table), "--glv", str(package)]) == 2
    assert "a coefficient needs the log2 ratio of a growth rate" in capsys.readouterr().err

    from grownet import rates as rate_module
    monkeypatch.setattr(rate_module, "easylinear", lambda times, values, *a, **kw: values[-1] / 10)
    monkeypatch.setattr(rate_module, "baranyi", lambda times, values, *a, **kw: values[-1] / 10)
    assert main(["derive", "--live", "--species", A, B, "--report-rates", "--format", "matrix",
                 "--derivation", "replicate", "--metric", "growth_rate", "--out", str(table),
                 "--rates", str(rates_file), "--glv", str(package), "--report", str(report)]) == 0

    rows = [line.split(",") for line in table.read_text(encoding="utf-8").strip().splitlines()]
    names = rows[0][1:]
    assert len(rows) == len(names) + 1
    assert float(rows[1 + names.index(A)][1 + names.index(B)]) > 0      # B facilitates A, as on the page
    assert rates_file.read_text(encoding="utf-8").splitlines()[0] == (
        "organism,growth_rate,unit,replicates,studies,method,lag,lag_method,carrying_capacity,"
        "capacity_unit,capacity_curves,capacity_curves_left_out,capacity_fall_from_peak,"
        "capacity_medium,capacity_source,doubling_time")
    with zipfile.ZipFile(io.BytesIO(package.read_bytes())) as archive:
        assert sorted(archive.namelist()) == ["README.txt", "growth_rates.csv",
                                              "interaction_matrix.Cells_per_mL.csv"]
        matrix_rows = archive.read("interaction_matrix.Cells_per_mL.csv").decode().strip().splitlines()
    fitted = {r.split(",")[0]: float(r.split(",")[1 + i]) for i, r in enumerate(matrix_rows[1:])}
    assert fitted[A] == pytest.approx(-0.4 / 2.0, rel=1e-3)     # the fitted diagonal, -r_i / K_i (#119)
    assert fitted[B] == pytest.approx(-0.2 / 1.5, rel=1e-3)
    text = report.read_text(encoding="utf-8")
    assert "Report growth rates (--report-rates): on" in text
    assert "growth rates (growth_rate:easylinear:5 in monoculture" in text
    assert f"  - {A}: 0.4 1/h, median of 4 monoculture replicate(s)" in text


def test_the_files_beside_the_network_need_the_rates_and_say_so(monkeypatch, tmp_path, capsys):
    from grownet.__main__ import main
    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    # the check runs before anything is derived, so no network is written and then refused its files
    assert main(["derive", "--live", "--species", A, "--glv", str(tmp_path / "glv.zip")]) == 2
    assert "--glv writes the growth rates of the run, so it needs --report-rates" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
    assert main(["derive", "SMGDB00000001", "--fixture", "x.json", "--report-rates"]) == 2
    assert "--report-rates reads the monoculture curves, so it needs --live" in capsys.readouterr().err


def test_the_glv_menu_sends_to_r_and_the_page_says_what_arrived(server, with_rates, monkeypatch):
    """Karoline, 2026-10-03: "one more result button to send gLV parameters to R", in "one single
    drop-down menu for gLV results where the user chooses whether to download or to send to R"."""
    from grownet import rates as rate_module
    from grownet import rbridge
    # in gLV mode, which is what a reader sending to R is in; the two-point curves need a stubbed rate
    monkeypatch.setattr(rate_module, "easylinear", lambda times, values, *a, **kw: values[-1] / 10)
    monkeypatch.setattr(rate_module, "baranyi", lambda times, values, *a, **kw: values[-1] / 10)
    base, token = server
    _finished(base, token, report_rates="1", metric="growth_rate", rate_method="baranyi")
    sent = {}

    def fake_send(payload, **kw):
        """What the R package answers, counted from the converted payload of #120."""
        sent.update(payload=payload)
        organisms = [name for block in payload["matrices"] for name in block["organisms"]]
        return {"received": True, "organisms": len(organisms),
                "growth_rates": len(payload["growth_rate_detail"]),
                "placeholders": len(payload["caveats"]["censored_cells"]), "without_a_rate": 0}

    monkeypatch.setattr(rbridge, "send", fake_send)
    _, page, _ = _open(f"{base}/glv?token={token}", b"to=r")
    assert "Sent to R: 2 organism(s), 2 growth rate(s)" in page
    assert sent["payload"]["format"] == "grownet.glv/v1"
    assert sent["payload"]["matrices"][0]["organisms"] == sorted([A, B])

    # the same menu downloads the zip, so one control covers both
    with urllib.request.urlopen(f"{base}/glv?token={token}", data=b"to=zip", timeout=10) as answer:
        assert answer.headers["Content-Type"] == "application/zip"
        assert answer.read()[:2] == b"PK"

    # and when no R session answers, the page says how to install the package and how to fetch instead
    def refuse(payload, **kw):
        raise rbridge.RError(rbridge.unreachable(8793, "Connection refused"))

    monkeypatch.setattr(rbridge, "send", refuse)
    _, page, _ = _open(f"{base}/glv?token={token}", b"to=r")
    assert "no R session is listening on port 8793" in page
    assert "install_github" in page and "grownet_glv(url)" in page


def test_r_can_fetch_the_same_parameters_from_the_page(server, with_rates, monkeypatch):
    """The other direction she asked for: when a port cannot be opened, R reads the payload from the page."""
    base, token = server
    from grownet import rates as rate_module
    monkeypatch.setattr(rate_module, "easylinear", lambda times, values, *a, **kw: values[-1] / 10)
    monkeypatch.setattr(rate_module, "baranyi", lambda times, values, *a, **kw: values[-1] / 10)
    page = _finished(base, token, report_rates="1", metric="growth_rate")
    assert "/glv.json?token=" in page                  # the address is printed under the control
    _, text, headers = _open(f"{base}/glv.json?token={token}")
    assert headers["Content-Type"].startswith("application/json")
    payload = json.loads(text)
    assert payload["format"] == "grownet.glv/v1"
    (block,) = payload["matrices"]
    assert block["organisms"] == sorted([A, B]) and block["unit"].startswith("1/(h x ")
    assert "readme" in payload and "caveats" in payload

    # and with a growth property that cannot give coefficients, this route says so too (#119, #120)
    _finished(base, token, report_rates="1")
    _, said, _ = _open(f"{base}/glv.json?token={token}")
    assert "No gLV parameters:" in said and "growth_rate" in said


# ---- the second input box: media, experiments or studies (#113) ----------------------------------
#
# Karoline, 2026-10-04: "I propose a second, optional, input field next to the first one with the taxa.
# Users can either specify names of media or a list of experiment identifiers there (so this last item can
# then be removed from the advanced options) ... The text above the second input field should also provide
# examples, like for the first input field."

def test_a_second_box_sits_beside_the_species_box_with_its_own_examples(server):
    base, token = server
    _, page, _ = _open(f"{base}/?token={token}")
    boxes = page[page.index('<div class="boxes">'):page.index("<div class=\"bar\">")]
    assert boxes.count("<textarea") == 2                     # the two boxes, side by side
    species = boxes[boxes.index('for="species"'):boxes.index('for="conditions"')]
    conditions = boxes[boxes.index('for="conditions"'):]
    assert "Media, experiments or studies (optional)" in conditions
    for part in (species, conditions):
        assert '<p class="examples">For example:' in part    # examples above both boxes
    from grownet.selection import EXAMPLES
    for example in EXAMPLES:
        assert example in conditions
    # and the study list is no longer an advanced setting, since the box took it over
    assert 'name="studies"' not in page
    assert "Only these studies" not in page


def test_what_is_typed_in_the_second_box_stays_there_and_in_the_report(server):
    base, token = server
    page = _finished(base, token, conditions="SMGDB00000001")
    assert ">SMGDB00000001</textarea>" in page
    _, report, _ = _open(f"{base}/report.txt?token={token}")
    assert "Media, experiments or studies (--conditions): SMGDB00000001" in report


def test_a_medium_that_matches_nothing_leaves_a_result_that_explains_itself(server):
    base, token = server
    page = _finished(base, token, conditions="a medium nobody used")
    assert "0 interaction(s)" in page or "no interactions" in page.lower()
    _, report, _ = _open(f"{base}/report.txt?token={token}")
    assert "no experiment of this study matches" in report


def test_drop_out_communities_stay_on_by_default_in_advanced_settings(server):
    """She kept the default: "I'd like to keep them by default." What gLV mode changes, it changes there,
    in sight, rather than behind the button."""
    base, token = server
    _, page, _ = _open(f"{base}/?token={token}")
    settings = page[page.index("<details>"):]
    assert 'name="include_dropout" value="1" checked' in settings
    assert "gLV mode unticks it" in settings                     # the setting says which button touches it


def test_glv_mode_on_the_command_line_sets_the_same_settings(capsys, monkeypatch, tmp_path):
    """The button has its flag, so the command line still does everything the page does."""
    from grownet import gui as gui_module
    from grownet.__main__ import build_parser, main
    derive = next(a for a in build_parser()._actions if a.dest == "cmd").choices["derive"]
    assert "--glv-mode" in {o for action in derive._actions for o in action.option_strings}

    monkeypatch.setattr("grownet.mgrowthdb.MGrowthDBClient", FakeClient)
    monkeypatch.setattr(gui_module, "growth_rates", lambda *a, **kw: (dict(RATES), []))
    captured = {}
    original = gui_module.run_query

    def remember(client, entries, settings=None, *args, **kw):
        captured["settings"] = settings
        return original(client, entries, settings, *args, **kw)

    monkeypatch.setattr(gui_module, "run_query", remember)
    out = tmp_path / "net.json"
    assert main(["derive", "--live", "--species", A, "--glv-mode", "--out", str(out)]) == 0
    assert "gLV mode: growth rates on, drop-out communities off" in capsys.readouterr().err
    assert captured["settings"]["report_rates"] is True
    assert captured["settings"]["include_dropout"] is False
    assert captured["settings"]["metric"] == "growth_rate"           # #119: L is a ratio of rates
    assert captured["settings"]["rate_method"] == "easylinear"      # hers, not the mode's
    # and the form a coefficient should be fitted by, which is what the mode is for (2026-10-10)
    assert captured["settings"]["derivation"] == "integrated"


def test_the_page_and_the_command_line_mean_the_same_by_glv_mode():
    """One definition of the mode, used by both."""
    from grownet.gui import DEFAULTS, glv_mode
    applied = glv_mode(dict(DEFAULTS))
    assert applied["report_rates"] is True and applied["include_dropout"] is False
    # the two Karoline named, the metric the coefficients of #119 need, and the derivation that fits a
    # coefficient rather than dividing a difference of two rates by one partner mean (2026-10-10);
    # nothing else moves
    assert {k: v for k, v in applied.items() if DEFAULTS[k] != v} == {
        "report_rates": True, "include_dropout": False, "metric": "growth_rate",
        "derivation": "integrated"}
    # and pressing it again puts every one of them back, the derivation included
    assert glv_mode(applied, on=False) == dict(DEFAULTS)


def test_the_name_is_never_styled_where_a_command_is_meant():
    """Karoline, 2026-10-04: "please make sure that command line calls in the help and README don't apply
    the grownet style (I found 1 case in the CLI description)". The name carries the wordmark in prose, so
    anything a reader would type has to stay plain, whether it sits in a code span or in a sentence."""
    import re
    from pathlib import Path

    from grownet import brand, gui
    mark = re.escape(brand.NAME_HTML)
    before = re.compile(r"(library\(|python -m |uvx |pip install |pipx install |-m )\s*$")
    after = re.compile(r"\s*(derive|gui|validate|schema|style)\b")
    pages = {"the help": gui.render_help("tok"), "the page": gui.render_form("tok"),
             "the about page": gui.render_about("tok"), "the legend page": gui.render_legend("tok")}
    for what, page in pages.items():
        for m in re.finditer(mark, page):
            around = page[max(0, m.start() - 70):m.end() + 50].replace("\n", " ")
            assert not before.search(page[max(0, m.start() - 20):m.start()]), f"{what}: {around}"
            assert not after.match(page[m.end():m.end() + 12]), f"{what}: {around}"

    # and the same in the README, where the name is written grow**net**
    text = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
    for m in re.finditer(re.escape("grow**net**"), text):
        around = text[max(0, m.start() - 70):m.end() + 50].replace("\n", " ")
        assert not before.search(text[max(0, m.start() - 20):m.start()]), around
        assert not after.match(text[m.end():m.end() + 12]), around
        assert text[max(0, m.start() - 1):m.start()] != "`", around      # never inside a code span


def test_marking_the_name_cannot_be_made_slow():
    """CodeQL, on the release pull request (2026-10-04): the two patterns behind the name styling were
    polynomial on a long run of "<" or of spaces. Nothing a user types reaches them unescaped, and now
    the patterns are bounded as well, so a pathological string is still linear."""
    import time

    from grownet import brand
    for text in ("<" * 40000, "<" + " " * 40000 + "p>grownet", "<p>" * 10000):
        started = time.perf_counter()
        brand.in_prose(text)
        assert time.perf_counter() - started < 1.0, f"slow on {text[:12]!r}..."
    # and it still marks a name in prose and leaves commands alone
    assert brand.in_prose("<p>grownet reads it.</p>") == f"<p>{brand.NAME_HTML} reads it.</p>"
    assert brand.in_prose("<code>grownet gui</code>") == "<code>grownet gui</code>"


def test_the_command_line_and_the_page_describe_the_same_settings():
    """Karoline, 2026-10-06, asking for a last check that "CLI and help are up to date with everything
    that happened". The mechanical halves are pinned elsewhere (every flag is explained, the defaults
    match); this pins the three that drifted during the 0.3.0 stack, where the flag's own help said less
    than the page's setting did."""
    from grownet import help as help_page
    from grownet.__main__ import build_parser

    derive = next(a for a in build_parser()._actions if a.dest == "cmd").choices["derive"]
    flag = {o: a.help for a in derive._actions for o in a.option_strings}

    # gLV mode sets three settings since #119, not two
    assert "growth rate" in flag["--glv-mode"] and "drop-out" in flag["--glv-mode"]
    # a rate travels with the lag and the capacity since #118
    assert "lag" in flag["--report-rates"] and "carrying capacity" in flag["--report-rates"]
    # and the lag is the Baranyi fit's whichever estimator produced the rate (her decision of 2026-10-06)
    assert "Baranyi" in flag["--rate-method"]
    # the two derivations are both named, on the flag and in the help's settings table
    assert "integrated" in flag["--derivation"] and "replicate" in flag["--derivation"]
    assert "integrated" in help_page.SETTINGS["derivation"][2]
