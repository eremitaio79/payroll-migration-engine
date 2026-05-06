from __future__ import annotations

import pandas as pd

from utils.normalizers import normalize_columns, normalize_int, normalize_string


def transform_vinculos(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(columns=["numfunc", "numvinc", "id_funcional", "regime_juridico", "tipo_vinculo", "ativo"])

    normalized = pd.DataFrame(
        {
            "numfunc": df["NUMFUNC"].map(normalize_int),
            "numvinc": df["NUMVINC"].map(normalize_int),
            "id_funcional": df["ID_FUNCIONAL"].map(normalize_string),
            "regime_juridico": df["REGIME_JURIDICO"].map(normalize_string),
            "tipo_vinculo": df["TIPO_VINCULO"].map(normalize_string),
            "ativo": "S",
        }
    )
    normalized = normalized.dropna(subset=["numfunc", "numvinc"])
    return normalized.drop_duplicates(subset=["numfunc", "numvinc"], keep="last").reset_index(drop=True)
