"""Database access helpers.

The pipeline and the API both go through here so that connection handling,
COPY-based bulk loading and the SQL query library have exactly one
implementation.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from analytics.config import QUERY_DIR, SCHEMA_FILE, database_url
from analytics.logging_config import get_logger

log = get_logger(__name__)


class DatabaseUnavailable(RuntimeError):
    """Raised when PostgreSQL cannot be reached."""


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(
        url or database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        future=True,
        connect_args={"connect_timeout": 3},
    )


def ping(engine: Engine | None = None) -> bool:
    engine = engine or get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("database ping failed", extra={"error": str(exc)})
        return False


def apply_schema(engine: Engine | None = None, schema_file: Path = SCHEMA_FILE) -> None:
    """Run the idempotent schema script."""
    engine = engine or get_engine()
    sql = schema_file.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    log.info("schema applied", extra={"file": schema_file.name})


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@lru_cache(maxsize=64)
def load_query(name: str) -> str:
    """Read a named .sql file from database/queries."""
    path = QUERY_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"No SQL query named {name!r} in {QUERY_DIR}")
    return path.read_text(encoding="utf-8")


def read_sql(sql: str, params: dict[str, Any] | None = None,
             engine: Engine | None = None) -> pd.DataFrame:
    engine = engine or get_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def read_query(name: str, params: dict[str, Any] | None = None,
               engine: Engine | None = None) -> pd.DataFrame:
    """Execute a query from the SQL library by file name."""
    return read_sql(load_query(name), params=params, engine=engine)


def scalar(sql: str, params: dict[str, Any] | None = None,
           engine: Engine | None = None) -> Any:
    engine = engine or get_engine()
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def truncate(tables: Sequence[str], engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    log.info("tables truncated", extra={"tables": ",".join(tables)})


MATERIALIZED_VIEWS = ("experiment_results", "experiment_user_results")


def refresh_materialized_views(engine: Engine | None = None) -> None:
    """Rebuild the session- and user-level rollups after a data load.

    Must run after every write to sessions, events or bookings, otherwise the
    dashboard serves the previous load's numbers.
    """
    engine = engine or get_engine()
    with engine.begin() as conn:
        for view in MATERIALIZED_VIEWS:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
            conn.execute(text(f"ANALYZE {view}"))
    log.info("materialized views refreshed", extra={"views": ",".join(MATERIALIZED_VIEWS)})


def copy_dataframe(df: pd.DataFrame, table: str, columns: Iterable[str] | None = None,
                   engine: Engine | None = None, chunk_size: int = 200_000) -> int:
    """Bulk load a DataFrame with PostgreSQL COPY.

    Roughly two orders of magnitude faster than executemany for the volumes
    this project generates (100k sessions, ~300k events).
    """
    engine = engine or get_engine()
    cols = list(columns) if columns else list(df.columns)
    frame = df[cols]
    total = 0

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            for start in range(0, len(frame), chunk_size):
                chunk = frame.iloc[start : start + chunk_size]
                buf = io.StringIO()
                chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
                buf.seek(0)
                statement = (
                    f"COPY {table} ({', '.join(cols)}) "
                    f"FROM STDIN WITH (FORMAT csv, NULL '\\N')"
                )
                with cur.copy(statement) as copy:
                    while data := buf.read(1 << 20):
                        copy.write(data)
                total += len(chunk)
        raw.commit()
    finally:
        raw.close()

    log.info("bulk loaded", extra={"table": table, "rows": total})
    return total
