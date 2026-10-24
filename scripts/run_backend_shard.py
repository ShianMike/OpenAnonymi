"""Run one CI shard, or all four locally on separate disposable PostgreSQL databases."""

import collections
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4


def module_groups(nodes):
    assert nodes, "No backend tests collected"
    counts = collections.Counter(node.split("::", 1)[0] for node in nodes)
    # shortcut: balance by case count; use durations if costly modules skew a shard.
    groups, weights = [[] for _ in range(4)], [0] * 4
    for module in sorted(counts, key=lambda module: (-counts[module], module)):
        index = min(range(4), key=weights.__getitem__)
        groups[index].append(module)
        weights[index] += counts[module]
    assert sorted(module for group in groups for module in group) == sorted(counts)
    assert sum(weights) == len(nodes) and all(groups)
    return groups, weights


def test_database_url(raw):
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    try:
        url = make_url(raw)
        valid = (url.drivername == "postgresql+psycopg" and
                 url.host in ("127.0.0.1", "localhost") and url.port == 5434 and
                 url.database and not url.query)
    except (ArgumentError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Parallel tests require PRIVACY_REVIEW_TEST_DATABASE_URL at localhost:5434")
    return url


def run_database_shard(url, modules, shard):
    from sqlalchemy import create_engine, text

    database = f"openanonymi_tests_{uuid4().hex}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        created = True
        raw = url.set(database=database).render_as_string(hide_password=False)
        # Test fixtures own their keys and mail settings; inherited service secrets change semantics.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("PRIVACY_REVIEW_")}
        env.update(PRIVACY_REVIEW_DATABASE_URL=raw, PRIVACY_REVIEW_TEST_DATABASE_URL=raw,
                   PRIVACY_REVIEW_ENVIRONMENT="test", PYTHONIOENCODING="utf-8",
                   PRIVACY_REVIEW_ALLOWED_ORIGINS='["http://localhost:5173"]')
        print(f"Shard {shard + 1}/4: migrating its disposable database", flush=True)
        migration = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                                   env=env, capture_output=True, text=True, encoding="utf-8",
                                   check=False)
        if migration.returncode:
            return migration.returncode, migration.stdout + migration.stderr
        print(f"Shard {shard + 1}/4: running tests", flush=True)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--durations=20", *modules],
                                env=env, capture_output=True, text=True, encoding="utf-8",
                                check=False)
        return result.returncode, result.stdout + result.stderr
    finally:
        try:
            if created:
                with admin.connect() as connection:
                    connection.execute(text(f'DROP DATABASE "{database}"'))
                    assert not connection.scalar(
                        text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
                    ), "Disposable test database remains"
        finally:
            admin.dispose()


def main():
    parallel = sys.argv[1:] == ["all"]
    if parallel:
        url = test_database_url(os.getenv("PRIVACY_REVIEW_TEST_DATABASE_URL", ""))
    else:
        shard = int(sys.argv[1])
        assert 0 <= shard < 4
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True, text=True, check=False,
    )
    if collected.returncode:
        print(collected.stdout)
        print(collected.stderr, file=sys.stderr)
        return collected.returncode
    nodes = [line for line in collected.stdout.splitlines()
             if line.startswith("tests/") and "::" in line]
    groups, weights = module_groups(nodes)
    if parallel:
        print(f"All {len(nodes)} backend cases: four isolated databases; counts {weights}", flush=True)
        failed = False
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = {pool.submit(run_database_shard, url, group, index): index
                       for index, group in enumerate(groups)}
            for future in as_completed(pending):
                index = pending[future]
                code, output = future.result()
                print(f"\nShard {index + 1}/4 finished (exit {code})\n{output}", flush=True)
                failed |= code != 0
        return int(failed)
    print(f"Backend shard {shard + 1}/4: {weights[shard]} of {len(nodes)} cases; "
          f"balanced counts {weights}", flush=True)
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "--durations=20",
                            *groups[shard], *sys.argv[2:]])


if __name__ == "__main__":
    sys.exit(main())
