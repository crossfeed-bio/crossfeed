# crossfeed

[![ci](https://github.com/crossfeed-bio/crossfeed/actions/workflows/ci.yml/badge.svg)](https://github.com/crossfeed-bio/crossfeed/actions/workflows/ci.yml)
[![license: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**crossfeed** turns experimentally grounded microbial co-growth data from
[mGrowthDB](https://mgrowthdb.gbiomed.kuleuven.be/) into directed interaction networks, in a neutral and
openly citable format that downstream tools (such as Syntropa and microbetag) can consume.

It is a thin client: it pulls from mGrowthDB and emits a network. Nothing to host, nothing to pay for on a
shared server, no runtime dependencies (the client is pure Python standard library). A well-run
repository, one per contributor, is all it needs.

This README is the full guide: install and run it, read and validate the output format, and plug in your
own derivation method. Nothing here needs another document to follow.

## Contents

- [Install](#install)
- [Quickstart](#quickstart)
- [What it does](#what-it-does)
- [The command line](#the-command-line)
- [The local page](#the-local-page)
- [The output format](#the-output-format)
- [Plug in your own method](#plug-in-your-own-method)
- [How the provisional baseline works](#how-the-provisional-baseline-works)
- [Guardrails](#guardrails)
- [Attribution and data governance](#attribution-and-data-governance)
- [License](#license)

## Install

Python 3.10 or newer.

```
git clone https://github.com/crossfeed-bio/crossfeed
cd crossfeed
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Quickstart

Run the first slice offline, from the bundled synthetic fixture (no network), to see a network:

```
python -m crossfeed derive SMGDB00000004 --fixture tests/fixtures/example_interactions.json
```

Run it live against mGrowthDB:

```
python -m crossfeed derive SMGDB00000004 --live
```

On the published study SMGDB00000004 the provisional baseline recovers Blautia hydrogenotrophica
facilitating Faecalibacterium prausnitzii, consistent with hydrogen and formate cross-feeding. Write the
result to a file and check it against the format:

```
python -m crossfeed derive SMGDB00000004 --live --out network.json
python -m crossfeed validate network.json
```

## What it does

Given a set of query organisms, crossfeed builds an interaction network on the fly from mGrowthDB
co-growth measurements. Each edge is a directed, condition-specific interaction (facilitation, inhibition,
or neutral) with its strength, its significance, and the experimental condition it holds in. Every edge
carries its provenance: the study or studies it was derived from, so attribution resolves at the edge
level.

The pipeline has three seams: a client that pulls raw growth from mGrowthDB (`crossfeed.mgrowthdb`), a
derivation step that turns growth into interaction records (`crossfeed.derive`, the part you will
replace), and the neutral network model the records map into (`crossfeed.model`). A first slice targets
the Faecalibacterium prausnitzii and Blautia hydrogenotrophica pair, shown feeding Syntropa, as the
concrete demonstration of the seam.

## The command line

```
python -m crossfeed derive STUDY [--live | --fixture FILE] [--deriver MODULE:CLASS] [--format json|graphml] [--out FILE]
python -m crossfeed validate FILE
python -m crossfeed schema [--out FILE]
```

- `derive STUDY --live` fetches the study from the mGrowthDB API and derives interactions.
- `derive STUDY --fixture FILE` runs the downstream seam offline from a JSON list of interaction records.
- `derive STUDY --live --deriver MODULE:CLASS` runs your own method instead of the baseline (see below).
- `--format graphml` emits GraphML (for Cytoscape, igraph, networkx, Gephi) instead of the neutral JSON.
- `--out FILE` writes the network to a file instead of stdout; attribution and skipped pairs print to
  stderr.
- `validate FILE` checks a network document against the neutral-format schema and exits non-zero if it
  fails.
- `schema` prints the JSON Schema (or writes it with `--out`).

A `crossfeed` console command is installed too, so `crossfeed derive ...` works after `pip install`.

## The local page

Prefer clicking to typing commands? `python -m crossfeed gui` starts a small page on your own machine and
opens it in the browser:

```
python -m crossfeed gui
```

Type species names (or NCBI taxon ids), one per line, and press "Find interactions". crossfeed resolves
the names to taxon ids from mGrowthDB's own strain records, finds the studies holding them, derives the
interactions, and shows them as a table with downloads for JSON and GraphML. Every setting sits behind
"Advanced settings" with the same defaults the command line uses.

The page is served from the standard library on 127.0.0.1 with a token in its URL, renders in Python with
no JavaScript, and uploads nothing: the data is pulled from mGrowthDB to your machine, and the results
stay there.

## The output format

`derive` emits one JSON document: the neutral interaction network. It is the contract downstream tools
read, and it is pinned by a JSON Schema at
[`schema/interaction_network.schema.json`](schema/interaction_network.schema.json).

```json
{
  "schema": "crossfeed.interaction_network/v0",
  "meta": {"source_db": "mGrowthDB (live)", "study_id": "SMGDB00000004"},
  "nodes": [
    {"id": "blautia hydrogenotrophica", "name": "Blautia hydrogenotrophica", "taxonomy": "", "model_ref": ""},
    {"id": "faecalibacterium prausnitzii", "name": "Faecalibacterium prausnitzii", "taxonomy": "", "model_ref": ""}
  ],
  "edges": [
    {
      "source": "blautia hydrogenotrophica",
      "target": "faecalibacterium prausnitzii",
      "effect": "facilitation",
      "strength": 1.28,
      "significance": 0.064,
      "p_value": 0.032,
      "condition": "FP/BH co-culture",
      "method": "crossfeed baseline v0 (PROVISIONAL): ...",
      "study_ids": ["SMGDB00000004"],
      "sd": 0.43,
      "se": 0.25,
      "n_with": 3,
      "n_without": 3,
      "outcome": "quantified",
      "metric": "auc",
      "quality": [],
      "notes": [],
      "evidence": "biculture",
      "community": ["blautia hydrogenotrophica", "faecalibacterium prausnitzii"]
    }
  ],
  "studies": [
    {"id": "SMGDB00000004", "citation": "Integrated culturing, modeling ...", "license": "", "url": "..."}
  ]
}
```

`effect` is the direction, one of `facilitation`, `inhibition`, `neutral`; the default derivation uses
`neutral` only for a mean of exactly zero, which has no direction and is always absent (see below), and it
remains for the retired baseline and existing files. `strength` and `significance` are your
method's numbers (or `null`). `study_ids` on every edge is the edge-level attribution and must carry at
least one study. `sd` and `se` are the standard deviation and standard error of the strength across
replicates, with `n_with` and `n_without` the replicate counts behind it, and `metric` the growth property compared (`auc` by default,
`max` selectable). `outcome` says what the comparison could establish: `quantified`, `obligate` (the
target grows only with the source present), `abolished` (only without it), or `no_growth`. For an
obligate or abolished edge, the count on the side without growth is its replicates without growth. A
comparison whose set was emptied by exclusions (every replicate spiked, for example) says nothing about
growth; it is skipped with a reason rather than read as obligate. `evidence`
says what the edge was derived from: `biculture` (a species alone against
the same species with one partner, a direct interaction) or `dropout` (a full community against the
community without the source species, so the effect is not necessarily direct; strictly a hyper-arc,
kept as an arc), or `null` when unknown; `community` lists the node ids of the community it came from.
`experiments` lists the ids of the mGrowthDB experiments whose replicates the edge compares, so edges that
share replicates (every drop-out arc of one design shares the full community) can be recognized.
These fields are optional, so documents without them stay valid.

**Drop-out designs.** A community of three or more members, together with experiments holding the same
community without one member under the same conditions, gives an arc from each removed member to each
remaining one. The arc is labeled `evidence: dropout` because the removed member may act through a third
species. Drop-out arcs are included by default; `--no-dropout` (or the matching advanced setting) leaves
them out. Experiments are pooled into one replicate set only when their conditions (cultivation mode and
the compartment records: medium, pH, temperature, gases, and so on) are identical, since interactions are
usually environmentally specific; under different conditions they give separate arcs. Because mGrowthDB
does not detail medium components well, their descriptions must also agree, apart from a trailing run
number ("All 1" and "All 2" pool; "with initial acetate" and "without initial acetate" do not).
Each arc is compared over its own window, the target's curves in the two sets, so one short curve
elsewhere in the design does not shorten every arc. A design does not
need every drop-out. mGrowthDB still measures the removed member in a drop-out experiment; that curve is
not used, and if it shows a positive signal the drop-out may not be clean, so its arcs are flagged
`removed_member_detected`. A larger community with no drop-out experiment is skipped, with a reason.

**How presence and absence are decided.** Every tested comparison is exported as an edge, and its
`status` says whether it counts as an interaction under the **absence threshold k**:

- `status` is `absent` when |log2 mean| < k × sd, and `present` otherwise. In words: an effect smaller than
  k standard deviations of its own spread is not treated as an interaction.
- The default is **k = 1**, which is the rule that the interval mean ± sd must stay on one side of zero.
  `--absence-threshold K` (or the matching advanced setting) changes it. **k = 0 marks nothing absent**, so
  every comparison is exported as present and the cut can be chosen later.
- `effect_over_sd` holds |log2 mean| / sd, the exact quantity the threshold cuts. In Cytoscape, a column
  filter keeping edges with `effect_over_sd` ≥ k reproduces the tool's rule for any k, so exporting with
  k = 0 and filtering in Cytoscape lets you watch how the network changes with the threshold.
- `weight` is |log2 mean|, always positive, for line widths and layouts. The sign stays in `effect` and
  `strength`.
- Example: an edge with log2 mean +0.53 and sd 0.91 has `effect_over_sd` 0.58, so it is absent at k = 1 and
  present at k = 0.5. An edge with −2.66 ± 2.38 has 1.12 and is present at k = 1.
- **Obligate** (the target grows only with the source present) and **abolished** (it grows only without
  it) are the extremes of facilitation and inhibition. They have no log2 ratio, so no `weight` and no
  `effect_over_sd`; they are always present and are drawn with their own style.
- A mean of exactly zero is always absent. A low-quality edge's `status` is `null` (undetermined) whatever
  its numbers, since low quality is never read as an absence; an edge with no spread estimate (a single
  replicate) is one such case and also has no `effect_over_sd`.
- Absent edges stay in the output. Hiding them is the display's job: the Cytoscape style hides `absent`
  edges by default, and the local page lists them in their own section. `meta.absence` records the rule,
  the k used, and how many edges it marked absent.

`quality` lists what makes an edge low quality: `single_replicate` (no spread can be estimated, so such an
edge carries no `sd`, `se` or test), `strains_pooled` (monocultures of different strains of one species were
pooled, until nodes are keyed by taxon id), `non_batch`, and `removed_member_detected` (a drop-out
experiment measured the member it should lack). A low-quality edge keeps the sign of its mean
and is never read as an absence. Low-quality edges are left out of the output by default
(`--include-low-quality`, or the matching advanced setting), and `meta.hidden` counts them.
`cautions` are shown without making an edge low quality: `two_replicates` marks an edge with exactly two
replicates on a side, whose sd rests on two values. Such an edge keeps its `status` and is exported.
`notes` inform without disqualifying, for example a replicate left out for an implausible spike. Every
comparison with at least two replicates per side also gets Welch's t-test on the per-replicate log2 values:
`p_value` is the raw value and `significance` the Benjamini-Hochberg adjusted one across all comparisons
tested in the derivation (`meta.statistics`). The test supports an edge when significant and decides
nothing: with few replicates, any of these results may change with more experiments.

## Plug in your own method

The derivation method is the scientific choice this collaboration exists to make: which growth metric, how
to read a per-strain signal inside a community, and the significance test. The options are laid out as a
menu in [docs/METHOD_NOTES.md](docs/METHOD_NOTES.md). Whatever you choose plugs in through one small
interface, the `Deriver`, and nothing else in the pipeline changes.

A `Deriver` is a class with one method, `derive(study, exps)`, that returns `(records, skipped)`. Here is
a complete one, with the record shape spelled out:

```python
from crossfeed.derive import Deriver

class MyDeriver(Deriver):
    name = "my-method"

    def derive(self, study, exps):
        # study is the mGrowthDB study dict; exps is the list of its experiment dicts
        # (communityStrains, bioreplicates -> measurementContexts -> subject/growthRate).
        # Return (records, skipped). Each record becomes one directed edge:
        records = [{
            "source": "partner_id",  "target": "focal_id",        # node ids            (required)
            "source_name": "Partner sp.", "target_name": "Focal sp.",  # display names   (optional)
            "effect": "facilitation",          # "facilitation" | "inhibition" | "neutral"
            "strength": 1.23,                  # your metric, any float, or None
            "significance": 0.01,              # a p-value, or None if the method is qualitative
            "condition": study.get("name", ""),
            "method": self.method,             # a short note on how the edge was computed
            "study_id": study["id"],           # edge-level attribution              (required)
        }]
        skipped = []   # list of (label, reason) for pairs the data did not cleanly support
        return records, skipped
```

Run your method live on any study, with no glue code:

```
python -m crossfeed derive SMGDB00000004 --live --deriver mymodule:MyDeriver
```

Test it offline before you touch the network. [`examples/custom_deriver.py`](examples/custom_deriver.py)
is a complete, runnable Deriver on synthetic data:

```
python examples/custom_deriver.py
```

and [`tests/test_deriver.py`](tests/test_deriver.py) shows how to unit-test a method with a fake client,
no network required. Changes to the method are scientific decisions, so please open an issue to discuss
before you implement one.

## How the derivation works

`ReplicateDeriver` (`src/crossfeed/derive.py`) is the default. It reads each replicate's measured growth
curve from mGrowthDB and compares replicate sets on the log2 scale, over the area under the curve by
default (`--metric max` for maximal abundance). Every edge therefore carries a spread, not just a number:
its mean, standard deviation, standard error, and the replicate counts behind each side.

Whether a comparison counts as an interaction follows that spread rather than a fixed cutoff on the
effect: it is `absent` when its effect is smaller than k standard deviations of its own spread
(|log2 mean| < k × sd, default k = 1, the mean ± sd rule), and `present` otherwise. There is no
"neutral edge": a comparison is either an interaction or the absence of one (Karoline). Absent comparisons
are kept as edges with `status` absent, so they can be shown and the threshold changed later, including in
Cytoscape on the `effect_over_sd` column. The section on the output format above spells out every case.

Edges that cannot be trusted are kept and labeled rather than dropped. `quality` says what is wrong with
an edge (a single replicate, or strains of one species pooled into one monoculture set) and such an edge
keeps the sign of its mean and is never reported as an absence of interaction. `notes` records what is
worth knowing without disqualifying it, such as a replicate left out because its curve carried an
implausible spike. Low-quality edges are computed and then hidden at output, with `--include-low-quality`
to show them; `meta.hidden` says how many were left out, so a network file never quietly under-reports.

Each comparison with at least two replicates per side also gets Welch's t-test on the per-replicate log2
values, reported as `p_value` and as `significance`, the Benjamini-Hochberg adjusted value over every
comparison tested in the derivation (`meta.statistics`). The test supports an edge when significant and
decides nothing: with two or three replicates a real effect often fails to reach significance, and any of
these results may change with more experiments.

Two things to read before trusting a magnitude. Where a study measures monoculture growth by flow
cytometry or optical density and per-strain co-culture growth by qPCR, each edge records both techniques
and flags the mismatch: a systematic offset between instruments enters the comparison, so near the
neutral band the sign can move and not only the size. And an edge computed from a single replicate
carries no sd or se at all, which is why it is flagged.

`BaselineDeriver` remains only as the retired placeholder, reachable with `--deriver`. The open method
choices, and who settled each, are in [docs/METHOD_NOTES.md](docs/METHOD_NOTES.md).

## Guardrails

Discipline is a feature here. Every commit and every CI run passes the same self-contained gate
(`checks/gate.py`): no committed secrets, no raw or pulled data (only the synthetic fixtures under
`tests/fixtures/`), no local-machine paths, imports that resolve to the standard library or crossfeed
itself, a documented house style, and a schema contract that keeps the shipped schema in step with the
code. The tests run on Python 3.10 to 3.12. Get the same checks locally with `make check`, or run them on
every commit with `pre-commit install`. See [CONTRIBUTING.md](CONTRIBUTING.md). Found a security issue?
Report it privately (see [SECURITY.md](SECURITY.md)), not in a public issue.

## Attribution and data governance

mGrowthDB is open, so crossfeed pulls from it directly. Per-study licenses are respected by citing every
study that supports a network at the edge level, rather than bundling. Unpublished collaborator data is
used only for the agreed analysis and is never ingested into any downstream corpus. See
[docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).

A joint open source project of Syntropa and the KU Leuven Laboratory of Molecular Bacteriology
(K. Faust, H. Zafeiropoulos). Contributions welcome.

## License

Apache-2.0. See [LICENSE](LICENSE).
