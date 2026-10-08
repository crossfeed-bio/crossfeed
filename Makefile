# Reproducible commands. `make check` runs everything CI runs.
.PHONY: install test gate lint check demo schema legend r-check release-check

install:
	pip install -e ".[dev]"

test:
	pytest -q

gate:
	python checks/gate.py

lint:
	ruff check .

# the release gate runs on every build too, with no tag: it checks that the version agrees across
# pyproject.toml, the package, CITATION.cff and r/DESCRIPTION and that the citation date matches the
# changelog heading, which used to be found only when somebody pushed the tag (#142 item 15)
release-check:
	python packaging/check_release.py

check: lint gate test release-check

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
