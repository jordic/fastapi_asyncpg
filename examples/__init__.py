from fastapi import FastAPI
from fastapi import Depends
from fastapi_asyncpg import configure_asyncpg

import pydantic as pd

app = FastAPI()


db = configure_asyncpg(app, "postgresql://postgres:postgres@localhost/db")


class Demo(pd.BaseModel):
    key: str
    value: str


class DemoObj(Demo):
    demo_id: int


@db.on_init
async def initialize_db(db):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS demo (
            demo_id serial primary key,
            key varchar not null,
            value varchar not null,
            UNIQUE(key)
        );
    """
    )


@app.post("/", response_model=DemoObj)
async def add_resource(data: Demo, db=Depends(db.connection)):
    """
    Add a resource to db:
    curl -X POST -d '{"key": "test", "value": "asdf"}' \
        http://localhost:8000/
    """
    result = await db.fetchrow(
        """
        INSERT into demo values (default, $1, $2) returning *
    """,
        data.key,
        data.value,
    )
    return dict(result)


@app.get("/{key:str}", response_model=DemoObj)
async def get_resouce(key: str, db=Depends(db.connection)):
    result = await db.fetchrow(
        """
        SELECT * from demo where key=$1
    """,
        key,
    )
    return dict(result)
