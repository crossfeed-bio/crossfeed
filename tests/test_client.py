"""The mGrowthDB client: caching, retries and kept-open connections, with the network faked or local."""
import http.server
import json
import threading

import pytest

import grownet.mgrowthdb as m
from grownet.mgrowthdb import MGrowthDBClient, MGrowthDBError


def _sending(monkeypatch, answers, calls=None):
    """Replace one request with the next of `answers`: bytes to return, or an exception to raise."""
    answers = list(answers)

    def fake_send(self, url, accept):
        if calls is not None:
            calls.append((url, accept))
        x = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(x, Exception):
            raise x
        return x

    monkeypatch.setattr(MGrowthDBClient, "_send", fake_send)


def test_caches_within_client(monkeypatch):
    calls = []
    _sending(monkeypatch, [json.dumps({"id": "S", "experiments": []}).encode()], calls)
    c = MGrowthDBClient()
    c.get_study("S")
    c.get_study("S")
    assert len(calls) == 1   # the second call is served from the cache


def test_cache_can_be_disabled(monkeypatch):
    calls = []
    _sending(monkeypatch, [b'{"ok": true}'], calls)
    c = MGrowthDBClient(cache=False)
    c.get_study("S")
    c.get_study("S")
    assert len(calls) == 2


def test_retries_transient_then_succeeds(monkeypatch):
    _sending(monkeypatch, [ConnectionResetError("down"), m._Status(503), b'{"ok": true}'])
    c = MGrowthDBClient(retries=3, backoff=0)
    assert c.get_measurement_context("X") == {"ok": True}


def test_a_growth_curve_is_retried_too(monkeypatch):
    # the CSV of a series had no retry, so one hiccup could drop a whole study
    _sending(monkeypatch, [ConnectionResetError("down"), b"time,value,std\n0,1,\n10,2,\n"])
    c = MGrowthDBClient(retries=2, backoff=0)
    assert c.get_measurement_series("C") == [(0.0, 1.0, None), (10.0, 2.0, None)]


def test_exhausted_retries_raise(monkeypatch):
    _sending(monkeypatch, [OSError("down")])
    c = MGrowthDBClient(retries=2, backoff=0)
    with pytest.raises(MGrowthDBError, match="could not reach"):
        c.get_study("S")


def test_404_is_not_retried(monkeypatch):
    calls = []
    _sending(monkeypatch, [m._Status(404, "Not Found")], calls)
    c = MGrowthDBClient(retries=3, backoff=0)
    with pytest.raises(MGrowthDBError, match="404"):
        c.get_study("NOPE")
    assert len(calls) == 1   # a 4xx is a real error; it is not retried


class _KeepAlive(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"          # keeps the connection open between requests
    connections = set()

    def log_message(self, *_):
        pass

    def do_GET(self):             # noqa: N802 - the name http.server requires
        _KeepAlive.connections.add(self.client_address)
        body = json.dumps({"path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_one_open_connection_serves_many_requests():
    # a new HTTPS connection per request cost about 120 ms against 55 ms on an open one
    _KeepAlive.connections = set()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _KeepAlive)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = MGrowthDBClient(base_url=f"http://127.0.0.1:{httpd.server_address[1]}/api/v1", cache=False)
        paths = [c.get_study(f"S{i}")["path"] for i in range(10)]
    finally:
        httpd.shutdown()
    assert paths[3] == "/api/v1/study/S3.json"
    assert len(_KeepAlive.connections) == 1              # ten requests, one connection


class _Study(http.server.BaseHTTPRequestHandler):
    """A study with one experiment, one bioreplicate and one series, and an `uploadedAt` the test moves."""

    uploaded = "2025-10-27T16:53:37+00:00"
    seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        _Study.seen.append(self.path)
        if self.path.endswith("/study/S1.json"):
            body, kind = json.dumps({"id": "S1", "uploadedAt": _Study.uploaded,
                                     "experiments": [{"id": "E1"}]}).encode(), "application/json"
        elif self.path.endswith("/experiment/E1.json"):
            body, kind = json.dumps({"id": "E1", "studyId": "S1",
                                     "bioreplicates": [{"id": "B1"}]}).encode(), "application/json"
        elif self.path.endswith("/bioreplicate/B1.json"):
            body, kind = json.dumps({"id": "B1", "studyId": "S1",
                                     "measurementContexts": [{"id": "C1"}]}).encode(), "application/json"
        elif self.path.endswith("/measurement-context/C1.csv"):
            body, kind = b"time,value,std\n0,1000,\n1,2000,\n", "text/csv"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serving():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Study)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/api/v1"


def _read_everything(client):
    """What a search reads for one study: the study, its experiment, its replicate and its series."""
    study = client.get_study("S1")
    for exp in study["experiments"]:
        record = client.get_experiment(exp["id"])
        for rep in record["bioreplicates"]:
            held = client.get_bioreplicate(rep["id"])
            for ctx in held["measurementContexts"]:
                client.get_measurement_series(ctx["id"])


def test_what_a_study_holds_is_reused_while_its_uploadedAt_is_unchanged(tmp_path):
    """Karoline, confirming for the mGrowthDB team on 2026-10-09: "uploadedAt is kept fresh - it's coupled
    to study submission." So everything a study holds may be reused while that stamp is unchanged, and the
    study record itself is always read live, because it is the check (#182).

    Live on SMGDB00000007 the same day: a first run sent 153 requests and a second sent 1.
    """
    _Study.seen, _Study.uploaded = [], "2025-10-27T16:53:37+00:00"
    httpd, base = _serving()
    try:
        first = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        _read_everything(first)
        cold = list(_Study.seen)
        assert sorted(p.rsplit("/", 1)[-1] for p in cold) == ["B1.json", "C1.csv", "E1.json", "S1.json"]
        assert first.fetched == 4 and first.reused == 0

        # a second run, nothing changed: only the study record is read, and it is read live
        _Study.seen = []
        second = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        _read_everything(second)
        assert [p.rsplit("/", 1)[-1] for p in _Study.seen] == ["S1.json"]
        assert second.reused == 3 and second.fetched == 1 and second.refreshed == []
        # and what it gives back is what the server gave the first run
        assert second.get_measurement_series("C1") == [(0.0, 1000.0, None), (1.0, 2000.0, None)]

        # the study is revised: its uploadedAt moves, so everything kept for it is dropped and re-read
        _Study.seen, _Study.uploaded = [], "2026-10-09T08:00:00+00:00"
        third = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        _read_everything(third)
        assert sorted(p.rsplit("/", 1)[-1] for p in _Study.seen) == ["B1.json", "C1.csv", "E1.json",
                                                                     "S1.json"]
        assert third.refreshed == ["S1"] and third.reused == 0

        # and the fourth run reuses the new version, so the drop did not break the keeping
        _Study.seen = []
        fourth = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        _read_everything(fourth)
        assert [p.rsplit("/", 1)[-1] for p in _Study.seen] == ["S1.json"] and fourth.reused == 3
    finally:
        httpd.shutdown()


def test_nothing_is_kept_when_the_cache_is_off(tmp_path):
    """`--no-cache` passes `cache_dir=None`, and then every run reads everything, which is what the page's
    All workflow does on its ephemeral runners."""
    _Study.seen, _Study.uploaded = [], "2025-10-27T16:53:37+00:00"
    httpd, base = _serving()
    try:
        for _ in range(2):
            _read_everything(MGrowthDBClient(base_url=base, cache_dir=None))
        assert len(_Study.seen) == 8                      # four reads, twice, nothing reused
        assert not list(tmp_path.iterdir())               # and nothing written anywhere
    finally:
        httpd.shutdown()


def test_a_response_whose_study_cannot_be_told_is_not_served_from_the_cache(tmp_path):
    """A series read without its bioreplicate having been read first cannot be attributed to a study, so
    nothing can say whether it is current, so it is read again rather than served."""
    _Study.seen, _Study.uploaded = [], "2025-10-27T16:53:37+00:00"
    httpd, base = _serving()
    try:
        c = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        c.get_study("S1")                                 # the stamp is known, but C1's owner is not
        c.get_measurement_series("C1")
        again = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        again.get_study("S1")
        _Study.seen = []
        again.get_measurement_series("C1")
        assert [p.rsplit("/", 1)[-1] for p in _Study.seen] == ["C1.csv"]   # read again, not served
    finally:
        httpd.shutdown()


def test_an_unwritable_cache_directory_does_not_fail_a_search(tmp_path):
    """A cache is a convenience: if it cannot be made, the search reads everything and says nothing."""
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    c = MGrowthDBClient(cache_dir=str(blocker / "under-a-file"))
    assert c.cache_dir is None


def test_every_count_a_reader_is_shown_is_made_under_the_lock(tmp_path):
    """`reused` and `fetched` are printed to a reader as the evidence that a network rests on responses
    kept from an earlier run, and six worker threads share one client, so `x += 1` on them has to be
    guarded like the two indexes are (Craig's agent on #185).

    The invariant is tested rather than the symptom: 120000 unguarded increments across six threads lost
    nothing in five trials on CPython 3.12, so a test that counted would pass either way and prove
    nothing. This one refuses any write to either counter made outside `_index_lock`, which is
    deterministic, and it keeps holding for an increment added somewhere else later.
    """
    class _Watched(MGrowthDBClient):
        _watching = False

        def _check(self, field):
            # single-threaded here, so the lock being held at all means this thread holds it
            assert self._index_lock.locked(), f"{field} was changed outside _index_lock"

        @property
        def reused(self):
            return self._reused

        @reused.setter
        def reused(self, value):
            if self._watching:
                self._check("reused")
            self._reused = value

        @property
        def fetched(self):
            return self._fetched

        @fetched.setter
        def fetched(self, value):
            if self._watching:
                self._check("fetched")
            self._fetched = value

    _Study.seen, _Study.uploaded = [], "2025-10-27T16:53:37+00:00"
    httpd, base = _serving()
    try:
        for expected_reads, expected_kept in ((4, 0), (1, 3)):
            c = _Watched(base_url=base, cache_dir=str(tmp_path))
            c._watching = True
            _read_everything(c)                     # raises in the setter if any count escapes the lock
            assert (c.fetched, c.reused) == (expected_reads, expected_kept)
    finally:
        httpd.shutdown()
