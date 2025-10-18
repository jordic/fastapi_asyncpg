from async_asgi_testclient import TestClient
from fastapi import Depends
from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi_asyncpg import configure_asyncpg
from fastapi_asyncpg import sql
from pytest_docker_fixtures import images
from typing import Optional

import pydantic as pd
import pytest
import asyncio

images.configure("postgresql", "postgres", "11.1", env={"POSTGRES_DB": "test_db"})

pytestmark = pytest.mark.asyncio


class KeyVal(pd.BaseModel):
    key: str
    value: str


SCHEMA = """
    DROP TABLE IF EXISTS keyval;
    CREATE TABLE keyval (
        key varchar,
        value varchar,
        UNIQUE(key)
    );
"""


@pytest.fixture(scope="function")
async def asgiapp(pg):
    host, port = pg
    url = f"postgresql://postgres@{host}:{port}/test_db"
    app = FastAPI()
    bdd = configure_asyncpg(app, url, min_size=1, max_size=2)

    @bdd.on_init
    async def on_init(conn):
        await conn.execute(SCHEMA)

    @app.post("/", response_model=KeyVal)
    async def add_resource(data: KeyVal, db=Depends(bdd.connection)):
        result = await db.fetchrow(
            """
            INSERT into keyval values ($1, $2) returning *
        """,
            data.key,
            data.value,
        )
        return dict(result)

    @app.get("/transaction")
    async def with_transaction(q: Optional[int] = 0, db=Depends(bdd.transaction)):
        for i in range(10):
            await db.execute("INSERT INTO keyval values ($1, $2)", f"t{i}", f"t{i}")
            if q == 1:
                raise HTTPException(412)
        return dict(result="ok")

    @app.get("/{key:str}", response_model=KeyVal)
    async def get_resouce(key: str, db=Depends(bdd.connection)):
        result = await db.fetchrow(
            """
            SELECT * from keyval where key=$1
        """,
            key,
        )
        if result:
            return dict(result)

    yield app, bdd


async def test_dependency(asgiapp):
    app, db = asgiapp
    async with TestClient(app) as client:
        res = await client.post("/", json={"key": "test", "value": "val1"})
        assert res.status_code == 200
        res = await client.get("/test")
        assert res.status_code == 200
        assert res.json()["key"] == "test"
        assert res.json()["value"] == "val1"


async def test_transaction(asgiapp):
    app, _ = asgiapp
    async with TestClient(app) as client:
        res = await client.get("/transaction")
        assert res.status_code == 200
        async with app.state.pool.acquire() as db:
            await sql.count(db, "keyval") == 10


async def test_transaction_fails(asgiapp):
    app, _ = asgiapp
    async with TestClient(app) as client:
        res = await client.get("/transaction?q=1")
        assert res.status_code == 412
        async with app.state.pool.acquire() as db:
            await sql.count(db, "keyval") == 0


async def test_pool_releases_connections(asgiapp):
    app, db = asgiapp
    async with TestClient(app) as client:
        res = await client.post("/", json={"key": "test", "value": "val1"})
        assert res.status_code == 200
        tasks = []
        for i in range(20):
            tasks.append(client.get("/test"))

        await asyncio.gather(*tasks)
        async with app.state.pool.acquire() as db:
            result = await db.fetchval("SELECT sum(numbackends) FROM pg_stat_database;")
            assert result == 2
