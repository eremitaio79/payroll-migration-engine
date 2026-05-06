from __future__ import annotations

from decimal import Decimal

import pandas as pd

from utils.hash_utils import stable_hash
from utils.normalizers import normalize_columns, normalize_date, normalize_decimal, normalize_int, normalize_string


ZERO = Decimal("0.00")


def transform_itens(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "numfunc",
                "numvinc",
                "mes_ano",
                "numero",
                "codigo_rubrica_origem",
                "nome_rubrica_origem",
                "tipo_rubrica_origem",
                "complemento",
                "info",
                "valor_vantagem",
                "valor_desconto",
                "valor_auxiliar",
                "valor_total_item",
                "item_hash",
            ]
        )

    normalized = pd.DataFrame(
        {
            "numfunc": df["NUMFUNC"].map(normalize_int),
            "numvinc": df["NUMVINC"].map(normalize_int),
            "mes_ano": df["MES_ANO"].map(normalize_date),
            "numero": df["NUMERO"].map(normalize_int),
            "codigo_rubrica_origem": df["RUBRICA"].map(normalize_int),
            "nome_rubrica_origem": df["NOME_RUBRICA"].map(normalize_string),
            "tipo_rubrica_origem": df["TIPO_RUBRICA"].map(normalize_string),
            "complemento": df["COMPLEMENTO"].map(normalize_string),
            "info": df["INFO"].map(normalize_string),
            "valor_vantagem": df["VANTAGEM"].map(normalize_decimal),
            "valor_desconto": df["DESCONTO"].map(normalize_decimal),
            "valor_auxiliar": df["AUXILIAR"].map(normalize_decimal),
        }
    )
    normalized = normalized.dropna(subset=["numfunc", "numvinc", "mes_ano", "numero"])
    normalized["valor_total_item"] = normalized.apply(
        lambda row: (row["valor_vantagem"] or ZERO) + (row["valor_auxiliar"] or ZERO) - (row["valor_desconto"] or ZERO),
        axis=1,
    )
    normalized["item_hash"] = normalized.apply(
        lambda row: stable_hash(
            row["numfunc"],
            row["numvinc"],
            row["mes_ano"],
            row["numero"],
            row["codigo_rubrica_origem"],
            row["complemento"],
            row["info"],
            row["valor_vantagem"] or ZERO,
            row["valor_desconto"] or ZERO,
            row["valor_auxiliar"] or ZERO,
        ),
        axis=1,
    )
    normalized = normalized.drop_duplicates(subset=["item_hash"], keep="last").reset_index(drop=True)
    normalized["sequencia_item"] = normalized.groupby(["numfunc", "numvinc", "mes_ano", "numero"]).cumcount() + 1
    return normalized
