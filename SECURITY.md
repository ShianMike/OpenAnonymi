# Security policy

## Supported versions

Security fixes target the latest code on `main` and the current official
deployment. Older commits and third-party deployments are not supported release
branches. Operators should update promptly after a fix is published.

## Report privately

Use [GitHub private vulnerability reporting](https://github.com/ShianMike/OpenAnonymi/security/advisories/new).
Do not publish exploit details, account identifiers, tokens, passwords, document
text, or personal data in a public issue.

Provide the affected commit or deployment, a minimal reproduction using
synthetic data, the impact, and any proposed fix. Keep testing to accounts and
environments you control. Do not probe or download another user's data. Reports
are reviewed by the maintainer; there is no guaranteed response time or paid
bounty program.

If the reporting form is unavailable, use the GitHub profile's available private
contact method or GitHub's reporting tools. Do not post a confidential report
publicly to work around an unavailable channel.

## Trust boundaries

- Every authenticated operation checks current workspace membership and the
  relevant owner, reviewer, or administrator authority.
- Browser sessions use cookies and CSRF checks. Production requires exact HTTPS
  origins, TLS, and verified TLS for remote PostgreSQL connections.
- Protected source and recovery content are encrypted with externally supplied
  keys. This is not end-to-end encryption: the API decrypts text for processing.
- Detection and OCR run locally. Recognition is probabilistic and incomplete;
  a human must inspect the result before sharing.
- Imported HTML, image references, and Markdown links remain inactive in the
  review. File and parsing limits apply before expensive processing.
- Deletion and expiration make content unavailable before bounded physical
  cleanup. Backup retention is the operator's responsibility.
- Logs use fixed messages and route templates. Do not add plaintext document
  content, query strings, credentials, recovery codes, or tokens to logs.

## Safe development and release

Use synthetic inputs and disposable test databases. Keep `.env`, keyrings,
database dumps, private screenshots, mail outboxes, and credentials outside Git.
The narrowly scoped secret-scan exceptions cover authored detector fixtures,
not real credentials.

Pull requests require CI. Workflows run with minimal permissions; untrusted
pull requests must not receive production secrets. The scheduled cleanup job
receives only a maintenance token, never database credentials or content keys.

Before deployment, verify migrations, lockfiles, the Linux native runtime,
backups and restore access, HTTPS headers, and the exact deployed commit.
See [deployment instructions](docs/DEPLOYMENT.md). A dependency version or a
passing unit test alone does not certify native vulnerability patch status.
