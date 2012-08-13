test:
	py.test --verbose .
coverage:
	py.test --cov-report html --cov .
