from __future__ import annotations

import pandas as pd

from utils.normalizers import normalize_columns, normalize_int, normalize_string


def transform_rubricas(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(columns=["codigo_rubrica", "nome_rubrica", "tipo_rubrica", "ativa"])

    normalized = pd.DataFrame(
        {
            "codigo_rubrica": df["RUBRICA"].map(normalize_int),
            "nome_rubrica": df["NOME_RUBRICA"].map(normalize_string),
            "tipo_rubrica": df["TIPO_RUBRICA"].map(normalize_string),
            "ativa": "S",
        }
    )
    normalized = normalized.dropna(subset=["codigo_rubrica", "nome_rubrica"])
    return normalized.drop_duplicates(subset=["codigo_rubrica"], keep="last").reset_index(drop=True)
