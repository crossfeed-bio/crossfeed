"""Sending a network to Cytoscape: the payload, the style, and what happens when it is not running."""
import http.server
import json
import threading

import pytest

from crossfeed.cytoscape import (
    OBLIGATE_WIDTH,
    CytoscapeError,
    line_style,
    network_json,
    send,
    style,
)
from crossfeed.mgrowthdb import records_to_network


def _net():
    recs = [
        {"source": "ncbi:1", "target": "ncbi:2", "source_name": "Alpha one", "target_name": "Beta two",
         "source_taxon_id": "1", "source_species": "alpha", "source_identity": "ncbi",
         "effect": "facilitation", "strength": 1.5, "weight": 1.5, "status": "present",
         "outcome": "quantified", "evidence": "biculture", "study_id": "S1", "metric": "auc"},
        {"source": "ncbi:2", "target": "ncbi:1", "effect": "inhibition", "strength": -0.2, "weight": 0.2,
         "status": "absent", "outcome": "quantified", "evidence": "dropout", "quality": ["single_replicate"],
         "community": ["ncbi:1", "ncbi:2"], "study_id": "S1"},
        {"source": "ncbi:1", "target": "ncbi:2", "effect": "facilitation", "strength": None, "weight": None,
         "status": "present", "outcome": "obligate", "evidence": "dropout", "study_id": "S1"},
    ]
    return records_to_network(recs)


class _Handler(http.server.BaseHTTPRequestHandler):
    seen = []
    fail_style = False

    def log_message(self, *_args):
        pass

    styles = []

    def do_GET(self):             # noqa: N802 - the name http.server requires
        payload = json.dumps(_Handler.styles).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):            # noqa: N802 - the name http.server requires
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        _Handler.seen.append((self.path, json.loads(body) if body.strip() else {}))
        if "/styles" in self.path and _Handler.fail_style:
            self.send_error(400, "style exists")
            return
        payload = json.dumps({"networkSUID": 52} if "/networks" in self.path else {}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def cyrest():
    _Handler.seen, _Handler.fail_style, _Handler.styles = [], False, []
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], _Handler.seen
    httpd.shutdown()


def test_the_payload_carries_every_node_and_edge_with_their_columns():
    payload = network_json(_net(), "study 4")
    assert payload["data"]["name"] == "study 4"
    nodes = {n["data"]["id"]: n["data"] for n in payload["elements"]["nodes"]}
    assert nodes["ncbi:1"]["name"] == "Alpha one" and nodes["ncbi:1"]["taxon_id"] == "1"
    first = payload["elements"]["edges"][0]["data"]
    assert (first["source"], first["target"]) == ("ncbi:1", "ncbi:2")
    assert first["effect"] == "facilitation" and first["weight"] == 1.5 and first["status"] == "present"
    assert first["interaction"] == "biculture"          # keeps parallel arcs apart when Cytoscape merges
    assert first["study_ids"] == "S1"


def test_the_two_dash_channels_and_the_missing_width_become_columns():
    edges = {(e["data"]["outcome"], e["data"]["interaction"]): e["data"]
             for e in network_json(_net())["elements"]["edges"]}
    assert edges[("quantified", "biculture")]["line_style"] == "SOLID"
    # a drop-out arc computed on one replicate carries both channels at once
    assert edges[("quantified", "dropout")]["line_style"] == "DASH_DOT"
    assert edges[("quantified", "dropout")]["display_weight"] == 0.2
    # obligate has no ratio, so it would vanish at width zero
    assert edges[("obligate", "dropout")]["line_style"] == "LONG_DASH"
    assert edges[("obligate", "dropout")]["display_weight"] == OBLIGATE_WIDTH


def test_the_style_maps_what_the_legend_shows():
    mappings = {(m["visualProperty"], m["mappingColumn"]): m for m in style()["mappings"]}
    colors = {p["key"]: p["value"] for p in mappings[("EDGE_STROKE_UNSELECTED_PAINT", "effect")]["map"]}
    assert colors["facilitation"] != colors["inhibition"]
    # uniform tips: the color alone says facilitation or inhibition (Karoline, 2026-09-27)
    shapes = {p["key"]: p["value"] for p in mappings[("EDGE_TARGET_ARROW_SHAPE", "effect")]["map"]}
    assert shapes["facilitation"] == shapes["inhibition"] == "ARROW"
    visible = {p["key"]: p["value"] for p in mappings[("EDGE_VISIBLE", "status")]["map"]}
    assert visible["absent"] == "false" and visible["present"] == "true"
    width = mappings[("EDGE_WIDTH", "display_weight")]
    assert width["mappingType"] == "continuous" and width["points"][0]["value"] == 0.0
    dashes = {p["key"] for p in mappings[("EDGE_LINE_TYPE", "line_style")]["map"]}
    assert dashes == {"SOLID", "LONG_DASH", "DOT", "DASH_DOT"}


def test_a_network_is_posted_and_its_id_reported_back(cyrest):
    port, seen = cyrest
    sent = send(_net(), port=port, name="study 4")
    assert sent["suid"] == 52 and sent["style"] == "crossfeed"
    paths = [path for path, _ in seen]
    assert any(p.startswith("/v1/networks") for p in paths)
    assert "/v1/styles" in paths and any(p.startswith("/v1/apply/styles/crossfeed/52") for p in paths)
    posted = next(body for path, body in seen if path.startswith("/v1/networks"))
    assert len(posted["elements"]["nodes"]) == 2 and len(posted["elements"]["edges"]) == 3


def test_a_style_cytoscape_already_has_is_left_alone(cyrest):
    # Cytoscape renames a style whose title it already has (crossfeed_0), so copies would pile up
    port, seen = cyrest
    _Handler.styles = ["default", "crossfeed"]
    assert send(_net(), port=port)["suid"] == 52
    assert not any(path == "/v1/styles" for path, _ in seen)
    assert any(path.startswith("/v1/apply/styles/crossfeed/52") for path, _ in seen)


def test_cytoscape_not_running_says_what_to_do(cyrest):
    port, _ = cyrest
    with pytest.raises(CytoscapeError) as e:
        send(_net(), port=port + 1)              # nothing listens there
    assert f"port {port + 1}" in str(e.value) and "Start Cytoscape" in str(e.value)


def test_nothing_is_sent_off_this_machine():
    from crossfeed.cytoscape import base_url
    assert base_url(1234).startswith("http://127.0.0.1:1234/")


def test_line_style_covers_the_channels_in_both_orders():
    net = _net()
    assert line_style(net.edges[0]) == "SOLID"
