from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

import pandas as pd

from cache.data_loader import decimal_or_zero
from utils.normalizers import classify_folha_tipo, normalize_folha_description, normalize_string


def classify_item(row: dict) -> tuple[str | None, Decimal]:
    desconto = decimal_or_zero(row.get("valor_desconto"))
    vantagem = decimal_or_zero(row.get("valor_vantagem"))
    auxiliar = decimal_or_zero(row.get("valor_auxiliar"))

    if desconto > 0:
        return "DESCONTO", desconto

    total_vantagem = vantagem + auxiliar
    if total_vantagem > 0:
        return "VANTAGEM", total_vantagem

    return None, Decimal("0.00")


def _resolve_folha_numeros(candidates_df: pd.DataFrame) -> dict[int, int]:
    if candidates_df.empty:
        return {}

    resolved: dict[int, int] = {}
    group_columns = ["numfunc", "ano", "mes"]
    for _, group in candidates_df.groupby(group_columns, sort=False):
        used_numbers: set[int] = set()
        ordered_group = group.sort_values(
            by=["num_folha", "numero", "id_contracheque"],
            na_position="last",
        )

        for row in ordered_group.to_dict(orient="records"):
            candidate_numbers: list[int] = []
            for key in ("num_folha", "numero", "id_contracheque"):
                value = row.get(key)
                if value is not None and not pd.isna(value):
                    candidate_numbers.append(int(value))

            resolved_number = next((value for value in candidate_numbers if value > 0 and value not in used_numbers), None)
            if resolved_number is None:
                fallback_base = int(row["id_contracheque"]) if row.get("id_contracheque") is not None else 0
                resolved_number = max(900000000, fallback_base)
                while resolved_number in used_numbers:
                    resolved_number += 1

            used_numbers.add(resolved_number)
            resolved[int(row["id_contracheque"])] = resolved_number

    return resolved


def build_cache_payloads(candidates_df: pd.DataFrame, items_df: pd.DataFrame) -> list[dict]:
    if candidates_df.empty:
        return []

    candidates_df = candidates_df.drop_duplicates(subset=["id_contracheque"], keep="last").reset_index(drop=True)
    items_grouped: dict[int, list[dict]] = {}
    for row in items_df.to_dict(orient="records"):
        items_grouped.setdefault(int(row["id_contracheque"]), []).append(row)

    folha_numero_map = _resolve_folha_numeros(candidates_df)
    payloads: list[dict] = []
    for candidate in candidates_df.to_dict(orient="records"):
        item_rows = items_grouped.get(int(candidate["id_contracheque"]), [])
        rubricas = []
        bruto = Decimal("0.00")
        descontos = Decimal("0.00")
        folha_descricao = (
            normalize_string(candidate.get("descricao_folha"))
            or normalize_string(candidate.get("folha_descricao_origem"))
            or ""
        )
        folha_numero = folha_numero_map[int(candidate["id_contracheque"])]
        folha_tipo = classify_folha_tipo(folha_descricao)

        for item in item_rows:
            tipo, valor = classify_item(item)
            if tipo is None or valor <= 0:
                continue
            rubricas.append(
                {
                    "codigo": int(item["codigo_rubrica_origem"]) if item["codigo_rubrica_origem"] is not None else 0,
                    "descricao": normalize_string(item["nome_rubrica_origem"]) or "",
                    "tipo": tipo,
                    "valor": float(valor),
                }
            )
            if tipo == "VANTAGEM":
                bruto += valor
            else:
                descontos += valor

        liquido = bruto - descontos
        descricao_competencia = (
            normalize_string(candidate.get("folha_descricao_origem"))
            or normalize_string(candidate.get("competencia"))
            or f"{int(candidate['mes']):02d}/{int(candidate['ano'])}"
        )
        data_liberacao = candidate.get("dt_lib_c_cheque")
        regime_juridico = (
            normalize_string(candidate.get("snap_regime_juridico"))
            or normalize_string(candidate.get("vinc_regime_juridico"))
            or ""
        )
        tipo_vinculo = (
            normalize_string(candidate.get("snap_tipo_vinculo"))
            or normalize_string(candidate.get("vinc_tipo_vinculo"))
            or ""
        )
        payload_json = {
            "servidor": {
                "nome": normalize_string(candidate.get("nome")) or "",
                "cpf": normalize_string(candidate.get("cpf")) or "",
                "matricula": str(candidate["numfunc"]),
                "id_funcional": normalize_string(candidate.get("id_funcional")) or "",
                "orgao": normalize_string(candidate.get("orgao")) or "",
                "cargo": normalize_string(candidate.get("cargo")) or "",
                "referencia_cargo": normalize_string(candidate.get("ref_cargo")) or "",
                "funcao": normalize_string(candidate.get("funcao")) or "",
                "referencia_funcao": normalize_string(candidate.get("ref_funcao")) or "",
                "municipio": normalize_string(candidate.get("municipio")) or "",
                "setor": normalize_string(candidate.get("setor")) or "",
                "regime_juridico": regime_juridico,
                "tipo_vinculo": tipo_vinculo,
                "banco": normalize_string(candidate.get("banco")) or "",
                "agencia": normalize_string(candidate.get("agencia")) or "",
                "conta": normalize_string(candidate.get("conta")) or "",
                "pis_pasep": normalize_string(candidate.get("pis_pasep")) or "",
                "identidade": normalize_string(candidate.get("identidade")) or "",
                "carga_horaria": float(decimal_or_zero(candidate.get("carga_horaria"))),
            },
            "competencia": {
                "ano": int(candidate["ano"]),
                "mes": int(candidate["mes"]),
                "descricao": descricao_competencia,
                "data_liberacao": data_liberacao.isoformat() if data_liberacao else "",
                "folha_numero": folha_numero,
                "folha_tipo": folha_tipo,
                "folha_descricao": folha_descricao,
            },
            "resumo": {
                "bruto": float(bruto),
                "descontos": float(descontos),
                "liquido": float(liquido),
            },
            "rubricas": rubricas,
        }
        payloads.append(
            {
                "matricula": str(candidate["numfunc"]),
                "cpf": normalize_string(candidate.get("cpf")) or "",
                "ano": int(candidate["ano"]),
                "mes": int(candidate["mes"]),
                "folha_numero": folha_numero,
                "folha_tipo": folha_tipo,
                "folha_descricao": normalize_folha_description(folha_descricao) or folha_descricao,
                "contracheque_json": payload_json,
            }
        )
    return payloads
