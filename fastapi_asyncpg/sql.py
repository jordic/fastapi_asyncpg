"""
helper function to scope sql to postgresql schema
"""


async def get(conn, table, condition="1 = 1", args=None, fields="*"):
    args = args or []
    sql = f"select {fields} from {table} where {condition}"
    return await conn.fetchrow(sql, *args)


async def select(conn, table, condition="1 = 1", args=None, fields="*"):
    args = args or []
    sql = f"select {fields} from {table} where {condition}"
    return await conn.fetch(sql, *args)


async def count(conn, table, where="1=1", args=None):
    args = args or []
    return await conn.fetchval(
        f"select count(*) from {table} WHERE {where}", *args
    )


async def insert(conn, table, values):
    qs = "insert into {table} ({columns}) values ({values}) returning *".format(
        table=table,
        values=",".join([f"${p + 1}" for p in range(len(values.values()))]),
        columns=",".join(list(values.keys())),
    )
    return await conn.fetchrow(qs, *list(values.values()))


async def update(conn, table, conditions: dict, values: dict):
    qs = "update {table} set {columns} where {cond} returning *"
    counter = 1
    params = []
    cond = []
    vals = []
    for column, value in conditions.items():
        cond.append(f"{column}=${counter}")
        params.append(value)
        counter += 1
    for column, value in values.items():
        vals.append(f"{column}=${counter}")
        params.append(value)
        counter += 1
    sql = qs.format(
        table=table, columns=" ,".join(vals), cond=" AND ".join(cond)
    )
    return await conn.fetchrow(sql, *params)


async def delete(db, table, condition, args=None):
    args = args or []
    await db.execute(f"DELETE FROM {table} WHERE {condition}", *args)


def query_to_json(query, name):
    """This query is useful to fetch a complex join
    with some aggregations as a single blob, and later,
    just hydrate it without having to iterate over the resultset

    .. Example:
        SELECT
            u.id::varchar,
            to_jsonb(array_agg(scopes)) as scopes,
        FROM auth.auth_user u
            LEFT join LATERAL (
                SELECT id, scope
                FROM auth.auth_user_scope
                WHERE user_id=u.id
            ) scopes on true
        WHERE user_id = ANY($1)
        GROUP BY u.user_id;

    This query will fetch a list of users, and aggregate it's
    scopes as an array of dicts
    """

    return f"""
        select
            array_to_json(array_agg(row_to_json(t))) as {name}
        from (
            {query}
        ) as t
    """


async def load_sqlfile(db, file):
    fs = file.open("r")
    data = fs.read()
    fs.close()
    await db.execute(data)
