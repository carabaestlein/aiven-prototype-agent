"""Opt-in checks against real PostgreSQL, isolated in a random test schema.

Use TEST_DATABASE_URL for a dedicated test database (never production), or install
pgserver==0.1.4 and set TEST_LOCAL_POSTGRES=1 for an ephemeral local server.
Neither mode calls a real model provider. Only the schema created here is dropped.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import HTTPException
import httpx
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import pytest

from service import RunService
from support import config
from workflow import build_graph


@pytest.fixture(scope="module")
def postgres_url(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    if os.environ.get("TEST_LOCAL_POSTGRES") != "1":
        pytest.skip("Set TEST_DATABASE_URL or TEST_LOCAL_POSTGRES=1 for real PostgreSQL checks")
    pgserver = pytest.importorskip("pgserver", reason="Install pgserver==0.1.4 for local PostgreSQL")
    import fasteners
    # Keep pgserver's lock and Unix socket out of the user's cache directory.
    # A short temporary path also respects macOS Unix-socket path limits.
    with tempfile.TemporaryDirectory(prefix="langgraph-pg-", dir="/tmp") as runtime:
        class TestPostgresServer(pgserver.PostgresServer):
            runtime_path = Path(runtime)
            _lock = fasteners.InterProcessLock(Path(runtime) / ".lock")

        server = TestPostgresServer(tmp_path_factory.mktemp("postgres"), cleanup_mode="delete")
        try:
            yield server.get_uri()
        finally:
            server.cleanup()


@pytest.fixture
def database_schema(postgres_url):
    schema = "langgraph_test_" + uuid4().hex
    with psycopg.connect(postgres_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield postgres_url, schema
    finally:
        with psycopg.connect(postgres_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@contextmanager
def open_runs(database_schema, settings=None):
    url, schema = database_schema
    # A schema-only search path prevents accidental use of pre-existing public
    # tables. Match the production autocommit and dictionary-row configuration.
    with ConnectionPool(url, min_size=1, max_size=10, timeout=10,
                        kwargs={"autocommit": True, "prepare_threshold": 0,
                                "row_factory": dict_row,
                                "options": "-c search_path=" + schema}) as pool:
        pool.wait(timeout=15)
        saver = PostgresSaver(pool)
        saver.setup()
        runs = RunService(pool, build_graph(saver, settings or config()))
        runs.setup()
        yield runs


def test_postgres_review_survives_pool_close_revision_and_approval(database_schema):
    with open_runs(database_schema) as original:
        first = original.create("Write a welcome note")
        original_pool = original.pool
        assert first["status"] == "awaiting_review"
        assert first["checkpoint"]
    assert original_pool.closed

    # Rebuild both saver and graph with completely new connections, using only
    # the run ID returned before shutdown to recover the persisted state.
    with open_runs(database_schema) as rebuilt:
        recovered = rebuilt.view(first["id"])
        assert recovered == first
        revised = rebuilt.execute(first["id"], "revise", "Keep it brief", first["checkpoint"])
        assert revised["status"] == "awaiting_review"
        assert revised["revision"] == 2
        assert revised["checkpoint"] != first["checkpoint"]
        assert "Keep it brief" in revised["draft"]
        with pytest.raises(HTTPException) as stale:
            rebuilt.execute(first["id"], "approve", checkpoint=first["checkpoint"])
        assert stale.value.status_code == 409
        completed = rebuilt.execute(first["id"], "approve", checkpoint=revised["checkpoint"])
        assert completed["status"] == "completed"

    with open_runs(database_schema) as final:
        assert final.view(first["id"]) == completed
        with final.pool.connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM checkpoints WHERE thread_id=%s",
                                (first["id"],)).fetchone()["n"] >= 5


def test_postgres_failed_step_survives_rebuild_and_explicit_continue(database_schema, monkeypatch):
    cfg = config()
    cfg.mode, cfg.model, cfg.model_key = "openai-compatible", "test-model", "test-only-secret"
    calls = []

    def fail(*args, **kwargs):
        calls.append("failed")
        raise httpx.ConnectError("test-only-secret must not be exposed")

    monkeypatch.setattr(httpx.Client, "post", fail)
    with open_runs(database_schema, cfg) as original:
        failed = original.create("Draft this after recovery")
        original_pool = original.pool
        assert failed["status"] == "needs_continue"
        assert failed["checkpoint"]
        assert "error" in failed and cfg.model_key not in str(failed)
    assert original_pool.closed

    def succeed(*args, **kwargs):
        calls.append("succeeded")
        return httpx.Response(200, request=httpx.Request("POST", "https://example.test"),
                              json={"choices": [{"message": {"content": "Recovered draft"}}]})

    monkeypatch.setattr(httpx.Client, "post", succeed)
    with open_runs(database_schema, cfg) as rebuilt:
        pending = rebuilt.view(failed["id"])
        assert pending["status"] == "needs_continue"
        assert pending["checkpoint"] == failed["checkpoint"]
        assert calls == ["failed"]  # Reading/rebuilding must not run work.
        recovered = rebuilt.execute(failed["id"], "continue")
        assert calls == ["failed", "succeeded"]
        assert recovered["status"] == "awaiting_review"
        assert recovered["draft"] == "Recovered draft"
        assert recovered["revision"] == 1
        assert recovered["checkpoint"] != failed["checkpoint"]
