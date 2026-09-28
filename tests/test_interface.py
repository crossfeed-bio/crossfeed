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
    assert "Sent to Cytoscape: network 9" in page and sent["edges"] == 2


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
    assert main(["derive", "--live", "--species", A, B, "--format", "graphml", "--out", str(out),
                 "--report", str(report), "--to-cytoscape", "--absence-threshold", "2"]) == 0
    assert ET.fromstring(out.read_text(encoding="utf-8")).tag.endswith("graphml") and sent["n"] == 2
    text = report.read_text(encoding="utf-8")
    assert f"tool: grownet {__version__}" in text and "Absence threshold k (--absence-threshold): 2.0" in text
    # the report is the page's own, for the same search
    page = gui.run_query(FakeClient(), [A, B], {"absence_threshold": 2.0})
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
           "include_low_quality": a.include_low_quality, "correction": a.correction,
           "include_dropout": not a.no_dropout, "include_non_batch": a.include_non_batch, "studies": a.study,
           "exclude_studies": a.exclude_studies, "only_entered": not a.all_partners, "merge_arcs": a.merge_arcs,
           "min_studies": a.min_studies, "merge_genera": a.merge_genera, "no_growth_alpha": a.no_growth_alpha,
           "no_growth_factor": a.no_growth_factor}
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
