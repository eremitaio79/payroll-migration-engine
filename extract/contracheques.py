from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


def _date_range(year: int, month: int | None = None, start_date: date | None = None, end_date: date | None = None) -> tuple[date, date]:
    if start_date is not None and end_date is not None:
        return start_date, end_date + timedelta(days=1)
    if month is None:
        return date(year, 1, 1), date(year + 1, 1, 1)
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    return start_date, end_date


def extract_contracheques(
    connection: Connection,
    year: int,
    source_name: str = "PAYROLL_CHECKS_VIEW",
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    start_date, end_date = _date_range(year, month, start_date, end_date)
    query = text(
        f"""
        SELECT
            MES_ANO,
            NUMERO,
            DATA_CONSOLIDACAO,
            DT_LIB_C_CHEQUE,
            NUMFUNC,
            NUMVINC,
            CPF,
            ID_FUNCIONAL,
            FOLHA,
            NOME,
            ORGAO,
            CARGO,
            REF_CARGO,
            FUNCAO,
            REF_FUNCAO,
            MUNICIPIO,
            SETOR,
            REGIME_JURIDICO,
            TIPO_VINCULO,
            BANCO,
            AGENCIA,
            CONTA,
            PIS_PASEP,
            IDENTIDADE,
            CARGA_HORARIA,
            BRUTO,
            DESCONTOS,
            LIQUIDO,
            RUBRICA,
            NOME_RUBRICA,
            COMPLEMENTO,
            INFO,
            COMPETENCIA,
            VANTAGEM,
            DESCONTO,
            AUXILIAR,
            TIPO_RUBRICA
        FROM {source_name}
        WHERE MES_ANO >= :start_date
          AND MES_ANO < :end_date
        """
    )
    return pd.read_sql_query(query, connection, params={"start_date": start_date, "end_date": end_date})


def iter_contracheques(
    connection: Connection,
    year: int,
    source_name: str = "PAYROLL_CHECKS_VIEW",
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    chunk_size: int = 20000,
):
    start_date, end_date = _date_range(year, month, start_date, end_date)
    query = text(
        f"""
        SELECT
            MES_ANO,
            NUMERO,
            DATA_CONSOLIDACAO,
            DT_LIB_C_CHEQUE,
            NUMFUNC,
            NUMVINC,
            CPF,
            ID_FUNCIONAL,
            FOLHA,
            NOME,
            ORGAO,
            CARGO,
            REF_CARGO,
            FUNCAO,
            REF_FUNCAO,
            MUNICIPIO,
            SETOR,
            REGIME_JURIDICO,
            TIPO_VINCULO,
            BANCO,
            AGENCIA,
            CONTA,
            PIS_PASEP,
            IDENTIDADE,
            CARGA_HORARIA,
            BRUTO,
            DESCONTOS,
            LIQUIDO,
            RUBRICA,
            NOME_RUBRICA,
            COMPLEMENTO,
            INFO,
            COMPETENCIA,
            VANTAGEM,
            DESCONTO,
            AUXILIAR,
            TIPO_RUBRICA
        FROM {source_name}
        WHERE MES_ANO >= :start_date
          AND MES_ANO < :end_date
        """
    )
    return pd.read_sql_query(
        query,
        connection,
        params={"start_date": start_date, "end_date": end_date},
        chunksize=chunk_size,
    )


def count_contracheques(
    connection: Connection,
    year: int,
    source_name: str = "PAYROLL_CHECKS_VIEW",
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    start_date, end_date = _date_range(year, month, start_date, end_date)
    query = text(
        f"""
        SELECT COUNT(1) AS total
        FROM {source_name}
        WHERE MES_ANO >= :start_date
          AND MES_ANO < :end_date
        """
    )
    return int(connection.execute(query, {"start_date": start_date, "end_date": end_date}).scalar() or 0)
