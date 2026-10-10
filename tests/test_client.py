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


def test_a_black_holed_ipv6_address_costs_three_seconds_and_then_ipv4(monkeypatch):
    """mGrowthDB publishes an AAAA and an A record, and on some networks the IPv6 address is a black hole.

    Measured at KU Leuven on 2026-10-09 against `mgrowthdb.gbiomed.kuleuven.be`: the IPv6 address never
    answers and macOS takes 17.5 seconds to say so, while IPv4 connects in 14 milliseconds. `getaddrinfo`
    returns IPv6 first and `socket.create_connection`, which `http.client` uses, walks the addresses in
    that order with the full timeout on each, so every new connection paid 17.5 seconds: six times in a
    cold run, one per worker thread. Live after this change: the first request takes 3.1 seconds and every
    later connection 0.09, because the family that answered is remembered.

    Here both families are faked, so the test needs no network: the v6 socket times out, the v4 one
    connects, and what is checked is the order, the timeout each attempt was given, and the memory.
    """
    import socket as socket_module

    from grownet import mgrowthdb

    V6, V4 = ("2a02::5", 443, 0, 0), ("134.58.134.5", 443)
    attempts = []

    class _Socket:
        def __init__(self, family, kind, proto):
            self.family, self.timeout = family, None

        def settimeout(self, t):
            self.timeout = t

        def connect(self, address):
            attempts.append((self.family, self.timeout, address))
            if self.family == socket_module.AF_INET6:
                raise TimeoutError("timed out")       # the black hole, after `timeout` seconds

        def close(self):
            pass

    def fake_getaddrinfo(host, port, *a, **kw):
        return [(socket_module.AF_INET6, socket_module.SOCK_STREAM, 6, "", V6),
                (socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", V4)]

    monkeypatch.setattr(mgrowthdb.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(mgrowthdb.socket, "socket", _Socket)
    monkeypatch.setattr(mgrowthdb, "_ANSWERED", {})

    sock = mgrowthdb._connect("mgrowthdb.example", 443, 30.0)
    assert sock.family == socket_module.AF_INET           # IPv4 answered, so IPv4 is what comes back
    assert sock.timeout == 30.0                           # and it carries the caller's timeout, not 3
    assert [(f, t) for f, t, _a in attempts] == [
        (socket_module.AF_INET6, mgrowthdb.FIRST_TRY),    # 3 seconds on the unproven family, not 30
        (socket_module.AF_INET, mgrowthdb.FIRST_TRY)]
    assert mgrowthdb._ANSWERED["mgrowthdb.example"] == socket_module.AF_INET

    # the second connection does not wait at all: the remembered family is tried first and gets the full
    # timeout, since it is the one expected to work
    attempts.clear()
    mgrowthdb._connect("mgrowthdb.example", 443, 30.0)
    assert [(f, t) for f, t, _a in attempts] == [(socket_module.AF_INET, 30.0)]


def test_nothing_forces_ipv4_so_an_ipv6_only_network_still_works(monkeypatch):
    """Forcing IPv4 would break a network that has only IPv6, so the order is a preference and both
    families are still tried. Here only the AAAA record exists and it answers."""
    import socket as socket_module

    from grownet import mgrowthdb

    attempts = []

    class _Socket:
        def __init__(self, family, kind, proto):
            self.family, self.timeout = family, None

        def settimeout(self, t):
            self.timeout = t

        def connect(self, address):
            attempts.append(self.family)

        def close(self):
            pass

    monkeypatch.setattr(mgrowthdb.socket, "getaddrinfo",
                        lambda *a, **kw: [(socket_module.AF_INET6, socket_module.SOCK_STREAM, 6, "",
                                           ("2a02::5", 443, 0, 0))])
    monkeypatch.setattr(mgrowthdb.socket, "socket", _Socket)
    monkeypatch.setattr(mgrowthdb, "_ANSWERED", {})
    sock = mgrowthdb._connect("v6only.example", 443, 30.0)
    assert sock.family == socket_module.AF_INET6 and attempts == [socket_module.AF_INET6]
    assert mgrowthdb._ANSWERED["v6only.example"] == socket_module.AF_INET6


def test_when_no_family_answers_the_last_error_is_raised(monkeypatch):
    """A network failure must stay a network failure, so `_request`'s retry rule and its message still
    apply rather than a new exception type leaking out."""
    import socket as socket_module

    from grownet import mgrowthdb

    class _Socket:
        def __init__(self, family, kind, proto):
            self.family = family

        def settimeout(self, t):
            pass

        def connect(self, address):
            raise OSError(61, "Connection refused")

        def close(self):
            pass

    monkeypatch.setattr(mgrowthdb.socket, "getaddrinfo",
                        lambda *a, **kw: [(socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "",
                                           ("134.58.134.5", 443))])
    monkeypatch.setattr(mgrowthdb.socket, "socket", _Socket)
    monkeypatch.setattr(mgrowthdb, "_ANSWERED", {})
    with pytest.raises(OSError, match="Connection refused"):
        mgrowthdb._connect("down.example", 443, 30.0)


def test_tls_verifies_the_name_the_certificate_has_to_match(monkeypatch):
    """`connect()` is overridden to choose the address, and must hand TLS the name the base class hands
    it: the host normally, and the tunnel target when a proxy is in the way, because that is the name the
    certificate has to match. Nothing in grownet calls `set_tunnel`, so the second case is unreachable
    today and this test is what keeps the override faithful to `http.client` (Craig's agent on #184).
    """
    from grownet import mgrowthdb

    class _Recorder:
        def __init__(self):
            self.names = []

        def wrap_socket(self, sock, server_hostname=None):
            self.names.append(server_hostname)
            return sock

    monkeypatch.setattr(mgrowthdb, "_connect", lambda host, port, timeout: "a socket")

    plain = mgrowthdb._HTTPSConnection("mgrowthdb.example", 443)
    plain._context = _Recorder()
    plain.connect()
    assert plain._context.names == ["mgrowthdb.example"]        # no proxy: the host itself

    proxied = mgrowthdb._HTTPSConnection("proxy.kuleuven.be", 3128)
    proxied.set_tunnel("mgrowthdb.example", 443)
    proxied._tunnel = lambda: None                              # the CONNECT itself is not what is tested
    proxied._context = _Recorder()
    proxied.connect()
    assert proxied._context.names == ["mgrowthdb.example"]      # not "proxy.kuleuven.be"


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


def test_a_study_with_no_uploadedAt_is_never_served_from_the_cache(tmp_path):
    """The whole feature rests on `uploadedAt`: a response may be reused only while the study's stamp is
    unchanged. A study that carries no stamp cannot answer that question, and it used to be cached
    hardest of all: `data.get("uploadedAt", "")` made the stamp `""`, which compares equal to itself on
    every later run, so `_stale` said current forever and a revised study was never read again
    (2026-10-10).

    `null` was already safe, because `.get` returned None and an unknown stamp is never served from. A
    missing key and a blank string now behave the same way.
    """
    class _NoStamp(http.server.BaseHTTPRequestHandler):
        value = {"n": 1000}
        seen: list = []

        def log_message(self, *a):
            pass

        def do_GET(self):
            _NoStamp.seen.append(self.path)
            if self.path.endswith("/study/S1.json"):
                body = json.dumps({"id": "S1", "experiments": [{"id": "E1"}]}).encode()   # no uploadedAt
            elif self.path.endswith("/experiment/E1.json"):
                body = json.dumps({"id": "E1", "studyId": "S1", "value": _NoStamp.value["n"]}).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    _NoStamp.seen, _NoStamp.value = [], {"n": 1000}
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _NoStamp)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/v1"
    try:
        first = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        first.get_study("S1")
        assert first.get_experiment("E1")["value"] == 1000

        _NoStamp.value["n"] = 9999            # the study is revised upstream
        _NoStamp.seen = []
        second = MGrowthDBClient(base_url=base, cache_dir=str(tmp_path))
        second.get_study("S1")
        assert second.get_experiment("E1")["value"] == 9999, "a stampless study was served from the cache"
        assert second.reused == 0
        assert [p.rsplit("/", 1)[-1] for p in _NoStamp.seen] == ["S1.json", "E1.json"]
    finally:
        httpd.shutdown()


def test_a_blank_or_whitespace_uploadedAt_keeps_nothing_and_is_reported_as_absent():
    """`or None` turned a missing key and `""` into None, and a whitespace string is truthy in Python, so
    `"   "` survived and compared equal to itself forever: #190 again with a space in it (found reviewing
    #205, 2026-10-10).

    And the version record is not a cache. `data_versions` is what a reader quotes when auditing where a
    network came from, and it wrote `uploaded_at: ""` for exactly the study whose version nothing can
    establish, so "we read a stamp and it was empty" and "there is no stamp" read the same.
    """
    from grownet.mgrowthdb import NO_STAMP, _stamp

    for blank in (None, "", "   ", "\t\n"):
        assert _stamp(blank) == NO_STAMP, f"{blank!r} is a spelling of blank"
    assert _stamp(" 2025-10-27T16:53:37+00:00 ") == "2025-10-27T16:53:37+00:00"

    class _Blank(http.server.BaseHTTPRequestHandler):
        value = {"n": 1000}
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.endswith("/study/S1.json"):
                body = json.dumps({"id": "S1", "uploadedAt": "   ",
                                   "experiments": [{"id": "E1"}]}).encode()
            else:
                body = json.dumps({"id": "E1", "studyId": "S1", "value": _Blank.value["n"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    import tempfile
    kept = tempfile.mkdtemp()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Blank)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/v1"
    try:
        first = MGrowthDBClient(base_url=base, cache_dir=kept)
        first.get_study("S1")
        assert first.get_experiment("E1")["value"] == 1000
        _Blank.value["n"] = 9999
        second = MGrowthDBClient(base_url=base, cache_dir=kept)
        second.get_study("S1")
        assert second.get_experiment("E1")["value"] == 9999, "a whitespace stamp was served from the cache"
    finally:
        httpd.shutdown()


def test_an_answer_that_carries_no_body_by_definition_is_not_parsed(monkeypatch):
    """204 and 205 are 2xx and carry no body (RFC 9110 15.3.5, 15.3.6), so the status guard that closed
    1xx and 3xx let them through to `json.loads`, which is the failure #191 is about: the command line
    reports the reader's own file as invalid and the status is lost (found reviewing #205)."""
    for code in (204, 205):
        _sending(monkeypatch, [m._Status(code, "No Content")])
        with pytest.raises(MGrowthDBError) as raised:
            MGrowthDBClient(retries=2, backoff=0, cache_dir=None).get_study("S")
        assert raised.value.status == code


def test_a_reply_that_is_not_a_representation_is_an_mgrowthdb_error(monkeypatch):
    """`_send` used to raise only on 4xx and 5xx, so a 3xx body, which is empty because `http.client`
    does not follow redirects, reached `json.loads`. The command line has no handler for that and told
    the user their own file was not valid JSON, with the exit code for a user error and no status on the
    error (2026-10-10). RFC 9110 section 15.4: a 3xx means further action is needed, not a
    representation.
    """
    for code in (301, 302, 304, 100):
        _sending(monkeypatch, [m._Status(code, "Moved")])
        c = MGrowthDBClient(retries=3, backoff=0, cache_dir=None)
        with pytest.raises(MGrowthDBError) as raised:
            c.get_study("S")
        assert raised.value.status == code, "the status has to survive, so a caller can tell cases apart"
        assert str(code) in str(raised.value)
        assert "check the id" not in str(raised.value)      # it is not the reader's mistake

    # and it is not retried: a redirect does not become a representation by asking again
    calls = []
    _sending(monkeypatch, [m._Status(301, "Moved")], calls)
    with pytest.raises(MGrowthDBError):
        MGrowthDBClient(retries=3, backoff=0, cache_dir=None).get_study("S")
    assert len(calls) == 1
