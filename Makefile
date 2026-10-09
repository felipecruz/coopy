test: clean
	python -m pytest --verbose
coverage:
	python -m pytest --cov-report html --cov coopy
clean:
	@rm -rf build/
	@rm -rf htmlcov/
	@rm -rf dist/
	@rm -rf *egg-info/
	@rm -f coopy.log*
	@find . -name '*.py[co,log,dat]' | xargs rm -f
	@find . -name '__pycache__' | xargs rm -rf
