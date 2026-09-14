# crossfeed

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

Scaffold. The neutral network model, the edge-level attribution, and the guardrails are in place and
tested. The live mGrowthDB API client is the next step (see `src/crossfeed/mgrowthdb.py`, to be wired
against the [mGrowthDB API](https://mgrowthdb.readthedocs.io/en/latest/api.html)). You can exercise
the whole downstream seam today on a synthetic example:

```
pip install -e ".[dev]"
python -m crossfeed.slices.fp_bh --fixture tests/fixtures/example_interactions.json
pytest -q
python checks/gate.py
```

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
