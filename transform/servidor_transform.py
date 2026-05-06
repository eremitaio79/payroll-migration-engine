from __future__ import annotations

import pandas as pd

from utils.normalizers import normalize_columns, normalize_int, normalize_string


def transform_servidores(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(columns=["numfunc", "cpf", "nome", "pis_pasep", "identidade"])

    normalized = pd.DataFrame(
        {
            "numfunc": df["NUMFUNC"].map(normalize_int),
            "cpf": df["CPF"].map(normalize_string),
            "nome": df["NOME"].map(normalize_string),
            "pis_pasep": df["PIS_PASEP"].map(normalize_string),
            "identidade": df["IDENTIDADE"].map(normalize_string),
        }
    )
    normalized = normalized.dropna(subset=["numfunc", "nome"])
    return normalized.drop_duplicates(subset=["numfunc"], keep="last").reset_index(drop=True)
