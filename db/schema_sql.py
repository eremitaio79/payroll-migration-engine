from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class SchemaBuildResult:
    sql: str
    schema: str
    table_count: int
    index_count: int
    foreign_key_count: int
    unique_constraint_count: int


TABLE_COUNT = 13
INDEX_COUNT = 37
FOREIGN_KEY_COUNT = 10
UNIQUE_CONSTRAINT_COUNT = 10


def build_normalized_postgres_schema_sql(schema: str = "public") -> SchemaBuildResult:
    schema = schema.strip() or "public"
    qschema = f'"{schema}"'

    statements = [
        f"""
CREATE SCHEMA IF NOT EXISTS {qschema};
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."usuario_portal" (
    "id_usuario" BIGSERIAL PRIMARY KEY,
    "login" VARCHAR(100) NOT NULL,
    "nome" VARCHAR(200) NOT NULL,
    "cpf" VARCHAR(11),
    "email" VARCHAR(200),
    "ativo" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    CONSTRAINT "usuario_portal_login_unique" UNIQUE ("login")
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."servidor" (
    "id_servidor" BIGSERIAL PRIMARY KEY,
    "numfunc" BIGINT NOT NULL,
    "cpf" VARCHAR(11),
    "nome" VARCHAR(300) NOT NULL,
    "pis_pasep" VARCHAR(11),
    "identidade" VARCHAR(48),
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    CONSTRAINT "servidor_numfunc_unique" UNIQUE ("numfunc")
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."usuario_servidor" (
    "id_usuario_servidor" BIGSERIAL PRIMARY KEY,
    "id_usuario" BIGINT NOT NULL,
    "id_servidor" BIGINT NOT NULL,
    "principal" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "usuario_servidor_id_usuario_id_servidor_unique" UNIQUE ("id_usuario", "id_servidor"),
    CONSTRAINT "usuario_servidor_id_usuario_foreign" FOREIGN KEY ("id_usuario")
        REFERENCES {qschema}."usuario_portal" ("id_usuario")
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT "usuario_servidor_id_servidor_foreign" FOREIGN KEY ("id_servidor")
        REFERENCES {qschema}."servidor" ("id_servidor")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."servidor_vinculo" (
    "id_vinculo" BIGSERIAL PRIMARY KEY,
    "id_servidor" BIGINT NOT NULL,
    "numvinc" BIGINT NOT NULL,
    "id_funcional" VARCHAR(81),
    "regime_juridico" VARCHAR(20),
    "tipo_vinculo" VARCHAR(20),
    "ativo" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    CONSTRAINT "servidor_vinculo_id_servidor_numvinc_unique" UNIQUE ("id_servidor", "numvinc"),
    CONSTRAINT "servidor_vinculo_id_servidor_foreign" FOREIGN KEY ("id_servidor")
        REFERENCES {qschema}."servidor" ("id_servidor")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."folha_referencia" (
    "id_folha_referencia" BIGSERIAL PRIMARY KEY,
    "mes_ano_folha" DATE NOT NULL,
    "num_folha" BIGINT NOT NULL,
    "descricao_folha" VARCHAR(30),
    "data_consolidacao" DATE,
    "dt_lib_c_cheque" DATE,
    "ano" SMALLINT NOT NULL,
    "mes" SMALLINT NOT NULL,
    "ativa" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "folha_referencia_mes_ano_folha_num_folha_unique" UNIQUE ("mes_ano_folha", "num_folha")
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."contracheque" (
    "id_contracheque" BIGSERIAL PRIMARY KEY,
    "id_vinculo" BIGINT NOT NULL,
    "id_folha_referencia" BIGINT NOT NULL,
    "mes_ano" DATE NOT NULL,
    "numero" BIGINT NOT NULL,
    "folha_descricao_origem" VARCHAR(31),
    "competencia" VARCHAR(7),
    "bruto" NUMERIC(15, 2),
    "descontos" NUMERIC(15, 2),
    "liquido" NUMERIC(15, 2),
    "data_consolidacao" DATE,
    "dt_lib_c_cheque" DATE,
    "ano" SMALLINT NOT NULL,
    "mes" SMALLINT NOT NULL,
    "hash_origem" VARCHAR(64),
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    CONSTRAINT "contracheque_id_vinculo_mes_ano_numero_unique" UNIQUE ("id_vinculo", "mes_ano", "numero"),
    CONSTRAINT "contracheque_id_vinculo_foreign" FOREIGN KEY ("id_vinculo")
        REFERENCES {qschema}."servidor_vinculo" ("id_vinculo")
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT "contracheque_id_folha_referencia_foreign" FOREIGN KEY ("id_folha_referencia")
        REFERENCES {qschema}."folha_referencia" ("id_folha_referencia")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."contracheque_snapshot_funcional" (
    "id_snapshot" BIGSERIAL PRIMARY KEY,
    "id_contracheque" BIGINT NOT NULL,
    "orgao" VARCHAR(50),
    "cargo" VARCHAR(100),
    "ref_cargo" VARCHAR(10),
    "funcao" VARCHAR(100),
    "ref_funcao" VARCHAR(2000),
    "municipio" VARCHAR(30),
    "setor" VARCHAR(50),
    "regime_juridico" VARCHAR(20),
    "tipo_vinculo" VARCHAR(20),
    "banco" VARCHAR(50),
    "agencia" VARCHAR(50),
    "conta" VARCHAR(20),
    "carga_horaria" NUMERIC(10, 2),
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "contracheque_snapshot_funcional_id_contracheque_unique" UNIQUE ("id_contracheque"),
    CONSTRAINT "contracheque_snapshot_funcional_id_contracheque_foreign" FOREIGN KEY ("id_contracheque")
        REFERENCES {qschema}."contracheque" ("id_contracheque")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."rubrica" (
    "id_rubrica" BIGSERIAL PRIMARY KEY,
    "codigo_rubrica" BIGINT NOT NULL,
    "nome_rubrica" VARCHAR(100) NOT NULL,
    "tipo_rubrica" VARCHAR(8),
    "ativa" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    CONSTRAINT "rubrica_codigo_rubrica_unique" UNIQUE ("codigo_rubrica")
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."contracheque_item" (
    "id_contracheque_item" BIGSERIAL PRIMARY KEY,
    "id_contracheque" BIGINT NOT NULL,
    "id_rubrica" BIGINT,
    "sequencia_item" INTEGER,
    "codigo_rubrica_origem" BIGINT,
    "nome_rubrica_origem" VARCHAR(100),
    "tipo_rubrica_origem" VARCHAR(8),
    "complemento" VARCHAR(20),
    "info" VARCHAR(496),
    "valor_vantagem" NUMERIC(15, 2),
    "valor_desconto" NUMERIC(15, 2),
    "valor_auxiliar" NUMERIC(15, 2),
    "valor_total_item" NUMERIC(15, 2),
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "contracheque_item_id_contracheque_foreign" FOREIGN KEY ("id_contracheque")
        REFERENCES {qschema}."contracheque" ("id_contracheque")
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT "contracheque_item_id_rubrica_foreign" FOREIGN KEY ("id_rubrica")
        REFERENCES {qschema}."rubrica" ("id_rubrica")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."carga_importacao" (
    "id_carga" BIGSERIAL PRIMARY KEY,
    "tipo_origem" VARCHAR(50) NOT NULL,
    "referencia" VARCHAR(50),
    "data_inicio" TIMESTAMP NOT NULL,
    "data_fim" TIMESTAMP NULL,
    "status" VARCHAR(20) NOT NULL,
    "qtd_registros_lidos" BIGINT DEFAULT 0,
    "qtd_registros_processados" BIGINT DEFAULT 0,
    "qtd_registros_erro" BIGINT DEFAULT 0,
    "observacao" VARCHAR(1000)
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."carga_importacao_erro" (
    "id_carga_erro" BIGSERIAL PRIMARY KEY,
    "id_carga" BIGINT NOT NULL,
    "chave_origem" VARCHAR(200),
    "mensagem_erro" VARCHAR(2000) NOT NULL,
    "payload_origem" TEXT,
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "carga_importacao_erro_id_carga_foreign" FOREIGN KEY ("id_carga")
        REFERENCES {qschema}."carga_importacao" ("id_carga")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."contracheque_consolidado" (
    "id_contracheque_consolidado" BIGSERIAL PRIMARY KEY,
    "id_contracheque" BIGINT NOT NULL,
    "total_vantagens" NUMERIC(15, 2),
    "total_descontos_itens" NUMERIC(15, 2),
    "total_itens" INTEGER,
    "divergencia_bruto" NUMERIC(15, 2),
    "divergencia_descontos" NUMERIC(15, 2),
    "divergencia_liquido" NUMERIC(15, 2),
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "contracheque_consolidado_id_contracheque_unique" UNIQUE ("id_contracheque"),
    CONSTRAINT "contracheque_consolidado_id_contracheque_foreign" FOREIGN KEY ("id_contracheque")
        REFERENCES {qschema}."contracheque" ("id_contracheque")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {qschema}."contracheque_cache" (
    "id" BIGSERIAL PRIMARY KEY,
    "matricula" VARCHAR(20) NOT NULL,
    "cpf" VARCHAR(11) NOT NULL,
    "ano" INTEGER NOT NULL,
    "mes" INTEGER NOT NULL,
    "contracheque_json" JSONB NOT NULL,
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    "folha_numero" INTEGER,
    "folha_tipo" VARCHAR(50),
    "folha_descricao" VARCHAR(150),
    CONSTRAINT "contracheque_cache_matricula_ano_mes_folha_numero_unique"
        UNIQUE ("matricula", "ano", "mes", "folha_numero")
);
""".strip(),
        f'CREATE INDEX IF NOT EXISTS "usuario_portal_cpf_index" ON {qschema}."usuario_portal" ("cpf");',
        f'CREATE INDEX IF NOT EXISTS "servidor_cpf_index" ON {qschema}."servidor" ("cpf");',
        f'CREATE INDEX IF NOT EXISTS "servidor_nome_index" ON {qschema}."servidor" ("nome");',
        f'CREATE INDEX IF NOT EXISTS "usuario_servidor_id_usuario_index" ON {qschema}."usuario_servidor" ("id_usuario");',
        f'CREATE INDEX IF NOT EXISTS "usuario_servidor_id_servidor_index" ON {qschema}."usuario_servidor" ("id_servidor");',
        f'CREATE INDEX IF NOT EXISTS "servidor_vinculo_id_servidor_index" ON {qschema}."servidor_vinculo" ("id_servidor");',
        f'CREATE INDEX IF NOT EXISTS "servidor_vinculo_id_funcional_index" ON {qschema}."servidor_vinculo" ("id_funcional");',
        f'CREATE INDEX IF NOT EXISTS "servidor_vinculo_regime_juridico_index" ON {qschema}."servidor_vinculo" ("regime_juridico");',
        f'CREATE INDEX IF NOT EXISTS "servidor_vinculo_tipo_vinculo_index" ON {qschema}."servidor_vinculo" ("tipo_vinculo");',
        f'CREATE INDEX IF NOT EXISTS "folha_referencia_ano_mes_index" ON {qschema}."folha_referencia" ("ano", "mes");',
        f'CREATE INDEX IF NOT EXISTS "folha_referencia_dt_lib_c_cheque_index" ON {qschema}."folha_referencia" ("dt_lib_c_cheque");',
        f'CREATE INDEX IF NOT EXISTS "folha_referencia_num_folha_index" ON {qschema}."folha_referencia" ("num_folha");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_id_vinculo_index" ON {qschema}."contracheque" ("id_vinculo");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_id_folha_referencia_index" ON {qschema}."contracheque" ("id_folha_referencia");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_ano_mes_index" ON {qschema}."contracheque" ("ano", "mes");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_id_vinculo_ano_mes_index" ON {qschema}."contracheque" ("id_vinculo", "ano", "mes");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_dt_lib_c_cheque_index" ON {qschema}."contracheque" ("dt_lib_c_cheque");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_hash_origem_index" ON {qschema}."contracheque" ("hash_origem");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_id_contracheque_index" ON {qschema}."contracheque_snapshot_funcional" ("id_contracheque");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_orgao_index" ON {qschema}."contracheque_snapshot_funcional" ("orgao");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_cargo_index" ON {qschema}."contracheque_snapshot_funcional" ("cargo");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_municipio_index" ON {qschema}."contracheque_snapshot_funcional" ("municipio");',
        f'CREATE INDEX IF NOT EXISTS "rubrica_nome_rubrica_index" ON {qschema}."rubrica" ("nome_rubrica");',
        f'CREATE INDEX IF NOT EXISTS "rubrica_tipo_rubrica_index" ON {qschema}."rubrica" ("tipo_rubrica");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_item_id_contracheque_index" ON {qschema}."contracheque_item" ("id_contracheque");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_item_id_rubrica_index" ON {qschema}."contracheque_item" ("id_rubrica");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_item_codigo_rubrica_origem_index" ON {qschema}."contracheque_item" ("codigo_rubrica_origem");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_item_tipo_rubrica_origem_index" ON {qschema}."contracheque_item" ("tipo_rubrica_origem");',
        f'CREATE INDEX IF NOT EXISTS "carga_importacao_tipo_origem_index" ON {qschema}."carga_importacao" ("tipo_origem");',
        f'CREATE INDEX IF NOT EXISTS "carga_importacao_status_index" ON {qschema}."carga_importacao" ("status");',
        f'CREATE INDEX IF NOT EXISTS "carga_importacao_referencia_index" ON {qschema}."carga_importacao" ("referencia");',
        f'CREATE INDEX IF NOT EXISTS "carga_importacao_erro_id_carga_index" ON {qschema}."carga_importacao_erro" ("id_carga");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_consolidado_id_contracheque_index" ON {qschema}."contracheque_consolidado" ("id_contracheque");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_cache_matricula_index" ON {qschema}."contracheque_cache" ("matricula");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_cache_cpf_index" ON {qschema}."contracheque_cache" ("cpf");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_cache_ano_mes_index" ON {qschema}."contracheque_cache" ("ano", "mes");',
        f'CREATE INDEX IF NOT EXISTS "contracheque_cache_matricula_ano_mes_index" ON {qschema}."contracheque_cache" ("matricula", "ano", "mes");',
    ]

    sql = "\n\n".join(statements) + "\n"

    return SchemaBuildResult(
        sql=sql,
        schema=schema,
        table_count=TABLE_COUNT,
        index_count=INDEX_COUNT,
        foreign_key_count=FOREIGN_KEY_COUNT,
        unique_constraint_count=UNIQUE_CONSTRAINT_COUNT,
    )


def write_schema_sql_file(sql: str, base_dir: str | Path, schema: str) -> Path:
    target_dir = Path(base_dir) / "reports" / "schema"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"postgres_schema_normalizado_{schema}_{timestamp}.sql"
    file_path = target_dir / filename
    file_path.write_text(sql, encoding="utf-8")
    return file_path
