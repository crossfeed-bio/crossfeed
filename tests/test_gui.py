"""The local page: rendering, the query behind it, and the server routes (a fake client, no live calls)."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

import pytest

from crossfeed.gui import DEFAULTS, parse_settings, render_form, render_result, run_query, serve
from crossfeed.mgrowthdb import MGrowthDBError

A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"


# Two-point curves over 10 h, so the area under the curve is 5 * (v0 + v1).
CURVES = {
    ("mono A", A): [(1, 1), (1, 1.4)],     # areas 10 and 12
    ("mono B", B): [(1, 1), (1, 1.4)],
    ("co", A): [(1, 3), (1, 3.8)],         # areas 20 and 24: B doubles A, 1.0 +/- 0.26 -> facilitation
    ("co", B): [(1, 1), (1, 1.4)],         # unchanged: 0 +/- 0.26 crosses zero -> absent, not an edge
}
TAXA = {A: 853, B: 53443}


def _experiment(name, species):
    """One experiment with two bioreplicates, each carrying a per-strain context per species."""
    return {
        "id": "E_" + name, "name": name,
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
            raise MGrowthDBError(f"mGrowthDB returned HTTP 404 for {study_id}")
        return EXPERIMENTS

    def get_study(self, study_id):
        if study_id != self.study_id:
            raise MGrowthDBError(f"mGrowthDB returned HTTP 404 for {study_id}")
        return {"id": study_id, "name": "fake study", "url": "http://example/study",
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
    return run_query(FakeClient(), list(entries), settings)


def test_species_names_reach_a_network():
    r = _query()
    assert r["taxon_ids"] == [853, 53443]
    assert r["studies"] == ["SMGDB00000001"]
    assert r["unresolved"] == [] and r["errors"] == []
    # B facilitates A (mean log2 1.0 +/- 0.26); A leaves B unchanged (0 +/- 0.26 crosses zero: absent)
    effects = {(e.source, e.target): e.effect for e in r["network"].edges}
    assert effects == {("blautia hydrogenotrophica", "faecalibacterium prausnitzii"): "facilitation"}
    assert [(a["source"], a["target"]) for a in r["absent"]] == [
        ("faecalibacterium prausnitzii", "blautia hydrogenotrophica")]


def test_taxon_ids_work_as_input():
    assert _query(entries=("853", "53443"))["taxon_ids"] == [853, 53443]


def test_unknown_species_is_reported_without_results():
    r = _query(entries=("Escherichia coli",))
    assert r["unresolved"] == ["Escherichia coli"]
    assert r["studies"] == [] and r["network"].edges == []
    page = render_result("tok", r)
    assert "Not in mGrowthDB" in page and "No interactions" in page


def test_absences_are_listed_apart_from_the_edges():
    r = _query()
    assert len(r["network"].edges) == 1
    assert len(r["network"].meta["absent"]) == 1
    page = render_result("tok", r)
    assert "1 tested comparison(s) with no interaction" in page and "adjusted p" in page


def test_only_entered_species_filters_other_pairs():
    both = _query()
    one = _query(entries=("Faecalibacterium prausnitzii",))
    assert len(both["network"].edges) == 1 and len(both["absent"]) == 1
    assert one["network"].edges == [] and one["absent"] == []     # the partner was not entered
    rest = _query(entries=("Faecalibacterium prausnitzii",), only_entered=False)
    assert len(rest["network"].edges) == 1 and len(rest["absent"]) == 1


def test_a_study_that_fails_is_reported_not_raised():
    r = run_query(FakeClient(), ["853"], {"studies": "SMGDB99999999"})
    assert r["errors"] and "SMGDB99999999" in r["errors"][0]
    assert r["network"].edges == []


def test_form_hides_every_setting_behind_one_button():
    page = render_form("tok")
    assert page.count("<details>") == 1 and "Advanced settings" in page
    head, _, tail = page.partition("<details>")
    assert "<select" not in head and "<input name=" not in head    # nothing but the species box is visible
    assert 'name="metric"' in tail and 'name="spike_factor"' in tail
    assert 'name="include_low_quality"' in tail and 'name="include_neutral"' not in page


@pytest.mark.parametrize("form, expected", [
    ({}, {**DEFAULTS, "only_entered": False}),   # an unticked checkbox is simply absent from a post
    ({"metric": ["max"], "spike_factor": ["50"], "studies": [" S1 "], "only_entered": ["1"],
      "include_low_quality": ["1"]},
     {"metric": "max", "spike_factor": 50.0, "studies": "S1", "only_entered": True, "include_low_quality": True}),
    ({"metric": ["nonsense"], "spike_factor": ["not a number"]}, {**DEFAULTS, "only_entered": False}),
])
def test_settings_fall_back_to_defaults(form, expected):
    assert parse_settings(form) == expected


def test_result_page_lists_arcs_and_download_links():
    page = render_result("tok", _query())
    assert "<table>" in page and "Faecalibacterium prausnitzii" in page
    assert "/download.json?token=tok" in page and "/download.graphml?token=tok" in page


def test_result_page_cites_every_study_with_its_license():
    page = render_result("tok", _query())
    assert "Sources" in page and "SMGDB00000001" in page and "fake study" in page
    assert "license: see study" in page and "supports 1 interaction(s)" in page


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

    import crossfeed.gui as gui

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


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8")


def test_server_serves_the_form_and_runs_a_search(server):
    base, token = server
    assert "Advanced settings" in _get(f"{base}/?token={token}")
    data = urllib.parse.urlencode({"species": "Faecalibacterium prausnitzii\nBlautia hydrogenotrophica",
                                   "metric": "growthRate", "deadband": "0.25", "only_entered": "1"})
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data.encode(), timeout=10) as r:
        page = r.read().decode("utf-8")
    assert "interaction(s)" in page and "facilitation" in page
    doc = json.loads(_get(f"{base}/download.json?token={token}"))
    assert len(doc["edges"]) == 1                      # the absent comparison is not an edge
    assert len(doc["meta"]["absent"]) == 1 and doc["meta"]["statistics"]["tests"] == 2
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
