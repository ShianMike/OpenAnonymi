# OpenAnonymi

[![CI](https://github.com/ShianMike/OpenAnonymi/actions/workflows/ci.yml/badge.svg)](https://github.com/ShianMike/OpenAnonymi/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

Review personal and sensitive details before sharing a document. OpenAnonymi
suggests findings, lets you correct each occurrence, and exports the reviewed
result after confirmation.

**[Open the app](https://openanonymi.com)** · [Development](docs/DEVELOPMENT.md) ·
[Deployment](docs/DEPLOYMENT.md) · [Report a vulnerability](SECURITY.md)

## What it does

- Imports text, Markdown, CSV, Word, and PDF, including bounded local English OCR.
- Suggests names, contact details, identifiers, dates, addresses, URLs, and secrets
  with local rules and models. Document text is not sent to an external AI service.
- Lets reviewers keep, replace, label, or remove findings, add missed details,
  inspect revisions, and confirm the final text.
- Supports workspace presets and custom detection rules, shared reviews,
  assignments, approvals, comments, notifications, and activity history.
- Exports reviewed text and supported document formats. Markdown formatting stays
  readable without executing HTML or opening embedded links or images.
- Provides workspace roles, email verification, two-step sign-in, retention
  defaults, cleanup, and display preferences.

Detection is a starting point, not a guarantee of anonymization. Inspect the
whole reviewed document, correct misses and false positives, and consider whether
the remaining context can still identify someone. English entity recognition and
OCR have language and model limits.

## Run locally

Use Python 3.11, Node.js 24, uv, and PostgreSQL 17. The frontend and backend have
committed lockfiles; use the locked dependencies.

1. Follow [the development setup](docs/DEVELOPMENT.md) to create a local database
   and an ignored backend `.env` with your own content key.
2. From `backend`, run `uv sync --locked`, `uv run alembic upgrade head`, then
   `uv run python -m app.accounts.bootstrap` on an empty database.
3. Start the API with `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. In a second terminal, run `npm ci` and `npm run dev` from `frontend`.
5. Open `http://localhost:5173` and sign in with the account you created.

Never reuse production database credentials, passwords, or encryption keys in a
local demonstration. SMTP is required for normal registration and recovery;
bootstrap is the initial local setup path.

## Checks

From `frontend`:

```sh
npm ci
npm test
npm run lint
npm run build
```

From `backend`, with a separate disposable PostgreSQL database on port **5434**
configured as `PRIVACY_REVIEW_TEST_DATABASE_URL`:

```sh
uv sync --locked
uv run ruff check app tests migrations ../scripts/run_backend_shard.py
uv run alembic upgrade head
uv run pytest -q
uv run python -m app.export_openapi ../frontend/openapi.json
```

Use the test database as `PRIVACY_REVIEW_DATABASE_URL` for the migration command.
Never point these checks at an application database. See
[the exact test setup](docs/DEVELOPMENT.md#tests).

Hosted CI runs four isolated PostgreSQL test shards, frontend checks, generated
API consistency checks, secret scanning, and a Linux container check that
exercises the real native parsing and OCR runtime.

## Repository

| Path | Purpose |
| --- | --- |
| `backend/app` | API, local detection, authorization, encrypted storage, exports |
| `backend/migrations` | Versioned PostgreSQL schema |
| `backend/tests` | Isolated tests and authored synthetic fixtures |
| `frontend/src` | React application and tests |
| `frontend/openapi.json` | Generated API contract |
| `scripts` | Required CI verification tools |
| `docs` | Public setup and deployment instructions |
| `.github` | CI, scheduled cleanup, review ownership, issue and PR templates |

Private environment files, account credentials, database dumps, internal build
notes, saved browser evidence, local demonstration data, and generated reports
are not release inputs. Do not attach real document content to issues or PRs.

## Security and deployment

The production image serves the frontend and API from one origin, runs as a
non-root user, validates configuration, and applies migrations before startup.
Stored document content is encrypted using keys supplied outside the database.
This is server-side encryption; the service can decrypt content to review it.

The operator remains responsible for TLS, secret storage, access controls,
database and key backups, retention, updates, and testing restoration. Deletion
from the application does not remove data from an operator's backups.
[Security policy](SECURITY.md) and [deployment requirements](docs/DEPLOYMENT.md)
describe the boundaries and release gates.

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Changes to `main` go through a pull
request and required CI checks. Small, reproducible changes with synthetic inputs
are easiest to review.

## License and attribution

Copyright © 2026 ShianMike and OpenAnonymi contributors.

Original project code is licensed under **AGPL-3.0-or-later**, with the reasonable
author attribution term in [NOTICE](NOTICE). Copies and derived applications
must preserve the copyright and an accessible **“Powered by OpenAnonymi”** credit
in their appropriate legal notices. Modified network deployments must offer
their corresponding source under the AGPL.

See [LICENSE](LICENSE) for the full terms and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for separately licensed assets.
The license does not grant trademark rights or imply endorsement.

The project discourages subscription paywalls around the community application
and encourages a free self-hosting path. This is a stated project principle,
not a ban on commercial use: AGPL permits paid hosting and subscriptions while
retaining its attribution and source-access requirements.
