.PHONY: format lint test test-js precommit

format:
	black .
	prettier --write app/static/js/**/*.js app/static/css/**/*.css

lint:
	flake8
	eslint 'app/static/js/**/*.js'

test:
	pytest

test-js:
	npm test

precommit:
	pre-commit run --all-files
