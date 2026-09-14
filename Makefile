# The same four checks CI runs, in the same order. Run `make check` before pushing.
#
# This target exists because the alternative failed twice: running the linter but forgetting
# the formatter, and running a locally installed tool older than the one CI installs. Both
# produced a red build on a change that was correct.
#
# Everything goes through `python -m` so the tools always come from the interpreter holding the
# project's dependencies, rather than from whatever happens to be first on PATH.

PYTHON ?= python3

.PHONY: help install check lint format typecheck test examples clean

help:
	@echo "install    install the package and dev tools"
	@echo "check      lint, format check, type check and test - exactly what CI runs"
	@echo "format     rewrite files to the canonical format"
	@echo "examples   run every example script"

install:
	$(PYTHON) -m pip install -e ".[dev]"

check: lint typecheck test

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

examples:
	@for script in examples/*.py; do echo "--- $$script"; $(PYTHON) "$$script" >/dev/null || exit 1; done
	@echo "all examples ran"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
