"""The neutral interaction-network format: a published JSON Schema and a dependency-free validator.

What crossfeed emits (crossfeed.model.InteractionNetwork.to_dict) is the contract downstream tools read
(Syntropa, microbetag). SCHEMA_DOC is the canonical JSON Schema (draft-07); it is also shipped as
`schema/interaction_network.schema.json` so any tool in any language can validate against a file.

`validate_document` enforces the same constraints with no third-party dependency, and additionally checks
referential integrity: every edge endpoint is a declared node, every cited study is declared, and every
edge carries at least one supporting study (the edge-level attribution the collaboration adopted).
"""
from __future__ import annotations

import json
import os

from .model import EFFECTS, EVIDENCE, SCHEMA, InteractionNetwork

SCHEMA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "schema", "interaction_network.schema.json",
)

SCHEMA_DOC = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://github.com/crossfeed-bio/crossfeed/blob/main/schema/interaction_network.schema.json",
    "title": "crossfeed interaction network",
    "description": ("The neutral, openly citable interaction-network format crossfeed emits from "
                    "mGrowthDB co-growth data. Interactions are directed and condition-specific, and "
                    "every edge carries the studies it was derived from (edge-level attribution)."),
    "type": "object",
    "required": ["schema", "nodes", "edges", "studies"],
    "additionalProperties": False,
    "properties": {
        "schema": {"const": SCHEMA},
        "meta": {"type": "object"},
        "nodes": {"type": "array", "items": {"$ref": "#/definitions/node"}},
        "edges": {"type": "array", "items": {"$ref": "#/definitions/edge"}},
        "studies": {"type": "array", "items": {"$ref": "#/definitions/study"}},
    },
    "definitions": {
        "node": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "taxonomy": {"type": "string"},
                "model_ref": {"type": "string"},
            },
        },
        "edge": {
            "type": "object",
            "required": ["source", "target", "effect", "study_ids"],
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "effect": {"enum": list(EFFECTS)},
                "strength": {"type": ["number", "null"]},
                "significance": {"type": ["number", "null"]},
                "condition": {"type": "string"},
                "method": {"type": "string"},
                "study_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "evidence": {"enum": [*EVIDENCE, None]},
                "community": {"type": "array", "items": {"type": "string"}},
            },
        },
        "study": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "citation": {"type": "string"},
                "license": {"type": "string"},
                "url": {"type": "string"},
            },
        },
    },
}


def schema_json(indent: int = 2) -> str:
    """The canonical schema as a JSON string (the exact content of the shipped schema file)."""
    return json.dumps(SCHEMA_DOC, indent=indent, ensure_ascii=False) + "\n"


def _objs(x):
    return x if isinstance(x, list) and all(isinstance(i, dict) for i in x) else None


def validate_document(doc) -> list:
    """Return every problem with `doc` as a crossfeed interaction-network document (empty list = valid).

    Dependency-free. Checks the top-level shape, per-item required fields and the effect enum, the
    non-empty study_ids on every edge, and (when the shape is sound) referential integrity via the model.
    """
    if not isinstance(doc, dict):
        return ["document is not a JSON object"]

    problems = []
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema is {doc.get('schema')!r}, expected {SCHEMA!r}")
    if "meta" in doc and not isinstance(doc["meta"], dict):
        problems.append("meta must be an object")

    lists = {}
    for key in ("nodes", "edges", "studies"):
        lst = _objs(doc.get(key, []))
        if lst is None:
            problems.append(f"{key} must be a list of objects")
        else:
            lists[key] = lst

    for i, n in enumerate(lists.get("nodes", [])):
        if not n.get("id"):
            problems.append(f"nodes[{i}] missing id")
    for i, s in enumerate(lists.get("studies", [])):
        if not s.get("id"):
            problems.append(f"studies[{i}] missing id")
    for i, e in enumerate(lists.get("edges", [])):
        if not e.get("source") or not e.get("target"):
            problems.append(f"edges[{i}] missing source or target")
        if e.get("effect") not in EFFECTS:
            problems.append(f"edges[{i}] effect {e.get('effect')!r} not in {EFFECTS}")
        if e.get("evidence") is not None and e.get("evidence") not in EVIDENCE:
            problems.append(f"edges[{i}] evidence {e.get('evidence')!r} not in {EVIDENCE}")
        community = e.get("community", [])
        if not isinstance(community, (list, tuple)) or not all(isinstance(m, str) for m in community):
            problems.append(f"edges[{i}] community must be a list of node ids")
        if not e.get("study_ids"):
            problems.append(f"edges[{i}] has no study_ids (edge-level attribution requires at least one)")

    if not problems:
        try:
            problems += InteractionNetwork.from_dict(doc).validate()
        except (TypeError, KeyError, ValueError) as ex:
            problems.append(f"could not load document into the model: {ex}")
    return problems


def validate_file(path: str) -> list:
    """Validate a network JSON file on disk. Returns the problem list (empty = valid)."""
    with open(path, encoding="utf-8") as f:
        return validate_document(json.load(f))
