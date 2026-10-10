# Contributing

Open an issue for a focused bug or improvement, or submit a small pull request.
For security vulnerabilities, use [the private reporting process](SECURITY.md).

1. Fork the repository and create a branch from `main`.
2. Follow [the development setup](docs/DEVELOPMENT.md).
3. Reproduce the problem with synthetic inputs. Never use real account or
   document data in tests, logs, screenshots, or attachments.
4. Change the shared implementation and its affected callers. Add a focused test
   for behavior, security, or a regression; avoid tests that merely repeat code.
5. Run the relevant checks, then submit a PR describing the problem, resulting
   behavior, verification, and any remaining limit.

Keep Python, Node, database, and generated API versions aligned with the
lockfiles and CI. When changing an API contract, regenerate
`frontend/openapi.json` with `python -m app.export_openapi`, then run
`npm run typegen` in `frontend`.

Changes to authentication, authorization, encryption, migrations, parsing,
exports, workflows, or deployment need particular care with backward
compatibility and data preservation. Never silently bypass validation to make
a test pass. Migration descriptions must explain what happens to existing data.

Only public application inputs, synthetic fixtures, and required verification
tools belong in Git. Internal notes and local evidence stay ignored. If secret
scanning flags a fixture, use a narrowly scoped, documented exception; never
allowlist a whole source directory or a real key.

The maintainer reviews PRs and the protected `main` branch requires passing
checks. Do not force-push shared branches or change release settings as part of
an unrelated PR.

Dependency updates are maintained manually. Dependabot vulnerability alerts stay
enabled, but automatic version and security update PRs are disabled to avoid
recurring branches. Submit lockfile updates through protected CI, merge into
`main`, and delete the temporary branch after merging.

By contributing original material, you agree to license it under the project's
[LICENSE](LICENSE) and attribution [NOTICE](NOTICE). Confirm that you have the
right to submit it, and preserve the licenses of third-party material.
Participation follows [the code of conduct](CODE_OF_CONDUCT.md).
