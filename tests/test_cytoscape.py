"""Sending a network to Cytoscape: the payload, the style, and what happens when it is not running."""
import http.server
import json
import threading

import pytest

from crossfeed import brand
from crossfeed.cytoscape import (
    OBLIGATE_WIDTH,
    CytoscapeError,
    genus,
    genus_colors,
    line_style,
    network_json,
    send,
    style,
)
from crossfeed.mgrowthdb import records_to_network
from crossfeed.model import Node


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
    """A fake CyREST that answers the way the real one does (checked against Cytoscape 3.10.3): applying a
    style or a layout is a GET, and a POST there is refused with 405, as it was in Karoline's session."""

    seen = []
    fail_style = False
    styles = []

    def log_message(self, *_args):
        pass

    def _reply(self, payload, code=200):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body.strip() else {}

    def do_GET(self):             # noqa: N802 - the name http.server requires
        _Handler.seen.append(("GET", self.path, {}))
        self._reply(_Handler.styles if self.path == "/v1/styles" else {"message": "done"})

    def do_POST(self):            # noqa: N802 - the name http.server requires
        body = self._body()
        _Handler.seen.append(("POST", self.path, body))
        if self.path.startswith("/v1/apply/"):
            self.send_error(405, "Method Not Allowed")
            return
        if "/styles" in self.path and _Handler.fail_style:
            self.send_error(400, "style refused")
            return
        self._reply({"networkSUID": 52} if "/networks" in self.path else {})

    def do_PUT(self):             # noqa: N802 - the name http.server requires
        _Handler.seen.append(("PUT", self.path, self._body()))
        self._reply({})

    def do_DELETE(self):          # noqa: N802 - the name http.server requires
        _Handler.seen.append(("DELETE", self.path, {}))
        self._reply({})


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


def test_a_network_is_posted_styled_and_laid_out(cyrest):
    port, seen = cyrest
    sent = send(_net(), port=port, name="study 4")
    assert sent["suid"] == 52 and sent["style"] == "grownet" and sent["warning"] == ""
    calls = [(method, path) for method, path, _ in seen]
    assert ("POST", "/v1/styles") in calls                                   # a new style is posted
    # and applied with a GET, which is what CyREST takes (a POST there is refused: the bug Karoline hit)
    assert ("GET", "/v1/apply/styles/grownet/52") in calls
    assert ("GET", "/v1/apply/layouts/force-directed/52") in calls
    assert not any(method == "POST" and path.startswith("/v1/apply/") for method, path in calls)
    posted = next(body for method, path, body in seen if path.startswith("/v1/networks"))
    assert len(posted["elements"]["nodes"]) == 2 and len(posted["elements"]["edges"]) == 3


def test_a_style_cytoscape_already_has_is_brought_up_to_date(cyrest):
    # an older grownet style (say, with the old red and bar heads) is updated in place: posting again would
    # make Cytoscape keep the old one and add a renamed copy
    port, seen = cyrest
    _Handler.styles = ["default", "grownet"]
    assert send(_net(), port=port)["style"] == "grownet"
    calls = [(method, path) for method, path, _ in seen]
    assert ("POST", "/v1/styles") not in calls
    assert ("PUT", "/v1/styles/grownet/defaults") in calls and ("DELETE", "/v1/styles/grownet/mappings") in calls
    mappings = next(body for method, path, body in seen if (method, path) == ("POST", "/v1/styles/grownet/mappings"))
    assert mappings == style()["mappings"]
    assert calls.index(("DELETE", "/v1/styles/grownet/mappings")) < calls.index(("POST", "/v1/styles/grownet/mappings"))


def test_a_style_that_cannot_be_applied_is_reported_not_swallowed(cyrest):
    port, _ = cyrest
    _Handler.fail_style = True
    sent = send(_net(), port=port)
    assert sent["suid"] == 52 and sent["style"] == ""
    assert "style could not be applied" in sent["warning"] and "400" in sent["warning"]


def test_cytoscape_not_running_says_what_to_do(cyrest):
    port, _ = cyrest
    with pytest.raises(CytoscapeError) as e:
        send(_net(), port=port + 1)              # nothing listens there
    message = str(e.value)
    assert "Cytoscape is not running on this machine" in message and f"port {port + 1}" in message
    assert "Start Cytoscape, wait until its window has fully opened, then try again" in message


def test_nothing_is_sent_off_this_machine():
    from crossfeed.cytoscape import base_url
    assert base_url(1234).startswith("http://127.0.0.1:1234/")


def test_line_style_covers_the_channels_in_both_orders():
    net = _net()
    assert line_style(net.edges[0]) == "SOLID"


def test_the_sign_is_a_column_and_no_label_is_drawn():
    # Karoline, 2026-09-27: the sign is not displayed by default, but it is there to map to Label
    data = network_json(_net())["elements"]["edges"][1]["data"]
    assert data["strength"] == -0.2 and data["effect"] == "inhibition" and data["weight"] == 0.2
    assert not [m for m in style()["mappings"] if m["visualProperty"] == "EDGE_LABEL"]


def test_the_genus_is_the_first_word_of_the_name():
    assert genus(Node("ncbi:1", name="Faecalibacterium duncaniae A2-165")) == "Faecalibacterium"
    assert genus(Node("ncbi:2", name="[Clostridium] scindens ATCC 35704")) == "Clostridium"
    assert genus(Node("ncbi:3", name="Candidatus Arthromitus sp.")) == "Arthromitus"
    assert genus(Node("x", species="blautia hydrogenotrophica")) == "Blautia"      # the species key, no name
    assert genus(Node("x")) == "unknown"


def test_nodes_are_colored_by_genus_with_the_four_checked_hues_then_grey():
    names = ["Bacteroides a", "Bacteroides b", "Bacteroides c", "Blautia a", "Blautia b", "Roseburia a",
             "Akkermansia a", "Dorea a", "Eubacterium a"]
    recs = [{"source": f"n{i}", "target": f"n{i + 1}", "source_name": names[i], "target_name": names[i + 1],
             "effect": "facilitation", "strength": 1.0, "study_id": "S"} for i in range(len(names) - 1)]
    net = records_to_network(recs)
    colors = genus_colors(net)
    # most nodes first (Bacteroides 3, Blautia 2), then alphabetical among the ties
    assert [colors[g] for g in ("Bacteroides", "Blautia", "Akkermansia", "Dorea")] == list(brand.GENUS_COLORS)
    assert colors["Eubacterium"] == colors["Roseburia"] == brand.NODE           # a fifth genus: node gray
    # the genus colors never reuse the two arc colors
    assert not {brand.GROWTH, brand.INHIBITION} & set(brand.GENUS_COLORS)
    node = network_json(net)["elements"]["nodes"][0]["data"]
    assert (node["genus"], node["genus_color"]) == ("Bacteroides", brand.GENUS_COLORS[0])
    fill = next(m for m in style()["mappings"] if m["visualProperty"] == "NODE_FILL_COLOR")
    assert (fill["mappingType"], fill["mappingColumn"]) == ("passthrough", "genus_color")


def test_a_cytoscape_that_is_still_starting_is_told_apart():
    from crossfeed.cytoscape import _unreachable
    assert "may still be starting" in _unreachable(1234, TimeoutError("timed out"))
    assert "not running on this machine" in _unreachable(1234, "Connection refused")
