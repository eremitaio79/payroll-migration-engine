from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


def _date_filter_clause(start_date: date | None, end_date: date | None) -> tuple[str, dict]:
    params: dict[str, object] = {}
    if start_date is None or end_date is None:
        return "", params

    params["start_date"] = start_date
    params["end_date_exclusive"] = end_date + timedelta(days=1)
    return " AND c.mes_ano >= :start_date AND c.mes_ano < :end_date_exclusive ", params


def count_cache_candidates(
    connection: Connection,
    year: int,
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    matricula: str | None = None,
) -> int:
    month_filter = " AND c.mes = :month " if month is not None else ""
    matricula_filter = " AND CAST(s.numfunc AS TEXT) = :matricula " if matricula is not None else ""
    params = {"year": year}
    if month is not None:
        params["month"] = month
    if matricula is not None:
        params["matricula"] = str(matricula)
    extra_filter, extra_params = _date_filter_clause(start_date, end_date)
    params.update(extra_params)
    query = text(
        f"""
        SELECT COUNT(1)
        FROM contracheque c
        JOIN servidor_vinculo sv ON sv.id_vinculo = c.id_vinculo
        JOIN servidor s ON s.id_servidor = sv.id_servidor
        WHERE c.ano = :year
        {month_filter}
        {matricula_filter}
        {extra_filter}
        """
    )
    return int(connection.execute(query, params).scalar() or 0)


def load_cache_candidates(
    connection: Connection,
    year: int,
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    matricula: str | None = None,
    offset: int = 0,
    limit: int = 1000,
) -> pd.DataFrame:
    month_filter = " AND c.mes = :month " if month is not None else ""
    matricula_filter = " AND CAST(s.numfunc AS TEXT) = :matricula " if matricula is not None else ""
    params = {"year": year, "offset_rows": offset, "limit_rows": limit}
    if month is not None:
        params["month"] = month
    if matricula is not None:
        params["matricula"] = str(matricula)
    extra_filter, extra_params = _date_filter_clause(start_date, end_date)
    params.update(extra_params)

    query = text(
        f"""
        SELECT DISTINCT ON (c.id_contracheque)
            c.id_contracheque,
            s.numfunc,
            s.nome,
            s.cpf,
            s.pis_pasep,
            s.identidade,
            sv.id_funcional,
            sv.regime_juridico AS vinc_regime_juridico,
            sv.tipo_vinculo AS vinc_tipo_vinculo,
            c.ano,
            c.mes,
            c.competencia,
            c.folha_descricao_origem,
            c.dt_lib_c_cheque,
            c.data_consolidacao,
            c.numero,
            fr.num_folha,
            fr.descricao_folha,
            csf.orgao,
            csf.cargo,
            csf.ref_cargo,
            csf.funcao,
            csf.ref_funcao,
            csf.municipio,
            csf.setor,
            csf.regime_juridico AS snap_regime_juridico,
            csf.tipo_vinculo AS snap_tipo_vinculo,
            csf.banco,
            csf.agencia,
            csf.conta,
            csf.carga_horaria
        FROM contracheque c
        JOIN servidor_vinculo sv ON sv.id_vinculo = c.id_vinculo
        JOIN servidor s ON s.id_servidor = sv.id_servidor
        LEFT JOIN folha_referencia fr ON fr.id_folha_referencia = c.id_folha_referencia
        LEFT JOIN contracheque_snapshot_funcional csf ON csf.id_contracheque = c.id_contracheque
        WHERE c.ano = :year
        {month_filter}
        {matricula_filter}
        {extra_filter}
        ORDER BY c.id_contracheque, s.numfunc, c.ano, c.mes, fr.num_folha NULLS LAST, c.numero
        OFFSET :offset_rows
        LIMIT :limit_rows
        """
    )
    return pd.read_sql_query(query, connection, params=params)


def load_cache_items(connection: Connection, contracheque_ids: list[int]) -> pd.DataFrame:
    if not contracheque_ids:
        return pd.DataFrame(
            columns=[
                "id_contracheque",
                "codigo_rubrica_origem",
                "nome_rubrica_origem",
                "tipo_rubrica_origem",
                "valor_vantagem",
                "valor_desconto",
                "valor_auxiliar",
            ]
        )

    query = text(
        """
        SELECT
            id_contracheque,
            codigo_rubrica_origem,
            nome_rubrica_origem,
            tipo_rubrica_origem,
            valor_vantagem,
            valor_desconto,
            valor_auxiliar
        FROM contracheque_item
        WHERE id_contracheque = ANY(:contracheque_ids)
        ORDER BY id_contracheque, sequencia_item NULLS LAST, id_contracheque_item
        """
    )
    return pd.read_sql_query(query, connection, params={"contracheque_ids": contracheque_ids})


def decimal_or_zero(value: object) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if pd.isna(value):
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    text_value = str(value).strip()
    if not text_value or text_value.lower() in {"nan", "none"}:
        return Decimal("0.00")
    try:
        return Decimal(text_value)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
