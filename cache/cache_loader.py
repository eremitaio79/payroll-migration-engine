from __future__ import annotations

from datetime import datetime

from sqlalchemy import Table, and_, delete, select, tuple_
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert


def _existing_cache_keys(connection: Connection, table: Table, rows: list[dict]) -> set[tuple[str, int, int, int]]:
    keys = list(
        dict.fromkeys(
            (
                str(row["matricula"]),
                int(row["ano"]),
                int(row["mes"]),
                int(row["folha_numero"]),
            )
            for row in rows
        )
    )
    if not keys:
        return set()

    statement = select(
        table.c.matricula,
        table.c.ano,
        table.c.mes,
        table.c.folha_numero,
    ).where(
        tuple_(table.c.matricula, table.c.ano, table.c.mes, table.c.folha_numero).in_(keys)
    )
    return {
        (str(row.matricula), int(row.ano), int(row.mes), int(row.folha_numero))
        for row in connection.execute(statement)
    }


def delete_contracheque_cache(
    connection: Connection,
    metadata,
    year: int,
    month: int | None = None,
    matricula: str | None = None,
) -> int:
    table: Table = metadata.tables["contracheque_cache"]
    filters = [table.c.ano == year]

    if matricula is not None and month is None:
        raise ValueError("Refresh de cache por matricula exige ano e mes.")

    if month is not None:
        filters.append(table.c.mes == month)

    if matricula is not None:
        filters.append(table.c.matricula == str(matricula))

    statement = delete(table).where(and_(*filters))
    result = connection.execute(statement)
    return int(result.rowcount or 0)


def load_contracheque_cache(connection: Connection, metadata, rows: list[dict]) -> dict[str, int]:
    if not rows:
        return {"processados": 0, "inseridos": 0, "atualizados": 0}
    now = datetime.now()
    payload = []
    for row in rows:
        prepared = dict(row)
        prepared["updated_at"] = now
        payload.append(prepared)
    table: Table = metadata.tables["contracheque_cache"]
    existing_keys = _existing_cache_keys(connection, table, payload)
    bulk_upsert(
        connection,
        table,
        payload,
        conflict_columns=["matricula", "ano", "mes", "folha_numero"],
        update_columns=["cpf", "folha_tipo", "folha_descricao", "contracheque_json", "updated_at"],
    )
    updated = len(existing_keys)
    inserted = len(payload) - updated
    return {"processados": len(payload), "inseridos": inserted, "atualizados": updated}
