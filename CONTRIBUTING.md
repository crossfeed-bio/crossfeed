# Contributing to crossfeed

crossfeed is a small open collaboration between Syntropa and the KU Leuven Laboratory of Molecular
Bacteriology. Issues and pull requests are welcome. Discipline is deliberate here: the checks below run
the same way for everyone, in CI and before every commit, so the repository stays honest and portable.

## Development setup

```
git clone https://github.com/crossfeed-bio/crossfeed
cd crossfeed
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install            # optional: run the checks on every commit (pip install pre-commit first)
```

## Before you open a pull request

Run the same checks CI runs, and make sure all pass. `make check` runs all three:

```
ruff check .              # lint
python checks/gate.py     # the guardrail gate
pytest -q                 # the tests
```

If you enabled `pre-commit install`, these run automatically on every commit.

## The guardrail gate

`checks/gate.py` is self-contained (no dependency on any private path) and blocks a class of mistake per
check: committed secrets, raw or pulled experimental data (only the synthetic fixtures under
`tests/fixtures/` belong in the repository, never data pulled from mGrowthDB or shared by a collaborator),
absolute local-machine paths, imports that are not the standard library or crossfeed, the house style,
and a schema contract. See [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md) for the data rules.

House style, checked on documentation: ASCII punctuation (use a comma, colon, parentheses, or the word
"to" for a range rather than an em dash or en dash), US spelling, and direct prose with no hedging
caveats. Keep it, and the check stays quiet.

## Adding a derivation method

The comparison method (the growth metric, how to read a per-strain signal inside a community, the
significance test) is the scientific choice this collaboration exists to make. It plugs in through the
`Deriver` interface in `src/crossfeed/derive.py`: subclass `Deriver`, implement `derive(study, exps)` to
return `(records, skipped)`, and it slots into `derive_interactions` and the CLI without touching the
model or the pipeline. `BaselineDeriver` is the provisional placeholder. Record what the data does not
support in `skipped` rather than inventing a value. Changes to the method are scientific decisions:
please open an issue to discuss before implementing.

## The neutral format is a contract

`src/crossfeed/model.py` and the JSON Schema at `schema/interaction_network.schema.json` are the contract
downstream tools read. Keep it backward compatible where you can, keep every edge carrying at least one
supporting study (the edge-level attribution), and regenerate the schema file from the code if you change
it (`python -m crossfeed schema --out schema/interaction_network.schema.json`). The gate fails if the
file and the code drift, or if an emitted network does not validate against its own schema.

## Style and scope

Keep pull requests small and focused, match the surrounding code, and note user-facing changes in
[CHANGELOG.md](CHANGELOG.md).
