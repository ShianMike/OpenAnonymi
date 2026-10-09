"""Validated process configuration. Never include setting values in errors."""

import re
import secrets
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import (
    Field,
    PrivateAttr,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(RuntimeError):
    """Configuration is absent or invalid, without disclosing supplied values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRIVACY_REVIEW_", env_file=".env", extra="ignore")

    database_url: str = Field(repr=False)
    allowed_origins: list[str]
    environment: Literal["development", "test", "production"] = "development"
    registration_enabled: bool = True
    active_key_id: str | None = None
    content_keys: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    attempt_subject_key: SecretStr | None = Field(default=None, repr=False)
    _attempt_subject_key: bytes = PrivateAttr(default_factory=lambda: secrets.token_bytes(32))
    smtp_host: str | None = None
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from: str | None = None
    email_check_deliverability: bool = True
    email_dns_timeout: int = Field(default=5, ge=2, le=10)
    email_block_disposable: bool = False
    email_allow_test_domains: bool = False
    dev_mail_outbox: Path | None = Field(default=None, repr=False)
    # Proxies in front of the app that append to X-Forwarded-For. Zero trusts no header.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    # Enable only behind a proxy that overwrites X-Forwarded-Proto (Heroku does).
    https_redirect_enabled: bool = False
    # libpq connect timeout in seconds; managed databases that suspend may need longer.
    database_connect_timeout: int = Field(default=2, ge=2, le=60)
    maintenance_token_sha256: SecretStr | None = Field(default=None, repr=False)

    @field_validator("attempt_subject_key")
    @classmethod
    def require_attempt_subject_key(cls, value: SecretStr | None):
        if value is not None:
            try:
                Fernet(value.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeEncodeError):
                raise ValueError("attempt subject key must be a base64-encoded 32-byte key") from None
        return value

    @field_validator("maintenance_token_sha256")
    @classmethod
    def require_maintenance_digest(cls, value: SecretStr | None):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value.get_secret_value()) is None:
            raise ValueError("maintenance digest must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("database_url")
    @classmethod
    def require_postgres_psycopg(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError:
            raise ValueError("must be a valid PostgreSQL psycopg URL") from None
        if url.drivername != "postgresql+psycopg" or not all(
            (url.host, url.database, url.username, url.password)
        ):
            raise ValueError("must be a PostgreSQL psycopg URL with host and credentials")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def require_explicit_origins(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("at least one allowed origin is required")
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
            ):
                raise ValueError("allowed origins must be explicit HTTP(S) origins")
        return values

    @field_validator("dev_mail_outbox")
    @classmethod
    def require_private_outbox(cls, value: Path | None, info: ValidationInfo):
        if value is None:
            return None
        if info.data.get("environment") == "production":
            raise ValueError("dev_mail_outbox is forbidden in production")
        value = value.resolve()
        if ".local-dev" not in value.parts:
            raise ValueError("dev_mail_outbox must be inside a .local-dev directory")
        return value

    @field_validator("email_allow_test_domains")
    @classmethod
    def refuse_test_domains_in_production(cls, value: bool, info: ValidationInfo):
        if value and info.data.get("environment") == "production":
            raise ValueError("email_allow_test_domains is forbidden in production")
        return value

    @model_validator(mode="after")
    def require_production_security(self) -> "Settings":
        if self.https_redirect_enabled and self.trusted_proxy_hops == 0:
            raise ValueError("HTTPS redirects require a configured trusted host proxy")
        smtp_fields = (
            self.smtp_host,
            self.smtp_username,
            self.smtp_password,
            self.smtp_from,
        )
        if any(smtp_fields) and not all(smtp_fields):
            raise ValueError("SMTP recovery requires host, username, password, and sender")
        if self.active_key_id and self.active_key_id not in self.content_keys:
            raise ValueError("active_key_id must identify a configured content key")
        if self.content_keys and not self.active_key_id:
            raise ValueError("active_key_id is required when content keys are configured")
        for key_id, key in self.content_keys.items():
            if (
                not key_id
                or len(key_id) > 80
                or not key_id.replace("-", "").replace("_", "").isalnum()
            ):
                raise ValueError(
                    "content key identifiers must use letters, digits, hyphens or underscores"
                )
            try:
                Fernet(key.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeEncodeError):
                raise ValueError("content keys must be valid Fernet keys") from None
        if self.environment == "production":
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("production origins must use HTTPS")
            if "change-me" in self.database_url:
                raise ValueError("production database credentials must be configured")
            database = make_url(self.database_url)
            # Plain loopback is reserved for disposable production-mode CI/browser drills.
            if database.host not in ("localhost", "127.0.0.1", "::1"):
                if database.query.get("sslmode") != "verify-full":
                    raise ValueError("production remote databases require sslmode=verify-full")
                if not database.query.get("sslrootcert"):
                    raise ValueError(
                        "production remote databases require a trusted root certificate"
                    )
            if not self.active_key_id:
                raise ValueError("production requires an active content encryption key")
            if self.attempt_subject_key is None:
                raise ValueError("production requires a stable attempt subject key")
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        fields = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        names = ", ".join(fields) or "settings"
        raise ConfigurationError(
            f"Invalid configuration: {names}. See backend/.env.example."
        ) from None
