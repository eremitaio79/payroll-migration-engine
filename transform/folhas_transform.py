from __future__ import annotations

import pandas as pd

from utils.normalizers import date_parts, normalize_columns, normalize_date, normalize_int, normalize_string


def transform_folhas(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "mes_ano_folha",
                "num_folha",
                "descricao_folha",
                "data_consolidacao",
                "dt_lib_c_cheque",
                "ano",
                "mes",
                "ativa",
            ]
        )

    normalized = pd.DataFrame(
        {
            "mes_ano_folha": df["MES_ANO_FOLHA"].map(normalize_date),
            "num_folha": df["NUM_FOLHA"].map(normalize_int),
            "descricao_folha": df["FOLHA"].map(normalize_string),
            "data_consolidacao": df["DATA_CONSOLIDACAO"].map(normalize_date),
            "dt_lib_c_cheque": df["DT_LIB_C_CHEQUE"].map(normalize_date),
            "ativa": "S",
        }
    )
    normalized[["ano", "mes"]] = normalized["mes_ano_folha"].apply(lambda value: pd.Series(date_parts(value)))
    normalized = normalized.dropna(subset=["mes_ano_folha", "num_folha"])
    return normalized.drop_duplicates(subset=["mes_ano_folha", "num_folha"], keep="last").reset_index(drop=True)
