# Reproducible commands. `make check` runs everything CI runs.
.PHONY: install test gate lint check demo schema

install:
	pip install -e ".[dev]"

test:
	pytest -q

gate:
	python checks/gate.py

lint:
	ruff check .

check: lint gate test

demo:
	python -m crossfeed derive SMGDB00000004 --fixture tests/fixtures/example_interactions.json

schema:
	python -m crossfeed schema
