test: clean
	python -m pytest --verbose
coverage:
	python -m pytest --cov-report html --cov coopy
lint:
	python -m ruff check .
	python -m ruff format --check .
format:
	python -m ruff check --fix .
	python -m ruff format .
clean:
	@rm -rf build/
	@rm -rf htmlcov/
	@rm -rf dist/
	@rm -rf *egg-info/
	@rm -f coopy.log*
	@find . -name '*.py[co,log,dat]' | xargs rm -f
	@find . -name '__pycache__' | xargs rm -rf
