from __future__ import annotations

from datetime import date, datetime


def _parse_iso_date(value: date | str | None, label: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} invalida. Use o formato YYYY-MM-DD.") from exc


def validate_year(year: int) -> int:
    if year < 1900 or year > 2100:
        raise ValueError("Ano informado fora do intervalo suportado.")
    return year


def validate_month(month: int | None) -> int | None:
    if month is None:
        return None
    if month < 1 or month > 12:
        raise ValueError("Mes informado fora do intervalo suportado (1-12).")
    return month


def validate_date_range(
    start_date: date | str | None,
    end_date: date | str | None,
    year: int,
    month: int | None = None,
) -> tuple[date | None, date | None]:
    start_date = _parse_iso_date(start_date, "Data inicial")
    end_date = _parse_iso_date(end_date, "Data final")

    if start_date is None and end_date is None:
        return None, None

    if start_date is None or end_date is None:
        raise ValueError("Informe data inicial e data final juntas.")

    if start_date > end_date:
        raise ValueError("A data inicial nao pode ser maior que a data final.")

    if start_date.year != year or end_date.year != year:
        raise ValueError("O intervalo informado deve pertencer ao ano selecionado.")

    if month is not None and (start_date.month != month or end_date.month != month):
        raise ValueError("O intervalo informado deve pertencer ao mes selecionado.")

    return start_date, end_date
