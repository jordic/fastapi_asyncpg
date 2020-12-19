.PHONY: isort black flake8 mypy

lint: isort black flake8 mypy

isort:
	isort fastapi_asyncpg

black:
	black fastapi_asyncpg/  -l 80

flake8:
	flake8 fastapi_asyncpg

mypy:
	mypy fastapi_asyncpg
