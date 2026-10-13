"""The page's report says what its search read and reused, as the command line's does (#187)."""
import threading
import time
import urllib.parse
import urllib.request

import pytest
from test_gui import A, B, FakeClient

import grownet.gui as gui
from grownet.gui import reads_since, serve


class Counting(FakeClient):
    """A client that keeps responses, as the real one does, and counts what it reads."""

    def __init__(self):
        self.cache_dir = "kept"
        self.fetched, self.reused, self.remembered, self.refreshed = 0, 0, 0, []

    def get_measurement_series(self, context_id):
        self.fetched += 1
        return super().get_measurement_series(context_id)


@pytest.fixture
def counted_server():
    holder, original = {}, gui._Server

    class Capture(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            holder["server"] = self

    gui._Server = Capture
    threading.Thread(target=serve, kwargs={"open_browser": False, "client_factory": Counting},
                     daemon=True).start()
    while "server" not in holder:
        time.sleep(0.01)
    gui._Server = original
    httpd = holder["server"]
    yield f"http://127.0.0.1:{httpd.server_address[1]}", httpd.RequestHandlerClass.token
    httpd.shutdown()


def _search(base, token):
    data = urllib.parse.urlencode({"species": f"{A}\n{B}", "only_entered": "1"}).encode()
    with urllib.request.urlopen(f"{base}/run?token={token}", data=data, timeout=10) as r:
        assert "interaction(s)" in r.read().decode("utf-8")
    with urllib.request.urlopen(f"{base}/report.txt?token={token}", timeout=10) as r:
        return r.read().decode("utf-8")


def test_the_page_report_counts_this_search_not_the_session(counted_server):
    """The page printed no `reads:` line at all, because its result carried no client. Handing it the
    client, as the issue first proposed, would print the session's totals: the page keeps one client for
    an hour, so a second search would report the first one's reads as its own."""
    base, token = counted_server
    first = [line for line in _search(base, token).splitlines() if line.startswith("reads:")]
    second = [line for line in _search(base, token).splitlines() if line.startswith("reads:")]
    assert first and second, "the page's report has no reads line"
    assert first == second, f"the second search reported the session's total: {first} then {second}"
    assert first[0].startswith("reads: ") and " from mGrowthDB, 0 reused" in first[0]


def test_reads_are_the_difference_over_the_search():
    client = Counting()
    client.fetched, client.reused, client.remembered, client.refreshed = 10, 4, 1, ["S1"]
    before = (client.fetched, client.reused, client.remembered, list(client.refreshed))
    client.fetched, client.reused, client.remembered, client.refreshed = 13, 9, 7, ["S1", "S2"]
    assert reads_since(client, before, False) == {"fetched": 3, "reused": 5, "remembered": 6,
                                                  "refreshed": ["S2"], "shared": False}
    client.cache_dir = None
    assert reads_since(client, before, False) is None, "nothing kept, nothing to say, as on the command line"
    assert reads_since(client, None, False) is None


def test_a_real_client_missing_a_counter_raises_rather_than_reporting_zero():
    """Craig's agent, on #283: defaults in `_counters` turned a renamed or missing counter on a real client
    into "0 from mGrowthDB", the silence #187 removed, reached from the other side."""
    import pytest

    from grownet.gui import _counters

    class Renamed(Counting):
        def __init__(self):
            super().__init__()
            del self.remembered
    with pytest.raises(AttributeError):
        _counters(Renamed())


def test_a_search_that_overlapped_another_does_not_print_a_mixed_count():
    """A search fans out to worker threads, so reads cannot be told apart by thread: with another search
    running at the same time the difference holds both, and the report says so instead of a number."""
    from grownet.report import report_text
    result = gui.run_query(FakeClient(), [A, B], {})
    result["reads"] = {"fetched": 7, "reused": 0, "refreshed": [], "shared": True}
    text = report_text(result)
    assert "reads: not counted for this search alone" in text and "reads: 7" not in text
    result["reads"]["shared"] = False
    assert "reads: 7 from mGrowthDB, 0 reused" in report_text(result)


def test_a_response_held_in_memory_is_counted():
    """Found by running the page live: a second search over the same studies was served from the client's
    memory, which nothing counted, and its report said "0 from mGrowthDB, 0 reused"."""
    from grownet.mgrowthdb import MGrowthDBClient
    from grownet.report import report_text
    client = MGrowthDBClient(cache_dir=None)
    client._mem = {"k": {"a": 1}}
    assert client._cache_get("k") == {"a": 1} and client.remembered == 1
    result = gui.run_query(FakeClient(), [A, B], {})
    result["reads"] = {"fetched": 0, "reused": 0, "remembered": 24, "refreshed": [], "shared": False}
    assert "24 answered from what this session had already read" in report_text(result)



def test_two_searches_at_once_are_both_marked_as_overlapping(monkeypatch):
    """Found in review: the overlap test set `shared=True` by hand, so removing the marking in the job
    runner left it green. Two searches here run through the real `_start`, the first held open until the
    second has started, and both must say their reads cannot be told apart."""
    import threading

    started, release = threading.Event(), threading.Event()

    def held(client, entries, settings, index, progress=None, all_studies=False):
        if entries == ["first"]:
            started.set()
            release.wait(5)
        return {"network": None, "errors": [], "notes": []}

    monkeypatch.setattr(gui, "run_query", held)
    monkeypatch.setattr(gui, "reads_since", lambda client, before, shared: {"shared": shared})

    class Host:
        state = {"index": {}, "index_built": __import__("time").monotonic(), "client": Counting()}
        client_factory = Counting

    host = Host()
    first = gui._Handler._start(host, ["first"], {})
    assert started.wait(5)
    second = gui._Handler._start(host, ["second"], {})
    second["thread"].join(5)
    release.set()
    first["thread"].join(5)
    assert first["result"]["reads"] == {"shared": True} and second["result"]["reads"] == {"shared": True}
    # and one alone is not
    alone = gui._Handler._start(host, ["third"], {})
    alone["thread"].join(5)
    assert alone["result"]["reads"] == {"shared": False}
