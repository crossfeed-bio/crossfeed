"""Karoline's interface requirements (#72), each checked against the running server, so none can be lost.

Her words, 2026-09-27: "there should be a progress bar to show something is going on while data are being
fetched and processed. Then, the output should be shown on the same page below the advanced settings, in
the form of three buttons: 1 to download the network, next to a menu where users can choose the network
format; 1 to send it to an open instance of Cytoscape and a last one with the detailed comments of the
search, which can also be downloaded as a text file that will also include all the settings."

And on #78: "The tool version should be also mentioned in the report accompanying each network."

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

from crossfeed import __version__, gui, interaction
from crossfeed.help import SETTINGS

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
