from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import Table, select
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert


def load_servidores(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["servidor"]
    rows = []
    for row in df.to_dict(orient="records"):
        payload = dict(row)
        payload["updated_at"] = datetime.now()
        rows.append(payload)
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["numfunc"],
        update_columns=["cpf", "nome", "pis_pasep", "identidade", "updated_at"],
    )
    return {"recebidos": len(rows), "processados": len(rows)}


def fetch_servidor_map(connection: Connection, metadata, numfuncs: list[int]) -> dict[int, int]:
    if not numfuncs:
        return {}
    tabela: Table = metadata.tables["servidor"]
    statement = select(tabela.c.numfunc, tabela.c.id_servidor).where(tabela.c.numfunc.in_(numfuncs))
    return {row.numfunc: row.id_servidor for row in connection.execute(statement)}
