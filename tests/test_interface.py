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
    form = {"species": f"{A}\n{B}", "only_entered": "1", **fields}
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
                 "--include-absent"]) == 0
    assert ET.fromstring(out.read_text(encoding="utf-8")).tag.endswith("graphml") and sent["n"] == 2
    text = report.read_text(encoding="utf-8")
    assert f"tool: grownet {__version__}" in text and "Absence threshold k (--absence-threshold): 2.0" in text
    # the report is the page's own, for the same search
    page = gui.run_query(FakeClient(), [A, B], {"absence_threshold": 2.0, "include_absent": True})
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
           "spike_factor": a.spike_factor, "absence_threshold": a.absence_threshold,
           "include_low_quality": a.include_low_quality, "include_absent": a.include_absent,
           "correction": a.correction,
           "include_dropout": not a.no_dropout, "include_non_batch": a.include_non_batch, "studies": a.study,
           "exclude_studies": a.exclude_studies, "only_entered": not a.all_partners, "merge_arcs": a.merge_arcs,
           "min_studies": a.min_studies, "merge_genera": a.merge_genera, "no_growth_alpha": a.no_growth_alpha,
           "no_growth_factor": a.no_growth_factor, "max_adjusted_p": a.max_adjusted_p,
           "report_rates": a.report_rates}
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
    # derived interaction networks."
    from pathlib import Path
    text = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
    assert text.startswith("# grownet: Growth-curve derived interaction networks\n") and "**grownet** turns" in text
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
                      "per_study": {"SMGDB00000001": 0.4}, "other_units": []},
         "ncbi:53443": {"name": B, "rate": 0.2, "unit": "1/h", "n": 4, "studies": ["SMGDB00000001"],
                        "per_study": {"SMGDB00000001": 0.2}, "other_units": []}}


@pytest.fixture
def with_rates(monkeypatch):
    """The fake study's curves are two points long, too short for a fitted rate, so the rates themselves
    are given here; `tests/test_growth_rates.py` checks how they are computed."""
    monkeypatch.setattr(gui, "growth_rates", lambda *a, **kw: (dict(RATES), []))


def test_report_growth_rates_is_a_checkbox_next_to_the_all_button(server):
    base, token = server
    _, page, _ = _open(f"{base}/?token={token}")
    bar = page[page.index('<div class="bar">'):]
    bar = bar[:bar.index("</div>")]
    assert 'name="all"' in bar and 'name="report_rates"' in bar     # the same row as All
    assert bar.index('name="report_rates"') > bar.index('name="all"')
    assert "Report growth rates" in bar
    assert 'name="report_rates"' not in page[page.index("<details"):]   # not in Advanced settings


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
    assert "Download the growth rates" not in page and "Generate gLV parameters" not in page
    # and asking for the files anyway says what to do, rather than writing an empty one
    _, answer, _ = _open(f"{base}/rates.csv?token={token}")
    assert "tick Report growth rates" in answer


def test_the_growth_rates_are_their_own_download_and_bring_the_glv_button(server, with_rates):
    base, token = server
    page = _finished(base, token, report_rates="1")
    outputs = page[page.index('<div class="bar outputs">'):]
    assert "Download the growth rates (.csv)" in outputs
    assert "Generate gLV parameters (.zip)" in outputs

    _, table, headers = _open(f"{base}/rates.csv?token={token}")
    assert headers["Content-Type"].startswith("text/csv")
    rows = [line.split(",") for line in table.strip().splitlines()]
    assert rows[0] == ["organism", "growth_rate", "unit", "replicates", "studies"]
    assert [row[0] for row in rows[1:]] == sorted([A, B])
    assert dict(zip([r[0] for r in rows[1:]], [r[1] for r in rows[1:]], strict=True))[A] == "0.4"

    # the rates travel with the network too, so a downloaded network says what it was reported with
    _, as_json, _ = _open(f"{base}/download?token={token}&format=json")
    reported = json.loads(as_json)["meta"]["growth_rates"]
    assert reported["organisms"]["ncbi:853"]["rate"] == 0.4 and reported["without_a_rate"] == []
    assert "median over replicates and studies" in reported["rule"]


def test_the_glv_package_holds_a_matrix_with_minus_one_on_the_diagonal_and_the_rates(server, with_rates):
    import io
    import zipfile
    base, token = server
    _finished(base, token, report_rates="1")
    with urllib.request.urlopen(f"{base}/glv.zip?token={token}", timeout=10) as r:
        assert r.headers["Content-Type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(r.read()))
    assert sorted(archive.namelist()) == ["README.txt", "growth_rates.csv", "interaction_matrix.csv"]
    rows = [line.split(",") for line in archive.read("interaction_matrix.csv").decode().strip().splitlines()]
    names = rows[0][1:]
    assert [rows[1 + i][1 + i] for i in range(len(names))] == ["-1"] * len(names)
    assert A in archive.read("growth_rates.csv").decode()
    readme = archive.read("README.txt").decode()
    assert "A[i][j] is the effect of j on i" in readme and "not a fitted glv coefficient" in readme.lower()


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
    assert main(["derive", "--live", "--species", A, B, "--report-rates", "--format", "matrix",
                 "--out", str(table), "--rates", str(rates_file), "--glv", str(package),
                 "--report", str(report)]) == 0

    rows = [line.split(",") for line in table.read_text(encoding="utf-8").strip().splitlines()]
    names = rows[0][1:]
    assert len(rows) == len(names) + 1
    assert float(rows[1 + names.index(A)][1 + names.index(B)]) > 0      # B facilitates A, as on the page
    assert rates_file.read_text(encoding="utf-8").splitlines()[0] == (
        "organism,growth_rate,unit,replicates,studies")
    with zipfile.ZipFile(io.BytesIO(package.read_bytes())) as archive:
        assert sorted(archive.namelist()) == ["README.txt", "growth_rates.csv", "interaction_matrix.csv"]
        matrix_rows = archive.read("interaction_matrix.csv").decode().strip().splitlines()
    assert [r.split(",")[1 + i] for i, r in enumerate(matrix_rows[1:])] == ["-1", "-1"]
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
