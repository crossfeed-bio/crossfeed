"""Export a crossfeed interaction network to standard graph formats for network tools.

The neutral JSON (`crossfeed.model.InteractionNetwork.to_dict`) is the canonical, openly citable output.
This module additionally serializes a network as GraphML, the XML format that Cytoscape, igraph,
networkx, and Gephi read, so a crossfeed network drops straight into an existing network workflow.

Dependency-free (standard library xml only). The graph is directed, and every edge keeps its effect,
strength, significance, condition, method, the space-joined study_ids (the edge-level attribution), and
when known the evidence (biculture or dropout), the space-joined community, the space-joined cautions,
and the space-joined ids of the experiments the edge compares.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .model import InteractionNetwork

_NS = "http://graphml.graphdrawing.org/xmlns"

# (key id, for, attribute name, attribute type)
_KEYS = [
    # what made the network and when (crossfeed.mgrowthdb.provenance), as graph attributes
    ("g_tool", "graph", "tool", "string"),
    ("g_tool_version", "graph", "tool_version", "string"),
    ("g_derived_on", "graph", "derived_on", "string"),
    ("g_derived_at", "graph", "derived_at", "string"),
    ("n_name", "node", "name", "string"),
    # Gephi takes a node's label from an attribute called label (Cytoscape uses name): the same strain name
    ("n_label", "node", "label", "string"),
    ("n_taxonomy", "node", "taxonomy", "string"),
    ("n_model_ref", "node", "model_ref", "string"),
    ("n_taxon_id", "node", "taxon_id", "string"),
    ("n_species", "node", "species", "string"),
    ("n_identity", "node", "identity", "string"),
    ("e_effect", "edge", "effect", "string"),
    ("e_strength", "edge", "strength", "double"),
    ("e_significance", "edge", "significance", "double"),
    ("e_condition", "edge", "condition", "string"),
    ("e_method", "edge", "method", "string"),
    ("e_study_ids", "edge", "study_ids", "string"),
    ("e_p_value", "edge", "p_value", "double"),
    ("e_weight", "edge", "weight", "double"),
    ("e_effect_over_sd", "edge", "effect_over_sd", "double"),
    ("e_status", "edge", "status", "string"),
    ("e_sd", "edge", "sd", "double"),
    ("e_se", "edge", "se", "double"),
    ("e_n_with", "edge", "n_with", "int"),
    ("e_n_without", "edge", "n_without", "int"),
    ("e_outcome", "edge", "outcome", "string"),
    ("e_metric", "edge", "metric", "string"),
    ("e_quality", "edge", "quality", "string"),
    ("e_notes", "edge", "notes", "string"),
    ("e_evidence", "edge", "evidence", "string"),
    ("e_community", "edge", "community", "string"),
    ("e_cautions", "edge", "cautions", "string"),
    ("e_experiments", "edge", "experiments", "string"),
    ("e_cultivation_mode", "edge", "cultivation_mode", "string"),
    ("e_merged_arcs", "edge", "merged_arcs", "int"),
    ("e_strength_range", "edge", "strength_range", "string"),
]


def _data(parent, key, value):
    if value is None or value == "":
        return
    d = ET.SubElement(parent, f"{{{_NS}}}data")
    d.set("key", key)
    d.text = str(value)


def to_graphml(net: InteractionNetwork, pretty: bool = True) -> str:
    """Serialize the network as a GraphML document (a directed graph)."""
    ET.register_namespace("", _NS)
    root = ET.Element(f"{{{_NS}}}graphml")
    for kid, kfor, kname, ktype in _KEYS:
        k = ET.SubElement(root, f"{{{_NS}}}key")
        k.set("id", kid)
        k.set("for", kfor)
        k.set("attr.name", kname)
        k.set("attr.type", ktype)

    graph = ET.SubElement(root, f"{{{_NS}}}graph")
    graph.set("edgedefault", "directed")
    for key in ("tool", "tool_version", "derived_on", "derived_at"):
        _data(graph, f"g_{key}", net.meta.get(key))

    for node in net.nodes.values():
        n = ET.SubElement(graph, f"{{{_NS}}}node")
        n.set("id", node.id)
        _data(n, "n_name", node.name)
        _data(n, "n_label", node.name or node.id)
        _data(n, "n_taxonomy", node.taxonomy)
        _data(n, "n_model_ref", node.model_ref)
        _data(n, "n_taxon_id", node.taxon_id)
        _data(n, "n_species", node.species)
        _data(n, "n_identity", node.identity)

    for i, e in enumerate(net.edges):
        ed = ET.SubElement(graph, f"{{{_NS}}}edge")
        ed.set("id", f"e{i}")
        ed.set("source", e.source)
        ed.set("target", e.target)
        _data(ed, "e_effect", e.effect)
        if e.strength is not None:
            _data(ed, "e_strength", e.strength)
        if e.significance is not None:
            _data(ed, "e_significance", e.significance)
        _data(ed, "e_condition", e.condition)
        _data(ed, "e_method", e.method)
        _data(ed, "e_study_ids", " ".join(e.study_ids))
        numbers = (("e_p_value", e.p_value), ("e_weight", e.weight), ("e_effect_over_sd", e.effect_over_sd),
                   ("e_sd", e.sd), ("e_se", e.se))
        for key, value in numbers:
            if value is not None:
                _data(ed, key, value)
        for key, value in (("e_n_with", e.n_with), ("e_n_without", e.n_without)):
            if value is not None:
                _data(ed, key, value)
        _data(ed, "e_status", e.status)
        _data(ed, "e_outcome", e.outcome)
        _data(ed, "e_metric", e.metric)
        _data(ed, "e_quality", " ".join(e.quality))
        _data(ed, "e_notes", "; ".join(e.notes))
        _data(ed, "e_evidence", e.evidence)
        _data(ed, "e_community", " ".join(e.community))
        _data(ed, "e_cautions", " ".join(e.cautions))
        _data(ed, "e_experiments", " ".join(e.experiments))
        if e.merged_arcs is not None:
            _data(ed, "e_merged_arcs", e.merged_arcs)
        _data(ed, "e_strength_range", " ".join(f"{x:g}" for x in e.strength_range))
        _data(ed, "e_cultivation_mode", e.cultivation_mode)

    if pretty:
        ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
