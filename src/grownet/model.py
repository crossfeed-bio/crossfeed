"""The grownet neutral interaction-network model.

An InteractionNetwork is the neutral format grownet emits from experimentally grounded
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
from dataclasses import asdict, dataclass, field, fields

# The format a network declares. It moved to v1 with 0.2.0, because `significance` changed meaning:
# it was the corrected p-value, and it is now -log10 of that, so the same field holds a different quantity
# and runs the other way. A version is a promise about content (Craig, on #71), and this is the one signal
# that says the meaning of a field moved; without it a reader of a v0 file would misread a 0.2.0 network
# silently. Nothing else about the format changed, and the fields added since v0 are optional.
# It moved to v2 with 0.3.0, for a reason about readers rather than about fields. The id is what
# `published.fresh` checks before an installed copy uses the daily All network, so that "a v0 daily
# network holds the old meaning, and the page derives live until the workflow republishes" (Karoline,
# 2026-10-04). 0.3.0 adds optional edge fields, and an installed 0.2.0 builds its edges with Edge(**e),
# which raises on a field it does not know: keeping the id would have let 0.2.0 accept the artifact and
# then fail on it, where moving the id makes it derive live as designed (found 2026-10-06).
SCHEMA = "grownet.interaction_network/v2"
# Older ids a reader still accepts, newest first. A v0 document is valid: its `significance` means what v0
# said it means, which is why `grownet validate` names the version it read.
PREVIOUS_SCHEMAS = ("grownet.interaction_network/v1", "grownet.interaction_network/v0")
KNOWN_SCHEMAS = (SCHEMA, *PREVIOUS_SCHEMAS)
EFFECTS = ("facilitation", "inhibition", "neutral")
# what an edge was derived from: a mono versus bi-culture comparison (a direct interaction), or a full
# versus drop-out community comparison (not necessarily direct: strictly a hyper-arc, kept as an arc)
EVIDENCE = ("biculture", "dropout")
# what the comparison could say about the target's growth (grownet.interaction)
OUTCOMES = ("quantified", "obligate", "abolished", "no_growth")
# why an edge is low quality: hidden by default and never read as the absence of an interaction
QUALITY_FLAGS = ("single_replicate", "strains_pooled", "non_batch", "removed_member_detected")
# cautions a reader should see that do not make an edge low quality: it keeps its status and is shown
CAUTIONS = ("two_replicates", "conditions_unverified", "stationary_phase_differs", "stationary_unchecked",
            "zero_at_start", "untested", "continuous_culture")
# what a node's id rests on: the NCBI taxon id of the strain, or genus and species of its name (#23)
IDENTITIES = ("ncbi", "name", "genus")
# whether a comparison counts as an interaction under the absence threshold (grownet.derive.absence)
STATUSES = ("present", "absent")


# words before a genus that are not a genus: "Candidatus Arthromitus", "unclassified Bacteroides",
# "uncultured Candidatus ..." (Craig's agent on #85); an organism known only to its genus joins that genus
# (Karoline, 2026-09-28)
GENUS_QUALIFIERS = ("candidatus", "unclassified", "uncultured")


def genus_name(name: str) -> str:
    """The genus of an organism name, as mGrowthDB writes the name (not NCBI's lineage): its first word
    after any qualifier ("Candidatus Arthromitus" -> Arthromitus, "unclassified Bacteroides" ->
    Bacteroides). NCBI's brackets stay: "[Clostridium] scindens" is placed outside Clostridium, so its
    genus is [Clostridium], apart from Clostridium itself (Karoline, 2026-09-28)."""
    words = (name or "").split()
    while words and words[0].lower() in GENUS_QUALIFIERS:
        words = words[1:]
    if not words:
        return "unknown"
    first = words[0]
    if first.startswith("[") and first.endswith("]"):
        return "[" + first[1:-1].capitalize() + "]"
    return first.capitalize()


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
    taxon_id: str = ""            # NCBI taxon id of the strain, as mGrowthDB records it
    species: str = ""             # genus and species from the name: the key to merge with species-level networks
    identity: str = ""            # what the id rests on: "ncbi" (the taxon id), "name" (genus and species),
    #                               or "genus" (a node that merges every strain of a genus)


@dataclass(frozen=True)
class Edge:
    """A directed, condition-specific interaction with edge-level provenance."""

    source: str                   # Node.id of the actor
    target: str                   # Node.id of the affected organism
    effect: str                   # one of EFFECTS
    strength: float | None = None       # e.g. a growth log-ratio
    # The three numbers of the test, in one direction each (Karoline, 2026-10-03): p_value is the raw
    # value of whatever test the derivation ran, which `meta.statistics.test` names (Welch's t-test on the
    # per-replicate log2 values for the specified comparison), q_value the same after correction for
    # multiple testing, and significance -log10(q_value), so that a larger significance means stronger
    # evidence and a continuous style can map it.
    significance: float | None = None   # -log10(q_value): larger is stronger, 0 at q = 1
    q_value: float | None = None        # p_value corrected for multiple testing (Benjamini-Hochberg or -Yekutieli)
    p_value: float | None = None        # the unadjusted p-value the correction started from
    weight: float | None = None         # |strength|, always positive, for widths and layouts
    effect_over_sd: float | None = None  # |strength| / sd, the quantity the absence threshold cuts
    status: str | None = None           # one of STATUSES, or None when undetermined (no spread)
    condition: str = ""           # the experimental condition (interactions are condition-specific)
    method: str = ""              # how the interaction was quantified
    study_ids: tuple = ()         # the studies supporting THIS edge (edge-level attribution)
    sd: float | None = None       # standard deviation of the strength, the spread of a single comparison
    se: float | None = None       # standard error of the strength, from the replicate spread
    n_with: int | None = None     # replicates with the source present
    n_without: int | None = None  # replicates with the source absent
    outcome: str | None = None    # one of OUTCOMES, or None when the deriver does not report one
    metric: str = ""              # the growth property compared (for example auc)
    quality: tuple = ()           # QUALITY_FLAGS that make the edge low quality; empty means no issue found
    notes: tuple = ()             # informative remarks that do not disqualify (an excluded outlier)
    evidence: str | None = None   # one of EVIDENCE, or None when unknown
    community: tuple = ()         # Node ids of the community the edge was derived from, when applicable
    cautions: tuple = ()          # CAUTIONS: shown to the reader, without making the edge low quality
    experiments: tuple = ()       # ids of the experiments whose replicates the edge compares (its origin)
    cultivation_mode: str = ""    # batch, chemostat, and so on, as mGrowthDB records it
    medium: str = ""              # the growth medium the comparison ran in, as mGrowthDB names it (#113)
    # The partner's abundance over the target's growth window, in the co-cultures this arc compares: the
    # x_j* a gLV coefficient divides by (#118). None when the partner was not measured there.
    partner_abundance: float | None = None
    partner_abundance_unit: str = ""      # the abundance unit it was measured in, never converted
    partner_abundance_n: int | None = None  # co-culture replicates behind the median
    # The metric itself in each set, which `strength` is the log2 ratio of: a set that did not grow has 0
    # here, so a censored pair is a measurement rather than a floor (#123).
    metric_with: float | None = None
    metric_without: float | None = None
    target_capacity: float | None = None       # the target's own plateau in the co-culture
    target_capacity_unit: str = ""
    target_capacity_n: int | None = None
    # A censored comparison has no ratio, so its cell holds a measured bound from the no-growth rule
    # instead of a stated extreme: at least this much facilitation, or at most this much inhibition (#129).
    strength_bound: float | None = None
    bound_rule: str = ""
    # What a derivation that fits the row rather than comparing sets has to say for itself (#127): the
    # coefficient it fitted, in 1/(time x abundance), and how well that fit was determined.
    coefficient: float | None = None
    coefficient_unit: str = ""
    fit_r2: float | None = None
    # the same row with every partner's effect set to zero: the line a fitted row has to beat to be a
    # measurement of an interaction rather than of the organism's own growth (#142 item 9)
    fit_null_r2: float | None = None
    fit_condition: float | None = None
    # the coefficient's own spread over the co-culture replicates, the replicates behind it, and the
    # monoculture stage's contribution on its own design: two disjoint designs rather than one mixed set,
    # so a reader can see which stage the uncertainty comes from (#142 item 2)
    coefficient_sd: float | None = None
    coefficient_n: int | None = None
    coefficient_sd_from_rate_stage: float | None = None
    # the two halves of `se`, and how the monoculture stage was resampled for the second
    se_replicates: float | None = None
    se_rate_stage: float | None = None
    rate_stage_method: str = ""
    rate_stage_n: int | None = None
    merged_arcs: int | None = None  # arcs merged into this one (register item 14), None when not merged
    strength_range: tuple = ()    # (lowest, highest) log2 mean of the merged arcs
    supporting_pairs: int | None = None  # with genus merging: the distinct species (or strain) pairs behind it
    merged_pairs: tuple = ()      # with genus merging: those pairs, as "source -> target"

    def validate(self) -> list:
        problems = []
        if self.effect not in EFFECTS:
            problems.append(f"edge {self.source}->{self.target}: effect {self.effect!r} not in {EFFECTS}")
        if self.status is not None and self.status not in STATUSES:
            problems.append(f"edge {self.source}->{self.target}: status {self.status!r} not in {STATUSES}")
        if self.weight is not None and self.weight < 0:
            problems.append(f"edge {self.source}->{self.target}: weight {self.weight} is negative")
        for flag in self.quality:
            if flag not in QUALITY_FLAGS:
                problems.append(f"edge {self.source}->{self.target}: quality flag {flag!r} not in {QUALITY_FLAGS}")
        for flag in self.cautions:
            if flag not in CAUTIONS:
                problems.append(f"edge {self.source}->{self.target}: caution {flag!r} not in {CAUTIONS}")
        if self.outcome is not None and self.outcome not in OUTCOMES:
            problems.append(f"edge {self.source}->{self.target}: outcome {self.outcome!r} not in {OUTCOMES}")
        if self.evidence is not None and self.evidence not in EVIDENCE:
            problems.append(f"edge {self.source}->{self.target}: evidence {self.evidence!r} not in {EVIDENCE}")
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
        # a field this reader does not know is dropped for every record kind, not only for edges: Node
        # and Study raised on one, so the 0.2.0-against-0.3.0 failure stayed armed for the next release
        # that adds a node or study field (#142 item 10)
        known_nodes = {f.name for f in fields(Node)}
        known_studies = {f.name for f in fields(Study)}
        known = {f.name for f in fields(Edge)}
        for s in d.get("studies", []):
            net.add_study(Study(**{k: v for k, v in s.items() if k in known_studies}))
        for n in d.get("nodes", []):
            net.add_node(Node(**{k: v for k, v in n.items() if k in known_nodes}))
        for e in d.get("edges", []):
            # a field this reader does not know is dropped rather than raising, so a newer document is
            # read as far as it can be: Edge(**e) is what made 0.2.0 fail on a 0.3.0 network
            e = {k: v for k, v in e.items() if k in known}
            e["study_ids"] = tuple(e.get("study_ids", ()))
            e["community"] = tuple(e.get("community", ()))
            e["quality"] = tuple(e.get("quality", ()))
            e["notes"] = tuple(e.get("notes", ()))
            e["cautions"] = tuple(e.get("cautions", ()))
            e["experiments"] = tuple(e.get("experiments", ()))
            e["strength_range"] = tuple(e.get("strength_range", ()))
            e["merged_pairs"] = tuple(e.get("merged_pairs", ()))
            net.add_edge(Edge(**e))
        return net
