from __future__ import annotations

import pandas as pd
from sqlalchemy import Table
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert


def prepare_snapshots(
    df: pd.DataFrame,
    vinculo_map: dict[tuple[int, int], int],
    contracheque_map: dict[tuple[int, object, int], int],
) -> tuple[pd.DataFrame, list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []
    for row in df.to_dict(orient="records"):
        id_vinculo = vinculo_map.get((row["id_servidor"], row["numvinc"]))
        if not id_vinculo:
            errors.append(
                {
                    "chave_origem": f'{row["numfunc"]}:{row["numvinc"]}:{row["mes_ano"]}:{row["numero"]}',
                    "mensagem_erro": "Vinculo nao encontrado para snapshot.",
                    "payload_origem": row,
                }
            )
            continue
        id_contracheque = contracheque_map.get((id_vinculo, row["mes_ano"], row["numero"]))
        if not id_contracheque:
            errors.append(
                {
                    "chave_origem": f'{row["numfunc"]}:{row["numvinc"]}:{row["mes_ano"]}:{row["numero"]}',
                    "mensagem_erro": "Contracheque nao encontrado para snapshot.",
                    "payload_origem": row,
                }
            )
            continue
        payload = dict(row)
        payload["id_contracheque"] = id_contracheque
        payload.pop("numfunc", None)
        payload.pop("numvinc", None)
        payload.pop("mes_ano", None)
        payload.pop("numero", None)
        payload.pop("id_servidor", None)
        rows.append(payload)
    return pd.DataFrame(rows), errors


def load_snapshots(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["contracheque_snapshot_funcional"]
    rows = df.to_dict(orient="records")
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["id_contracheque"],
        update_columns=[
            "orgao",
            "cargo",
            "ref_cargo",
            "funcao",
            "ref_funcao",
            "municipio",
            "setor",
            "regime_juridico",
            "tipo_vinculo",
            "banco",
            "agencia",
            "conta",
            "carga_horaria",
        ],
    )
    return {"recebidos": len(rows), "processados": len(rows)}
