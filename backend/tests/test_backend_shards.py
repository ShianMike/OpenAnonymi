"""Parallel test execution must preserve coverage, failures, and database boundaries."""

import runpy
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from sqlalchemy.engine import make_url

runner = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/run_backend_shard.py"))


def test_shards_partition_every_module_once_without_losing_parameterized_cases():
    nodes = [f"tests/test_{module}.py::test_case[{case}]"
             for module, count in enumerate((20, 12, 10, 8, 6, 4, 2)) for case in range(count)]
    groups, counts = runner["module_groups"](nodes)
    assert sum(counts) == len(nodes)
    assert sorted(module for group in groups for module in group) == [
        f"tests/test_{module}.py" for module in range(7)
    ]
    assert all(groups) and max(counts) - min(counts) <= 6


@pytest.mark.parametrize("raw", [
    "", "invalid-private-value", "postgresql+psycopg://test:private@127.0.0.1:5433/review",
    "postgresql+psycopg://test:private@db.example.invalid:5434/review_test",
    "postgresql+psycopg://test:private@127.0.0.1:5434/", "sqlite:///review_test",
    "postgresql+psycopg://test:private@127.0.0.1:5434/review_test?host=remote&port=5432",
])
def test_parallel_runner_refuses_live_or_remote_database_and_does_not_echo_credentials(raw):
    with pytest.raises(ValueError, match="localhost:5434") as error:
        runner["test_database_url"](raw)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_parallel_runner_accepts_only_the_explicit_disposable_postgres_server(host):
    raw = f"postgresql+psycopg://test:synthetic@{host}:5434/review_test"
    assert runner["test_database_url"](raw).render_as_string(hide_password=False) == raw


def test_numbered_ci_shard_still_forwards_pytest_options_and_failure(monkeypatch):
    nodes = [f"tests/test_{index}.py::test_case" for index in range(4)]
    collected = subprocess.CompletedProcess([], 0, "\n".join(nodes), "")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: collected)
    call = MagicMock(return_value=3)
    monkeypatch.setattr(subprocess, "call", call)
    monkeypatch.setattr(runner["sys"], "argv", ["run_backend_shard.py", "1", "--maxfail=1"])
    assert runner["main"]() == 3
    assert call.call_args.args[0] == [
        runner["sys"].executable, "-m", "pytest", "-q", "--durations=20",
        "tests/test_1.py", "--maxfail=1",
    ]


@pytest.mark.parametrize("failure", ["none", "migration", "tests", "spawn"])
def test_database_cleanup_and_failure_propagation_survive_worker_failures(monkeypatch, failure):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = None
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setenv("PRIVACY_REVIEW_CONTENT_KEYS", "inherited-private-key")
    monkeypatch.setenv("PRIVACY_REVIEW_SMTP_HOST", "mail.example.invalid")
    calls = []

    def run(command, *, env, **kwargs):
        calls.append(command)
        assert "PRIVACY_REVIEW_CONTENT_KEYS" not in env
        assert "PRIVACY_REVIEW_SMTP_HOST" not in env
        url = make_url(env["PRIVACY_REVIEW_DATABASE_URL"])
        assert url.database.startswith("openanonymi_tests_") and url.database != "review_test"
        assert env["PRIVACY_REVIEW_TEST_DATABASE_URL"] == env["PRIVACY_REVIEW_DATABASE_URL"]
        assert env["PRIVACY_REVIEW_ENVIRONMENT"] == "test"
        if failure == "spawn":
            raise OSError("Synthetic process failure")
        code = int((failure == "migration" and "alembic" in command) or
                   (failure == "tests" and "pytest" in command))
        return subprocess.CompletedProcess(command, code, "synthetic output", "")

    monkeypatch.setattr(subprocess, "run", run)
    url = make_url("postgresql+psycopg://test:synthetic@127.0.0.1:5434/review_test")
    if failure == "spawn":
        with pytest.raises(OSError, match="Synthetic process failure"):
            runner["run_database_shard"](url, ["tests/test_example.py"], 0)
    else:
        code, _ = runner["run_database_shard"](url, ["tests/test_example.py"], 0)
        assert code == (0 if failure == "none" else 1)
        assert len(calls) == (1 if failure == "migration" else 2)
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert len(statements) == 2
    assert statements[0].startswith('CREATE DATABASE "openanonymi_tests_')
    assert statements[1] == statements[0].replace("CREATE", "DROP", 1)
    connection.scalar.assert_called_once()
    engine.dispose.assert_called_once()
