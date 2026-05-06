from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import Table, select, tuple_
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert


def prepare_vinculos(df: pd.DataFrame, servidor_map: dict[int, int]) -> tuple[pd.DataFrame, list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []

    for row in df.to_dict(orient="records"):
        id_servidor = servidor_map.get(row["numfunc"])
        if not id_servidor:
            errors.append(
                {
                    "chave_origem": f'{row["numfunc"]}:{row["numvinc"]}',
                    "mensagem_erro": "Servidor nao encontrado para o vinculo.",
                    "payload_origem": row,
                }
            )
            continue
        rows.append(
            {
                "id_servidor": id_servidor,
                "numvinc": row["numvinc"],
                "id_funcional": row["id_funcional"],
                "regime_juridico": row["regime_juridico"],
                "tipo_vinculo": row["tipo_vinculo"],
                "ativo": row["ativo"],
                "updated_at": datetime.now(),
            }
        )
    return pd.DataFrame(rows), errors


def load_vinculos(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["servidor_vinculo"]
    rows = df.to_dict(orient="records")
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["id_servidor", "numvinc"],
        update_columns=["id_funcional", "regime_juridico", "tipo_vinculo", "ativo", "updated_at"],
    )
    return {"recebidos": len(rows), "processados": len(rows)}


def fetch_vinculo_map(connection: Connection, metadata, df: pd.DataFrame) -> dict[tuple[int, int], int]:
    if df.empty:
        return {}
    tabela: Table = metadata.tables["servidor_vinculo"]
    keys = [(row.id_servidor, row.numvinc) for row in df.itertuples()]
    statement = select(tabela.c.id_servidor, tabela.c.numvinc, tabela.c.id_vinculo).where(
        tuple_(tabela.c.id_servidor, tabela.c.numvinc).in_(keys)
    )
    return {(row.id_servidor, row.numvinc): row.id_vinculo for row in connection.execute(statement)}
