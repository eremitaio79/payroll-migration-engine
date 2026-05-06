from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import Table, select
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert


def load_rubricas(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["rubrica"]
    rows = []
    for row in df.to_dict(orient="records"):
        payload = dict(row)
        payload["updated_at"] = datetime.now()
        rows.append(payload)
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["codigo_rubrica"],
        update_columns=["nome_rubrica", "tipo_rubrica", "ativa", "updated_at"],
    )
    return {"recebidos": len(rows), "processados": len(rows)}


def fetch_rubrica_map(connection: Connection, metadata, codigos: list[int]) -> dict[int, int]:
    if not codigos:
        return {}
    tabela: Table = metadata.tables["rubrica"]
    statement = select(tabela.c.codigo_rubrica, tabela.c.id_rubrica).where(tabela.c.codigo_rubrica.in_(codigos))
    return {row.codigo_rubrica: row.id_rubrica for row in connection.execute(statement)}
