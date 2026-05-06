from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

from utils.normalizers import normalize_folha_description


class ValidationAccumulator:
    def __init__(
        self,
        folhas_lookup_desc: dict[tuple[date, str | None], dict[str, Any]],
        folhas_lookup_mes: dict[date, dict[str, Any]],
    ) -> None:
        self.folhas_lookup_desc = folhas_lookup_desc
        self.folhas_lookup_mes = folhas_lookup_mes
        self.servidores_unicos: set[int] = set()
        self.vinculos_unicos: set[tuple[int, int]] = set()
        self.rubricas_unicas: set[int] = set()
        self.contracheques_total = 0
        self.mapeados_por_descricao = 0
        self.mapeados_por_fallback = 0
        self.nao_mapeados = 0
        self.rubricas_nulas = 0
        self.nomes_rubrica_vazios = 0
        self.contracheques_sem_vinculo = 0
        self.exemplos_falha_mapeamento: list[dict[str, Any]] = []
        self.exemplos_sem_vinculo: list[dict[str, Any]] = []
        self.exemplos_rubrica_nula: list[dict[str, Any]] = []
        self.contracheques_por_mes: Counter[date] = Counter()
        self.itens_por_contracheque: Counter[tuple[int, int, date, int]] = Counter()

    def consume(
        self,
        servidores_df: pd.DataFrame,
        vinculos_df: pd.DataFrame,
        rubricas_df: pd.DataFrame,
        contracheques_df: pd.DataFrame,
        itens_df: pd.DataFrame,
    ) -> None:
        self.servidores_unicos.update(
            int(value) for value in servidores_df["numfunc"].dropna().tolist()
        )
        vinculos_set = {
            (int(row["numfunc"]), int(row["numvinc"]))
            for row in vinculos_df.to_dict(orient="records")
        }
        self.vinculos_unicos.update(vinculos_set)
        self.rubricas_unicas.update(
            int(value) for value in rubricas_df["codigo_rubrica"].dropna().tolist()
        )

        for row in rubricas_df.to_dict(orient="records"):
            nome = row.get("nome_rubrica")
            if nome is None or str(nome).strip() == "":
                self.nomes_rubrica_vazios += 1

        for row in contracheques_df.to_dict(orient="records"):
            self.contracheques_total += 1
            self.contracheques_por_mes[row["mes_ano"]] += 1

            chave_descricao = (row["mes_ano"], normalize_folha_description(row["folha_descricao_origem"]))
            if chave_descricao in self.folhas_lookup_desc:
                self.mapeados_por_descricao += 1
            else:
                mes_info = self.folhas_lookup_mes.get(row["mes_ano"])
                if mes_info and mes_info["count"] == 1:
                    self.mapeados_por_fallback += 1
                else:
                    self.nao_mapeados += 1
                    if len(self.exemplos_falha_mapeamento) < 50:
                        self.exemplos_falha_mapeamento.append(
                            {
                                "numfunc": row["numfunc"],
                                "numvinc": row["numvinc"],
                                "mes_ano": row["mes_ano"],
                                "numero": row["numero"],
                                "folha_descricao_origem": row["folha_descricao_origem"],
                            }
                        )

            if (row["numfunc"], row["numvinc"]) not in vinculos_set:
                self.contracheques_sem_vinculo += 1
                if len(self.exemplos_sem_vinculo) < 50:
                    self.exemplos_sem_vinculo.append(
                        {
                            "numfunc": row["numfunc"],
                            "numvinc": row["numvinc"],
                            "mes_ano": row["mes_ano"],
                            "numero": row["numero"],
                        }
                    )

        for row in itens_df.to_dict(orient="records"):
            chave_cc = (row["numfunc"], row["numvinc"], row["mes_ano"], row["numero"])
            self.itens_por_contracheque[chave_cc] += 1
            if row.get("codigo_rubrica_origem") is None:
                self.rubricas_nulas += 1
                if len(self.exemplos_rubrica_nula) < 50:
                    self.exemplos_rubrica_nula.append(
                        {
                            "numfunc": row["numfunc"],
                            "numvinc": row["numvinc"],
                            "mes_ano": row["mes_ano"],
                            "numero": row["numero"],
                            "codigo_rubrica_origem": row["codigo_rubrica_origem"],
                            "nome_rubrica_origem": row["nome_rubrica_origem"],
                        }
                    )

    def finalize(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        media_itens = 0.0
        if self.itens_por_contracheque:
            media_itens = round(sum(self.itens_por_contracheque.values()) / len(self.itens_por_contracheque), 2)

        mapeamento = {
            "total_contracheques": self.contracheques_total,
            "mapeados_por_descricao": self.mapeados_por_descricao,
            "mapeados_por_fallback": self.mapeados_por_fallback,
            "nao_mapeados": self.nao_mapeados,
            "taxa_sucesso": _percent(self.mapeados_por_descricao + self.mapeados_por_fallback, self.contracheques_total),
            "taxa_fallback": _percent(self.mapeados_por_fallback, self.contracheques_total),
            "taxa_erro": _percent(self.nao_mapeados, self.contracheques_total),
            "exemplos_falha": self.exemplos_falha_mapeamento,
        }
        servidor_vinculo = {
            "servidores_unicos": len(self.servidores_unicos),
            "vinculos_unicos": len(self.vinculos_unicos),
            "contracheques_sem_vinculo": self.contracheques_sem_vinculo,
            "exemplos_sem_vinculo": self.exemplos_sem_vinculo,
        }
        rubrica = {
            "rubricas_distintas": len(self.rubricas_unicas),
            "rubricas_nulas": self.rubricas_nulas,
            "nomes_rubrica_vazios": self.nomes_rubrica_vazios,
            "exemplos_rubrica_nula": self.exemplos_rubrica_nula,
        }
        distribuicao = {
            "contracheques_por_mes": [
                {"mes_ano": mes, "quantidade": quantidade}
                for mes, quantidade in sorted(self.contracheques_por_mes.items())
            ],
            "media_itens_por_contracheque": media_itens,
        }
        return mapeamento, servidor_vinculo, rubrica, distribuicao


def _percent(value: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((value / total) * 100, 2)
