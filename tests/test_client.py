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
