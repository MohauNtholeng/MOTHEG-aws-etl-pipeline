.PHONY: install-dev lint test format check

install-dev:
	python -m pip install -e .[dev]

lint:
	ruff check src tests

test:
	pytest -q

format:
	ruff check --fix src tests

check: lint test
