"""Send a network into a running Cytoscape, with the style the legend describes.

Cytoscape ships CyREST, a REST API on `http://localhost:1234/v1`, so a plain POST puts a derived network
into the open session: no file, no dependency, nothing hosted (Karoline, #25). The neutral JSON stays the
canonical output; this is one route among JSON and GraphML, not a privileged one.

What the style draws, decided with Karoline (#25, #47, #62):

  * direction by color: facilitation green, inhibition red, both ending in the same arrowhead, so the
    tips stay uniform and the color alone carries the sign (Karoline, 2026-09-27);
  * width by `weight` (|log2 mean|), so a thicker arc is a larger effect;
  * absent edges hidden, since presence is the threshold k's business and absences are kept for the
    reader to switch on;
  * dash patterns for the two channels that tell a reader how much to trust an arc: long dashes for
    drop-out evidence (possibly indirect) and dots for a single replicate ("Cytoscape supports different
    dash styles", Karoline), combined when an arc is both;
  * obligate and abolished arcs, which have no ratio, drawn at a fixed width rather than disappearing at
    width zero;
  * no edge labels: a network stays readable, and the sign is a column instead, so a reader who wants it
    in the picture maps Label to `strength` themselves (Karoline, 2026-09-27);
  * nodes colored by genus, taken from the first word of the name, so no lineage is needed, each genus
    its own color (Karoline, 2026-09-27). `brand.GENUS_COLORS` runs from most to least distinct; the most
    common genera of a network take the first colors.
    The color is computed per network into `genus_color`, and the style passes it through, so sending a
    second network never recolors the first. The label sits below the node, in ink, readable on any fill.

Cytoscape maps one column to one visual property, so the two dash channels and the missing width are
computed here into `line_style` and `display_weight` columns rather than layered as several mappings.
These columns exist only in what Cytoscape receives; the neutral format does not gain fields.

Everything is sent to the configured localhost port and nowhere else.
"""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

from . import brand
from .model import InteractionNetwork, genus_name

PORT = 1234
STYLE_NAME = brand.NAME
# the legend's colors, and the same reason for the orange (see grownet.legend)
FACILITATION, INHIBITION, MUTED = brand.GROWTH, brand.INHIBITION, "#8A8A8A"
OBLIGATE_WIDTH = 8.0          # obligate and abolished arcs have no |log2 mean| to scale with


def base_url(port: int = PORT) -> str:
    return f"http://127.0.0.1:{port}/v1"


def line_style(edge) -> str:
    """The dash pattern of an arc: one column, because Cytoscape maps one column per property."""
    dropout = edge.evidence == "dropout"
    single = "single_replicate" in edge.quality
    if dropout and single:
        return "DASH_DOT"
    if dropout:
        return "LONG_DASH"
    if single:
        return "DOT"
    return "SOLID"


def display_weight(edge) -> float:
    """The width column: the edge weight, or a fixed width for an arc that has no ratio."""
    if edge.outcome in ("obligate", "abolished"):
        return OBLIGATE_WIDTH
    return float(edge.weight or 0.0)


def genus(node) -> str:
    """The genus of a node, from its name or its genus-and-species key (`model.genus_name`)."""
    return genus_name(node.name or node.species)


def genus_colors(net: InteractionNetwork) -> dict:
    """genus -> color, each genus its own: the most common genera of this network take the first, most
    distinct colors (ties alphabetical). Past the list's length, which mGrowthDB does not reach, it repeats."""
    counts = Counter(genus(node) for node in net.nodes.values())
    ranked = sorted(counts, key=lambda g: (-counts[g], g))
    return {g: brand.GENUS_COLORS[i % len(brand.GENUS_COLORS)] for i, g in enumerate(ranked)}


def network_json(net: InteractionNetwork, name: str = "grownet") -> dict:
    """The network as Cytoscape.js JSON: every node and edge attribute becomes a column."""
    colors = genus_colors(net)
    nodes = [{"data": {"id": node.id, "name": node.name or node.id, "taxon_id": node.taxon_id,
                       "species": node.species, "identity": node.identity, "genus": genus(node),
                       "genus_color": colors[genus(node)]}}
             for node in net.nodes.values()]
    edges = []
    for edge in net.edges:
        data = {"source": edge.source, "target": edge.target,
                # the interaction column decides whether Cytoscape's merge collapses parallel edges, so
                # it carries the evidence: a biculture arc and a drop-out arc for one pair stay apart
                "interaction": edge.evidence or "interaction",
                "effect": edge.effect, "strength": edge.strength, "weight": edge.weight,
                "effect_over_sd": edge.effect_over_sd, "status": edge.status or "undetermined",
                "outcome": edge.outcome or "", "sd": edge.sd, "se": edge.se,
                "n_with": edge.n_with, "n_without": edge.n_without,
                "p_value": edge.p_value, "q_value": edge.q_value, "significance": edge.significance,
                "metric": edge.metric, "condition": edge.condition,
                # cultivation_mode arrives with #42; read it defensively so either order of merge works
                "cultivation_mode": getattr(edge, "cultivation_mode", ""),
                "medium": getattr(edge, "medium", ""),   # the environment it was derived in (#113)
                # the partner's abundance over the target's growth window, for a gLV coefficient (#118)
                "partner_abundance": getattr(edge, "partner_abundance", None),
                "partner_abundance_unit": getattr(edge, "partner_abundance_unit", ""),
                # the two absolute rates a coefficient is the difference of (#123)
                "metric_with": getattr(edge, "metric_with", None),
                "metric_without": getattr(edge, "metric_without", None),
                # a censored arc's cell is a bound, not a ratio (#129)
                "strength_bound": getattr(edge, "strength_bound", None),
                "quality": " ".join(edge.quality), "cautions": " ".join(edge.cautions),
                "notes": "; ".join(edge.notes), "community": " ".join(edge.community),
                "experiments": " ".join(edge.experiments), "study_ids": " ".join(edge.study_ids),
                "merged_arcs": edge.merged_arcs, "strength_range": " ".join(f"{x:g}" for x in edge.strength_range),
                "supporting_pairs": edge.supporting_pairs, "merged_pairs": "; ".join(edge.merged_pairs),
                "line_style": line_style(edge), "display_weight": display_weight(edge)}
        # A number sent as null becomes 0.0 in Cytoscape, and 0 is the strongest possible q-value: an
        # untested arc would then pass a "q below 0.05" filter there. Leaving the key out keeps the cell
        # genuinely empty (checked against Cytoscape 3.10.3, 2026-10-03).
        edges.append({"data": {k: v for k, v in data.items() if v is not None}})
    return {"data": {"name": name, "shared_name": name}, "elements": {"nodes": nodes, "edges": edges}}


def _discrete(column: str, prop: str, mapping: dict, kind: str = "String") -> dict:
    return {"mappingType": "discrete", "mappingColumn": column, "mappingColumnType": kind,
            "visualProperty": prop,
            "map": [{"key": key, "value": value} for key, value in mapping.items()]}


def style(name: str = STYLE_NAME) -> dict:
    """The visual style, as CyREST takes it: defaults plus one mapping per visual property."""
    return {
        "title": name,
        "defaults": [
            {"visualProperty": "NODE_SHAPE", "value": "ELLIPSE"},
            {"visualProperty": "NODE_FILL_COLOR", "value": brand.NODE},
            {"visualProperty": "NODE_BORDER_PAINT", "value": "#FFFFFF"},
            {"visualProperty": "NODE_BORDER_WIDTH", "value": 2},
            {"visualProperty": "NODE_LABEL_COLOR", "value": brand.INK},
            {"visualProperty": "NODE_LABEL_FONT_SIZE", "value": 12},
            # the label under the node, on the canvas, so it reads whatever the genus color
            {"visualProperty": "NODE_LABEL_POSITION", "value": "S,N,c,0.00,4.00"},
            {"visualProperty": "NODE_SIZE", "value": 40},
            {"visualProperty": "EDGE_TRANSPARENCY", "value": 200},
            {"visualProperty": "EDGE_WIDTH", "value": 2},
        ],
        "mappings": [
            {"mappingType": "passthrough", "mappingColumn": "name", "mappingColumnType": "String",
             "visualProperty": "NODE_LABEL"},
            # the genus color computed for this network (genus_colors)
            {"mappingType": "passthrough", "mappingColumn": "genus_color", "mappingColumnType": "String",
             "visualProperty": "NODE_FILL_COLOR"},
            _discrete("effect", "EDGE_STROKE_UNSELECTED_PAINT",
                      {"facilitation": FACILITATION, "inhibition": INHIBITION, "neutral": MUTED}),
            _discrete("effect", "EDGE_TARGET_ARROW_UNSELECTED_PAINT",
                      {"facilitation": FACILITATION, "inhibition": INHIBITION, "neutral": MUTED}),
            # every arc ends in the same arrowhead; the color says facilitation or inhibition
            # (Karoline, on the mark, 2026-09-27)
            _discrete("effect", "EDGE_TARGET_ARROW_SHAPE",
                      {"facilitation": "ARROW", "inhibition": "ARROW", "neutral": "NONE"}),
            _discrete("line_style", "EDGE_LINE_TYPE",
                      {"SOLID": "SOLID", "LONG_DASH": "LONG_DASH", "DOT": "DOT", "DASH_DOT": "DASH_DOT"}),
            # absent edges stay in the file and out of the picture (Karoline, option B on #54)
            _discrete("status", "EDGE_VISIBLE", {"absent": "false", "present": "true",
                                                 "undetermined": "true"}),
            {"mappingType": "continuous", "mappingColumn": "display_weight",
             "mappingColumnType": "Double", "visualProperty": "EDGE_WIDTH",
             "points": [{"value": 0.0, "lesser": "1.0", "equal": "1.0", "greater": "1.0"},
                        {"value": 4.0, "lesser": "10.0", "equal": "10.0", "greater": "10.0"}]},
        ],
    }


# Cytoscape's XML names for CyREST's column types
_XML_TYPES = {"String": "string", "Double": "float", "Integer": "integer", "Long": "long", "Boolean": "boolean"}


def style_xml(name: str = STYLE_NAME) -> str:
    """The same style as `style`, in the XML that File, Import, Styles from File reads.

    Cytoscape reads a style file only in this form: the CyREST JSON that `send` posts, and even the JSON
    Cytoscape itself exports, are refused with "Don't know how to read file" (Karoline, 3.10.4, 2026-09-28).
    """
    s = style(name)
    sections = {"NODE": [], "EDGE": []}
    props = {}
    for d in s["defaults"]:
        props[d["visualProperty"]] = ET.Element("visualProperty", name=d["visualProperty"],
                                                default=str(d["value"]))
    for m in s["mappings"]:
        vp = m["visualProperty"]
        prop = props.setdefault(vp, ET.Element("visualProperty", name=vp))
        kind = m["mappingType"]
        mapping = ET.SubElement(prop, f"{kind}Mapping", attributeName=m["mappingColumn"],
                                attributeType=_XML_TYPES[m["mappingColumnType"]])
        if kind == "discrete":
            for entry in m["map"]:
                ET.SubElement(mapping, "discreteMappingEntry", attributeValue=entry["key"], value=entry["value"])
        elif kind == "continuous":
            for p in m["points"]:
                ET.SubElement(mapping, "continuousMappingPoint", attrValue=str(p["value"]),
                              equalValue=p["equal"], greaterValue=p["greater"], lesserValue=p["lesser"])
    for vp, prop in props.items():
        sections[vp.split("_", 1)[0]].append(prop)
    vizmap = ET.Element("vizmap", id=f"VizMap-{name}", documentVersion="3.1")
    visual_style = ET.SubElement(vizmap, "visualStyle", name=name)
    ET.SubElement(visual_style, "network")
    node = ET.SubElement(visual_style, "node")
    ET.SubElement(node, "dependency", name="nodeSizeLocked", value="true")
    node.extend(sections["NODE"])
    edge = ET.SubElement(visual_style, "edge")
    # the arrowhead takes its color from its own mapping, the same as the line's
    ET.SubElement(edge, "dependency", name="arrowColorMatchesEdge", value="false")
    edge.extend(sections["EDGE"])
    ET.indent(vizmap, space="    ")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(vizmap, "unicode") + "\n"


class CytoscapeError(RuntimeError):
    """Cytoscape could not be reached or refused the request, with what to do about it."""


# What can go wrong on the wire: urllib's own errors, and http.client's for a listener that answers with
# something that is not HTTP (a database, a dev server on the wrong port), which is not a URLError and
# escaped as a traceback before (found by Craig's agent, #70). TimeoutError and OSError cover a socket
# that times out or resets outside urllib's wrapping.
WIRE_ERRORS = (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError)


def _local(url: str) -> str:
    """Every request goes to this machine: checked here, where the request is made, not only by callers."""
    if not url.startswith("http://127.0.0.1:"):
        raise CytoscapeError(f"refusing to send to {url!r}: grownet only talks to a Cytoscape on this machine")
    return url


def _get(url: str, timeout: float = 30.0):
    with urllib.request.urlopen(_local(url), timeout=timeout) as response:     # noqa: S310 - checked
        return json.loads(response.read().decode("utf-8") or "null")


def _post(url: str, payload, timeout: float = 30.0):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(_local(url), data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 - localhost only
        text = response.read().decode("utf-8")
    return json.loads(text) if text.strip() else {}


# Numbers an arc may not have: an untested arc has no test, an obligate one no ratio, a merged one no
# spread. They are left out of the payload rather than sent as null, because Cytoscape reads a null number
# as 0.0 and 0 is the strongest q-value there is. The column is then declared here instead, so every arc
# carries all of them and a reader can style or filter on any one, with the cells of the arcs that have no
# value genuinely empty (Karoline, 2026-10-03; checked against Cytoscape 3.10.3).
OPTIONAL_EDGE_COLUMNS = (("p_value", "Double"), ("q_value", "Double"), ("significance", "Double"),
                         ("strength", "Double"), ("weight", "Double"), ("effect_over_sd", "Double"),
                         ("sd", "Double"), ("se", "Double"), ("n_with", "Integer"),
                         ("n_without", "Integer"), ("merged_arcs", "Integer"),
                         ("supporting_pairs", "Integer"))


def _declare_columns(root: str, suid, timeout: float) -> list:
    """Create the edge columns an arc may not carry, so the table holds every one. Returns their names."""
    table = f"{root}/networks/{suid}/tables/defaultedge"
    try:
        listed = _get(f"{table}/columns", timeout)
    except (urllib.error.URLError, http.client.HTTPException, ValueError):
        return []                      # the network is in; a missing column is not worth failing over
    if not isinstance(listed, list):
        listed = []                    # anything else is not a column list, so take none as present
    present = {column.get("name") for column in listed if isinstance(column, dict)}
    declared = []
    for column, kind in OPTIONAL_EDGE_COLUMNS:
        if column in present:
            continue
        try:
            _post(f"{table}/columns", {"name": column, "type": kind, "immutable": False}, timeout)
            declared.append(column)
        except (urllib.error.URLError, http.client.HTTPException, ValueError):
            continue
    return declared


def send(net: InteractionNetwork, port: int = PORT, name: str = "grownet",
         apply_style: bool = True, layout: str = "force-directed", timeout: float = 30.0) -> dict:
    """Post `net` into a running Cytoscape and return {"suid", "style", "warning", "columns", "url"}.

    Raises CytoscapeError with what to do when Cytoscape is not running, the port is wrong, or CyREST
    refuses the request. Nothing is sent anywhere but this port on the loopback interface.
    """
    root = base_url(port)
    try:
        created = _post(f"{root}/networks?title={urllib.parse.quote(name)}&collection={brand.NAME}",
                        network_json(net, name), timeout)
    except urllib.error.HTTPError as e:
        raise CytoscapeError(f"Cytoscape refused the network ({e.code} {e.reason}). Update Cytoscape to 3.8 or "
                             "later, whose CyREST takes networks this way.") from None
    except http.client.HTTPException as e:
        raise CytoscapeError(
            f"something is listening on port {port}, but it is not Cytoscape: it did not answer the way "
            f"Cytoscape's CyREST does ({type(e).__name__}). Check which port Cytoscape uses (its cyrest.port "
            "property, 1234 unless changed) and that no other program holds it.") from None
    except WIRE_ERRORS as e:
        raise CytoscapeError(_unreachable(port, getattr(e, "reason", e))) from None
    suid = created.get("networkSUID", created.get("data", {}).get("networkSUID"))
    if suid is None:
        raise CytoscapeError(f"Cytoscape accepted the network but reported no network id: {created!r}")

    declared = _declare_columns(root, suid, timeout)
    applied, warning = "", ""
    if apply_style:
        try:
            _ensure_style(root, timeout)
            # applying a style or a layout is a GET in CyREST; a POST is refused (405), which is how the
            # style went missing before (#76)
            _get(f"{root}/apply/styles/{urllib.parse.quote(STYLE_NAME)}/{suid}", timeout)
            applied = STYLE_NAME
            if layout:
                _get(f"{root}/apply/layouts/{urllib.parse.quote(layout)}/{suid}", timeout)
        except urllib.error.HTTPError as e:
            warning = f"the network is in Cytoscape, but its style could not be applied ({e.code} {e.reason})"
        except WIRE_ERRORS as e:
            warning = f"the network is in Cytoscape, but its style could not be applied ({getattr(e, 'reason', e)})"
    return {"suid": suid, "style": applied, "warning": warning, "columns": declared,
            "url": f"{root}/networks/{suid}"}


def _unreachable(port: int, reason) -> str:
    """What to do when nothing answers on the CyREST port, worded for the page and the command line."""
    if "timed out" in str(reason).lower():
        return (f"Cytoscape did not answer on port {port} in time: it may still be starting. Wait until its "
                "window has fully opened, then try again.")
    return (f"Cytoscape is not running on this machine, or not listening on port {port} ({reason}). Start "
            "Cytoscape, wait until its window has fully opened, then try again. Cytoscape listens on port 1234 "
            "unless its cyrest.port property (Edit, Preferences, Properties) says otherwise; the command line "
            "takes another port with --cytoscape-port.")


def _ensure_style(root: str, timeout: float) -> None:
    """Make the grownet style in Cytoscape the one this version draws.

    A new style is posted. One that exists is updated in place, so it always matches the legend: posting
    again would make Cytoscape keep the old one and add a renamed copy (grownet_0), and leaving it alone
    kept an old red and bar heads in use. The defaults are replaced with PUT; the mappings are deleted one
    visual property at a time and posted again, since CyREST refuses deleting them all at once (405, found
    live on 3.10.3) and does not say whether a POST over an existing mapping replaces it.
    """
    wanted = style(STYLE_NAME)
    name = urllib.parse.quote(STYLE_NAME)
    if STYLE_NAME not in (_get(f"{root}/styles", timeout) or []):
        _post(f"{root}/styles", wanted, timeout)
        return
    _request("PUT", f"{root}/styles/{name}/defaults", wanted["defaults"], timeout)
    for mapping in _get(f"{root}/styles/{name}/mappings", timeout) or []:
        prop = urllib.parse.quote(mapping["visualProperty"])
        _request("DELETE", f"{root}/styles/{name}/mappings/{prop}", None, timeout)
    _post(f"{root}/styles/{name}/mappings", wanted["mappings"], timeout)


def _request(method: str, url: str, payload, timeout: float = 30.0):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(_local(url), data=body, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 - localhost only
        return response.read()
