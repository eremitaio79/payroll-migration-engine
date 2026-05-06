from __future__ import annotations

import oracledb
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from config import Settings


def create_oracle_engine(settings: Settings) -> Engine:
    if settings.oracle_client_lib_dir:
        oracledb.init_oracle_client(lib_dir=settings.oracle_client_lib_dir)
    return create_engine(settings.oracle_dsn, future=True)


def initialize_oracle_session(connection: Connection) -> None:
    # Some Oracle environments require session bootstrap logic before querying
    # application views. The public case-study version keeps this hook optional.
    return None


def resolve_oracle_object_name(connection: Connection, object_name: str, source_schema: str | None = None) -> str:
    if source_schema:
        return f"{source_schema}.{object_name}"

    synonym_exists = connection.execute(
        text(
            """
            SELECT 1
            FROM user_objects
            WHERE object_name = :object_name
              AND object_type = 'SYNONYM'
            """
        ),
        {"object_name": object_name.upper()},
    ).scalar()
    if synonym_exists:
        return object_name

    owner = connection.execute(
        text(
            """
            SELECT owner
            FROM (
                SELECT owner
                FROM all_objects
                WHERE object_name = :object_name
                  AND object_type IN ('VIEW', 'TABLE')
                ORDER BY CASE WHEN owner = USER THEN 0 ELSE 1 END, owner
            )
            WHERE ROWNUM = 1
            """
        ),
        {"object_name": object_name.upper()},
    ).scalar()
    if owner:
        return f"{owner}.{object_name}"

    return object_name
