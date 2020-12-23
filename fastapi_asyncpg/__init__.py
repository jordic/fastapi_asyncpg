from __future__ import annotations

from fastapi import FastAPI

import asyncpg
import typing


async def noop(db: asyncpg.Connection):
    return


class configure_asyncpg:
    def __init__(
        self,
        app: FastAPI,
        dsn: str,
        *,
        init_db: typing.Callable = None,  # callable for running sql on init
        pool=None,  # usable on testing
        **options,
    ):
        """This is the entry point to configure an asyncpg pool with fastapi.

        Arguments
            app: The fastapp application that we use to store the pool
                and bind to it's initialitzation events
            dsn: A postgresql desn like postgresql://user:password@postgresql:5432/db
            init_db: Optional callable that receives a db connection,
                for doing an initialitzation of it
            pool: This is used for testing to skip the pool initialitzation
                an just use the SingleConnectionTestingPool
            **options: connection options to directly pass to asyncpg driver
                see: https://magicstack.github.io/asyncpg/current/api/index.html#connection-pools
        """
        self.app = app
        self.dsn = dsn
        self.init_db = init_db
        self.con_opts = options
        self._pool = pool
        self.app.router.add_event_handler("startup", self.on_connect)
        self.app.router.add_event_handler("shutdown", self.on_disconnect)

    async def on_connect(self):
        """handler called during initialitzation of asgi app, that connects to
        the db"""
        # if the pool is comming from outside (tests), don't connect it
        if self._pool:
            self.app.state.pool = self._pool
            return
        pool = await asyncpg.create_pool(dsn=self.dsn, **self.con_opts)
        async with pool.acquire() as db:
            await self.init_db(db)
        self.app.state.pool = pool

    async def on_disconnect(self):
        # if the pool is comming from outside, don't desconnect it
        # someone else will do (usualy a pytest fixture)
        if self._pool:
            return
        await self.app.state.pool.close()

    def on_init(self, func):
        self.init_db = func
        return func

    @property
    def pool(self):
        return self.app.state.pool

    async def connection(self):
        """
        A ready to use connection Dependency just usable
        on your path functions that gets a connection from the pool
        Example:
            db = configure_asyncpg(app, "dsn://")
            @app.get("/")
            async def get_content(db = Depens(db.connection)):
                await db.fetch("SELECT * from pg_schemas")
        """
        async with self.pool.acquire() as db:
            yield db

    async def transaction(self):
        """
        A ready to use transaction Dependecy just usable on a path function
        Example:
            db = configure_asyncpg(app, "dsn://")
            @app.get("/")
            async def get_content(db = Depens(db.transaction)):
                await db.execute("insert into keys values (1, 2)")
                await db.execute("insert into keys values (1, 2)")
        All view function executed, are wrapped inside a postgresql transaction
        """
        async with self.pool.acquire() as db:
            txn = db.transaction()
            await txn.start()
            try:
                yield db
            except:  # noqa
                await txn.rollback()
                raise
            else:
                await txn.commit()

    atomic = transaction


class SingleConnectionTestingPool:
    """A fake pool that simulates pooling, but runs on
    a single transaction that it's rolled back after
    each test.
    With some large schemas this seems to be faster than
    the other approach
    """

    def __init__(
        self,
        conn: asyncpg.Connection,
        initialize: typing.Callable = None,
        add_logger_postgres: bool = False,
    ):
        self._conn = conn
        self.tx = None
        self.started = False
        self.add_logger_postgres = add_logger_postgres
        self.initialize = initialize

    def acquire(self, *, timeout=None):
        return ConAcquireContext(self._conn, self)

    async def start(self):
        if self.started:
            return

        def log_postgresql(con, message):
            print(message)

        if self.add_logger_postgres:
            self._conn.add_log_listener(log_postgresql)
        self.tx = self._conn.transaction()
        await self.tx.start()
        await self.initialize(self._conn)
        self.started = True

    async def release(self):
        if self.tx:
            await self.tx.rollback()

    def __getattr__(self, key):
        return getattr(self._conn, key)


async def create_pool_test(
    dsn: str,
    *,
    initialize: typing.Callable = None,
    add_logger_postgres: bool = False,
):
    """This part is only used for testing,
    we create a fake "pool" that just starts a connecion,
    that does a transaction inside it"""
    conn = await asyncpg.connect(dsn=dsn)
    pool = SingleConnectionTestingPool(
        conn, initialize=initialize, add_logger_postgres=add_logger_postgres
    )
    return pool


class ConAcquireContext:
    def __init__(self, conn, manager):
        self._conn = conn
        self.manager = manager

    async def __aenter__(self):
        if not self.manager.tx:
            await self.manager.start()
        self.tr = self._conn.transaction()
        await self.tr.start()
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.tr.rollback()
        else:
            await self.tr.commit()
