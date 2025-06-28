.PHONY: format format-yaml lint test test-js precommit setup

format:
	uv run black .
	prettier --write app/static/js/**/*.js app/static/css/**/*.css

format-yaml:
        prettier --write '*.yml'

lint:
	uv run flake8
	uv run ruff check --exit-zero .
	eslint 'app/static/js/**/*.js'

test:
	uv run pytest

test-js:
	npm test

precommit:
	uv run pre-commit run --all-files

setup:
        ./scripts/setup_env.sh
