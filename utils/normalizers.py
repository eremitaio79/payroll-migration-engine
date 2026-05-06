from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import unicodedata
from typing import Any

import pandas as pd


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.copy()
    renamed.columns = [str(column).upper() for column in renamed.columns]
    return renamed


MONTH_ALIASES = {
    "JAN": "01",
    "JANEIRO": "01",
    "FEB": "02",
    "FEV": "02",
    "FEVEREIRO": "02",
    "MAR": "03",
    "MARCO": "03",
    "MARÇO": "03",
    "APR": "04",
    "ABR": "04",
    "ABRIL": "04",
    "MAY": "05",
    "MAI": "05",
    "MAIO": "05",
    "JUN": "06",
    "JUNHO": "06",
    "JUL": "07",
    "JULHO": "07",
    "AUG": "08",
    "AGO": "08",
    "AGOSTO": "08",
    "SEP": "09",
    "SET": "09",
    "SETEMBRO": "09",
    "OCT": "10",
    "OUT": "10",
    "OUTUBRO": "10",
    "NOV": "11",
    "NOVEMBRO": "11",
    "DEC": "12",
    "DEZ": "12",
    "DEZEMBRO": "12",
}


def normalize_folha_description(value: Any) -> str | None:
    text = normalize_string(value)
    if text is None:
        return None

    normalized = re.sub(r"\s+", " ", text).strip().upper()
    normalized = normalized.replace(" - ", " - ")

    def replace_month(match: re.Match[str]) -> str:
        month_token = match.group("month")
        year_token = match.group("year")
        month_number = MONTH_ALIASES.get(month_token.upper(), month_token)
        if month_number.isdigit() and len(month_number) == 1:
            month_number = month_number.zfill(2)
        return f"{month_number}/{year_token}"

    normalized = re.sub(
        r"(?P<month>[A-ZÇ]+|\d{1,2})/(?P<year>\d{4})",
        replace_month,
        normalized,
    )
    return normalized


def normalize_text_token(value: Any) -> str:
    text = normalize_string(value) or ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().upper()


def classify_folha_tipo(value: Any) -> str:
    normalized = normalize_text_token(value)
    if "DECIMO" in normalized or "13" in normalized:
        return "DECIMO"
    if "NORMAL" in normalized:
        return "NORMAL"
    if "AVULSA" in normalized:
        return "AVULSO"
    if "ESTORNO" in normalized:
        return "ESTORNO"
    return "OUTROS"


def normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if pd.isna(value):
        return None
    return int(value)


def normalize_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if pd.isna(value):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def normalize_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if pd.isna(value):
        return None
    return pd.to_datetime(value).date()


def date_parts(value: date | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    return value.year, value.month
