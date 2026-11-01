"""Shared fixtures for tests that need the live seeded database.

golden_cases is session-scoped and shared by test_golden.py, test_scorers.py,
and test_invariants.py: building it runs the real specialist+gate pipeline
live against Postgres for all 200 disputes, making it the single most
expensive fixture in the suite. It reseeds the database immediately before
building, so it's correct regardless of what ran earlier in the session --
and since specialists and the gate never write (DEC-0001), nothing run after
it can dirty what it already built.
"""
import psycopg2
import pytest

from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from evals.golden import build_golden_dataset


@pytest.fixture(scope="session")
def golden_cases():
    try:
        conn = psycopg2.connect(default_dsn())
        conn.close()
    except psycopg2.OperationalError:
        pytest.skip("Postgres is not reachable; start it with `docker compose up -d`")
    load_into_postgres(generate_dataset(42), default_dsn())
    return build_golden_dataset(seed=42)
