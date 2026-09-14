"""The crossfeed neutral interaction-network model.

An InteractionNetwork is the neutral format crossfeed emits from experimentally grounded
co-growth data (mGrowthDB). Downstream tools (Syntropa, microbetag) read it.

Design notes (from the KU Leuven collaboration, 2026-09):
  * interactions are DIRECTED (source affects target) and CONDITION-SPECIFIC: a reliable
    network is specific to one experimental condition and one way of comparing growth
    curves (mono vs bi-culture, or sub-community).
  * every edge carries its PROVENANCE, the study or studies it was derived from, so
    attribution resolves at the edge level (per-study licenses are respected by citing
    the studies behind each edge, not by bundling).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

SCHEMA = "crossfeed.interaction_network/v0"
EFFECTS = ("facilitation", "inhibition", "neutral")


@dataclass(frozen=True)
class Study:
    """A source study behind one or more edges (the unit of attribution)."""

    id: str                       # e.g. an mGrowthDB study id like "SMGDB00000004"
    citation: str = ""            # human-readable citation
    license: str = ""             # the study's reported license (per-study; respected at edge level)
    url: str = ""


@dataclass(frozen=True)
class Node:
    """An organism (taxon or strain) in the network."""

    id: str                       # stable id within the network
    name: str = ""                # e.g. "Faecalibacterium prausnitzii"
    taxonomy: str = ""            # optional lineage or NCBI taxid
    model_ref: str = ""           # optional link to a metabolic model (for Syntropa)


@dataclass(frozen=True)
class Edge:
    """A directed, condition-specific interaction with edge-level provenance."""

    source: str                   # Node.id of the actor
    target: str                   # Node.id of the affected organism
    effect: str                   # one of EFFECTS
    strength: float | None = None       # e.g. a growth log-ratio
    significance: float | None = None   # e.g. an adjusted p-value
    condition: str = ""           # the experimental condition (interactions are condition-specific)
    method: str = ""              # how the interaction was quantified
    study_ids: tuple = ()         # the studies supporting THIS edge (edge-level attribution)

    def validate(self) -> list:
        problems = []
        if self.effect not in EFFECTS:
            problems.append(f"edge {self.source}->{self.target}: effect {self.effect!r} not in {EFFECTS}")
        if not self.study_ids:
            problems.append(
                f"edge {self.source}->{self.target}: no study_ids "
                "(edge-level attribution requires at least one)"
            )
        return problems


@dataclass
class InteractionNetwork:
    nodes: dict = field(default_factory=dict)     # id -> Node
    edges: list = field(default_factory=list)     # list[Edge]
    studies: dict = field(default_factory=dict)   # id -> Study
    meta: dict = field(default_factory=dict)      # source_db, query organisms, condition, tool version, ...
    schema: str = SCHEMA

    def add_study(self, study: Study) -> None:
        self.studies[study.id] = study

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def validate(self) -> list:
        """Return every structural problem (empty list means the network is well formed)."""
        problems = []
        for e in self.edges:
            problems += e.validate()
            if e.source not in self.nodes:
                problems.append(f"edge references missing source node {e.source!r}")
            if e.target not in self.nodes:
                problems.append(f"edge references missing target node {e.target!r}")
            for sid in e.study_ids:
                if sid not in self.studies:
                    problems.append(f"edge {e.source}->{e.target} cites unknown study {sid!r}")
        return problems

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "meta": self.meta,
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
            "studies": [asdict(s) for s in self.studies.values()],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> InteractionNetwork:
        net = cls(meta=d.get("meta", {}), schema=d.get("schema", SCHEMA))
        for s in d.get("studies", []):
            net.add_study(Study(**s))
        for n in d.get("nodes", []):
            net.add_node(Node(**n))
        for e in d.get("edges", []):
            e = dict(e)
            e["study_ids"] = tuple(e.get("study_ids", ()))
            net.add_edge(Edge(**e))
        return net
