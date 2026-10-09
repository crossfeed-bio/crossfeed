"""Export a grownet interaction network to standard graph formats for network tools.

The neutral JSON (`grownet.model.InteractionNetwork.to_dict`) is the canonical, openly citable output.
This module additionally serializes a network as GraphML, the XML format that Cytoscape, igraph,
networkx, and Gephi read, so a grownet network drops straight into an existing network workflow.

Dependency-free (standard library xml only). The graph is directed, and every edge keeps its effect,
strength, significance (-log10 of the q-value), the q-value, condition, method, the space-joined
study_ids (the edge-level attribution), and
when known the evidence (biculture or dropout), the space-joined community, the space-joined cautions,
and the space-joined ids of the experiments the edge compares.

It also carries the columns the grownet Cytoscape style maps, which "Send to Cytoscape" computes: the
node's genus and genus color, and the edge's line style and display width. Without them a GraphML file
imported into Cytoscape and given the grownet style drew no dashes, no widths and no genus colors
(Karoline, step 8 of the audit, 2026-09-28).
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .model import InteractionNetwork

_NS = "http://graphml.graphdrawing.org/xmlns"

# (key id, for, attribute name, attribute type)
_KEYS = [
    # what made the network and when (grownet.mgrowthdb.provenance), as graph attributes
    ("g_tool", "graph", "tool", "string"),
    ("g_tool_version", "graph", "tool_version", "string"),
    ("g_derived_on", "graph", "derived_on", "string"),
    ("g_derived_at", "graph", "derived_at", "string"),
    ("g_provisional", "graph", "provisional", "string"),
    # the absence rule and its threshold k, and how many arcs were suppressed and why. An absent arc is an
    # edge and travels as one, but without k there is nothing to calibrate it against, and the Cytoscape
    # layered network is built on this route (Craig's agent on #136, #142 item 15)
    ("g_absence_rule", "graph", "absence_rule", "string"),
    ("g_absence_k", "graph", "absence_k", "double"),
    ("g_absence_count", "graph", "absence_count", "int"),
    ("g_hidden", "graph", "hidden", "string"),
    ("g_statistics_test", "graph", "statistics_test", "string"),
    ("n_name", "node", "name", "string"),
    # Gephi takes a node's label from an attribute called label (Cytoscape uses name): the same strain name
    ("n_label", "node", "label", "string"),
    ("n_taxonomy", "node", "taxonomy", "string"),
    ("n_model_ref", "node", "model_ref", "string"),
    ("n_taxon_id", "node", "taxon_id", "string"),
    ("n_species", "node", "species", "string"),
    ("n_identity", "node", "identity", "string"),
    ("n_genus", "node", "genus", "string"),
    ("n_genus_color", "node", "genus_color", "string"),
    ("e_effect", "edge", "effect", "string"),
    ("e_strength", "edge", "strength", "double"),
    ("e_significance", "edge", "significance", "double"),
    ("e_q_value", "edge", "q_value", "double"),
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
    ("e_medium", "edge", "medium", "string"),
    ("e_partner_abundance", "edge", "partner_abundance", "double"),
    ("e_partner_abundance_unit", "edge", "partner_abundance_unit", "string"),
    ("e_partner_abundance_n", "edge", "partner_abundance_n", "int"),
    ("e_metric_with", "edge", "metric_with", "double"),
    ("e_metric_without", "edge", "metric_without", "double"),
    ("e_target_capacity", "edge", "target_capacity", "double"),
    ("e_target_capacity_unit", "edge", "target_capacity_unit", "string"),
    ("e_target_capacity_n", "edge", "target_capacity_n", "int"),
    ("e_strength_bound", "edge", "strength_bound", "double"),
    ("e_bound_rule", "edge", "bound_rule", "string"),
    ("e_coefficient", "edge", "coefficient", "double"),
    ("e_coefficient_unit", "edge", "coefficient_unit", "string"),
    ("e_fit_r2", "edge", "fit_r2", "double"),
    ("e_fit_condition", "edge", "fit_condition", "double"),
    # the fit's own null and its uncertainty, on the same route the rest of the arc travels: Cytoscape is
    # where a reader looks at these numbers, and they were emitted in the JSON and nowhere else
    ("e_fit_null_r2", "edge", "fit_null_r2", "double"),
    # the share of the measured course the rows cover, and the rate mismatch that would zero the arc
    ("e_fit_window_share", "edge", "fit_window_share", "double"),
    ("e_rate_mismatch_to_zero", "edge", "rate_mismatch_to_zero", "double"),
    ("e_coefficient_sd", "edge", "coefficient_sd", "double"),
    ("e_coefficient_n", "edge", "coefficient_n", "int"),
    ("e_coefficient_sd_from_rate_stage", "edge", "coefficient_sd_from_rate_stage", "double"),
    ("e_se_replicates", "edge", "se_replicates", "double"),
    ("e_se_rate_stage", "edge", "se_rate_stage", "double"),
    ("e_se_rate_selection", "edge", "se_rate_selection", "double"),
    ("e_rate_selection_spread", "edge", "rate_selection_spread", "double"),
    ("e_rate_stage_method", "edge", "rate_stage_method", "string"),
    ("e_rate_stage_n", "edge", "rate_stage_n", "int"),
    ("e_merged_arcs", "edge", "merged_arcs", "int"),
    ("e_strength_range", "edge", "strength_range", "string"),
    ("e_supporting_pairs", "edge", "supporting_pairs", "int"),
    ("e_merged_pairs", "edge", "merged_pairs", "string"),
    ("e_line_style", "edge", "line_style", "string"),
    ("e_display_weight", "edge", "display_weight", "double"),
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
    for key in ("tool", "tool_version", "derived_on", "derived_at", "provisional"):
        _data(graph, f"g_{key}", net.meta.get(key))
    # the absence rule, its threshold and the suppressed counts, so an edge marked absent can be read
    # against the k that marked it, and the test the derivation ran (#142 item 15)
    absence = net.meta.get("absence") or {}
    _data(graph, "g_absence_rule", absence.get("rule"))
    _data(graph, "g_absence_k", absence.get("k"))
    _data(graph, "g_absence_count", absence.get("absent"))
    hidden = net.meta.get("hidden") or {}
    _data(graph, "g_hidden", "; ".join(f"{name} {count}" for name, count in sorted(hidden.items()))
          if hidden else None)
    _data(graph, "g_statistics_test", (net.meta.get("statistics") or {}).get("test"))

    from .cytoscape import display_weight, genus, genus_colors, line_style  # the style's own columns
    colors = genus_colors(net)
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
        _data(n, "n_genus", genus(node))
        _data(n, "n_genus_color", colors[genus(node)])

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
        if e.q_value is not None:
            _data(ed, "e_q_value", e.q_value)
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
        if e.supporting_pairs is not None:
            _data(ed, "e_supporting_pairs", e.supporting_pairs)
        _data(ed, "e_merged_pairs", "; ".join(e.merged_pairs))
        _data(ed, "e_line_style", line_style(e))
        _data(ed, "e_display_weight", display_weight(e))
        _data(ed, "e_cultivation_mode", e.cultivation_mode)
        _data(ed, "e_medium", e.medium)
        _data(ed, "e_partner_abundance", e.partner_abundance)
        _data(ed, "e_partner_abundance_unit", e.partner_abundance_unit)
        _data(ed, "e_partner_abundance_n", e.partner_abundance_n)
        _data(ed, "e_metric_with", e.metric_with)
        _data(ed, "e_metric_without", e.metric_without)
        _data(ed, "e_target_capacity", e.target_capacity)
        _data(ed, "e_target_capacity_unit", e.target_capacity_unit)
        _data(ed, "e_target_capacity_n", e.target_capacity_n)
        _data(ed, "e_strength_bound", e.strength_bound)
        _data(ed, "e_bound_rule", e.bound_rule)
        _data(ed, "e_coefficient", e.coefficient)
        _data(ed, "e_coefficient_unit", e.coefficient_unit)
        _data(ed, "e_fit_r2", e.fit_r2)
        _data(ed, "e_fit_condition", e.fit_condition)
        for name in ("fit_null_r2", "coefficient_sd", "coefficient_n",
                     "coefficient_sd_from_rate_stage", "se_replicates", "se_rate_stage",
                     "se_rate_selection", "rate_selection_spread",
                     "rate_stage_method", "rate_stage_n", "fit_window_share",
                     "rate_mismatch_to_zero"):
            _data(ed, f"e_{name}", getattr(e, name, None))

    if pretty:
        ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
