"""The gLV payload and sending it to a listening R session (#110, converted on #120).

Karoline, 2026-10-03: "a companion plugin for R that would allow sending gLV parameters directly to R via
REST ... The problem is the README: caveats such as the placeholders for obligates/abolished taxa have to
reach the user". So the payload carries the caveats as data, and what the R package does with them is
checked in `r/tests/testthat`; here the wire and the shape are checked, with a stand-in listener that
answers the way the R package does.
"""
import http.server
import json
import threading

import pytest

from grownet import matrix, rbridge
from grownet.mgrowthdb import records_to_network

METRIC = "growth_rate:easylinear:5"


def _arc(source, target, strength, **extra):
    """One arc with what a coefficient is made of (#118, #123), since the payload now carries those."""
    without = 0.4
    record = {"source": source, "target": target, "source_name": source.upper(),
              "target_name": target.upper(),
              "effect": "facilitation" if (strength or 1) > 0 else "inhibition",
              "strength": strength, "status": "present", "outcome": "quantified", "study_id": "S1",
              "metric": METRIC, "evidence": "biculture", "partner_abundance": 2.0e8,
              "partner_abundance_unit": "Cells/mL", "partner_abundance_n": 3,
              "metric_with": None if strength is None else without * 2 ** strength,
              "metric_without": without, "target_capacity": 3.0e8,
              "target_capacity_unit": "Cells/mL", "target_capacity_n": 3}
    record.update(extra)
    if record["outcome"] == "obligate":
        record.update(metric_with=without * 2, metric_without=0.0)
    return record


def _net():
    """Three organisms: a measured arc, an obligate one with no ratio, and a pair that disagrees in sign."""
    arcs = [_arc("a", "b", 1.5),
            _arc("a", "c", None, outcome="obligate"),
            _arc("b", "c", 2.0, study_id="S1"), _arc("b", "c", -2.0, study_id="S2")]
    net = records_to_network(arcs, meta={"tool_version": "9.9.9", "absence": {"k": 1.0},
                                         "source_db": "mGrowthDB (live)"})
    return net


def _rate(name, rate=0.4, capacity=1.0e9):
    return {"name": name, "rate": rate, "unit": "1/h", "n": 3, "studies": ["S1"],
            "per_study": {"S1": rate}, "method": METRIC, "lag": 0.5, "lag_method": "baranyi",
            "capacity": capacity, "capacity_unit": "Cells/mL", "capacity_n": 3}


RATES = {"a": _rate("A"), "b": _rate("B", 0.2, 5.0e8), "c": _rate("C", 0.5, 2.0e8)}


class _Listener(http.server.BaseHTTPRequestHandler):
    """What `grownet::grownet_listen` does, in Python: take the POST and answer what it holds."""

    received: list = []
    answer = {"received": True, "organisms": 3, "growth_rates": 1, "placeholders": 1, "without_a_rate": 2}

    def log_message(self, *_args):
        pass

    def do_POST(self):            # noqa: N802 - the name http.server requires
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).received.append((self.path, json.loads(body.decode("utf-8"))))
        payload = json.dumps(self.answer).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def listener():
    """A stand-in R session on a free port; yields (port, what it received)."""
    _Listener.received = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Listener)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], _Listener.received
    server.shutdown()


def test_the_payload_carries_the_numbers_in_the_order_the_formula_reads():
    payload = matrix.glv_payload(_net(), RATES)
    assert payload["format"] == "grownet.glv/v1"
    (block,) = payload["matrices"]
    names = block["organisms"]
    assert names == ["A", "B", "C"]
    cell = {(i, j): block["interactions"][i][j] for i in range(3) for j in range(3)}
    # A affects B, rows affected: (0.4 * 2^1.5 - 0.4) / 2e8
    assert cell[(names.index("B"), names.index("A"))] == pytest.approx(
        (0.4 * 2 ** 1.5 - 0.4) / 2.0e8)
    assert all(cell[(i, i)] < 0 for i in range(3))                  # every diagonal is fitted
    assert [d["organism"] for d in payload["growth_rate_detail"]] == ["A", "B", "C"]


def test_the_caveats_travel_as_data_not_only_as_prose():
    """A reader of a README can skip it; a program cannot skip a field."""
    caveats = matrix.glv_payload(_net(), RATES)["caveats"]
    assert caveats["censored_cells"] == [{"affected": "C", "actor": "A"}]
    assert caveats["sign_conflicts"] == [{"affected": "C", "actor": "B"}]
    assert caveats["absence_k"] == 1.0 and "fitted" in caveats["diagonal"]
    assert "per-capita" in caveats["coefficients"] and "never converted" in caveats["units"]
    assert "A x = -r" in caveats["unbounded"]
    # and the README travels too, so nothing a reader would have seen is lost on this route
    assert "THE COEFFICIENTS" in matrix.glv_payload(_net(), RATES)["readme"]


def test_sending_posts_the_payload_to_the_listening_session_and_reports_what_it_took(listener):
    port, received = listener
    payload = matrix.glv_payload(_net(), RATES)
    answer = rbridge.send(payload, port=port)
    assert answer["received"] is True and answer["organisms"] == 3
    (path, sent), = received
    assert path == rbridge.PATH
    assert sent["matrices"][0]["organisms"] == ["A", "B", "C"]
    assert sent["caveats"]["censored_cells"] == [{"affected": "C", "actor": "A"}]


def test_nothing_listening_says_how_to_install_the_package_and_how_to_fetch_instead():
    with pytest.raises(rbridge.RError) as raised:
        rbridge.send({}, port=9, timeout=2)        # port 9 discards, so nothing answers
    message = str(raised.value)
    assert "no R session is listening on port 9" in message
    assert rbridge.INSTALL_R in message and "grownet_listen()" in message
    assert "grownet_glv(url)" in message           # the way that needs no listener


def test_a_listener_that_is_not_the_r_package_is_told_apart(listener):
    port, _ = listener
    _Listener.answer = {"hello": "I am something else"}
    try:
        with pytest.raises(rbridge.RError, match="did not confirm the parameters"):
            rbridge.send(matrix.glv_payload(_net(), RATES), port=port)
    finally:
        _Listener.answer = {"received": True, "organisms": 3, "growth_rates": 1, "placeholders": 1,
                            "without_a_rate": 2}


def test_parameters_go_to_this_machine_and_nowhere_else():
    with pytest.raises(rbridge.RError, match="only talks to an R session on this machine"):
        rbridge._local("http://example.org/grownet/glv")
