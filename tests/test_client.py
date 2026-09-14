"""The mGrowthDB client: caching and retry behavior, with the network faked (no live calls)."""
import json
import urllib.error

import pytest

import crossfeed.mgrowthdb as m
from crossfeed.mgrowthdb import MGrowthDBClient, MGrowthDBError


class _Resp:
    """A minimal stand-in for the urlopen context manager that json.load can read."""

    def __init__(self, payload):
        self._b = json.dumps(payload)

    def read(self, *_):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_caches_within_client(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        return _Resp({"id": "S", "experiments": []})

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    c = MGrowthDBClient()
    c.get_study("S")
    c.get_study("S")
    assert calls["n"] == 1   # the second call is served from the cache


def test_cache_can_be_disabled(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        return _Resp({"ok": True})

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    c = MGrowthDBClient(cache=False)
    c.get_study("S")
    c.get_study("S")
    assert calls["n"] == 2


def test_retries_transient_then_succeeds(monkeypatch):
    seq = [urllib.error.URLError("down"), urllib.error.URLError("down"), _Resp({"ok": True})]

    def fake_urlopen(req, timeout=None):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    c = MGrowthDBClient(retries=3, backoff=0)
    assert c.get_measurement_context("X") == {"ok": True}


def test_exhausted_retries_raise(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    c = MGrowthDBClient(retries=2, backoff=0)
    with pytest.raises(MGrowthDBError, match="could not reach"):
        c.get_study("S")


def test_404_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    c = MGrowthDBClient(retries=3, backoff=0)
    with pytest.raises(MGrowthDBError, match="404"):
        c.get_study("NOPE")
    assert calls["n"] == 1   # a 4xx is a real error; it is not retried
