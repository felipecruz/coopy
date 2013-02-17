test:
	py.test --verbose .
coverage:
	py.test --cov-report html --cov .
clean:
	@rm -rf build/
	@rm -rf htmlcov/
	@rm -rf dist/
	@rm -rf *egg-info/
	@rm coopy.log*
	@find . -name '*.py[co,log,dat]' -exec rm -f {} ';'
	@find . -name '__pycache__' -exec rm -rf {} ';'
