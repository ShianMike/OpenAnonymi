# Database certificate authority

`supabase-ca.crt` is Supabase's public Root 2021 CA certificate. It contains no private key.

Source: https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

SHA-256 of the DER certificate:
`807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa`

Expires April 26, 2031. Replace it from the provider's authenticated dashboard or official
HTTPS download when the provider rotates its CA. Verify the replacement before deploying.

The production connection URL uses `sslmode=verify-full&sslrootcert=/app/certs/supabase-ca.crt`.
This verifies both the certificate chain and the database hostname. An unrelated database
provider must use its own trusted certificate, or `sslrootcert=system` for a publicly trusted
certificate. See [Supabase SSL documentation](https://supabase.com/docs/guides/platform/ssl-enforcement).
