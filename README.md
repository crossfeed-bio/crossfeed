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

`effect` is one of `facilitation`, `inhibition`, `neutral`. `strength` and `significance` are your
method's numbers (or `null`). `study_ids` on every edge is the edge-level attribution and must carry at
least one study. `sd` and `se` are the standard deviation and standard error of the strength across
replicates, with `n_with` and `n_without` the replicate counts behind it, and `metric` the growth property compared (`auc` by default,
`max` selectable). `outcome` says what the comparison could establish: `quantified`, `obligate` (the
target grows only with the source present), `abolished` (only without it), or `no_growth`. `evidence`
says what the edge was derived from: `biculture` (a species alone against
the same species with one partner, a direct interaction) or `dropout` (a full community against the
community without the source species, so the effect is not necessarily direct; strictly a hyper-arc,
kept as an arc), or `null` when unknown; `community` lists the node ids of the community it came from.
Both fields are optional, so documents without them stay valid.

**How an interaction is decided.** A comparison is an edge when its mean plus or minus its standard
deviation stays on one side of zero: `facilitation` above, `inhibition` below. When that interval crosses
zero on data without quality issues there is no interaction, which is the absence of an edge, not a
"neutral edge": such comparisons are listed in the network's `meta.absent`, with the same numbers an edge
carries, and never in `edges`. `quality` lists what makes an edge low quality: `single_replicate` (no
spread can be estimated, so such an edge carries no `sd`, `se` or test), `strains_pooled` (monocultures of
different strains of one species were pooled, until nodes are keyed by taxon id), and `non_batch`. A
low-quality edge keeps the sign of its mean and is never read as an absence; low-quality edges are hidden
by default (`--include-low-quality`, or the matching advanced setting), and `meta.hidden` counts them.
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

## How the provisional baseline works

`BaselineDeriver` (`src/crossfeed/derive.py`) is a documented, provisional placeholder so the seam runs
end to end today. It uses log2 of the per-strain growth-rate ratio (co-culture over monoculture), on
two-member co-cultures only, and marks every edge qualitative (no significance test yet). It skips any
pair the data does not cleanly support rather than inventing a value.

A caveat is recorded on every edge: in the demonstration study the monoculture growth is measured by flow
cytometry or optical density while the per-strain co-culture growth is measured by qPCR, so the direction
of an interaction is dependable while the magnitude is provisional. The comparison method, the growth
metric, the per-strain signal inside a community, and the significance test are the pieces to scope
together; see [docs/METHOD_NOTES.md](docs/METHOD_NOTES.md).

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
