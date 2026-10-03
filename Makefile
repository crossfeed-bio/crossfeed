# Reproducible commands. `make check` runs everything CI runs.
.PHONY: install test gate lint check demo schema legend r-check

install:
	pip install -e ".[dev]"

test:
	pytest -q

gate:
	python checks/gate.py

lint:
	ruff check .

check: lint gate test

# the R companion package (r/): built and checked the way CRAN does, where R is installed
r-check:
	R CMD build r
	R CMD check --no-manual grownet_*.tar.gz
	rm -rf grownet_*.tar.gz grownet.Rcheck

demo:
	python -m grownet derive SMGDB00000004 --fixture tests/fixtures/example_interactions.json

schema:
	python -m grownet schema

legend:
	python -c "from grownet.legend import legend_svg; open('docs/legend.svg', 'w').write(legend_svg())"
