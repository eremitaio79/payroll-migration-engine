from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import Table, select, tuple_
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert
from utils.normalizers import normalize_folha_description


def prepare_contracheques(
    df: pd.DataFrame,
    vinculo_map: dict[tuple[int, int], int],
    folha_desc_map: dict[tuple, int],
    folha_mes_unica_map: dict,
) -> tuple[pd.DataFrame, list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []

    for row in df.to_dict(orient="records"):
        id_vinculo = vinculo_map.get((row["id_servidor"], row["numvinc"]))
        descricao_normalizada = normalize_folha_description(row["folha_descricao_origem"])
        id_folha = folha_desc_map.get((row["mes_ano"], descricao_normalizada))
        if id_folha is None:
            id_folha = folha_mes_unica_map.get(row["mes_ano"])

        if not id_vinculo:
            errors.append(
                {
                    "chave_origem": f'{row["numfunc"]}:{row["numvinc"]}:{row["mes_ano"]}:{row["numero"]}',
                    "mensagem_erro": "Vinculo nao encontrado para o contracheque.",
                    "payload_origem": row,
                }
            )
            continue

        if not id_folha:
            errors.append(
                {
                    "chave_origem": f'{row["numfunc"]}:{row["numvinc"]}:{row["mes_ano"]}:{row["numero"]}',
                    "mensagem_erro": "Folha de referencia nao encontrada para o contracheque.",
                    "payload_origem": row,
                }
            )
            continue

        rows.append(
            {
                "id_vinculo": id_vinculo,
                "id_folha_referencia": id_folha,
                "mes_ano": row["mes_ano"],
                "numero": row["numero"],
                "folha_descricao_origem": row["folha_descricao_origem"],
                "competencia": row["competencia"],
                "bruto": row["bruto"],
                "descontos": row["descontos"],
                "liquido": row["liquido"],
                "data_consolidacao": row["data_consolidacao"],
                "dt_lib_c_cheque": row["dt_lib_c_cheque"],
                "ano": row["ano"],
                "mes": row["mes"],
                "hash_origem": row["hash_origem"],
                "updated_at": datetime.now(),
            }
        )

    prepared = pd.DataFrame(rows)
    return prepared, errors


def load_contracheques(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["contracheque"]
    rows = df.to_dict(orient="records")
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["id_vinculo", "mes_ano", "numero"],
        update_columns=[
            "id_folha_referencia",
            "folha_descricao_origem",
            "competencia",
            "bruto",
            "descontos",
            "liquido",
            "data_consolidacao",
            "dt_lib_c_cheque",
            "ano",
            "mes",
            "hash_origem",
            "updated_at",
        ],
    )
    return {"recebidos": len(rows), "processados": len(rows)}


def fetch_contracheque_map(connection: Connection, metadata, df: pd.DataFrame) -> dict[tuple[int, object, int], int]:
    if df.empty:
        return {}
    tabela: Table = metadata.tables["contracheque"]
    keys = [(row.id_vinculo, row.mes_ano, row.numero) for row in df.itertuples()]
    statement = select(tabela.c.id_vinculo, tabela.c.mes_ano, tabela.c.numero, tabela.c.id_contracheque).where(
        tuple_(tabela.c.id_vinculo, tabela.c.mes_ano, tabela.c.numero).in_(keys)
    )
    return {(row.id_vinculo, row.mes_ano, row.numero): row.id_contracheque for row in connection.execute(statement)}
