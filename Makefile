.PHONY: format lint test test-js precommit setup

format:
	black .
	prettier --write app/static/js/**/*.js app/static/css/**/*.css

lint:
        flake8
        ruff check --exit-zero .
        eslint 'app/static/js/**/*.js'

test:
	pytest

test-js:
	npm test

precommit:
        pre-commit run --all-files

setup:
        ./scripts/setup_env.sh
