"""Bring the database schema up to date. The only place schemas are changed.

``upgrade_database()`` runs at startup (API and worker) and from the command line
(``python -m app.migrate``). It applies Alembic migrations, after first adopting
databases that were created before migrations existed: those have tables but no
``alembic_version`` row, and may be missing tables or columns added since. Their
gaps are filled (new columns are added as nullable), then they are stamped as up
to date.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateTable

from . import models  # noqa: F401  (registers every table)
from .db import Base, engine

log = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _adopt_unversioned(connection: Connection) -> list[str]:
    """Fill the gaps in a database made by ``create_all`` before migrations existed.

    Only additions are made: missing tables are created and missing columns are
    added as nullable. Nothing is dropped or altered.
    """
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    changes: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            connection.execute(CreateTable(table))
            changes.append(f"created table {table.name}")
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            column_type = column.type.compile(dialect=connection.dialect)
            connection.execute(
                text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
            )
            changes.append(f"added column {table.name}.{column.name}")
    return changes


def upgrade_database() -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        config = alembic_config(connection)
        if "users" in tables and "alembic_version" not in tables:
            changes = _adopt_unversioned(connection)
            command.stamp(config, "head")
            log.info("adopted an unversioned database: %s", "; ".join(changes) or "no changes")
        else:
            command.upgrade(config, "head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    upgrade_database()
    print("database is up to date")
