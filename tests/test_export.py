"""GraphML export: well-formed, directed, and it keeps effect, attribution, and null handling right."""
from xml.etree import ElementTree as ET

from grownet.export import to_graphml
from grownet.mgrowthdb import records_to_network

NS = {"g": "http://graphml.graphdrawing.org/xmlns"}


def _net():
    recs = [
        {"source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
         "strength": 1.2, "significance": 0.01, "condition": "C", "method": "m", "study_id": "S1"},
        {"source": "a", "target": "c", "effect": "neutral", "strength": None, "significance": None,
         "study_id": "S1"},
    ]
    return records_to_network(recs)


def test_graphml_is_well_formed_and_directed():
    root = ET.fromstring(to_graphml(_net()))
    assert root.find("g:graph", NS).get("edgedefault") == "directed"
    assert len(root.findall(".//g:node", NS)) == 3
    assert len(root.findall(".//g:edge", NS)) == 2


def test_graphml_edge_carries_effect_and_attribution():
    root = ET.fromstring(to_graphml(_net()))
    edge = [e for e in root.findall(".//g:edge", NS) if e.get("target") == "b"][0]
    data = {d.get("key"): d.text for d in edge.findall("g:data", NS)}
    assert data["e_effect"] == "facilitation"
    assert data["e_study_ids"] == "S1"
    assert data["e_strength"] == "1.2"


def test_graphml_omits_null_numbers():
    root = ET.fromstring(to_graphml(_net()))
    neutral = [e for e in root.findall(".//g:edge", NS) if e.get("target") == "c"][0]
    keys = {d.get("key") for d in neutral.findall("g:data", NS)}
    assert "e_strength" not in keys and "e_significance" not in keys


def test_graphml_carries_evidence_and_community_when_known():
    recs = [{"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0, "study_id": "S1",
             "evidence": "dropout", "community": ["a", "b", "c"]}]
    root = ET.fromstring(to_graphml(records_to_network(recs)))
    data = {d.get("key"): d.text for d in root.find(".//g:edge", NS).findall("g:data", NS)}
    assert data["e_evidence"] == "dropout"
    # "; " and not " ": a node id can contain a space, so the space-joined form could not be
    # split back on 115 of 145 corpus arcs (#245)
    assert data["e_community"] == "a; b; c"
    # an edge without evidence has neither key
    unknown = [e for e in ET.fromstring(to_graphml(_net())).findall(".//g:edge", NS) if e.get("target") == "b"][0]
    assert {"e_evidence", "e_community"}.isdisjoint(d.get("key") for d in unknown.findall("g:data", NS))


def test_graphml_carries_cautions_and_experiments():
    recs = [{"source": "a", "target": "b", "effect": "facilitation", "strength": 1.0, "study_id": "S1",
             "evidence": "dropout", "cautions": ["two_replicates"], "experiments": ["E1", "E2"]}]
    root = ET.fromstring(to_graphml(records_to_network(recs)))
    data = {d.get("key"): d.text for d in root.find(".//g:edge", NS).findall("g:data", NS)}
    assert data["e_cautions"] == "two_replicates"
    assert data["e_experiments"] == "E1 E2"


def test_graphml_nodes_carry_taxon_id_species_and_identity():
    recs = [{"source": "ncbi:853", "target": "ncbi:53443", "source_name": "Faecalibacterium prausnitzii A2-165",
             "source_taxon_id": "853", "source_species": "faecalibacterium prausnitzii", "source_identity": "ncbi",
             "effect": "facilitation", "strength": 1.0, "study_id": "S1"}]
    root = ET.fromstring(to_graphml(records_to_network(recs)))
    node = next(n for n in root.findall(".//g:node", NS) if n.get("id") == "ncbi:853")
    data = {d.get("key"): d.text for d in node.findall("g:data", NS)}
    assert data["n_name"] == "Faecalibacterium prausnitzii A2-165"      # the label Cytoscape shows
    assert (data["n_taxon_id"], data["n_species"], data["n_identity"]) == \
        ("853", "faecalibacterium prausnitzii", "ncbi")


def test_graphml_nodes_carry_a_label_for_gephi():
    # Gephi's GraphML importer reads node labels from "label" and edge weights from "weight" (checked in
    # its ImporterGraphML); Cytoscape reads "name". A node carries both, and every edge its weight.
    net = records_to_network([{"source": "ncbi:1", "target": "ncbi:2", "source_name": "Strain one",
                               "target_name": "Strain two", "strength": -1.5, "weight": 1.5,
                               "effect": "inhibition", "study_id": "S1"}])
    root = ET.fromstring(to_graphml(net))
    keys = {k.get("id"): k.get("attr.name") for k in root.findall("g:key", NS)}
    assert keys["n_label"] == "label" and keys["e_weight"] == "weight"
    labels = [d.text for d in root.findall(".//g:node/g:data", NS) if d.get("key") == "n_label"]
    assert labels == ["Strain one", "Strain two"]


def test_graphml_carries_the_columns_the_cytoscape_style_maps():
    # Karoline (2026-09-28, audit step 8): "Cytoscape load of graphml works, but cytoscape style is not fully
    # applied": the style maps line_style, display_weight and genus_color, which only Send to Cytoscape wrote
    from grownet.model import Edge, InteractionNetwork, Node
    net = InteractionNetwork()
    net.add_node(Node("a", name="Blautia obeum"))
    net.add_node(Node("b", name="[Clostridium] scindens"))
    net.add_edge(Edge("a", "b", "facilitation", strength=1.5, weight=1.5, evidence="dropout",
                      quality=("single_replicate",)))
    net.add_edge(Edge("b", "a", "facilitation", outcome="obligate"))
    root = ET.fromstring(to_graphml(net))                               # well formed, parallel arcs allowed
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    names = {k.get("id"): k.get("attr.name") for k in root.findall("g:key", ns)}
    values = [{names[d.get("key")]: d.text for d in el.findall("g:data", ns)}
              for el in root.findall("g:graph/g:edge", ns) + root.findall("g:graph/g:node", ns)]
    first, obligate, a, b = values
    assert (first["line_style"], first["display_weight"]) == ("DASH_DOT", "1.5")   # drop-out and one replicate
    assert (obligate["line_style"], obligate["display_weight"]) == ("SOLID", "8.0")  # no ratio: the fixed width
    assert (a["genus"], b["genus"]) == ("Blautia", "[Clostridium]")                   # brackets kept
    assert a["genus_color"] != b["genus_color"]


def test_community_is_joined_so_a_consumer_can_split_it_back():
    """`community` holds NODE IDS, and a node id under identity "name" is a lowercase species name with a
    space in it. Joined with a space, a 14-member community read as a 16-member one whose two extra
    members were word fragments: on the live corpus 115 of 145 arcs could not be split back (#245).
    `notes` and `merged_pairs` in the same emitter already used "; " for exactly this reason."""
    import xml.etree.ElementTree as ET

    from grownet import cytoscape, export, model

    net = model.InteractionNetwork(
        nodes={"lachnoclostridium symbiosum": model.Node(id="lachnoclostridium symbiosum",
                                                         name="Lachnoclostridium symbiosum"),
               "ncbi:1590": model.Node(id="ncbi:1590", name="Lactobacillus")},
        edges=[model.Edge(source="ncbi:1590", target="lachnoclostridium symbiosum",
                          effect="inhibition", strength=-1.0, evidence="dropout",
                          community=["lachnoclostridium symbiosum", "ncbi:1590"],
                          study_ids=["SMGDB00000008"])],
        studies={"SMGDB00000008": model.Study(id="SMGDB00000008")})

    doc = ET.fromstring(export.to_graphml(net))
    values = [d.text for d in doc.iter("{http://graphml.graphdrawing.org/xmlns}data")
              if d.get("key") == "e_community"]
    assert values, "no community value in the GraphML, so this test proves nothing"
    assert values[0].split("; ") == ["lachnoclostridium symbiosum", "ncbi:1590"]
    # and the space-joined form would not have round-tripped, which is the whole point
    assert values[0].split(" ") != ["lachnoclostridium symbiosum", "ncbi:1590"]

    row = cytoscape.network_json(net, "x")["elements"]["edges"][0]["data"]
    assert row["community"].split("; ") == ["lachnoclostridium symbiosum", "ncbi:1590"]

    # and the rule is declared where the "space-joined community" claim used to be
    assert "joined with \"; \", not \" \"" in (export.__doc__ or "")


def test_every_record_field_reaches_the_cytoscape_table():
    """A field in the file and in GraphML must be a column in Cytoscape too, or it stops at the table.

    `taxonomy` and `model_ref` did exactly that, which is the same asymmetry the edge payload's own
    comment records as fixed for the three error components: found by comparing the two emitters rather
    than by reading either (#245 class, found reviewing round 10). `model_ref` is named for the
    downstream consumer the neutral format exists to serve.

    Asserted as SET EQUALITY against the dataclasses, not as a list written here, so a field added to
    `Node` or `Edge` without a column fails with its own name. The presentation columns Cytoscape styles
    on are listed, because they are the deliberate extras and the asymmetry runs only that way.
    """
    from dataclasses import fields

    from grownet import cytoscape, model

    net = model.InteractionNetwork()
    net.add_node(model.Node(id="a", name="Aa bb", taxonomy="Bacteria;Firmicutes;Aa bb",
                            model_ref="https://example.org/model/aa", taxon_id="1", species="aa bb",
                            identity="ncbi"))
    net.add_node(model.Node(id="b", name="Bb cc"))
    net.add_study(model.Study(id="S"))
    net.add_edge(model.Edge(source="a", target="b", effect="facilitation", study_ids=("S",),
                            strength=1.0))
    payload = cytoscape.network_json(net)["elements"]

    node_extra = {"genus", "genus_color"}
    node_columns = set(payload["nodes"][0]["data"])
    assert node_columns - node_extra == {f.name for f in fields(model.Node)}, (
        "the Cytoscape node table and the Node record disagree: "
        f"only in the record {sorted({f.name for f in fields(model.Node)} - node_columns)}, "
        f"only in the table {sorted(node_columns - node_extra - {f.name for f in fields(model.Node)})}")

    # the two that were missing, by value, so a column present and empty does not pass
    data = payload["nodes"][0]["data"]
    assert data["taxonomy"] == "Bacteria;Firmicutes;Aa bb"
    assert data["model_ref"] == "https://example.org/model/aa"

    # The edge side needs an edge with EVERY field set, because the payload omits a None: a sparse edge
    # would make this pass by having nothing to drop. Values are filled by declared type rather than
    # listed, so a new field is filled too.
    filled = {}
    for f in fields(model.Edge):
        kind = str(f.type)
        if f.name in ("source", "target"):
            filled[f.name] = "a" if f.name == "source" else "b"
        elif f.name == "effect":
            filled[f.name] = "facilitation"
        elif "tuple" in kind:
            # a *_range holds numbers, which the payload formats with :g
            filled[f.name] = (1.0, 2.0) if f.name.endswith("_range") else ("x",)
        elif "int" in kind:
            filled[f.name] = 2
        elif "float" in kind:
            filled[f.name] = 1.5
        else:
            filled[f.name] = "x"
    whole = model.InteractionNetwork()
    whole.add_node(model.Node(id="a", name="Aa bb"))
    whole.add_node(model.Node(id="b", name="Bb cc"))
    whole.add_study(model.Study(id="S"))
    whole.add_edge(model.Edge(**{**filled, "study_ids": ("S",)}))
    edge_columns = set(cytoscape.network_json(whole)["elements"]["edges"][0]["data"])

    # `evidence` travels as the `interaction` column by design, so it is named rather than silently
    # allowed, and the presentation columns are the deliberate extras
    edge_extra = {"interaction", "line_style", "display_weight"}
    edge_fields = {f.name for f in fields(model.Edge)}
    assert not edge_fields - edge_columns - {"evidence"}, (
        f"these Edge fields are not Cytoscape columns: {sorted(edge_fields - edge_columns - {'evidence'})}")
    assert not edge_columns - edge_extra - edge_fields, (
        f"these Cytoscape columns are not Edge fields: {sorted(edge_columns - edge_extra - edge_fields)}")
