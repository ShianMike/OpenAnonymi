# Development

Requirements: Python 3.11, Node.js 24, uv, and PostgreSQL 17. Install these from
their official distributions. Commands below run from the repository root
unless a working directory is specified.

## Database

Create a development database and a separate role with a password. One
disposable local option, if Docker is installed:

```sh
docker run --name openanonymi-dev -e POSTGRES_USER=review -e POSTGRES_PASSWORD=local-development-only -e POSTGRES_DB=review -p 127.0.0.1:5432:5432 -d postgres:17
```

This container is for local development only. Use a persistent PostgreSQL
installation or managed service with protected backups for real data.

## API

From `backend`:

```sh
uv sync --locked
```

Copy `.env.example` to `.env` and set `PRIVACY_REVIEW_DATABASE_URL` to your
development database. On PowerShell, use `Copy-Item .env.example .env`;
on a POSIX shell, use `cp .env.example .env`.

Generate a fresh content key locally:

```sh
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste it into the ignored `.env` as the `local-v1` value of
`PRIVACY_REVIEW_CONTENT_KEYS`. Keep
`PRIVACY_REVIEW_ACTIVE_KEY_ID=local-v1`. Never commit or share that key.

```sh
uv run python -m app.check_config
uv run alembic upgrade head
uv run python -m app.accounts.bootstrap
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Bootstrap works only on an empty database and prompts for the initial email,
workspace, and password. Use an address you control. Its password prompt avoids
putting a password in the command line. SMTP is needed for normal registration,
email verification, and recovery; configure your own local mail service through
the backend variables.

## Frontend

In another terminal, from `frontend`:

```sh
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the loopback API. No
frontend environment variable is needed for this setup. The only permitted
browser-visible variable is `VITE_API_BASE_URL`; never put secrets in it or
introduce another `VITE_` variable.

## Tests

Use a new, disposable PostgreSQL 17 database on port **5434**. Tests create and
delete data and some exercise key rotation. Do not use the application database.

```sh
docker run --name openanonymi-test -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=ci-only-password -e POSTGRES_DB=review_test -p 127.0.0.1:5434:5432 -d postgres:17
```

From `backend`, set both database variables to
`postgresql+psycopg://postgres:ci-only-password@127.0.0.1:5434/review_test`
and `PRIVACY_REVIEW_ENVIRONMENT=test`. PowerShell:

```powershell
$env:PRIVACY_REVIEW_TEST_DATABASE_URL = 'postgresql+psycopg://postgres:ci-only-password@127.0.0.1:5434/review_test'
$env:PRIVACY_REVIEW_DATABASE_URL = $env:PRIVACY_REVIEW_TEST_DATABASE_URL
$env:PRIVACY_REVIEW_ENVIRONMENT = 'test'
$env:PRIVACY_REVIEW_ALLOWED_ORIGINS = '["http://localhost:5173"]'
uv run alembic upgrade head
uv run pytest -q
uv run ruff check app tests migrations ../scripts/run_backend_shard.py
```

On a POSIX shell, use `export VARIABLE=value` for the same variables. Hosted CI
uses four separate database services. To run all four shards locally:

```sh
uv run python ../scripts/run_backend_shard.py all
```

This command accepts only a PostgreSQL test URL on `localhost:5434` or
`127.0.0.1:5434`, without URL query parameters. Its database role needs permission
to create databases, which the key-rotation tests also require. The runner creates
and migrates four unique databases, runs disjoint groups of complete test modules,
and removes only the databases it created. Any migration, test, or cleanup failure
fails the command.
The numbered `0` through `3` modes remain the individual CI shards. Use ordinary
`pytest` for a serial run on one disposable database; do not run multiple pytest
processes against the same database. Tests skipped because no database URL was
supplied do not establish a release pass.

From `frontend`, run `npm test`, `npm run lint`, `npm run build`, then
`npm run typegen`. From `backend`, regenerate the schema with
`uv run python -m app.export_openapi ../frontend/openapi.json`.
Generated schema and types must match the committed contract.

Vitest caches transformed modules under `frontend/node_modules/.vitest-cache`
between runs. Test files still run in separate processes with isolated module
state. After changing the test configuration or diagnosing a suspected stale
transform, run `npm exec -- vitest --clearCache` from `frontend`.

The PostgreSQL fixtures reuse only the initial test accounts’ real Argon2
password hashes within one pytest session. Each case still gets fresh users,
workspace data, application state, encryption keys, clients, and database
connections. Password changes and verification use the normal application code.
Each disposable database runs its cases serially; access and concurrency tests
rely on independently committed transactions and must not share live app data.

CI also runs `scripts/verify_frontend_config.py` and
`scripts/verify_container_runtime.py`. The latter is intended for the Linux
Docker image and verifies the actual parser/OCR libraries and workload.

## Private local files

Keep local databases, keyrings, outboxes, credentials, screenshots containing
account or review content, and generated reports outside tracked files.
Ignored files can still be added with `git add -f`; review staged paths and scan
for secrets before pushing. Synthetic fixtures are for tests, not demo accounts
with shared passwords on a public deployment.
