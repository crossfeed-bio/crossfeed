"""The local page: rendering, the query behind it, and the server routes (a fake client, no live calls)."""
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

import pytest

from grownet import __version__, gui, interaction
from grownet.gui import DEFAULTS, parse_settings, render_form, render_result, run_query, serve
from grownet.mgrowthdb import MGrowthDBError


@pytest.fixture(autouse=True)
def _no_growth_rule_off(monkeypatch):
    """The fake study here predates the no-growth rule (#37): its curves check the page, not the rule."""
    monkeypatch.setattr(interaction, "NO_GROWTH_ALPHA", 0.0)
    monkeypatch.setattr(interaction, "NO_GROWTH_FACTOR", 0.0)

A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"


# Two-point curves over 10 h, so the area under the curve is 5 * (v0 + v1).
CURVES = {
    ("mono A", A): [(1, 1), (1, 1.4)],     # areas 10 and 12
    ("mono B", B): [(1, 1), (1, 1.4)],
    ("co", A): [(1, 3), (1, 3.8)],         # areas 20 and 24: B doubles A, 1.0 +/- 0.26 -> facilitation
    ("co", B): [(1, 1), (1, 1.4)],         # unchanged: mean 0 -> an edge with status absent
}
TAXA = {A: 853, B: 53443}


def _experiment(name, species):
    """One experiment with two bioreplicates, each carrying a per-strain context per species."""
    return {
        "id": "E_" + name, "name": name, "cultivationMode": "batch",
        "communityStrains": [{"name": sp, "NCBId": TAXA[sp]} for sp in species],
        "bioreplicates": [{"id": f"{name}/{i}", "name": f"{name}_{i}"} for i in (0, 1)],
    }


EXPERIMENTS = [_experiment("mono A", [A]), _experiment("mono B", [B]), _experiment("co", [A, B])]


class FakeClient:
    """One study whose experiments carry measured series, the way mGrowthDB serves them."""

    study_id = "SMGDB00000001"

    def _experiment_of(self, name):
        return next(e for e in EXPERIMENTS if e["name"] == name)

    def study_experiments(self, study_id):
        if study_id != self.study_id:
            raise MGrowthDBError(f"mGrowthDB returned HTTP 404 for {study_id}", status=404)
        return EXPERIMENTS

    def get_study(self, study_id):
        if study_id != self.study_id:
            raise MGrowthDBError(f"mGrowthDB returned HTTP 404 for {study_id}", status=404)
        return {"id": study_id, "name": "fake study", "url": "http://example/study",
                "uploadedAt": "2025-06-26T13:03:03+00:00", "publishedAt": "2025-06-29T10:25:52+00:00",
                "experiments": [{"id": e["id"]} for e in EXPERIMENTS]}

    def get_experiment(self, experiment_id):
        return next(e for e in EXPERIMENTS if e["id"] == experiment_id)

    def get_bioreplicate(self, bioreplicate_id):
        name, _, index = str(bioreplicate_id).partition("/")
        experiment = self._experiment_of(name)
        return {
            "id": bioreplicate_id, "name": f"{name}_{index}", "isAverage": False,
            "measurementTimeUnits": "h",
            "measurementContexts": [
                {"id": f"{name}/{index}/{strain['name']}", "techniqueType": "qpcr",
                 "techniqueUnits": "Cells/mL", "subject": {"type": "strain", "name": strain["name"]}}
                for strain in experiment["communityStrains"]
            ],
        }

    def get_measurement_series(self, context_id):
        name, index, species = str(context_id).split("/")
        v0, v1 = CURVES[(name, species)][int(index)]
        return [(0.0, float(v0), None), (10.0, float(v1), None)]

    def search(self, strain_ncbi_ids=None, metabolite_chebi_ids=None):
        return {"studies": [self.study_id]}


def _query(entries=("Faecalibacterium prausnitzii", "Blautia hydrogenotrophica"), **settings):
    # the fake study's second arc is absent, and a file holds absences only when asked (Karoline,
    # 2026-10-03). Tests about everything else keep both arcs in view; the default is checked in
    # test_the_file_holds_what_the_page_counts.
    #
    # `derivation` is the specified comparison here, which is no longer the shipped default (Karoline,
    # 2026-10-06). This double's curves are two measurements per set, which is all that comparison
    # needs and far too few to fit a row from a time course, so the integrated default would make every
    # test in this file assert an empty network. The shipped default is exercised end to end in
    # tests/test_integrated_wiring.py against simulated curves, and the page's own setting is checked
    # there too.
    settings = {"include_absent": True, "derivation": "replicate", **settings}
    return run_query(FakeClient(), list(entries), settings)


def test_species_names_reach_a_network():
    r = _query()
    assert r["taxon_ids"] == [853, 53443]
    assert r["studies"] == ["SMGDB00000001"]
    assert r["unresolved"] == [] and r["errors"] == []
    # B facilitates A (mean log2 1.0 +/- 0.26); A leaves B unchanged (mean 0: absent at any threshold)
    status = {(e.source, e.target): (e.effect, e.status) for e in r["network"].edges}
    # nodes are strains keyed by taxon id (#23): 853 is F. prausnitzii, 53443 B. hydrogenotrophica here
    assert status == {("ncbi:53443", "ncbi:853"): ("facilitation", "present"),
                      ("ncbi:853", "ncbi:53443"): ("neutral", "absent")}


def test_taxon_ids_work_as_input():
    assert _query(entries=("853", "53443"))["taxon_ids"] == [853, 53443]


def test_unknown_species_is_reported_without_results():
    r = _query(entries=("Escherichia coli",))
    assert r["unresolved"] == ["Escherichia coli"]
    assert r["studies"] == [] and r["network"].edges == []
    page = render_result("tok", r)
    assert "Not used:" in page and "no species or strain of this name in mGrowthDB" in page
    assert "No interactions" in page


def test_absent_edges_are_kept_and_shown_apart():
    r = _query()
    assert len(r["network"].edges) == 2 and r["absence"]["absent"] == 1
    page = render_result("tok", r)
    assert "1 interaction(s)" in page
    assert "1 edge(s) below the absence threshold (k = 1)" in page and "|mean| / sd" in page


def test_only_entered_species_filters_other_pairs():
    both = _query()
    one = _query(entries=("Faecalibacterium prausnitzii",))
    assert len(both["network"].edges) == 2
    assert one["network"].edges == []                   # the partner was not entered
    rest = _query(entries=("Faecalibacterium prausnitzii",), only_entered=False)
    assert len(rest["network"].edges) == 2


def test_a_study_that_fails_is_reported_not_raised():
    r = run_query(FakeClient(), ["853"], {"conditions": "SMGDB99999999", "derivation": "replicate"})
    assert r["errors"] and "SMGDB99999999" in r["errors"][0]
    assert r["network"].edges == []


def test_form_hides_every_setting_behind_one_button():
    page = render_form("tok")
    assert page.count("<details>") == 1 and "Advanced settings" in page
    head, _, tail = page.partition("<details>")
    # only the two boxes and the four buttons are visible; every setting sits behind the button
    # (Karoline, 2026-10-04, after a first attempt put two of them in the bar: "this is now quite complex.
    # So how about moving both options back to advanced parameters ... and instead introduce a button
    # 'gLV mode' next to 'All'")
    assert "<select" not in head
    assert not re.findall(r'<input[^>]*name="([^"]+)"', head)
    assert 'name="metric"' in tail and 'name="spike_factor"' in tail
    # the no-growth rule's two numbers are advanced settings, shown with the rule's own defaults (#37)
    assert 'name="no_growth_alpha"' in tail and 'name="no_growth_factor"' in tail
    assert 'name="include_low_quality"' in tail and 'name="include_neutral"' not in page
    # drop-out communities are included by default, and both gLV settings are advanced settings again
    assert 'name="include_dropout" value="1" checked' in tail
    assert 'name="report_rates" value="1">' in tail            # off by default
    assert "gLV mode" in head                                   # the button that sets them both


@pytest.mark.parametrize("form, expected", [
    # an unticked checkbox is simply absent from a post
    ({}, {**DEFAULTS, "only_entered": False, "include_dropout": False}),
    ({"metric": ["growth_rate"], "rate_method": ["baranyi"], "rate_window": ["7"], "spike_factor": ["50"],
      "conditions": [" S1 "], "only_entered": ["1"],
      "include_low_quality": ["1"], "include_dropout": ["1"], "no_growth_alpha": ["0.01"],
      "no_growth_factor": ["4"], "exclude_studies": [" SMGDB00000008 "], "merge_arcs": ["1"], "min_studies": ["2"],
      "merge_genera": ["1"]},
     {"metric": "growth_rate", "rate_method": "baranyi", "rate_window": 7, "spike_factor": 50.0, "conditions": "S1",
      "only_entered": True, "include_low_quality": True, "include_absent": False,
      "correction": "bh", "absence_threshold": 1.0, "include_dropout": True, "include_non_batch": False,
      "no_growth_alpha": 0.01, "no_growth_factor": 4.0, "exclude_studies": "SMGDB00000008", "merge_arcs": True,
      "min_studies": 2, "merge_genera": True, "max_adjusted_p": None, "report_rates": False,
          "steady_check": False, "derivation": "replicate",
          "capacity_max_fall": DEFAULTS["capacity_max_fall"]}),
    ({"metric": ["nonsense"], "spike_factor": ["not a number"]},
     {**DEFAULTS, "only_entered": False, "include_dropout": False}),
])
def test_settings_fall_back_to_defaults(form, expected):
    assert parse_settings(form) == expected


@pytest.mark.parametrize("form, expected", [
    ({"max_adjusted_p": ["0.1"]}, None),                          # a value without the tick: still off
    ({"filter_adjusted_p": ["1"], "max_adjusted_p": ["0.1"]}, 0.1),
    ({"filter_adjusted_p": ["1"], "max_adjusted_p": ["nonsense"]}, 0.05),
    ({"filter_adjusted_p": ["1"], "max_adjusted_p": ["5"]}, 0.05),  # not a probability
    ({"filter_adjusted_p": ["1"], "max_adjusted_p": ["0"]}, 0.05),
])
def test_the_adjusted_p_filter_is_off_unless_ticked_and_takes_a_probability(form, expected):
    # Karoline (2026-09-30): "an advanced option, by default off"; "Settable, 0.05 default"
    assert DEFAULTS["max_adjusted_p"] is None
    assert parse_settings(form)["max_adjusted_p"] == expected


def test_result_page_lists_arcs_and_download_links():
    page = render_result("tok", _query())
    assert "<table>" in page and "Faecalibacterium prausnitzii" in page
    # one download button with a format menu (#76)
    assert 'action="/download"' in page and '<option value="json">' in page and '<option value="graphml">' in page


def test_result_page_cites_every_study_with_its_license():
    page = render_result("tok", _query())
    assert "Sources" in page and "SMGDB00000001" in page and "fake study" in page
    assert "license: see study" in page and "supports 2 interaction(s)" in page


def test_result_page_says_the_method_is_provisional():
    page = render_result("tok", _query())
    assert "standard deviation" in page and "multiple testing" in page and "does not decide" in page
    # the replicate comparison refuses to compare across techniques, so nothing is flagged here
    assert "different techniques" not in page


# ---- the server itself ---------------------------------------------------------------------------

@pytest.fixture
def server():
    """The real handler on a free port, with the fake client; yields (url, token)."""
    import http.server

    import grownet.gui as gui

    holder = {}
    original = gui._Server

    class Capture(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            holder["server"] = self

    gui._Server = Capture
    thread = threading.Thread(target=serve, kwargs={"open_browser": False, "client_factory": FakeClient},
                              daemon=True)
    thread.start()
    while "server" not in holder:
        time.sleep(0.01)
    gui._Server = original
    httpd = holder["server"]
    handler = httpd.RequestHandlerClass
    assert issubclass(handler, http.server.BaseHTTPRequestHandler)
    yield f"http://127.0.0.1:{httpd.server_address[1]}", handler.token
    httpd.shutdown()


def visible(page: str) -> str:
    """The page as a reader sees it: the name carries markup in prose, so assertions on sentences use this."""
    return re.sub(r"<[^>]+>", "", page)


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8")


def test_server_serves_the_form_and_runs_a_search(server):
    base, token = server
    assert "Advanced settings" in _get(f"{base}/?token={token}")
    data = urllib.parse.urlencode({"species": "Faecalibacterium prausnitzii\nBlautia hydrogenotrophica",
                                   "metric": "growthRate", "deadband": "0.25", "only_entered": "1",
                                   "derivation": "replicate"})
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data.encode(), timeout=10) as r:
        page = r.read().decode("utf-8")
    assert "interaction(s)" in page and "facilitation" in page
    doc = json.loads(_get(f"{base}/download.json?token={token}"))
    # the file holds what the page counts: the absent arc is left out and reported (Karoline, 2026-10-03)
    assert [e["status"] for e in doc["edges"]] == ["present"]
    assert doc["meta"]["absence"]["k"] == 1.0 and doc["meta"]["statistics"]["tests"] == 2
    assert ET.fromstring(_get(f"{base}/download.graphml?token={token}")) is not None


def test_server_refuses_a_request_without_the_token(server):
    base, _ = server
    for url in (f"{base}/", f"{base}/download.json?token=wrong"):
        with pytest.raises(urllib.error.HTTPError) as e:
            _get(url)
        assert e.value.code == 403


def test_server_asks_for_a_species_when_none_given(server):
    base, token = server
    data = urllib.parse.urlencode({"species": "  "}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10) as r:
        assert "Type at least one species" in r.read().decode("utf-8")


def test_a_port_in_use_gives_a_plain_message_not_a_traceback():
    import socket

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        with pytest.raises(SystemExit, match=f"cannot use port {port}"):
            serve(port=port, open_browser=False)


def test_the_legend_is_reachable_from_the_page_and_needs_the_token(server):
    base, token = server
    assert 'href="/legend?token=tok"' in render_form("tok")
    assert 'href="/legend?token=tok"' in render_result("tok", _query())
    assert "Interaction network legend" in _get(f"{base}/legend?token={token}")
    with pytest.raises(urllib.error.HTTPError) as bad:
        _get(f"{base}/legend?token=wrong")
    assert bad.value.code == 403


def test_the_example_button_fills_the_box_with_species_that_work(server):
    base, token = server
    data = urllib.parse.urlencode({"species": "", "example": "1"}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10) as r:
        page = r.read().decode("utf-8")
    for name in gui.EXAMPLE:
        assert name in page
    assert "<textarea" in page and "interaction(s)" not in page      # the form, not a search

    # and what the button fills in is what a search takes: the fake study holds A and B under other
    # names, so the mechanism is checked with those (the real pair is checked live, see the description)
    filled = urllib.parse.urlencode({"species": f"{A}\n{B}", "only_entered": "1"}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=filled, timeout=10) as r:
        assert "interaction(s)" in r.read().decode("utf-8")


def test_the_example_puts_every_setting_back_to_its_default(server):
    """The Example shows what the tool does with nothing changed, so it cannot inherit a mode.

    It used to carry the posted settings through, and the two buttons beside it set some: after gLV mode
    the example ran with drop-out communities off, and after the gLV example with that example's study
    still in the second box. Either gave an empty network and the page said nothing about why
    (Karoline, 2026-10-09).
    """
    base, token = server
    pressed = urllib.parse.urlencode({
        "species": "", "example": "1",
        # what gLV mode leaves behind, and what the gLV example leaves in the second box
        "report_rates": "1", "metric": "growth_rate", "conditions": "SMGDB00000002",
        # and an ordinary setting a user may have changed
        "absence_threshold": "3",
    }).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=pressed, timeout=10) as r:
        page = r.read().decode("utf-8")

    assert 'aria-pressed="false"' in page                      # gLV mode off
    assert "SMGDB00000002" not in page                         # the second box is empty again
    assert 'name="absence_threshold" type="text" size="6" value="1.0"' in page   # not the 3 posted
    assert '<option value="auc" selected' in page              # the default growth property
    assert "checked" in page.split('name="include_dropout"')[1][:90]   # drop-out communities back on
    for name in gui.EXAMPLE:
        assert name in page


def test_the_about_button_names_the_builders_as_agreed_and_links_the_repository(server):
    base, token = server
    assert f'href="/about?token={token}"' in _get(f"{base}/help?token={token}")    # on every page
    page = _get(f"{base}/about?token={token}")
    # Craig's agreed wording on #80, word for word
    # the name carries its own markup in prose (brand.in_prose), so the sentence is read as a reader sees it
    assert ("grownet was built by Karoline Faust (KU Leuven) and Craig Heilmann (Syntropa), working through "
            "their AI coding agents (Claude).") in visible(page)
    assert '<a href="https://github.com/crossfeed-bio/crossfeed">' in page and f"Version {__version__}" in page
    with pytest.raises(urllib.error.HTTPError) as bad:
        _get(f"{base}/about?token=wrong")
    assert bad.value.code == 403


def test_the_help_button_opens_a_help_page_behind_the_token(server):
    base, token = server
    assert f'href="/help?token={token}"' in _get(f"{base}/?token={token}")
    page = _get(f"{base}/help?token={token}")
    assert '<h2 class="page">Help ' in page and "Advanced settings" in page
    assert f'href="/legend?token={token}"' in page                   # the legend is reachable from help
    for name in gui.EXAMPLE:
        assert name in page
    with pytest.raises(urllib.error.HTTPError) as bad:
        _get(f"{base}/help?token=wrong")
    assert bad.value.code == 403


def test_a_species_entered_under_its_new_name_still_matches_the_study_that_uses_the_old_one():
    # taxon 411483 is "Faecalibacterium prausnitzii A2-165" in SMGDB00000004 and "Faecalibacterium
    # duncaniae A2-165" in others. Matching the entered name against the study's name dropped every edge
    # (#73); the taxon id is what holds across the renaming.
    index = {"faecalibacterium duncaniae": {853: "Faecalibacterium duncaniae A2-165"},
             "blautia hydrogenotrophica": {53443: B}}
    r = run_query(FakeClient(), ["Faecalibacterium duncaniae", "Blautia hydrogenotrophica"],
                  {"only_entered": True, "include_absent": True, "derivation": "replicate"}, index=index)
    assert r["taxon_ids"] == [853, 53443]
    assert len(r["network"].edges) == 2          # the study names the strain prausnitzii, the ids agree


def test_the_send_to_cytoscape_button_uses_the_network_already_computed(server, monkeypatch):
    base, token = server
    data = urllib.parse.urlencode({"species": "Faecalibacterium prausnitzii\nBlautia hydrogenotrophica",
                                   "only_entered": "1", "derivation": "replicate"}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10) as r:
        assert "Send to Cytoscape" in r.read().decode("utf-8")

    sent = {}

    def fake_send(net, **kwargs):
        sent["edges"] = len(net.edges)
        return {"suid": 7, "style": "grownet", "url": "http://127.0.0.1:1234/v1/networks/7"}

    monkeypatch.setattr(gui, "send", fake_send)
    with urllib.request.urlopen(f"{base}/cytoscape?token={token}", data=b"", timeout=10) as r:
        page = r.read().decode("utf-8")
    # one arc: the page counts one interaction, and Cytoscape gets exactly that (Karoline, 2026-10-03)
    assert "Sent to Cytoscape: network 7" in page and sent["edges"] == 1


def test_cytoscape_not_running_is_explained_on_the_page(server, monkeypatch):
    base, token = server
    data = urllib.parse.urlencode({"species": "Faecalibacterium prausnitzii", "only_entered": ""}).encode()
    urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10).read()

    def refuse(net, **kwargs):
        raise gui.CytoscapeError("could not reach Cytoscape on port 1234 (Connection refused). Start it")

    monkeypatch.setattr(gui, "send", refuse)
    with urllib.request.urlopen(f"{base}/cytoscape?token={token}", data=b"", timeout=10) as r:
        page = r.read().decode("utf-8")
    assert "could not reach Cytoscape on port 1234" in page and "Traceback" not in page


def test_the_page_carries_the_mark_and_a_favicon(server):
    base, token = server
    page = _get(f"{base}/?token={token}")
    assert 'rel="icon" href="data:image/svg+xml;utf8,' in page      # no extra request, no packaged file
    assert page.count("<svg") >= 1 and "aria-label=\"grownet\"" in page


def test_the_species_list_is_built_once_per_session(server, monkeypatch):
    # building the index reads every study in mGrowthDB (about 40 s live); a second search reuses it
    calls = []
    original = gui.species_index
    monkeypatch.setattr(gui, "species_index", lambda client, **kw: calls.append(1) or original(client, **kw))
    base, token = server
    for _ in range(2):
        data = urllib.parse.urlencode({"species": f"{A}\n{B}", "only_entered": "1"}).encode()
        with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10) as r:
            assert "interaction(s)" in r.read().decode("utf-8")
    assert len(calls) == 1


def test_an_empty_result_names_the_step_that_found_nothing():
    # a name mGrowthDB does not hold: the page says so, instead of the explanation about study designs
    unknown = render_result("tok", _query(entries=("Escherichia coli",)))
    assert "None of the entries could be used" in unknown and "drop-out designs" not in unknown
    assert "Download network" not in unknown and "Send to Cytoscape" not in unknown   # nothing to send
    assert ">Report</summary>" in unknown and "#empty" in unknown                     # but the why is there
    r = _query()
    r["studies"], r["network"].edges = [], []
    assert "no study grows them" in render_result("tok", r)


def test_an_excluded_study_is_never_searched():
    # the fake search finds SMGDB00000001; excluding it leaves nothing to derive, found or named
    assert _query()["studies"] == ["SMGDB00000001"]
    assert _query(exclude_studies="smgdb00000001")["studies"] == []
    named = _query(studies="SMGDB00000001", exclude_studies="SMGDB00000001, SMGDB00000009")
    assert named["studies"] == [] and named["network"].edges == []
    assert 'name="exclude_studies"' in render_form("tok") and 'value=""' in render_form("tok")


def test_the_settings_say_what_is_absent_and_what_the_replicates_are():
    # Karoline, 2026-09-27: "absence of what?", and "a set" was not explained
    page = render_form("tok")
    assert "an interaction counts as absent (the species do not affect each other)" in page
    assert "the replicate\n  growth curves of that species in one culture condition" in page
    assert "a set " not in page


def test_an_empty_result_caused_by_a_setting_names_the_setting():
    excluded = render_result("tok", _query(exclude_studies="SMGDB00000001"))
    assert "The only studies holding these species are in Exclude these studies (SMGDB00000001)" in excluded
    partners = render_result("tok", _query(entries=("Faecalibacterium prausnitzii",)))
    assert "involves a species you did not enter" in partners and "untick Only interactions" in partners
    typo = render_result("tok", _query(entries=("Blautia hydrogenotrophca",)))
    assert "Did you mean: Blautia hydrogenotrophica?" in typo


def test_a_strain_is_named_by_its_current_name():
    # taxon 853 is "Faecalibacterium prausnitzii A2-165" in the fake study; a later study calls it duncaniae,
    # so the node and the resolved list use that name, while the old name still finds it (#24)
    from grownet.taxonomy import SpeciesIndex
    index = SpeciesIndex({"faecalibacterium prausnitzii": {853: A}, "blautia hydrogenotrophica": {53443: B}},
                         current={853: "Faecalibacterium duncaniae A2-165"})
    r = run_query(FakeClient(), ["Faecalibacterium prausnitzii", "Blautia hydrogenotrophica"],
                  {"include_absent": True, "derivation": "replicate"}, index=index)
    node = r["network"].nodes["ncbi:853"]
    assert (node.name, node.species) == ("Faecalibacterium duncaniae A2-165", "faecalibacterium duncaniae")
    assert r["resolved"][0] == ("Faecalibacterium prausnitzii", {853: "Faecalibacterium duncaniae A2-165"})
    assert len(r["network"].edges) == 2



def test_a_node_keyed_by_name_keeps_its_own_name_when_its_taxon_id_is_shared():
    # Audit 2026-09-28: SMGDB00000008 gives Lachnoclostridium clostridioforme 2_1_49FAA and L. symbiosum
    # WAL-14673 the same taxon id, 1506553. The derivation keys both nodes by name; renaming by the id's
    # latest name turned the symbiosum node into a second "clostridioforme", name and species key alike.
    from grownet.gui import _current_names
    from grownet.model import InteractionNetwork, Node
    net = InteractionNetwork()
    net.add_node(Node("lachnoclostridium symbiosum", name="Lachnoclostridium symbiosum WAL-14673",
                      taxon_id="1506553", species="lachnoclostridium symbiosum", identity="name"))
    net.add_node(Node("ncbi:853", name=A, taxon_id="853", species="faecalibacterium prausnitzii", identity="ncbi"))
    _current_names(net, {1506553: "Lachnoclostridium clostridioforme 2_1_49FAA",
                         853: "Faecalibacterium duncaniae A2-165"})
    kept = net.nodes["lachnoclostridium symbiosum"]
    assert (kept.name, kept.species) == ("Lachnoclostridium symbiosum WAL-14673", "lachnoclostridium symbiosum")
    assert net.nodes["ncbi:853"].name == "Faecalibacterium duncaniae A2-165"      # a taxon-keyed node still is

# ---- All, a genus entered, and the level genus arcs count at (Karoline 2026-09-28) ------------------

def test_all_ignores_the_box_and_derives_every_study_with_every_partner():
    r = run_query(FakeClient(), ["whatever is typed"],
                  {"derivation": "replicate", "only_entered": True}, all_studies=True)
    assert r["all"] and r["studies"] == ["SMGDB00000001"] and r["resolved"] == [] and r["unresolved"] == []
    assert r["network"].meta["query"] == "all" and r["network"].edges        # the study's arcs, every partner
    page = render_result("tok", r)
    assert "<h2>All of mGrowthDB</h2>" in page and "1 studies" in page


def test_all_still_leaves_out_the_excluded_studies_and_says_so():
    r = run_query(FakeClient(), [], {"derivation": "replicate", "exclude_studies": "SMGDB00000001"}, all_studies=True)
    assert r["studies"] == [] and "Exclude these studies" in render_result("tok", r)


def test_the_all_button_sits_next_to_example_with_its_explainer(server):
    base, token = server
    form = _get(f"{base}/?token={token}")
    assert '<button type="submit" name="example" value="1">Example</button>\n<button type="submit" name="all"' in form
    assert "All derives every study, ignoring the boxes" in form
    # and the gLV example button beside them, which fills the boxes and the settings for a package that
    # simulates and runs the search (Karoline, 2026-10-07)
    assert 'name="glv_example" value="1">gLV example</button>' in form
    assert "gLV example fills" in form
    with urllib.request.urlopen(f"{base}/run?token={token}", data=b"all=1&species=", timeout=10) as r:
        page = r.read().decode("utf-8")
    assert "All of mGrowthDB" in page or "Searching" in page             # a quick fake search, or its progress


def test_a_genus_entered_brings_in_all_its_species_and_is_shown_as_a_genus():
    r = _query(entries=("Faecalibacterium", "Blautia"))
    assert r["genera"] == {"Faecalibacterium": ["Faecalibacterium prausnitzii"],
                           "Blautia": ["Blautia hydrogenotrophica"]}
    assert r["taxon_ids"] == [853, 53443] and r["network"].edges             # both genera entered: the arc stays
    assert "Blautia (genus): Blautia hydrogenotrophica" in render_result("tok", r)


def test_genus_arcs_count_strain_pairs_only_when_every_entry_is_a_taxon_id():
    assert gui.support_level(["853", " txid53443 "]) == "strain"
    assert gui.support_level(["853", "Blautia hydrogenotrophica"]) == "species"
    assert gui.support_level(["Faecalibacterium prausnitzii A2-165"]) == "species"   # a name: the whole species
    assert gui.support_level([]) == "species"                                        # All


def test_merge_to_genus_from_the_page_gives_genus_nodes():
    r = _query(merge_genera=True)
    assert set(r["network"].nodes) == {"Faecalibacterium", "Blautia"}
    assert all(e.supporting_pairs == 1 for e in r["network"].edges)


def test_average_replicates_are_one_line_per_experiment_in_what_a_reader_sees():
    # Karoline (2026-09-28): 555 of all of mGrowthDB's 1972 skip lines were average replicates, one each
    from grownet.adapter import AVERAGE, condensed
    skipped = [("E1: Average(E1)", AVERAGE), ("E1: r1", "a spike"), ("E1: Average 2", AVERAGE), ("E2: avg", AVERAGE)]
    assert condensed(skipped) == [("E1", f"2 average replicate(s) left out ({AVERAGE})"), ("E1: r1", "a spike"),
                                  ("E2", f"1 average replicate(s) left out ({AVERAGE})")]


def test_only_the_latest_searches_are_kept_and_a_running_one_never_goes():
    # code review of 2026-09-28: every search stayed in memory for the life of the page
    jobs = {f"j{i}": {"status": "done"} for i in range(25)}
    jobs["j0"]["status"] = "running"
    gui.prune_jobs(jobs, keep=20)
    assert "j0" in jobs and "j1" not in jobs and "j24" in jobs and len(jobs) == 21
def test_an_unreachable_mgrowthdb_is_reported_not_read_as_an_empty_database():
    # audit step 7 (2026-09-28): with nothing listening, the species list came back empty and the page
    # said "no species or strain of this name in mGrowthDB"; a missing study (404) still ends the crawl
    from grownet.mgrowthdb import MGrowthDBClient
    from grownet.taxonomy import species_index
    down = MGrowthDBClient(base_url="http://127.0.0.1:9/api/v1", retries=1, timeout=2)
    with pytest.raises(MGrowthDBError, match="mGrowthDB could not be read"):
        species_index(down)
    assert species_index(FakeClient()).studies == ["SMGDB00000001"]     # 404s after it end the crawl


def test_a_growth_curve_that_fails_to_download_makes_the_result_incomplete():
    # audit step 7: a series that mGrowthDB fails to deliver after the retries was only one line among the
    # pairs the data did not support; the search now says at the top that its result is incomplete
    class Flaky(FakeClient):
        def get_measurement_series(self, context_id):
            if context_id.startswith("co/0/"):
                raise MGrowthDBError("mGrowthDB returned HTTP 500 for a series (server error)", status=500)
            return super().get_measurement_series(context_id)
    r = run_query(Flaky(), ["Faecalibacterium prausnitzii", "Blautia hydrogenotrophica"], {})
    assert any("could not be read from mGrowthDB" in e and "incomplete" in e for e in r["errors"])


# ---- the All network derived once a day in the grownet repository (#96) ------------------------------

def test_the_daily_all_network_is_used_when_fresh_and_the_settings_are_the_defaults(monkeypatch):
    # Karoline (2026-09-28): "For the All network, could we build it, save it in grownet's github, serve from
    # there if less than a day old", and "let's serve the All network from the grownet repository"
    import datetime
    import io

    from grownet import published
    # the defaults on both sides, which is what `published.usable` asks: the double's curves give the
    # default derivation nothing, so this network is empty, and what the test checks is the serving rule
    live = run_query(FakeClient(), [], {}, all_studies=True, published=False)
    payload = json.loads(json.dumps(published.to_payload(live)))          # as the release asset holds it
    derived = datetime.datetime.fromisoformat(payload["network"]["meta"]["derived_at"])

    def opener(url, timeout):
        assert url == published.URL
        return io.BytesIO(json.dumps(payload).encode())
    in_23_hours = published.fetch_from(opener, now=derived + datetime.timedelta(hours=23))
    assert in_23_hours["network"].edges == live["network"].edges and in_23_hours["skipped"] == live["skipped"]
    assert published.fetch_from(opener, now=derived + datetime.timedelta(hours=25)) is None   # a day: live
    monkeypatch.setattr(published, "fetch",
                        lambda: published.fetch_from(opener, now=derived + datetime.timedelta(hours=1)))
    r = run_query(FakeClient(), [], {}, all_studies=True)
    assert r["published"] == payload["network"]["meta"]["derived_at"] and r["all"]
    assert "derived once a day" in render_result("tok", r)

    # the published file says how to read it, as the page does (Craig's agent, #96), in JSON and GraphML.
    # This half is read from a served network that has arcs, which the double's two-point curves give the
    # specified comparison: `usable` only serves a query at the defaults, and the default derivation fits
    # a time course, so the two halves of this rule are checked on their own terms (2026-10-06).
    from grownet.derive import PROVISIONAL
    from grownet.export import to_graphml
    with_arcs = run_query(FakeClient(), [], {"derivation": "replicate"}, all_studies=True, published=False)
    served = published.fetch_from(
        lambda url, timeout: io.BytesIO(json.dumps(published.to_payload(with_arcs)).encode()),
        now=datetime.datetime.fromisoformat(
            published.to_payload(with_arcs)["network"]["meta"]["derived_at"]) + datetime.timedelta(hours=1))
    assert served["network"].edges
    # escaped on the page: the text comes from a file downloaded from GitHub
    assert served["network"].meta["provisional"] == PROVISIONAL
    # the sentence names the tool, which carries markup in prose, so it is read as a reader sees it
    served["all"] = True
    assert PROVISIONAL in html.unescape(visible(render_result("tok", {**with_arcs, **served})))
    assert "g_provisional" in to_graphml(served["network"])
    assert "few replicates" in to_graphml(served["network"])
    # any other setting derives it live, and so does the command line's --no-published
    assert "published" not in run_query(FakeClient(), [],
                                        {"derivation": "replicate", "absence_threshold": 2.0},
                                        all_studies=True)
    assert "published" not in run_query(FakeClient(), [], {"derivation": "replicate"},
                                        all_studies=True, published=False)


def test_a_published_file_of_another_format_or_schema_is_not_used():
    import datetime

    from grownet import published
    from grownet.model import SCHEMA
    now = datetime.datetime(2026, 9, 28, 12, tzinfo=datetime.timezone.utc)
    good = {"format": published.FORMAT, "network": {"schema": SCHEMA,
                                                     "meta": {"derived_at": "2026-09-28T10:00:00+00:00"}}}
    assert published.fresh(good, now)
    assert not published.fresh({**good, "format": "grownet.all_result/v0"}, now)
    assert not published.fresh({**good, "network": {**good["network"], "schema": "other/v1"}}, now)
    # a file published before the schema id became grownet's (#102) is derived again, not read
    assert not published.fresh({**good, "network": {**good["network"],
                                                    "schema": "crossfeed.interaction_network/v0"}}, now)
    assert not published.fresh({**good, "network": {**good["network"], "meta": {}}}, now)
    # the id moved to v2 with the optional arc fields of #118, and this is the half of that which this
    # copy can test: a daily network written by 0.2.x is read as a format it does not know, so the page
    # derives live. The other half is an installed 0.2.0 doing the same with a v2 artifact, which is why
    # the id had to move at all (Craig's agent, on #121)
    assert not published.fresh({**good, "network": {**good["network"],
                                                    "schema": "grownet.interaction_network/v1"}}, now)


def test_an_unreadable_published_network_derives_live_rather_than_raising():
    """Craig's agent, on #121: `from_payload` sat outside `fetch_from`'s guard, and nothing above it had a
    handler, so a document this copy cannot build left the All button by exception instead of falling back
    to a live derivation. Any failure to read the artifact now means None, which is "derive live"."""
    import contextlib
    import datetime
    import io
    import json

    from grownet import published
    from grownet.model import SCHEMA
    now = datetime.datetime(2026, 9, 28, 12, tzinfo=datetime.timezone.utc)
    payload = {"format": published.FORMAT,
               "network": {"schema": SCHEMA, "meta": {"derived_at": "2026-09-28T10:00:00+00:00"},
                           "nodes": [], "studies": [], "edges": []},
               "skipped": [], "resolved": [], "unresolved": [], "studies": [], "errors": []}

    def opener(url, timeout=None):
        return contextlib.closing(io.BytesIO(json.dumps(payload).encode("utf-8")))

    assert published.fetch_from(opener, now=now) is not None       # a readable one is still read

    def raising(*_args, **_kwargs):
        raise TypeError("Edge.__init__() got an unexpected keyword argument 'from_the_future'")

    saved = published.from_payload
    try:
        published.from_payload = raising
        assert published.fetch_from(opener, now=now) is None
    finally:
        published.from_payload = saved


def test_the_page_offers_the_adjusted_p_filter_off_and_says_what_it_left_out():
    # Karoline (2026-09-30): the filter is "by default off", and "the help should motivate why"
    form = render_form("tok", job="j1")
    assert 'name="filter_adjusted_p" value="1">' in form
    assert 'name="max_adjusted_p" type="text" size="6" value="0.05"' in form
    assert 'href="/help?token=tok&amp;job=j1#statistics"' in form        # the why, keeping the search
    # and across which data the p-values are corrected (Karoline, 2026-09-30)
    assert ("across every comparison of this search together: all arcs of all the studies it reads"
            in " ".join(form.split()))
    live = run_query(FakeClient(), [], {"derivation": "replicate"}, all_studies=True, published=False)
    tested = [e for e in live["network"].edges if e.status == "present" and e.significance is not None]
    assert tested, "the fake studies need a tested interaction for this test"
    r = run_query(FakeClient(), [], {"derivation": "replicate", "max_adjusted_p": 1e-12},
                  all_studies=True, published=False)
    assert r["hidden"]["not_significant"] == len(tested) and r["settings"]["max_adjusted_p"] == 1e-12
    assert r["network"].meta["statistics"]["filter"]["left_out"] == len(tested)
    from grownet.report import report_text
    page = render_result("tok", r)
    assert f"Left out by the q-value filter: {len(tested)} interaction(s)" in page
    assert "With the q-value filter on" in page                           # the caution says it decides too
    assert "interactions above 1e-12 left out" in report_text(r) and "q-value filter" in report_text(r)


def test_a_result_the_filter_emptied_says_so_rather_than_blaming_the_threshold():
    from grownet.model import InteractionNetwork
    result = _query()
    result["hidden"] = {"low_quality": 0, "not_significant": 3}
    doc = result["network"].to_dict()
    absent_only = InteractionNetwork.from_dict({**doc, "edges": [{**e, "status": "absent"} for e in doc["edges"]]})
    page = render_result("tok", {**result, "network": absent_only})
    assert "<h2>No interactions pass the q-value filter</h2>" in page
    empty = render_result("tok", {**result, "network": InteractionNetwork.from_dict({**doc, "edges": []})})
    assert "The q-value filter left out all 3 interaction(s)" in empty


def test_an_empty_result_says_what_the_second_box_left_out():
    """With a medium that only some studies carry, the page says the box's part before the rest, so a
    user is not sent looking for a data problem that is really a filter (#113)."""
    from grownet.gui import _empty_reason
    result = {"settings": {**DEFAULTS, "conditions": "mucin"}, "studies": ["S1", "S2", "S3"],
              "resolved": [("x", {1: "x"})], "errors": [], "network": None, "hidden": {},
              "skipped": [("study S2", "no experiment of this study matches the media, experiments or "
                           "studies entered"),
                          ("study S3", "no experiment of this study matches the media, experiments or "
                           "studies entered"),
                          ("a pair", "no usable per-strain series")]}
    reason = _empty_reason(result)
    assert reason.startswith("The second box left out 2 of the 3 study(ies) searched")
    assert "mucin" in reason
    # with the box empty, nothing is said about it
    result["settings"] = {**DEFAULTS}
    assert "second box" not in _empty_reason(result)


def test_opening_the_page_without_the_token_explains_itself(server):
    """Karoline, 2026-10-04: "localhost:8791 shows an error". Opening the port by hand, or an old tab from
    a previous run, used to give a bare server error page. It still refuses, in grownet's own words."""
    import urllib.error
    import urllib.request

    from grownet.gui import render_token_page
    page = visible(render_token_page(had_token=False, port=8791))
    assert "grownet is running on this machine" in page
    assert "http://127.0.0.1:8791/?token=" in page          # where to find the real link
    assert "grownet gui" in page
    assert "from an earlier run" in visible(render_token_page(had_token=True, port=8791))

    base, token = server
    try:
        urllib.request.urlopen(f"{base}/", timeout=5)
        raise AssertionError("the page opened without a token")
    except urllib.error.HTTPError as refused:
        assert refused.code == 403                           # still refused, just not bare
        body = refused.read().decode("utf-8")
    assert "grownet is running on this machine" in visible(body)
    assert token not in body                                 # never the token itself


def test_the_glv_example_button_configures_everything_and_runs(server):
    """Karoline, 2026-10-07: "include a gLV example button in the GUI that configures everything for a
    working gLV example". It fills both boxes and the one setting a package cannot be built without, and
    runs the search, so a reader gets a package to simulate from one press.

    The double here serves the fake study, not SMGDB00000006, so what this pins is the configuring: the
    example's species in the first box, its study in the second, Report growth rates on, and the shipped
    derivation untouched. The package the real study gives is what the help's steps walk through.
    """
    import grownet.gui as gui
    base, token = server
    data = urllib.parse.urlencode({"glv_example": "1"}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=30) as r:
        page = r.read().decode("utf-8")
    assert "Advanced settings" in page            # the result page, not an error

    doc = json.loads(_get(f"{base}/download.json?token={token}"))
    said = doc["meta"]["settings"]
    assert said["report_rates"] is True           # a package needs a rate per organism
    assert said["conditions"] == gui.GLV_EXAMPLE_STUDY
    assert said["derivation"] == gui.DEFAULTS["derivation"]
    # the species it asked for are the example's, which the report of the run names
    report = _get(f"{base}/report.txt?token={token}")
    for name in gui.GLV_EXAMPLE:
        assert name in report
