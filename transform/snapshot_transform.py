from __future__ import annotations

import pandas as pd

from utils.normalizers import normalize_columns, normalize_decimal, normalize_int, normalize_string


def transform_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "numfunc",
                "numvinc",
                "mes_ano",
                "numero",
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
            ]
        )

    normalized = pd.DataFrame(
        {
            "numfunc": df["NUMFUNC"].map(normalize_int),
            "numvinc": df["NUMVINC"].map(normalize_int),
            "mes_ano": pd.to_datetime(df["MES_ANO"]).dt.date,
            "numero": df["NUMERO"].map(normalize_int),
            "orgao": df["ORGAO"].map(normalize_string),
            "cargo": df["CARGO"].map(normalize_string),
            "ref_cargo": df["REF_CARGO"].map(normalize_string),
            "funcao": df["FUNCAO"].map(normalize_string),
            "ref_funcao": df["REF_FUNCAO"].map(normalize_string),
            "municipio": df["MUNICIPIO"].map(normalize_string),
            "setor": df["SETOR"].map(normalize_string),
            "regime_juridico": df["REGIME_JURIDICO"].map(normalize_string),
            "tipo_vinculo": df["TIPO_VINCULO"].map(normalize_string),
            "banco": df["BANCO"].map(normalize_string),
            "agencia": df["AGENCIA"].map(normalize_string),
            "conta": df["CONTA"].map(normalize_string),
            "carga_horaria": df["CARGA_HORARIA"].map(normalize_decimal),
        }
    )
    normalized = normalized.dropna(subset=["numfunc", "numvinc", "mes_ano", "numero"])
    return normalized.drop_duplicates(subset=["numfunc", "numvinc", "mes_ano", "numero"], keep="last").reset_index(drop=True)
