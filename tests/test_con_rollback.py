from async_asgi_testclient import TestClient
from fastapi import Depends
from fastapi import FastAPI
from fastapi_asyncpg import configure_asyncpg
from fastapi_asyncpg import create_pool_test
from fastapi_asyncpg import sql
from pathlib import Path
from pytest_docker_fixtures import images

import json
import pydantic as pd
import pytest
import typing

pytestmark = pytest.mark.asyncio

dir = Path(__file__).parent

images.configure(
    "postgresql", "postgres", "11.1", env={"POSTGRES_DB": "test_db"}
)


@pytest.fixture
async def pool(pg):
    host, port = pg
    url = f"postgresql://postgres@{host}:{port}/test_db"

    async def initialize(conn):
        await sql.load_sqlfile(conn, dir / "data.sql")

    pool = await create_pool_test(url, initialize=initialize)
    yield pool
    if pool._conn.is_closed():
        return
    await pool.release()


async def test_testing_pool_works(pool):
    async with pool.acquire() as db:
        await sql.insert(db, "test", {"item": "test", "val": "value"})
        assert await sql.count(db, "test") == 1


async def test_the_db_is_empty_again(pool):
    async with pool.acquire() as db:
        assert await sql.count(db, "test") == 0


async def test_sql(pool):
    """ sql.py contains poor man sql helpers to work with sql and asyncpg """
    async with pool.acquire() as db:
        res = await sql.insert(db, "test", {"item": "test", "val": "value"})
        result = await sql.get(db, "test", "id=$1", args=[res["id"]])
        assert dict(res) == dict(result)
        elements = await sql.select(db, "test")
        assert len(elements) == 1
        assert dict(elements[0]) == dict(result)
        elements = await sql.select(db, "test", condition="id=$1", args=[1])
        assert dict(elements[0]) == dict(result)
        updated = await sql.update(db, "test", {"id": 1}, {"val": "value2"})
        assert dict(updated) != dict(result)
        assert updated["val"] == "value2"

        res = await db.fetchrow(sql.query_to_json("SELECT * from test", "row"))
        data = json.loads(res["row"])
        assert data[0] == dict(updated)
        await sql.delete(db, "test", "id=$1", args=[1])
        assert await sql.count(db, "test") == 0


async def test_app_with_fixture(pool):
    """
    Things are more interesting when you want to test some
    data, and you want to setup the db state
    """
    async with pool.acquire() as db:
        # we setup the db at a desired state
        await sql.insert(db, "test", {"item": "test", "val": "value"})

    app = FastAPI()
    bdd = configure_asyncpg(app, "", pool=pool)

    @app.get("/")
    async def get(conn=Depends(bdd.connection)):
        res = await conn.fetch("SELECT * from test")
        return [dict(r) for r in res]

    async with TestClient(app) as client:
        res = await client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data[0]["item"] == "test"
        assert data[0]["val"] == "value"


# we can go a bit crazy with pydantic
# and simulate an orm wiht it
# this could be a mixin, that you add to your schemas
# also you need some __property__ with your primary key
# and check it
class Schema(pd.BaseModel):
    __tablename__ = "test"

    item: str
    val: str
    id: typing.Optional[int]

    async def save(self, db):
        if self.id is None:
            result = await sql.insert(
                db, self.__tablename__, self.dict(exclude_unset=True)
            )
            self.id = result["id"]
        else:
            result = await sql.update_by(
                db,
                self.__tablename__,
                {"id": self.id},
                self.dict(exclude=["id"]),
            )
            for key, val in dict(result):
                setattr(self, key, val)


async def test_experimental(pool):
    item = Schema(item="asdf", val="xxxx")
    async with pool.acquire() as db:
        await item.save(db)
        assert await sql.count(db, "test") == 1
