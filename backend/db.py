"""Private PostgreSQL access, bounded read-only transactions."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@lru_cache(maxsize=1)
def engine():
    return create_engine(URL.create(
        "postgresql+psycopg2", username=os.getenv("DATA_ANALYST_USER", "data_analyst"),
        password=os.getenv("DATA_ANALYST_PASSWORD", ""),
        host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
        port=int(os.getenv("GOLD_POSTGRES_PORT", "5432")),
        database=os.getenv("GOLD_POSTGRES_DB", "gold"),
    ), pool_pre_ping=True, pool_size=3, max_overflow=2, connect_args={
        "connect_timeout": 3,
        "options": "-c default_transaction_read_only=on -c statement_timeout=10000",
    })


def query(sql: str, params: dict | None = None) -> list[dict]:
    with engine().connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]
