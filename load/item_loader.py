from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import Table, select
from sqlalchemy.engine import Connection

from utils.hash_utils import stable_hash


ZERO = Decimal("0.00")


def prepare_itens(
    df: pd.DataFrame,
    vinculo_map: dict[tuple[int, int], int],
    contracheque_map: dict[tuple[int, object, int], int],
    rubrica_map: dict[int, int],
) -> tuple[pd.DataFrame, list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []
    for row in df.to_dict(orient="records"):
        id_vinculo = vinculo_map.get((row["id_servidor"], row["numvinc"]))
        if not id_vinculo:
            errors.append(
                {
                    "chave_origem": row["item_hash"],
                    "mensagem_erro": "Vinculo nao encontrado para item.",
                    "payload_origem": row,
                }
            )
            continue
        id_contracheque = contracheque_map.get((id_vinculo, row["mes_ano"], row["numero"]))
        if not id_contracheque:
            errors.append(
                {
                    "chave_origem": row["item_hash"],
                    "mensagem_erro": "Contracheque nao encontrado para item.",
                    "payload_origem": row,
                }
            )
            continue
        payload = dict(row)
        payload["id_contracheque"] = id_contracheque
        payload["id_rubrica"] = rubrica_map.get(row["codigo_rubrica_origem"])
        payload.pop("numfunc", None)
        payload.pop("numvinc", None)
        payload.pop("mes_ano", None)
        payload.pop("numero", None)
        payload.pop("id_servidor", None)
        rows.append(payload)
    return pd.DataFrame(rows), errors


def _existing_hashes(connection: Connection, metadata, contracheque_ids: list[int]) -> set[str]:
    if not contracheque_ids:
        return set()
    tabela: Table = metadata.tables["contracheque_item"]
    statement = select(
        tabela.c.id_contracheque,
        tabela.c.codigo_rubrica_origem,
        tabela.c.complemento,
        tabela.c.info,
        tabela.c.valor_vantagem,
        tabela.c.valor_desconto,
        tabela.c.valor_auxiliar,
    ).where(tabela.c.id_contracheque.in_(contracheque_ids))
    hashes = set()
    for row in connection.execute(statement).mappings():
        hashes.add(
            stable_hash(
                row["id_contracheque"],
                row["codigo_rubrica_origem"],
                row["complemento"],
                row["info"],
                row["valor_vantagem"] or ZERO,
                row["valor_desconto"] or ZERO,
                row["valor_auxiliar"] or ZERO,
            )
        )
    return hashes


def load_itens(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["contracheque_item"]
    rows = df.to_dict(orient="records")
    existing = _existing_hashes(connection, metadata, [row["id_contracheque"] for row in rows])
    pending = []
    for row in rows:
        row_hash = stable_hash(
            row["id_contracheque"],
            row["codigo_rubrica_origem"],
            row["complemento"],
            row["info"],
            row["valor_vantagem"] or ZERO,
            row["valor_desconto"] or ZERO,
            row["valor_auxiliar"] or ZERO,
        )
        if row_hash not in existing:
            row.pop("item_hash", None)
            pending.append(row)
    if pending:
        connection.execute(tabela.insert(), pending)
    return {"recebidos": len(rows), "processados": len(pending)}
