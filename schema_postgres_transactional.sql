-- ============================================================================
-- Script: script_gera_tabelas_cc_begin_commit_comentado.sql
-- Objetivo:
--   Criar a estrutura completa do banco PostgreSQL normalizado utilizada pelo
--   ETL de contracheques.
--
-- Caracteristicas:
--   - Transacional: usa BEGIN/COMMIT
--   - Idempotente na criacao estrutural: usa IF NOT EXISTS onde aplicavel
--   - Baseado no estado real validado das migrations + banco PostgreSQL atual
--
-- Observacoes:
--   - Este script cria a estrutura no schema public
--   - Nao remove objetos existentes
--   - Nao popula dados
--   - Se alguma tabela ja existir com estrutura divergente, a execucao pode
--     falhar em constraints, FKs ou indices subsequentes
-- ============================================================================

BEGIN;

-- ============================================================================
-- BLOCO 1 - GARANTIA DO SCHEMA DE DESTINO
-- Garante a existencia do schema public antes da criacao das tabelas.
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS "public";

-- ============================================================================
-- BLOCO 2 - TABELAS BASE DE IDENTIDADE E RELACIONAMENTO DE ACESSO
-- Essas tabelas representam:
--   - usuarios do portal
--   - servidores
--   - vinculo entre usuario do portal e servidor
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."usuario_portal" (
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

CREATE TABLE IF NOT EXISTS "public"."servidor" (
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

CREATE TABLE IF NOT EXISTS "public"."usuario_servidor" (
    "id_usuario_servidor" BIGSERIAL PRIMARY KEY,
    "id_usuario" BIGINT NOT NULL,
    "id_servidor" BIGINT NOT NULL,
    "principal" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "usuario_servidor_id_usuario_id_servidor_unique" UNIQUE ("id_usuario", "id_servidor"),
    CONSTRAINT "usuario_servidor_id_usuario_foreign" FOREIGN KEY ("id_usuario")
        REFERENCES "public"."usuario_portal" ("id_usuario")
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT "usuario_servidor_id_servidor_foreign" FOREIGN KEY ("id_servidor")
        REFERENCES "public"."servidor" ("id_servidor")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- ============================================================================
-- BLOCO 3 - TABELAS DE VINCULO FUNCIONAL E REFERENCIA DE FOLHA
-- Essas tabelas estruturam:
--   - vinculos funcionais do servidor
--   - referencias de folha por competencia e numero de folha
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."servidor_vinculo" (
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
        REFERENCES "public"."servidor" ("id_servidor")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "public"."folha_referencia" (
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

-- ============================================================================
-- BLOCO 4 - TABELA CENTRAL DE CONTRACHEQUE
-- Esta e a entidade principal da base normalizada.
-- Ela depende de servidor_vinculo e folha_referencia.
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."contracheque" (
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
        REFERENCES "public"."servidor_vinculo" ("id_vinculo")
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT "contracheque_id_folha_referencia_foreign" FOREIGN KEY ("id_folha_referencia")
        REFERENCES "public"."folha_referencia" ("id_folha_referencia")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- ============================================================================
-- BLOCO 5 - TABELAS SATELITES DO CONTRACHEQUE
-- Complementam o contracheque com:
--   - snapshot funcional
--   - rubricas
--   - itens detalhados
--   - consolidado resumido
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."contracheque_snapshot_funcional" (
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
        REFERENCES "public"."contracheque" ("id_contracheque")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "public"."rubrica" (
    "id_rubrica" BIGSERIAL PRIMARY KEY,
    "codigo_rubrica" BIGINT NOT NULL,
    "nome_rubrica" VARCHAR(100) NOT NULL,
    "tipo_rubrica" VARCHAR(8),
    "ativa" CHAR(1) NOT NULL DEFAULT 'S',
    "created_at" TIMESTAMP NULL,
    "updated_at" TIMESTAMP NULL,
    CONSTRAINT "rubrica_codigo_rubrica_unique" UNIQUE ("codigo_rubrica")
);

CREATE TABLE IF NOT EXISTS "public"."contracheque_item" (
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
        REFERENCES "public"."contracheque" ("id_contracheque")
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT "contracheque_item_id_rubrica_foreign" FOREIGN KEY ("id_rubrica")
        REFERENCES "public"."rubrica" ("id_rubrica")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "public"."contracheque_consolidado" (
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
        REFERENCES "public"."contracheque" ("id_contracheque")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- ============================================================================
-- BLOCO 6 - TABELAS DE AUDITORIA DE CARGA
-- Registram execucoes, status, quantidades processadas e erros de importacao.
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."carga_importacao" (
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

CREATE TABLE IF NOT EXISTS "public"."carga_importacao_erro" (
    "id_carga_erro" BIGSERIAL PRIMARY KEY,
    "id_carga" BIGINT NOT NULL,
    "chave_origem" VARCHAR(200),
    "mensagem_erro" VARCHAR(2000) NOT NULL,
    "payload_origem" TEXT,
    "created_at" TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "carga_importacao_erro_id_carga_foreign" FOREIGN KEY ("id_carga")
        REFERENCES "public"."carga_importacao" ("id_carga")
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- ============================================================================
-- BLOCO 7 - TABELA DE CACHE JSON
-- Estrutura derivada para leitura rapida do contracheque processado.
-- Inclui a versao atual com suporte a multiplos contracheques por competencia.
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."contracheque_cache" (
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

-- ============================================================================
-- BLOCO 8 - INDICES OPERACIONAIS
-- Melhoram performance das consultas, joins, filtros por competencia, lookup
-- por matricula, chaves tecnicas e uso geral do ETL e da API.
-- ============================================================================

CREATE INDEX IF NOT EXISTS "usuario_portal_cpf_index" ON "public"."usuario_portal" ("cpf");
CREATE INDEX IF NOT EXISTS "servidor_cpf_index" ON "public"."servidor" ("cpf");
CREATE INDEX IF NOT EXISTS "servidor_nome_index" ON "public"."servidor" ("nome");
CREATE INDEX IF NOT EXISTS "usuario_servidor_id_usuario_index" ON "public"."usuario_servidor" ("id_usuario");
CREATE INDEX IF NOT EXISTS "usuario_servidor_id_servidor_index" ON "public"."usuario_servidor" ("id_servidor");
CREATE INDEX IF NOT EXISTS "servidor_vinculo_id_servidor_index" ON "public"."servidor_vinculo" ("id_servidor");
CREATE INDEX IF NOT EXISTS "servidor_vinculo_id_funcional_index" ON "public"."servidor_vinculo" ("id_funcional");
CREATE INDEX IF NOT EXISTS "servidor_vinculo_regime_juridico_index" ON "public"."servidor_vinculo" ("regime_juridico");
CREATE INDEX IF NOT EXISTS "servidor_vinculo_tipo_vinculo_index" ON "public"."servidor_vinculo" ("tipo_vinculo");
CREATE INDEX IF NOT EXISTS "folha_referencia_ano_mes_index" ON "public"."folha_referencia" ("ano", "mes");
CREATE INDEX IF NOT EXISTS "folha_referencia_dt_lib_c_cheque_index" ON "public"."folha_referencia" ("dt_lib_c_cheque");
CREATE INDEX IF NOT EXISTS "folha_referencia_num_folha_index" ON "public"."folha_referencia" ("num_folha");
CREATE INDEX IF NOT EXISTS "contracheque_id_vinculo_index" ON "public"."contracheque" ("id_vinculo");
CREATE INDEX IF NOT EXISTS "contracheque_id_folha_referencia_index" ON "public"."contracheque" ("id_folha_referencia");
CREATE INDEX IF NOT EXISTS "contracheque_ano_mes_index" ON "public"."contracheque" ("ano", "mes");
CREATE INDEX IF NOT EXISTS "contracheque_id_vinculo_ano_mes_index" ON "public"."contracheque" ("id_vinculo", "ano", "mes");
CREATE INDEX IF NOT EXISTS "contracheque_dt_lib_c_cheque_index" ON "public"."contracheque" ("dt_lib_c_cheque");
CREATE INDEX IF NOT EXISTS "contracheque_hash_origem_index" ON "public"."contracheque" ("hash_origem");
CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_id_contracheque_index" ON "public"."contracheque_snapshot_funcional" ("id_contracheque");
CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_orgao_index" ON "public"."contracheque_snapshot_funcional" ("orgao");
CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_cargo_index" ON "public"."contracheque_snapshot_funcional" ("cargo");
CREATE INDEX IF NOT EXISTS "contracheque_snapshot_funcional_municipio_index" ON "public"."contracheque_snapshot_funcional" ("municipio");
CREATE INDEX IF NOT EXISTS "rubrica_nome_rubrica_index" ON "public"."rubrica" ("nome_rubrica");
CREATE INDEX IF NOT EXISTS "rubrica_tipo_rubrica_index" ON "public"."rubrica" ("tipo_rubrica");
CREATE INDEX IF NOT EXISTS "contracheque_item_id_contracheque_index" ON "public"."contracheque_item" ("id_contracheque");
CREATE INDEX IF NOT EXISTS "contracheque_item_id_rubrica_index" ON "public"."contracheque_item" ("id_rubrica");
CREATE INDEX IF NOT EXISTS "contracheque_item_codigo_rubrica_origem_index" ON "public"."contracheque_item" ("codigo_rubrica_origem");
CREATE INDEX IF NOT EXISTS "contracheque_item_tipo_rubrica_origem_index" ON "public"."contracheque_item" ("tipo_rubrica_origem");
CREATE INDEX IF NOT EXISTS "carga_importacao_tipo_origem_index" ON "public"."carga_importacao" ("tipo_origem");
CREATE INDEX IF NOT EXISTS "carga_importacao_status_index" ON "public"."carga_importacao" ("status");
CREATE INDEX IF NOT EXISTS "carga_importacao_referencia_index" ON "public"."carga_importacao" ("referencia");
CREATE INDEX IF NOT EXISTS "carga_importacao_erro_id_carga_index" ON "public"."carga_importacao_erro" ("id_carga");
CREATE INDEX IF NOT EXISTS "contracheque_consolidado_id_contracheque_index" ON "public"."contracheque_consolidado" ("id_contracheque");
CREATE INDEX IF NOT EXISTS "contracheque_cache_matricula_index" ON "public"."contracheque_cache" ("matricula");
CREATE INDEX IF NOT EXISTS "contracheque_cache_cpf_index" ON "public"."contracheque_cache" ("cpf");
CREATE INDEX IF NOT EXISTS "contracheque_cache_ano_mes_index" ON "public"."contracheque_cache" ("ano", "mes");
CREATE INDEX IF NOT EXISTS "contracheque_cache_matricula_ano_mes_index" ON "public"."contracheque_cache" ("matricula", "ano", "mes");

-- ============================================================================
-- BLOCO 9 - FINALIZACAO DA TRANSACAO
-- Se tudo ocorrer bem, consolida a criacao da estrutura.
-- ============================================================================
COMMIT;
