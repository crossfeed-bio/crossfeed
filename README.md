# crossfeed

[![ci](https://github.com/crossfeed-bio/crossfeed/actions/workflows/ci.yml/badge.svg)](https://github.com/crossfeed-bio/crossfeed/actions/workflows/ci.yml)
[![license: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**crossfeed** turns experimentally grounded microbial co-growth data from
[mGrowthDB](https://mgrowthdb.gbiomed.kuleuven.be/) into directed interaction networks, in a
neutral and openly citable format that downstream tools (such as Syntropa and microbetag) can
consume.

It is a thin client: it pulls from mGrowthDB and emits a network. Nothing to host, nothing to pay
for on a shared server. A well-run repository, one per contributor, is all it needs.

## What it does

Given a set of query organisms, crossfeed builds an interaction network on the fly from mGrowthDB
co-growth measurements. Each edge is a directed, condition-specific interaction (facilitation,
inhibition, or neutral) with its strength, its significance, and the experimental condition it holds
in. Every edge carries its provenance: the study or studies it was derived from, so attribution
resolves at the edge level.

A first slice targets the *Faecalibacterium prausnitzii* to *Blautia hydrogenotrophica* pair, shown
feeding Syntropa, as the concrete demonstration of the seam.

## Status

The mGrowthDB API client is wired against the live REST API (`src/crossfeed/mgrowthdb.py`), and the FP/BH
first slice runs end to end on real published data. The neutral network model, the edge-level attribution,
and the guardrails are in place and tested.

```
pip install -e ".[dev]"

# any study, live from the mGrowthDB API (provisional baseline)
python -m crossfeed derive SMGDB00000004 --live

# the named FP/BH first slice, offline from the bundled fixture
python -m crossfeed.slices.fp_bh --fixture tests/fixtures/example_interactions.json

# validate a network document against the neutral-format schema
python -m crossfeed validate network.json

# the tests and the guardrail gate (both run in CI)
pytest -q
python checks/gate.py
```

The interaction DERIVATION is a documented, PROVISIONAL baseline (`src/crossfeed/derive.py`): it compares
a strain's growth alone vs with a partner (log2 growthRate, pairwise co-cultures only) and skips what the
data does not cleanly support, but the comparison method (the growth metric, reading a per-strain signal
inside a community, the significance test) is a scientific choice still to be scoped with the KU Leuven
side. On the published three-species study SMGDB00000004 the baseline already recovers a sensible signal:
Blautia hydrogenotrophica facilitating Faecalibacterium prausnitzii, consistent with hydrogen and formate
cross-feeding.

## How interactions are derived (provisional baseline)

An interaction is inferred by comparing a strain's growth alone against its growth with a partner, under
one condition. The current baseline (`src/crossfeed/derive.py`) uses log2 of the per-strain growth-rate
ratio (co-culture over monoculture), on two-member co-cultures only, and marks every edge qualitative (no
significance test yet). It skips any pair the data does not cleanly support rather than inventing a value.

A caveat is recorded on every edge: in the demonstration study the monoculture growth is measured by flow
cytometry or optical density while the per-strain co-culture growth is measured by qPCR, so the direction
of an interaction is dependable but the magnitude is provisional. The comparison method, the growth
metric, the per-strain signal inside a community, and the significance test remain the scientific piece to
be scoped with the KU Leuven side.

## Guardrails

Discipline is a feature here. Every commit and every CI run passes the same self-contained gate
(`checks/gate.py`): no committed secrets, no raw or pulled data (only the synthetic fixtures under
`tests/fixtures/`), no local-machine paths, imports that resolve to the standard library or crossfeed
itself, a documented house style, and a schema contract that keeps the shipped
`schema/interaction_network.schema.json` in step with the code. The tests run on Python 3.10 to 3.12.
Contributors get the same checks locally with `pre-commit install`; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Attribution and data governance

mGrowthDB is open, so crossfeed pulls from it directly. Per-study licenses are respected by citing
every study that supports a network at the edge level, rather than bundling. Unpublished collaborator
data is used only for the agreed analysis and is never ingested into any downstream corpus. See
[docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).

## Collaboration

A joint open source project of Syntropa and the KU Leuven Lab of Molecular Bacteriology
(K. Faust, H. Zafeiropoulos). Contributions welcome.

## License

Apache-2.0. See [LICENSE](LICENSE).
