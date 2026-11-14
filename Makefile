.PHONY: all test lint regions fetch parse attention clean

PY ?= python
LIMIT ?= 0

all: test lint
	@echo '[ok] all targets passed'

install:
	$(PY) -m pip install -e '.[dev]'

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests scripts

regions:
	$(PY) scripts/build_regions.py

probe:
	$(PY) scripts/probe_portals.py

fetch:
	$(PY) -m gra.fetch --limit $(LIMIT)

parse:
	$(PY) -m gra.parse

attention:
	$(PY) -m gra.attention

clean:
	rm -rf data/interim logs .pytest_cache
