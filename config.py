from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy.engine import URL


load_dotenv()


@dataclass(frozen=True)
class Settings:
    oracle_host: str
    oracle_port: int
    oracle_service: str
    oracle_user: str
    oracle_password: str
    oracle_client_lib_dir: str | None
    oracle_source_schema: str | None
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    default_year: int = 2026

    @property
    def oracle_dsn(self) -> str:
        return URL.create(
            "oracle+oracledb",
            username=self.oracle_user,
            password=self.oracle_password,
            host=self.oracle_host,
            port=self.oracle_port,
            query={"service_name": self.oracle_service},
        ).render_as_string(hide_password=False)

    @property
    def postgres_dsn(self) -> str:
        return URL.create(
            "postgresql+psycopg2",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return value


def load_settings() -> Settings:
    return Settings(
        oracle_host=_required_env("ORACLE_HOST"),
        oracle_port=int(_required_env("ORACLE_PORT")),
        oracle_service=_required_env("ORACLE_SERVICE"),
        oracle_user=_required_env("ORACLE_USER"),
        oracle_password=_required_env("ORACLE_PASSWORD"),
        oracle_client_lib_dir=os.getenv("ORACLE_CLIENT_LIB_DIR", "").strip() or None,
        oracle_source_schema=os.getenv("ORACLE_SOURCE_SCHEMA", "").strip() or None,
        postgres_host=_required_env("POSTGRES_HOST"),
        postgres_port=int(_required_env("POSTGRES_PORT")),
        postgres_db=_required_env("POSTGRES_DB"),
        postgres_user=_required_env("POSTGRES_USER"),
        postgres_password=_required_env("POSTGRES_PASSWORD"),
        default_year=int(os.getenv("ETL_DEFAULT_YEAR", "2026")),
    )
