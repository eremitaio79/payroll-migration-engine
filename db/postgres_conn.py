from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import MetaData, Table, create_engine, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, Engine

from config import Settings


TABLE_NAMES = [
    "carga_importacao",
    "carga_importacao_erro",
    "folha_referencia",
    "servidor",
    "servidor_vinculo",
    "rubrica",
    "contracheque",
    "contracheque_snapshot_funcional",
    "contracheque_item",
    "contracheque_consolidado",
    "contracheque_cache",
]


def create_postgres_engine(settings: Settings) -> Engine:
    return create_engine(settings.postgres_dsn, future=True)


def reflect_metadata(engine: Engine) -> MetaData:
    metadata = MetaData()
    metadata.reflect(bind=engine, only=TABLE_NAMES)
    return metadata


def bulk_upsert(
    connection: Connection,
    table: Table,
    rows: list[dict],
    conflict_columns: list[str],
    update_columns: list[str],
) -> None:
    if not rows:
        return

    statement = insert(table).values(rows)
    excluded = statement.excluded
    update_payload = {column: getattr(excluded, column) for column in update_columns}
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=[table.c[column] for column in conflict_columns],
            set_=update_payload,
        )
    )


def fetch_existing_map(
    connection: Connection,
    table: Table,
    key_columns: list[str],
    value_column: str,
    keys: Iterable[tuple],
) -> dict[tuple, int]:
    normalized_keys = list(dict.fromkeys(keys))
    if not normalized_keys:
        return {}

    result: dict[tuple, int] = {}
    chunk_size = 1000
    for index in range(0, len(normalized_keys), chunk_size):
        chunk = normalized_keys[index : index + chunk_size]
        statement = select(
            *(table.c[column] for column in key_columns),
            table.c[value_column],
        ).where(tuple_(*(table.c[column] for column in key_columns)).in_(chunk))
        for row in connection.execute(statement).mappings():
            key = tuple(row[column] for column in key_columns)
            result[key] = row[value_column]
    return result
