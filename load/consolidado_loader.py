from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import Table
from sqlalchemy.engine import Connection

from db.postgres_conn import bulk_upsert


ZERO = Decimal("0.00")


def prepare_consolidados(
    contracheques_df: pd.DataFrame,
    itens_df: pd.DataFrame,
    contracheque_map: dict[tuple[int, object, int], int],
) -> pd.DataFrame:
    if contracheques_df.empty:
        return pd.DataFrame(
            columns=[
                "id_contracheque",
                "total_vantagens",
                "total_descontos_itens",
                "total_itens",
                "divergencia_bruto",
                "divergencia_descontos",
                "divergencia_liquido",
            ]
        )

    agrupado = (
        itens_df.groupby("id_contracheque", as_index=False)
        .agg(
            total_vantagens=("valor_vantagem", "sum"),
            total_auxiliar=("valor_auxiliar", "sum"),
            total_descontos_itens=("valor_desconto", "sum"),
            total_itens=("id_contracheque", "count"),
        )
        .fillna(ZERO)
    )
    lookup = agrupado.set_index("id_contracheque").to_dict(orient="index")

    rows = []
    for row in contracheques_df.to_dict(orient="records"):
        id_contracheque = contracheque_map.get((row["id_vinculo"], row["mes_ano"], row["numero"]))
        if not id_contracheque:
            continue
        resumo = lookup.get(
            id_contracheque,
            {
                "total_vantagens": ZERO,
                "total_auxiliar": ZERO,
                "total_descontos_itens": ZERO,
                "total_itens": 0,
            },
        )
        total_vantagens = (resumo["total_vantagens"] or ZERO) + (resumo["total_auxiliar"] or ZERO)
        total_descontos = resumo["total_descontos_itens"] or ZERO
        liquido_itens = total_vantagens - total_descontos
        rows.append(
            {
                "id_contracheque": id_contracheque,
                "total_vantagens": total_vantagens,
                "total_descontos_itens": total_descontos,
                "total_itens": int(resumo["total_itens"]),
                "divergencia_bruto": (row["bruto"] or ZERO) - total_vantagens,
                "divergencia_descontos": (row["descontos"] or ZERO) - total_descontos,
                "divergencia_liquido": (row["liquido"] or ZERO) - liquido_itens,
            }
        )
    return pd.DataFrame(rows)


def load_consolidados(connection: Connection, metadata, df: pd.DataFrame) -> dict[str, int]:
    tabela: Table = metadata.tables["contracheque_consolidado"]
    rows = df.to_dict(orient="records")
    bulk_upsert(
        connection,
        tabela,
        rows,
        conflict_columns=["id_contracheque"],
        update_columns=[
            "total_vantagens",
            "total_descontos_itens",
            "total_itens",
            "divergencia_bruto",
            "divergencia_descontos",
            "divergencia_liquido",
        ],
    )
    return {"recebidos": len(rows), "processados": len(rows)}
