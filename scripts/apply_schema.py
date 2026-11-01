"""Applies db/schema.sql to a running, empty Postgres instance.

Used by CI: the GitHub Actions Postgres service container starts with no
schema at all, unlike the local docker-compose setup, where
docker-entrypoint-initdb.d applies db/schema.sql automatically on first init.
Run as a module, not a script, so the `app` package import resolves:
    python3 -m scripts.apply_schema
"""
from __future__ import annotations

from pathlib import Path

import psycopg2

from app.generate_data import default_dsn

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def main() -> None:
    sql = SCHEMA_FILE.read_text()
    conn = psycopg2.connect(default_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print(f"applied {SCHEMA_FILE} to {default_dsn()}")


if __name__ == "__main__":
    main()
