"""The neutral interaction-network format: a published JSON Schema and a dependency-free validator.

What grownet emits (grownet.model.InteractionNetwork.to_dict) is the contract downstream tools read
(Syntropa, microbetag). SCHEMA_DOC is the canonical JSON Schema (draft-07); it is also shipped as
`schema/interaction_network.schema.json` so any tool in any language can validate against a file.

`validate_document` enforces the same constraints with no third-party dependency, and additionally checks
referential integrity: every edge endpoint is a declared node, every cited study is declared, and every
edge carries at least one supporting study (the edge-level attribution the collaboration adopted).
"""
from __future__ import annotations

import json
import os

from .model import (
    CAUTIONS,
    EFFECTS,
    EVIDENCE,
    IDENTITIES,
    KNOWN_SCHEMAS,
    OUTCOMES,
    QUALITY_FLAGS,
    STATUSES,
    InteractionNetwork,
)

# The committed copy of the schema, inside a checkout. It is for the repository's own tools, the gate
# and the tests: an installed copy has no such file (the path would land above site-packages), and
# nothing in `src/` reads it, because `schema_json()` writes the same document from the code. The sdist
# carries it through MANIFEST.in so a packager can run the tests (found missing 2026-10-06).
SCHEMA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "schema", "interaction_network.schema.json",
)

# What `meta` holds (#117, Craig while approving 0.2.0: "`meta` is still unconstrained in the schema ...
# the release that moves the version is the natural place to declare those sub-properties").
#
# Two kinds of key, said in the descriptions so a reader knows which to depend on:
#   * a **promise**: the format states it and a later version will not change its meaning silently;
#   * **recorded**: written because it is useful to have, and free to change with the thing it describes
#     (the settings of a run, for example, change whenever a setting is added).
#
# It stays permissive on purpose: no `additionalProperties`, so a network written by a later version, the
# fixtures and the daily All network all keep validating. Declaring a key constrains its type, not its
# presence.
META_DESCRIPTION = ("how this network was made. The keys described as a promise are part of the format; "
                    "the others are recorded because they are useful, and may change with what they "
                    "describe. Keys not declared here are allowed, so a network from a later version "
                    "still validates.")
_PROMISE = "a promise of the format: "
_RECORDED = "recorded, not promised: "
META_PROPERTIES = {
    "tool": {"type": "string", "description": _PROMISE + "the tool that derived this network"},
    "tool_version": {"type": "string", "description": _PROMISE + "its version"},
    "derived_on": {"type": "string", "description": _PROMISE + "the date it was derived (UTC)"},
    "derived_at": {"type": "string", "description": _PROMISE + "when it was derived, to the second"},
    "source_db": {"type": "string",
                  "description": _PROMISE + "where the growth data came from, and whether live or a "
                                            "fixture"},
    "provisional": {"type": "string",
                    "description": _PROMISE + "present while the derivation method is provisional, "
                                              "saying so in words"},
    "absence": {"type": "object",
                "description": _PROMISE + "the absence threshold this network was written with: k, and "
                                          "how many comparisons fell below it"},
    "statistics": {"type": "object",
                   "description": _PROMISE + "the test behind p_value and q_value, the correction used "
                                             "and how many comparisons it ran over"},
    "query": {"type": "string", "description": _RECORDED + "what was searched: species, all, or a study"},
    "species": {"type": "array", "description": _RECORDED + "the names typed into the search"},
    "studies": {"type": "array", "description": _RECORDED + "the studies the search read"},
    "settings": {"type": "object", "description": _RECORDED + "every setting the run used"},
    "selection": {"type": "object",
                  "description": _RECORDED + "what the second box asked for: media, experiments or "
                                             "studies"},
    "no_growth": {"type": "object", "description": _RECORDED + "the no-growth rule's own numbers"},
    "filters": {"type": "object", "description": _RECORDED + "what was filtered out of the output"},
    "hidden": {"type": "object", "description": _RECORDED + "how many arcs were hidden, and why"},
    "merge": {"type": "object", "description": _RECORDED + "what merging parallel arcs did"},
    "genus": {"type": "object", "description": _RECORDED + "what merging to the genus level did"},
    "data": {"type": "object",
             "description": _RECORDED + "the data version: the API, when it was read, and what the "
                                        "database reported about itself"},
    "growth_rates": {"type": "object",
                     "description": _RECORDED + "the growth rates reported beside the network, with the "
                                                "rule they were derived by and the organisms that have "
                                                "none"},
}

SCHEMA_DOC = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://raw.githubusercontent.com/crossfeed-bio/crossfeed/main/schema/interaction_network.schema.json",
    "title": "grownet interaction network",
    "description": ("The neutral, openly citable interaction-network format grownet emits from "
                    "mGrowthDB co-growth data. Interactions are directed and condition-specific, and "
                    "every edge carries the studies it was derived from (edge-level attribution)."),
    "type": "object",
    "required": ["schema", "nodes", "edges", "studies"],
    "additionalProperties": False,
    "properties": {
        "schema": {"enum": list(KNOWN_SCHEMAS)},
        "meta": {"type": "object", "description": META_DESCRIPTION, "properties": META_PROPERTIES},
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
                "taxon_id": {"type": "string"},
                "species": {"type": "string"},
                "identity": {"enum": [*IDENTITIES, ""]},
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
                "significance": {"type": ["number", "null"], "minimum": 0},
                "q_value": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "condition": {"type": "string"},
                "method": {"type": "string"},
                "study_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "p_value": {"type": ["number", "null"]},
                "weight": {"type": ["number", "null"], "minimum": 0},
                "effect_over_sd": {"type": ["number", "null"], "minimum": 0},
                "status": {"enum": [*STATUSES, None]},
                "sd": {"type": ["number", "null"]},
                "se": {"type": ["number", "null"]},
                "n_with": {"type": ["integer", "null"]},
                "n_without": {"type": ["integer", "null"]},
                "outcome": {"enum": [*OUTCOMES, None]},
                "metric": {"type": "string"},
                "quality": {"type": "array", "items": {"enum": list(QUALITY_FLAGS)}},
                "notes": {"type": "array", "items": {"type": "string"}},
                "evidence": {"enum": [*EVIDENCE, None]},
                "community": {"type": "array", "items": {"type": "string"}},
                "cautions": {"type": "array", "items": {"enum": list(CAUTIONS)}},
                "experiments": {"type": "array", "items": {"type": "string"}},
                "cultivation_mode": {"type": "string"},
                "medium": {"type": "string"},
                "partner_abundance": {"type": ["number", "null"]},
                "partner_abundance_unit": {"type": "string"},
                "partner_abundance_n": {"type": ["integer", "null"]},
                "metric_with": {"type": ["number", "null"]},
                "metric_without": {"type": ["number", "null"]},
                "target_capacity": {"type": ["number", "null"]},
                "target_capacity_unit": {"type": "string"},
                "target_capacity_n": {"type": ["integer", "null"]},
                "strength_bound": {"type": ["number", "null"]},
                "bound_rule": {"type": "string"},
                "coefficient": {"type": ["number", "null"]},
                "coefficient_unit": {"type": "string"},
                "fit_r2": {"type": ["number", "null"]},
                "fit_null_r2": {"type": ["number", "null"]},
                "fit_condition": {"type": ["number", "null"]},
                # the coefficient's uncertainty, as two disjoint designs: the co-culture replicates, and
                # the monoculture stage resampled over its own replicates (#142 item 2)
                "coefficient_sd": {"type": ["number", "null"]},
                "coefficient_n": {"type": ["integer", "null"]},
                "coefficient_sd_from_rate_stage": {"type": ["number", "null"]},
                "se_replicates": {"type": ["number", "null"]},
                "se_rate_stage": {"type": ["number", "null"]},
                "rate_stage_method": {"type": "string"},
                "rate_stage_n": {"type": ["integer", "null"]},
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


_META_TYPES = {"string": str, "array": list, "object": dict}


def _meta_problems(meta: dict) -> list:
    """Where a declared key of `meta` holds the wrong kind of value. A key this schema does not declare is
    left alone, which is what keeps a network from a later version valid here (#117)."""
    problems = []
    for key, value in meta.items():
        declared = META_PROPERTIES.get(key)
        if declared is None or value is None:
            continue
        kind = _META_TYPES[declared["type"]]
        if not isinstance(value, kind) or isinstance(value, bool):
            problems.append(f"meta.{key} must be {declared['type']}, not {type(value).__name__}")
    return problems


def validate_document(doc) -> list:
    """Return every problem with `doc` as a grownet interaction-network document (empty list = valid).

    Dependency-free. Checks the top-level shape, per-item required fields and the effect enum, the
    non-empty study_ids on every edge, and (when the shape is sound) referential integrity via the model.
    """
    if not isinstance(doc, dict):
        return ["document is not a JSON object"]

    problems = []
    if doc.get("schema") not in KNOWN_SCHEMAS:
        problems.append(f"schema is {doc.get('schema')!r}, expected one of {list(KNOWN_SCHEMAS)}")
    if "meta" in doc and not isinstance(doc["meta"], dict):
        problems.append("meta must be an object")
    elif "meta" in doc:
        problems += _meta_problems(doc["meta"])

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
        if n.get("identity", "") not in (*IDENTITIES, ""):
            problems.append(f"nodes[{i}] identity {n.get('identity')!r} not in {IDENTITIES}")
    for i, s in enumerate(lists.get("studies", [])):
        if not s.get("id"):
            problems.append(f"studies[{i}] missing id")
    for i, e in enumerate(lists.get("edges", [])):
        if not e.get("source") or not e.get("target"):
            problems.append(f"edges[{i}] missing source or target")
        if e.get("effect") not in EFFECTS:
            problems.append(f"edges[{i}] effect {e.get('effect')!r} not in {EFFECTS}")
        if e.get("status") is not None and e.get("status") not in STATUSES:
            problems.append(f"edges[{i}] status {e.get('status')!r} not in {STATUSES}")
        if isinstance(e.get("weight"), (int, float)) and e["weight"] < 0:
            problems.append(f"edges[{i}] weight must not be negative")
        quality = e.get("quality", [])
        if not isinstance(quality, (list, tuple)) or any(q not in QUALITY_FLAGS for q in quality):
            problems.append(f"edges[{i}] quality must be a list of {QUALITY_FLAGS}")
        cautions = e.get("cautions", [])
        if not isinstance(cautions, (list, tuple)) or any(c not in CAUTIONS for c in cautions):
            problems.append(f"edges[{i}] cautions must be a list of {CAUTIONS}")
        experiments = e.get("experiments", [])
        if not isinstance(experiments, (list, tuple)) or not all(isinstance(x, str) for x in experiments):
            problems.append(f"edges[{i}] experiments must be a list of experiment ids")
        if e.get("outcome") is not None and e.get("outcome") not in OUTCOMES:
            problems.append(f"edges[{i}] outcome {e.get('outcome')!r} not in {OUTCOMES}")
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
