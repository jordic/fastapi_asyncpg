.PHONY: lint mypy test

lint:
	uv run --python 3.10 --extra dev ruff check . --fix
	uv run --python 3.10 --extra dev ruff format .
	mypy .

mypy:
	uv run --python 3.10 --extra dev mypy fastapi_asyncpg

test:
	uv run --python 3.9 --extra test pytest tests
	uv run --python 3.10 --extra test pytest tests
	uv run --python 3.11 --extra test pytest tests
	uv run --python 3.12 --extra test pytest tests
	uv run --python 3.13 --extra test pytest tests
