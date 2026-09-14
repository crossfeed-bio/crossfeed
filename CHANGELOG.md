# Changelog

All notable changes to crossfeed are recorded here. The format follows Keep a Changelog, and versions
stay in the 0.0.x range while the interface settles. A released version is a promise about content: a
tagged version is never reused for changed content.

## [0.0.2] (unreleased)

### Added
- A pluggable derivation seam (`crossfeed.derive.Deriver`): the comparison method is a drop-in strategy,
  with the provisional `BaselineDeriver` as one implementation. The agreed method arrives as another
  `Deriver` without touching the model or the pipeline.
- A generic command line (`python -m crossfeed derive|validate|schema`, and a `crossfeed` console script)
  that derives a network for any mGrowthDB study, validates a network document, or emits the schema.
- A published JSON Schema for the neutral format (`schema/interaction_network.schema.json`) plus a
  dependency-free `crossfeed.schema.validate_document`.
- mGrowthDB client hardening: in-memory and optional on-disk response caching, and retries with backoff
  on transient network failures and 5xx responses.
- An expanded guardrail gate (`checks/gate.py`) covering secrets, raw data, local-machine paths,
  self-contained imports, house style (ASCII punctuation, US spelling, no hedging caveats), and a schema
  contract check. A pre-commit hook and a Makefile run the gate, tests, and lint the same way CI does.

### Changed
- crossfeed now has no runtime dependencies: the client uses the standard library `urllib`, and the
  unused `requests` dependency was dropped.

## [0.0.1] (2026-09-14)

### Added
- Initial public release: the neutral interaction-network model with edge-level attribution, the live
  mGrowthDB API client, and the FP/BH first slice running on the published study SMGDB00000004 and
  recovering Blautia hydrogenotrophica facilitating Faecalibacterium prausnitzii.
