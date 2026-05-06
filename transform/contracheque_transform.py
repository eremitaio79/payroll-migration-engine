from __future__ import annotations

import pandas as pd

from utils.hash_utils import stable_hash
from utils.normalizers import date_parts, normalize_columns, normalize_date, normalize_decimal, normalize_int, normalize_string


def transform_contracheques(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "numfunc",
                "numvinc",
                "mes_ano",
                "numero",
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
            ]
        )

    normalized = pd.DataFrame(
        {
            "numfunc": df["NUMFUNC"].map(normalize_int),
            "numvinc": df["NUMVINC"].map(normalize_int),
            "mes_ano": df["MES_ANO"].map(normalize_date),
            "numero": df["NUMERO"].map(normalize_int),
            "folha_descricao_origem": df["FOLHA"].map(normalize_string),
            "competencia": df["COMPETENCIA"].map(normalize_string),
            "bruto": df["BRUTO"].map(normalize_decimal),
            "descontos": df["DESCONTOS"].map(normalize_decimal),
            "liquido": df["LIQUIDO"].map(normalize_decimal),
            "data_consolidacao": df["DATA_CONSOLIDACAO"].map(normalize_date),
            "dt_lib_c_cheque": df["DT_LIB_C_CHEQUE"].map(normalize_date),
        }
    )
    normalized = normalized.dropna(subset=["numfunc", "numvinc", "mes_ano", "numero"])
    normalized[["ano", "mes"]] = normalized["mes_ano"].apply(lambda value: pd.Series(date_parts(value)))
    normalized["hash_origem"] = normalized.apply(
        lambda row: stable_hash(row["numfunc"], row["numvinc"], row["mes_ano"], row["numero"]),
        axis=1,
    )
    return normalized.drop_duplicates(subset=["numfunc", "numvinc", "mes_ano", "numero"], keep="last").reset_index(drop=True)
