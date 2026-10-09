# Deployment and release

The supported production shape is the root Docker image serving the website
and API from the same HTTPS origin, with PostgreSQL 17 and externally stored
content keys. `heroku.yml` builds this image for the existing Heroku deployment;
the image can also run on another compatible container host.

## Required configuration

Use [backend/.env.example](../backend/.env.example) as the setting reference,
not as a production secret file. Supply settings through the host's secret
store.

| Setting | Production requirement |
| --- | --- |
| `PRIVACY_REVIEW_ENVIRONMENT` | `production` |
| `PRIVACY_REVIEW_DATABASE_URL` | PostgreSQL with certificate and hostname verification: `sslmode=verify-full`, using the provider's public CA or `sslrootcert=system` |
| `PRIVACY_REVIEW_ALLOWED_ORIGINS` | JSON array of exact HTTPS website origins |
| `PRIVACY_REVIEW_ACTIVE_KEY_ID`, `PRIVACY_REVIEW_CONTENT_KEYS` | Active Fernet key ID and keyring, outside Git and the database |
| `PRIVACY_REVIEW_ATTEMPT_SUBJECT_KEY` | Separate, stable base64-encoded 32-byte authentication-limiter key; keep fixed when content keys rotate |
| `PRIVACY_REVIEW_HTTPS_REDIRECT_ENABLED` | `true` behind a correctly configured trusted HTTPS proxy |
| `PRIVACY_REVIEW_TRUSTED_PROXY_HOPS` | Measured trusted proxy chain length; do not blindly trust visitor-supplied forwarding headers |
| `PRIVACY_REVIEW_SMTP_*` | Authenticated SMTP with STARTTLS for registration, verification, recovery, and optional notification emails |
| `PRIVACY_REVIEW_SMTP_REPLY_TO` | Optional deployment support address for replies and contact links; defaults to the configured sender |
| `PRIVACY_REVIEW_REGISTRATION_ENABLED` | `true` for open signup, `false` to close registration |
| `PRIVACY_REVIEW_MAINTENANCE_TOKEN_SHA256` | SHA-256 digest of a random maintenance bearer token |

Use a direct connection or session pooler; do not use a transaction pooler.
Keep retired encryption keys while any retained content or backup needs them.
Back up the database and the keyring separately, restrict access, and verify a
restore procedure before a migration.

## Image and startup

```sh
docker build --pull -t openanonymi .
```

The Docker build context is an allowlist. It excludes tests, credentials,
private notes, reports, and local data. Build from the reviewed commit.

The image runs as a non-root user with one Uvicorn worker. Startup validates
configuration, applies `alembic upgrade head`, then serves on `$PORT`.
Do not start multiple migration processes concurrently. The CPU model and native
parsers require a measured memory budget; the official deployment uses a 1 GB
instance. Recheck the real workload before reducing that budget.

`/api/v1/health/live` checks process liveness.
`/api/v1/health/ready` also checks database readiness.
Production should block API docs and debug endpoints, use secure cookie
settings, and retain the application's security headers. Cache static assets
according to their content hashes; bypass caches for `/api/*` and
user-specific responses.

## Merge gates

Changes reach `main` through a PR with up-to-date required checks:

- Backend (PostgreSQL 17), aggregating all four isolated shards.
- Frontend, including tests, lint, build, public environment validation, and API
  type consistency.
- Backend container smoke test, including the actual Linux native runtime.
- Repository security, including secret scanning and public file boundaries.

Require resolved conversations, prohibit force pushes and branch deletion, and
enforce the rules for administrators. Use squash merges to retain a linear
release history. CI success is necessary but does not prove a deployed release.

## Release procedure

1. Review the final diff, public file list, secrets scan, licenses, and generated
   API. Verify the full history is suitable before changing repository visibility.
2. Confirm all required PR checks pass for the current PR head, then merge.
3. Record the resulting `main` commit and deploy that exact source.
4. Confirm the host's build and release succeeded, the expected migration is at
   head, and the single web process is healthy.
5. Verify the public site and readiness route, security headers, static asset
   versions, sign-in/review UI, and inaccessible private/debug routes.
6. Confirm scheduled cleanup runs and that existing content keys and retained
   application data remain available.

If startup fails, inspect redacted fixed-message logs and the host's release
status. Do not regenerate keys or restore an old database blindly. A code
rollback does not reverse a schema migration; inspect migration compatibility
and recover using a verified backup when necessary.

When upgrading a deployment that previously derived limiter digests from its
active content key, initialize the stable limiter key from that existing HKDF
output before changing content keys. It uses SHA-256, 32 bytes, no salt, and
`info=b"openanonymi-attempt-subjects-v1"`. Keep that value fixed thereafter so
existing authentication budgets and subject counts survive the upgrade.

## Scheduled cleanup

The application performs bounded cleanup. The separate
[maintenance workflow](../.github/workflows/maintenance.yml) runs every six hours
and can be dispatched manually.

Configure GitHub secret `OPENANONYMI_MAINTENANCE_TOKEN` with the raw random
token and variable `OPENANONYMI_API_BASE` with the HTTPS API URL ending in
`/api/v1`. The API host stores only the token's SHA-256 digest. GitHub does not
need production database credentials or encryption keys. The workflow has no
repository write permissions.

Physical cleanup is bounded and may require several passes. Operators must
monitor failed or overdue runs; unavailable content does not mean every backup
copy has been destroyed.

## Attribution and source

Retain the project and dependency notices in the image. The application exposes
copyright, license, and source links. A modified network deployment must link to
its own corresponding source and preserve the reasonable OpenAnonymi attribution
described in [NOTICE](../NOTICE).
