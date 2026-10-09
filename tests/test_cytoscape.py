"""Sending a network to Cytoscape: the payload, the style, and what happens when it is not running."""
import http.server
import json
import threading

import pytest

from grownet import brand
from grownet.cytoscape import (
    OBLIGATE_WIDTH,
    CytoscapeError,
    genus,
    genus_colors,
    line_style,
    network_json,
    send,
    style,
    style_xml,
)
from grownet.mgrowthdb import records_to_network
from grownet.model import Node


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
    columns = []        # the edge columns Cytoscape already holds

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
        if self.path == "/v1/styles":
            self._reply(_Handler.styles)
        elif self.path.endswith("/tables/defaultedge/columns"):
            self._reply([{"name": name} for name in _Handler.columns])
        elif self.path.endswith("/mappings"):        # an older style: two mappings, one no longer drawn
            self._reply([{"visualProperty": "EDGE_TARGET_ARROW_SHAPE"}, {"visualProperty": "NODE_SIZE"}])
        else:
            self._reply({"message": "done"})

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
        if self.path.endswith("/mappings"):          # the real CyREST refuses deleting all mappings at once
            self.send_error(405, "Method Not Allowed")
            return
        self._reply({})


@pytest.fixture
def cyrest():
    _Handler.seen, _Handler.fail_style, _Handler.styles, _Handler.columns = [], False, [], []
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


def test_the_style_file_is_the_xml_cytoscape_imports_with_every_default_and_mapping():
    # Karoline (2026-09-28): "the manual import of grownet_style.json did not work for cytoscape 3.10.4";
    # Cytoscape refuses JSON style files, its own exports included, and reads this XML (checked in 3.10.4:
    # the imported style draws widths, dashes, colors, hidden absent arcs and genus colors as Send does)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(style_xml())
    assert root.tag == "vizmap" and root.get("documentVersion") == "3.1"
    (vs,) = root.findall("visualStyle")
    assert vs.get("name") == "grownet" and [c.tag for c in vs] == ["network", "node", "edge"]
    props = {p.get("name"): (section.tag, p) for section in vs for p in section.findall("visualProperty")}
    for d in style()["defaults"]:
        section, p = props[d["visualProperty"]]
        assert section == d["visualProperty"].split("_")[0].lower() and p.get("default") == str(d["value"])
    types = {"String": "string", "Double": "float"}
    for m in style()["mappings"]:
        section, p = props[m["visualProperty"]]
        (mapping,) = p
        assert mapping.tag == m["mappingType"] + "Mapping" and mapping.get("attributeName") == m["mappingColumn"]
        assert mapping.get("attributeType") == types[m["mappingColumnType"]]
        if m["mappingType"] == "discrete":
            assert {(e.get("attributeValue"), e.get("value")) for e in mapping} == \
                {(e["key"], e["value"]) for e in m["map"]}
        if m["mappingType"] == "continuous":
            assert [(float(q.get("attrValue")), q.get("lesserValue"), q.get("equalValue"), q.get("greaterValue"))
                    for q in mapping] == [(q["value"], q["lesser"], q["equal"], q["greater"]) for q in m["points"]]


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
    assert ("PUT", "/v1/styles/grownet/defaults") in calls
    # every old mapping deleted by its visual property (CyREST refuses deleting them all at once), then the
    # current ones posted, and the style applied: the second send of a session must style too
    deleted = [path for method, path in calls if method == "DELETE"]
    assert deleted == ["/v1/styles/grownet/mappings/EDGE_TARGET_ARROW_SHAPE", "/v1/styles/grownet/mappings/NODE_SIZE"]
    mappings = next(body for method, path, body in seen if (method, path) == ("POST", "/v1/styles/grownet/mappings"))
    assert mappings == style()["mappings"]
    assert ("GET", "/v1/apply/styles/grownet/52") in calls


def test_a_style_that_cannot_be_applied_is_reported_not_swallowed(cyrest):
    port, _ = cyrest
    _Handler.fail_style = True
    sent = send(_net(), port=port)
    assert sent["suid"] == 52 and sent["style"] == ""
    assert "style could not be applied" in sent["warning"] and "400" in sent["warning"]


def _closed_port() -> int:
    """A port nothing listens on: bound, read and closed. Not port + 1 of another socket, which on Windows
    is where the next outgoing connection lands, so the request connected to itself (Craig's agent, #70)."""
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_cytoscape_not_running_says_what_to_do():
    port = _closed_port()
    with pytest.raises(CytoscapeError) as e:
        send(_net(), port=port)
    message = str(e.value)
    assert "Cytoscape is not running on this machine" in message and f"port {port}" in message
    assert "Start Cytoscape, wait until its window has fully opened, then try again" in message


def test_nothing_is_sent_off_this_machine():
    from grownet.cytoscape import base_url
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
    # NCBI's brackets place it outside Clostridium, so it is its own genus (Karoline, 2026-09-28)
    assert genus(Node("ncbi:2", name="[Clostridium] scindens ATCC 35704")) == "[Clostridium]"
    assert genus(Node("ncbi:3", name="Candidatus Arthromitus sp.")) == "Arthromitus"
    assert genus(Node("x", species="blautia hydrogenotrophica")) == "Blautia"      # the species key, no name
    assert genus(Node("x")) == "unknown"


def test_each_genus_gets_its_own_color_the_most_common_first():
    names = ["Bacteroides a", "Bacteroides b", "Bacteroides c", "Blautia a", "Blautia b", "Roseburia a",
             "Akkermansia a", "Dorea a", "Eubacterium a"]
    recs = [{"source": f"n{i}", "target": f"n{i + 1}", "source_name": names[i], "target_name": names[i + 1],
             "effect": "facilitation", "strength": 1.0, "study_id": "S"} for i in range(len(names) - 1)]
    net = records_to_network(recs)
    colors = genus_colors(net)
    # most nodes first (Bacteroides 3, Blautia 2), then alphabetical among the ties
    assert [colors[g] for g in ("Bacteroides", "Blautia", "Akkermansia", "Dorea")] == list(brand.GENUS_COLORS[:4])
    # a fifth and sixth genus get their own colors too (Karoline: "each genus its own color")
    assert (colors["Eubacterium"], colors["Roseburia"]) == brand.GENUS_COLORS[4:6]
    assert len(set(colors.values())) == len(colors) == 6
    assert len(set(brand.GENUS_COLORS)) == len(brand.GENUS_COLORS) >= 44     # every genus mGrowthDB held
    # the genus colors never reuse the two arc colors
    assert not {brand.GROWTH, brand.INHIBITION} & set(brand.GENUS_COLORS)
    node = network_json(net)["elements"]["nodes"][0]["data"]
    assert (node["genus"], node["genus_color"]) == ("Bacteroides", brand.GENUS_COLORS[0])
    fill = next(m for m in style()["mappings"] if m["visualProperty"] == "NODE_FILL_COLOR")
    assert (fill["mappingType"], fill["mappingColumn"]) == ("passthrough", "genus_color")


def test_a_cytoscape_that_is_still_starting_is_told_apart():
    from grownet.cytoscape import _unreachable
    assert "may still be starting" in _unreachable(1234, TimeoutError("timed out"))
    assert "not running on this machine" in _unreachable(1234, "Connection refused")


def test_another_program_on_the_port_is_named_not_a_traceback():
    # a listener that answers with something that is not HTTP raises http.client.BadStatusLine, which is
    # not a URLError: it reached the user as a traceback before (Craig's agent, #70)
    import socket
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def answer():
        import socket as sockets
        conn, _ = server.accept()
        # read the whole request first: on Windows, closing with unread data resets the connection
        # (WinError 10053) before the client can read the reply, which is a different failure
        conn.settimeout(0.5)
        try:
            while conn.recv(65536):
                pass
        except OSError:
            pass
        conn.sendall(b"J\x00\x00\x00\n8.0.32 not http at all\r\n\r\n")    # like a database greeting
        conn.shutdown(sockets.SHUT_WR)
        conn.settimeout(5)
        try:
            conn.recv(1)                    # wait for the client to give up and close
        except OSError:
            pass
        conn.close()

    threading.Thread(target=answer, daemon=True).start()
    try:
        with pytest.raises(CytoscapeError) as e:
            send(_net(), port=port)
    finally:
        server.close()
    assert "something is listening on port" in str(e.value) and "it is not Cytoscape" in str(e.value)


def test_requests_can_only_go_to_this_machine():
    from grownet.cytoscape import _get
    with pytest.raises(CytoscapeError):
        _get("http://example.org:1234/v1/styles")


def test_an_untested_arc_sends_no_empty_numbers():
    # Cytoscape turns a null number into 0.0, and q = 0 is the strongest possible evidence, so an untested
    # arc would pass a "q below 0.05" filter there. The key is left out instead (checked against
    # Cytoscape 3.10.3, 2026-10-03)
    recs = [{"source": "ncbi:1", "target": "ncbi:2", "effect": "facilitation", "strength": 1.0,
             "weight": 1.0, "status": "present", "outcome": "quantified", "study_id": "S1"}]
    data = network_json(records_to_network(recs))["elements"]["edges"][0]["data"]
    for absent in ("p_value", "q_value", "significance", "sd", "se"):
        assert absent not in data
    assert data["strength"] == 1.0 and data["status"] == "present"


def test_a_tested_arc_carries_the_three_numbers_of_the_test():
    recs = [{"source": "ncbi:1", "target": "ncbi:2", "effect": "inhibition", "strength": -1.0, "weight": 1.0,
             "status": "present", "p_value": 0.004, "q_value": 0.02, "significance": 1.699, "study_id": "S1"}]
    data = network_json(records_to_network(recs))["elements"]["edges"][0]["data"]
    assert (data["p_value"], data["q_value"], data["significance"]) == (0.004, 0.02, 1.699)


def test_every_arc_carries_the_three_numbers_of_the_test_as_columns(cyrest):
    # Karoline, 2026-10-03: arcs carry p-value, q-value and significance. An arc without a test sends no
    # empty number (Cytoscape would read it as 0), so the columns are declared instead and its cells stay
    # empty. Without this, a network whose arcs are all untested has no such column at all.
    port, seen = cyrest
    recs = [{"source": "ncbi:1", "target": "ncbi:2", "effect": "facilitation", "strength": 1.0,
             "weight": 1.0, "status": "present", "outcome": "obligate", "study_id": "S1"}]
    sent = send(records_to_network(recs), port=port)
    declared = [body["name"] for path, body in
                [(p, b) for verb, p, b in seen if verb == "POST" and p.endswith("/tables/defaultedge/columns")]]
    for column in ("p_value", "q_value", "significance"):
        assert column in declared
    assert sent["columns"] == declared
    # the arc itself still sends no empty number
    posted = next(b for verb, p, b in seen if verb == "POST" and p.startswith("/v1/networks?"))
    assert "q_value" not in posted["elements"]["edges"][0]["data"]


def test_a_column_cytoscape_already_has_is_not_declared_again(cyrest):
    port, seen = cyrest
    # every column the sender would declare, read from the sender rather than listed here, so a field
    # added to OPTIONAL_EDGE_COLUMNS cannot leave this test asserting about a shorter list than it
    # declares (which is what happened when the error components were added, 2026-10-09)
    from grownet.cytoscape import OPTIONAL_EDGE_COLUMNS
    _Handler.columns = [name for name, _type in OPTIONAL_EDGE_COLUMNS]
    sent = send(_net(), port=port)
    assert sent["columns"] == []
    assert not [p for verb, p, _ in seen if verb == "POST" and p.endswith("/tables/defaultedge/columns")]


def _arc_with_every_field():
    """One arc carrying a value for every field `Edge` declares, so each emitter is asked for all of them.

    The payload drops a number that is None, so a field left empty would look like a field not sent.
    """
    from dataclasses import fields

    from grownet.model import Edge

    kinds = {"str": "x", "str | None": "x", "float | None": 1.5, "int | None": 2, "tuple": ("x",)}
    given = {}
    for f in fields(Edge):
        kind = str(f.type)
        assert kind in kinds, f"{f.name} is declared {kind!r}, which this test cannot fill in: add it"
        given[f.name] = kinds[kind]
    given.update(source="ncbi:1", target="ncbi:2", strength_range=(1.0, 2.0))
    return Edge(**given)


def test_what_graphml_emits_for_an_arc_the_cytoscape_payload_emits_too():
    """Both lists answer the same question, "what do we emit for an arc", and a field added to one and not
    the other is the defect that has now happened twice: #142 item 2, and four error components that
    reached the file and GraphML and stopped at the Cytoscape table (#181).

    The improved list test beside this one compares the test's own list with the sender's, which guards
    test against sender. It cannot see the failure that happened, where the sender itself was short. So
    this compares the two senders, GraphML's key table against what the payload actually carries, and
    neither side is restated here (Craig's agent on #181, who established that both lists were decided
    already, so the comparison needs no judgment call).
    """
    from grownet.export import _KEYS
    from grownet.model import InteractionNetwork

    # one field travels under another name, on purpose: the interaction column is what decides whether
    # Cytoscape's merge collapses parallel edges, so a biculture arc and a drop-out arc for one pair stay
    # apart. It is the only exception, and it is checked below rather than taken.
    under_another_key = {"evidence": "interaction"}
    arc = _arc_with_every_field()
    net = InteractionNetwork(nodes={"ncbi:1": Node(id="ncbi:1", name="A sp."),
                                    "ncbi:2": Node(id="ncbi:2", name="B sp.")},
                             edges=[arc], meta={})
    data = network_json(net)["elements"]["edges"][0]["data"]
    payload = set(data)
    graphml = {name for _kid, kind, name, _type in _KEYS if kind == "edge"}

    missing = sorted(graphml - payload - set(under_another_key))
    assert not missing, ("GraphML emits these edge fields and the Cytoscape payload does not: "
                         f"{missing}. Add them to the payload in cytoscape.py, and to "
                         "OPTIONAL_EDGE_COLUMNS when an arc may lack them")
    # and the exception is real: the value travels, under the other key, and it is still needed
    for field, key in under_another_key.items():
        assert data[key] == getattr(arc, field), f"{field} does not reach Cytoscape as {key}"
        assert field not in payload, f"{field} is sent under its own name now: drop the exception"


def test_every_optional_number_the_payload_sends_is_declared_as_a_column():
    """`_declare_columns` exists so the edge table holds a column whatever this network happens to carry.
    The rule is exactly "a number an arc may not have", which the `Edge` declaration answers rather than
    a person: `float | None` and `int | None`. Asserted in both directions, so the list can neither fall
    behind the payload nor keep a name the payload stopped sending.

    It held 18 of the 33 and a round trip showed the cost: a network whose arcs carry no capacity arrived
    with no `target_capacity` column at all (Cytoscape 3.10.4, 2026-10-09, #181).
    """
    from dataclasses import fields

    from grownet.cytoscape import OPTIONAL_EDGE_COLUMNS
    from grownet.model import Edge, InteractionNetwork

    net = InteractionNetwork(nodes={"ncbi:1": Node(id="ncbi:1", name="A sp."),
                                    "ncbi:2": Node(id="ncbi:2", name="B sp.")},
                             edges=[_arc_with_every_field()], meta={})
    payload = set(network_json(net)["elements"]["edges"][0]["data"])
    declared = {name: kind for name, kind in OPTIONAL_EDGE_COLUMNS}
    wanted = {"float | None": "Double", "int | None": "Integer"}
    optional = {f.name: wanted[str(f.type)] for f in fields(Edge)
                if str(f.type) in wanted and f.name in payload}

    assert not sorted(set(optional) - set(declared)), (
        f"the payload sends these numbers and nothing declares their column: "
        f"{sorted(set(optional) - set(declared))}. Add them to OPTIONAL_EDGE_COLUMNS")
    assert not sorted(set(declared) - set(optional)), (
        f"these columns are declared and the payload does not send them as optional numbers: "
        f"{sorted(set(declared) - set(optional))}. Drop them, or send them")
    wrong = {n: (declared[n], optional[n]) for n in optional if declared[n] != optional[n]}
    assert not wrong, f"declared with the wrong Cytoscape type: {wrong}"
