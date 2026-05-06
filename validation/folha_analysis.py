from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

from utils.normalizers import normalize_folha_description


def build_folha_lookup(folhas_df: pd.DataFrame) -> tuple[dict[tuple[date, str | None], dict[str, Any]], dict[date, dict[str, Any]]]:
    descricao_map: dict[tuple[date, str | None], dict[str, Any]] = {}
    mes_map: dict[date, dict[str, Any]] = {}

    for row in folhas_df.to_dict(orient="records"):
        descricao_normalizada = normalize_folha_description(row["descricao_folha"])
        registro = {
            "mes_ano_folha": row["mes_ano_folha"],
            "num_folha": row["num_folha"],
            "descricao_folha": row["descricao_folha"],
            "descricao_folha_normalizada": descricao_normalizada,
        }
        descricao_map[(row["mes_ano_folha"], descricao_normalizada)] = registro
        mes_map.setdefault(
            row["mes_ano_folha"],
            {"count": 0, "num_folhas": [], "descricoes": [], "descricoes_normalizadas": []},
        )
        mes_map[row["mes_ano_folha"]]["count"] += 1
        mes_map[row["mes_ano_folha"]]["num_folhas"].append(row["num_folha"])
        mes_map[row["mes_ano_folha"]]["descricoes"].append(row["descricao_folha"])
        mes_map[row["mes_ano_folha"]]["descricoes_normalizadas"].append(descricao_normalizada)

    return descricao_map, mes_map


def analyze_folhas_por_mes(folhas_df: pd.DataFrame) -> dict[str, Any]:
    _, mes_map = build_folha_lookup(folhas_df)
    meses_multiplos = [
        {
            "mes_ano": mes,
            "quantidade_folhas": data["count"],
            "num_folhas": sorted(set(data["num_folhas"])),
            "descricoes": sorted({descricao for descricao in data["descricoes"] if descricao}),
        }
        for mes, data in sorted(mes_map.items())
        if data["count"] > 1
    ]
    total_meses = len(mes_map)
    meses_folha_unica = sum(1 for data in mes_map.values() if data["count"] == 1)
    meses_multiplas_folhas = len(meses_multiplos)

    return {
        "total_meses": total_meses,
        "meses_folha_unica": meses_folha_unica,
        "meses_multiplas_folhas": meses_multiplas_folhas,
        "meses_multiplos": meses_multiplos,
    }


def analyze_distribuicao_folhas(folhas_df: pd.DataFrame) -> Counter:
    return Counter(row["mes_ano_folha"] for row in folhas_df.to_dict(orient="records"))
