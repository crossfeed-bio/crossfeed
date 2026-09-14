# Contributing to crossfeed

crossfeed is a small open collaboration between Syntropa and the KU Leuven Laboratory of Molecular
Bacteriology. Issues and pull requests are welcome.

## Development setup

```
git clone https://github.com/crossfeed-bio/crossfeed
cd crossfeed
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before you open a pull request

Run the same two checks CI runs, and make sure both pass:

```
pytest -q
python checks/gate.py
```

`checks/gate.py` is the guardrail. It blocks committed secrets and any raw or pulled experimental data
(see `docs/DATA_GOVERNANCE.md`). Never commit data pulled from mGrowthDB or shared by a collaborator; only
the small synthetic fixtures under `tests/fixtures/` belong in the repository.

## Scope of a change

- The interaction derivation (`src/crossfeed/derive.py`) is a provisional baseline. Changes to the
  comparison method, the growth metric, or the significance test are scientific decisions for the
  collaboration: please open an issue to discuss before implementing.
- The neutral network model (`src/crossfeed/model.py`) is the contract downstream tools read. Keep it
  backward compatible where you can, and keep every edge carrying at least one supporting study (the
  edge-level attribution).

## Style

Keep pull requests small and focused, and match the surrounding code.
