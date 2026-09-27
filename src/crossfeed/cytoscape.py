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
    width zero.

Cytoscape maps one column to one visual property, so the two dash channels and the missing width are
computed here into `line_style` and `display_weight` columns rather than layered as several mappings.
These columns exist only in what Cytoscape receives; the neutral format does not gain fields.

Everything is sent to the configured localhost port and nowhere else.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .model import InteractionNetwork

PORT = 1234
STYLE_NAME = "crossfeed"
# the legend's colors, and the same reason for the orange (see crossfeed.legend)
FACILITATION, INHIBITION, MUTED = "#1A7F5A", "#C2410C", "#8A8A8A"
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


def network_json(net: InteractionNetwork, name: str = "crossfeed") -> dict:
    """The network as Cytoscape.js JSON: every node and edge attribute becomes a column."""
    nodes = [{"data": {"id": node.id, "name": node.name or node.id, "taxon_id": node.taxon_id,
                       "species": node.species, "identity": node.identity}}
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
                "p_value": edge.p_value, "significance": edge.significance,
                "metric": edge.metric, "condition": edge.condition,
                # cultivation_mode arrives with #42; read it defensively so either order of merge works
                "cultivation_mode": getattr(edge, "cultivation_mode", ""),
                "quality": " ".join(edge.quality), "cautions": " ".join(edge.cautions),
                "notes": "; ".join(edge.notes), "community": " ".join(edge.community),
                "experiments": " ".join(edge.experiments), "study_ids": " ".join(edge.study_ids),
                "line_style": line_style(edge), "display_weight": display_weight(edge)}
        edges.append({"data": data})
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
            {"visualProperty": "NODE_FILL_COLOR", "value": "#F2F2F2"},
            {"visualProperty": "NODE_BORDER_PAINT", "value": "#666666"},
            {"visualProperty": "NODE_LABEL_FONT_SIZE", "value": 12},
            {"visualProperty": "NODE_SIZE", "value": 45},
            {"visualProperty": "EDGE_TRANSPARENCY", "value": 200},
            {"visualProperty": "EDGE_WIDTH", "value": 2},
        ],
        "mappings": [
            {"mappingType": "passthrough", "mappingColumn": "name", "mappingColumnType": "String",
             "visualProperty": "NODE_LABEL"},
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


class CytoscapeError(RuntimeError):
    """Cytoscape could not be reached or refused the request, with what to do about it."""


def _get(url: str, timeout: float = 30.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:       # noqa: S310 - localhost only
        return json.loads(response.read().decode("utf-8") or "null")


def _post(url: str, payload, timeout: float = 30.0):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 - localhost only
        text = response.read().decode("utf-8")
    return json.loads(text) if text.strip() else {}


def send(net: InteractionNetwork, port: int = PORT, name: str = "crossfeed",
         apply_style: bool = True, layout: str = "force-directed", timeout: float = 30.0) -> dict:
    """Post `net` into a running Cytoscape and return {"suid", "style", "url"}.

    Raises CytoscapeError with what to do when Cytoscape is not running, the port is wrong, or CyREST
    refuses the request. Nothing is sent anywhere but this port on the loopback interface.
    """
    root = base_url(port)
    try:
        created = _post(f"{root}/networks?title={urllib.parse.quote(name)}&collection=crossfeed",
                        network_json(net, name), timeout)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise CytoscapeError(
            f"could not reach Cytoscape on port {port} ({reason}). Start Cytoscape, check that its CyREST "
            f"port is {port} (Edit, Preferences, cyrest.port), or pass another port.") from None
    suid = created.get("networkSUID", created.get("data", {}).get("networkSUID"))
    if suid is None:
        raise CytoscapeError(f"Cytoscape accepted the network but reported no network id: {created!r}")

    applied = ""
    if apply_style:
        try:
            # Cytoscape does not refuse a style whose title it already has: it renames the new one
            # (crossfeed_0, crossfeed_1, ...), so a second run would pile up copies. Ask first, and leave
            # a style that is already there alone, since the user may have adjusted it.
            existing = _get(f"{root}/styles", timeout) or []
            if STYLE_NAME not in existing:
                _post(f"{root}/styles", style(name=STYLE_NAME), timeout)
        except urllib.error.HTTPError as e:
            raise CytoscapeError(f"Cytoscape refused the style ({e.code} {e.reason})") from None
        except urllib.error.URLError as e:
            raise CytoscapeError(f"could not send the style to Cytoscape ({getattr(e, 'reason', e)})") from None
        try:
            _post(f"{root}/apply/styles/{urllib.parse.quote(STYLE_NAME)}/{suid}", {}, timeout)
            if layout:
                _post(f"{root}/apply/layouts/{urllib.parse.quote(layout)}/{suid}", {}, timeout)
        except urllib.error.URLError:
            pass                                 # the network is in; a style or layout is cosmetic
        applied = STYLE_NAME
    return {"suid": suid, "style": applied, "url": f"{root}/networks/{suid}"}
