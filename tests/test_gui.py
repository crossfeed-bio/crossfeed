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


def _mono(name, rate, taxon):
    return {"id": "E" + name, "name": name, "communityStrains": [{"name": name, "NCBId": taxon}],
            "bioreplicates": [{"name": "r1", "measurementContexts": [
                {"techniqueType": "fc", "subject": {"type": "bioreplicate", "name": name}, "growthRate": rate}]}]}


CO = {"id": "Eco", "name": "FP/BH co-culture",
      "communityStrains": [{"name": A, "NCBId": 853}, {"name": B, "NCBId": 53443}],
      "bioreplicates": [{"name": "Average", "measurementContexts": [
          {"techniqueType": "qpcr", "subject": {"type": "strain", "name": A}, "growthRate": 0.66},
          {"techniqueType": "qpcr", "subject": {"type": "strain", "name": B}, "growthRate": 0.31}]}]}
EXPERIMENTS = [_mono(A, 0.30, 853), _mono(B, 0.30, 53443), CO]


class FakeClient:
    """One study (SMGDB00000001) with the FP/BH mono and co-culture experiments."""

    study_id = "SMGDB00000001"

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

    def search(self, strain_ncbi_ids=None, metabolite_chebi_ids=None):
        return {"studies": [self.study_id]}


def _query(entries=("Faecalibacterium prausnitzii", "Blautia hydrogenotrophica"), **settings):
    return run_query(FakeClient(), list(entries), settings)


def test_species_names_reach_a_network():
    r = _query()
    assert r["taxon_ids"] == [853, 53443]
    assert r["studies"] == ["SMGDB00000001"]
    assert r["unresolved"] == [] and r["errors"] == []
    # B facilitates A (0.66 against 0.30 alone); A leaves B about unchanged
    effects = {(e.source, e.target): e.effect for e in r["network"].edges}
    assert effects[("blautia hydrogenotrophica", "faecalibacterium prausnitzii")] == "facilitation"
    assert effects[("faecalibacterium prausnitzii", "blautia hydrogenotrophica")] == "neutral"


def test_taxon_ids_work_as_input():
    assert _query(entries=("853", "53443"))["taxon_ids"] == [853, 53443]


def test_unknown_species_is_reported_without_results():
    r = _query(entries=("Escherichia coli",))
    assert r["unresolved"] == ["Escherichia coli"]
    assert r["studies"] == [] and r["network"].edges == []
    page = render_result("tok", r)
    assert "Not in mGrowthDB" in page and "No interactions" in page


def test_only_entered_species_filters_other_pairs():
    both = _query()
    one = _query(entries=("Faecalibacterium prausnitzii",))
    assert len(both["network"].edges) == 2
    assert one["network"].edges == []          # the partner was not entered
    assert len(_query(entries=("Faecalibacterium prausnitzii",), only_entered=False)["network"].edges) == 2


def test_a_study_that_fails_is_reported_not_raised():
    r = run_query(FakeClient(), ["853"], {"studies": "SMGDB99999999"})
    assert r["errors"] and "SMGDB99999999" in r["errors"][0]
    assert r["network"].edges == []


def test_form_hides_every_setting_behind_one_button():
    page = render_form("tok")
    assert page.count("<details>") == 1 and "Advanced settings" in page
    head, _, tail = page.partition("<details>")
    assert "<select" not in head and "<input name=" not in head    # nothing but the species box is visible
    assert 'name="metric"' in tail and 'name="deadband"' in tail


@pytest.mark.parametrize("form, expected", [
    ({}, {**DEFAULTS, "only_entered": False}),   # an unticked checkbox is simply absent from a post
    ({"metric": ["auc"], "deadband": ["0.5"], "studies": [" S1 "], "only_entered": ["1"]},
     {"metric": "auc", "deadband": 0.5, "studies": "S1", "only_entered": True}),
    ({"metric": ["nonsense"], "deadband": ["not a number"]}, {**DEFAULTS, "only_entered": False}),
])
def test_settings_fall_back_to_defaults(form, expected):
    assert parse_settings(form) == expected


def test_result_page_lists_arcs_and_download_links():
    page = render_result("tok", _query())
    assert "<table>" in page and "Faecalibacterium prausnitzii" in page
    assert "/download.json?token=tok" in page and "/download.graphml?token=tok" in page


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
    assert len(doc["edges"]) == 2
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
