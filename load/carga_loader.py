from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Table, update
from sqlalchemy.engine import Engine


def iniciar_carga(engine: Engine, metadata, tipo_origem: str, referencia: str | None) -> int:
    tabela: Table = metadata.tables["carga_importacao"]
    with engine.begin() as connection:
        result = connection.execute(
            tabela.insert().values(
                tipo_origem=tipo_origem,
                referencia=referencia,
                data_inicio=datetime.now(),
                status="INICIADO",
                qtd_registros_lidos=0,
                qtd_registros_processados=0,
                qtd_registros_erro=0,
            )
        )
        return int(result.inserted_primary_key[0])


def finalizar_carga(
    engine: Engine,
    metadata,
    id_carga: int,
    status: str,
    qtd_lidos: int,
    qtd_processados: int,
    qtd_erros: int,
    observacao: str | None = None,
) -> None:
    tabela: Table = metadata.tables["carga_importacao"]
    with engine.begin() as connection:
        connection.execute(
            update(tabela)
            .where(tabela.c.id_carga == id_carga)
            .values(
                data_fim=datetime.now(),
                status=status,
                qtd_registros_lidos=qtd_lidos,
                qtd_registros_processados=qtd_processados,
                qtd_registros_erro=qtd_erros,
                observacao=observacao,
            )
        )


def registrar_erros(engine: Engine, metadata, id_carga: int, erros: list[dict[str, Any]]) -> None:
    if not erros:
        return

    tabela: Table = metadata.tables["carga_importacao_erro"]
    payload = [
        {
            "id_carga": id_carga,
            "chave_origem": erro.get("chave_origem"),
            "mensagem_erro": erro.get("mensagem_erro", "Erro nao informado"),
            "payload_origem": json.dumps(erro.get("payload_origem"), ensure_ascii=False, default=str),
        }
        for erro in erros
    ]
    with engine.begin() as connection:
        connection.execute(tabela.insert(), payload)
