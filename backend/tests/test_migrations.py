"""The migrations must produce exactly the schema the models describe, and old
databases created before migrations existed must be brought up to date."""

from __future__ import annotations

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db import Base, engine
from app.migrate import alembic_config, upgrade_database


def _reset() -> None:
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_upgrade_head_matches_the_models():
    _reset()
    upgrade_database()
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "render_as_batch": True}
        )
        differences = compare_metadata(context, Base.metadata)
    assert differences == [], differences


def test_migrations_downgrade_and_upgrade_cleanly():
    _reset()
    upgrade_database()
    with engine.begin() as connection:
        config = alembic_config(connection)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        command.upgrade(config, "head")
        assert "users" in inspect(connection).get_table_names()


def test_old_unversioned_database_is_adopted():
    """A database made by create_all before a column existed, like the demo
    database that failed with 'no such column: jobs.run_after'."""
    _reset()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE jobs DROP COLUMN run_after"))
        connection.execute(text("DROP TABLE rerank_scores"))

    upgrade_database()

    inspector = inspect(create_engine(engine.url))
    assert "run_after" in {c["name"] for c in inspector.get_columns("jobs")}
    assert "rerank_scores" in inspector.get_table_names()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version is not None
    upgrade_database()  # a second run is a no-op


def test_app_starts_on_an_old_database(client):
    """The startup path runs the migration, so the API answers instead of crashing."""
    assert client.get("/readyz").json()["status"] == "ready"
