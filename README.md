# FastAPI AsyncPG

FastAPI integration for AsyncPG

## Narrative

First of all, so sorry for my poor english. I will be so happy,
if someone pushes a PR correcting all my english mistakes. Anyway
I will try to do my best.

Looking at fastapi ecosystem seems like everyone is trying to integrate
fastapi with orms, but from my experience working with raw
sql I'm so productive.

If you think a bit around, your real model layer, is the schema on your
db (you can add abastractions on top of it), but what ends
is your data, and these are tables, columns and rows.

Also, sql, it's one of the best things I learned
because it's something that always is there.

On another side, postgresql it's robust and rock solid,
thousands of projects depend on it, and use it as their storage layer.
AsyncPG it's a crazy fast postgresql driver
written from scratch.

FastAPI seems like a clean, and developer productive approach to web
frameworks. It's crazy how well it integrates with OpenAPI,
and how easy makes things to a developer to move on.

## Integration

fastapi_asyncpg trys to integrate fastapi and asyncpg in an idiomatic way.
fastapi_asyncpg when configured exposes two injectable providers to
fastapi path functions, can use:

- `db.connection` : it's just a raw connection picked from the pool,
  that it's auto released when pathfunction ends, this is mostly
  merit of the DI system around fastapi.

- `db.transaction`: the same, but wraps the pathfuncion on a transaction
  this is more or less the same than the `atomic` decorator from Django.
  also `db.atomic` it's aliased

```python
from fastapi import FastAPI
from fastapi import Depends
from fastapi_asyncpg import configure_asyncpg

app = FastAPI()
# we need to pass the fastapi app to make use of lifespan asgi events
db = configure_asyncpg(app, "postgresql://postgres:postgres@localhost/db")

@db.on_init
async def initialization(conn):
    # you can run your db initialization code here
    await conn.execute("SELECT 1")


@app.get("/")
async def get_content(db=Depends(db.connection)):
    rows = await db.fetch("SELECT wathever FROM tablexxx")
    return [dict(r) for r in rows]

@app.post("/")
async def mutate_something_compled(db=Depends(db.atomic))
    await db.execute()
    await db.execute()
    # if something fails, everyting is rolleback, you know all or nothing
```

And there's also an `initialization` callable on the main factory function.
That can be used like in flask to initialize whatever you need on the db.
The `initialization` is called right after asyncpg stablishes a connection,
and before the app fully boots. (Some projects use this as a poor migration
runner, not the best practice if you are deploying multiple
instances of the app).

## Testing

For testing we use [pytest-docker-fixtures](https://pypi.org/project/pytest-docker-fixtures/), it requires docker on the host machine or on whatever CI you use
(seems like works as expected with github actions)

It works, creating a container for the session and exposing it as pytest fixture.
It's a good practice to run tests with a real database, and
pytest-docker-fixtures make it's so easy. As a bonus, all fixtures run on a CI.
We use Jenkins witht docker and docker, but also seems like travis and github actions
also work.

The fixture needs to be added to the pytest plugins `conftest.py` file.

on conftest.py

```python
pytest_plugins = [
    "pytest_docker_fixtures",
]
```

With this in place, we can just yield a pg fixture

```python
from pytest_docker_fixtures import images

# image params can be configured from here
images.configure(
    "postgresql", "postgres", "11.1", env={"POSTGRES_DB": "test_db"}
)

# and then on our test we have a pg container running
# ready to recreate our db
async def test_pg(pg):
    host, port = pg
    dsn = f"postgresql://postgres@{host}:{port}/test_db"
    await asyncpg.Connect(dsn=dsn)
    # let's go

```

With this in place, we can just create our own pytest.fixture that
_patches_ the app dsn to make it work with our custom created
container.

````python

from .app import app, db
from async_asgi_testclient import TestClient

import pytest

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def asgi_app(pg)
    host, port = pg
    dsn = f"postgresql://postgres@{host}:{port}/test_db"
    # here we patch the dsn for the db
    # con_opts: are also accessible
    db.dsn = dsn
    yield app, db

async def test_something(asgi_app):
    app, db = asgi_app
    async with db.pool.acquire() as db:
        # setup your test state

    # this context manager handlers lifespan events
    async with TestClient(app) as client:
        res = await client.request("/")
```

Anyway if the application will grow, to multiples subpackages,
and apps, we trend to build the main app as a factory, that
creates it, something like:

```python
from fastapi_asyncpg import configure_asyncpg
from apppackage import settings

import venusian

def make_asgi_app(settings):
    app = FastAPI()
    db = configure_asyncpg(settings.DSN)

    scanner = venusian.Scanner(app=app)
    venusian.scan(theapp)
    return app
````

Then on the fixture, we just need, to factorze and app from our function

```python

from .factory import make_asgi_app
from async_asgi_testclient import TestClient

import pytest

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def asgi_app(pg)
    host, port = pg
    dsn = f"postgresql://postgres@{host}:{port}/test_db"
    app = make_asgi_app({"dsn": dsn})
    # ther's a pointer on the pool into app.state
    yield app

async def test_something(asgi_app):
    app = asgi_app
    pool = app.state.pool
    async with db.pool.acquire() as db:
        # setup your test state

    # this context manager handlers lifespan events
    async with TestClient(app) as client:
        res = await client.request("/")

```

There's also another approach exposed and used on [tests](tests/test_db.py),
that exposes a single connection to the test and rolls back changes on end.
We use this approach on a large project (500 tables per schema and
multiples schemas), and seems like it speeds up a bit test creation.
This approach is what [Databases](https://www.encode.io/databases/) it's using.
Feel free to follow the tests to see if it feets better.

## Extras

There are some utility functions I daily use with asyncpg that helps me
speed up some sql operations like, they are all on sql.py, and mostly are
self documented. They are in use on tests.

### Authors

`fastapi_asyncpg` was written by `Jordi collell <jordic@gmail.com>`\_.
