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
