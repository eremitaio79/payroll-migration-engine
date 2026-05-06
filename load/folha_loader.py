from __future__ import annotations

import pandas as pd
from sqlalchemy import Table
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert, fetch_existing_map


def load_folhas(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["folha_referencia"]
    rows = df.to_dict(orient="records")
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["mes_ano_folha", "num_folha"],
        update_columns=["descricao_folha", "data_consolidacao", "dt_lib_c_cheque", "ano", "mes", "ativa"],
    )
    return {"recebidos": len(rows), "processados": len(rows)}


def fetch_folha_map(connection: Connection, metadata, df: pd.DataFrame) -> dict[tuple, int]:
    tabela: Table = metadata.tables["folha_referencia"]
    keys = [(row.mes_ano_folha, row.num_folha) for row in df.itertuples()]
    return fetch_existing_map(connection, tabela, ["mes_ano_folha", "num_folha"], "id_folha_referencia", keys)
