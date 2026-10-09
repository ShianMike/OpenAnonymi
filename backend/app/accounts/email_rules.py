"""Account creation validates domains; lookups preserve legacy addresses without DNS."""

import logging
from functools import lru_cache
from pathlib import Path

import dns.resolver
from email_validator import (
    EmailNotValidError,
    EmailUndeliverableError,
    caching_resolver,
    validate_email,
)

from app.config import Settings


class EmailRuleError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


@lru_cache(maxsize=9)
def shared_resolver(timeout: int):
    return caching_resolver(timeout=timeout)


@lru_cache(maxsize=1)
def disposable_domains() -> frozenset[str]:
    return frozenset(
        line.strip()
        for line in (Path(__file__).parent / "data/disposable_domains.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    )


def creation_email(raw: str, settings: Settings, *, resolver=None) -> str:
    try:
        result = validate_email(
            raw.strip(),
            allow_smtputf8=False,
            check_deliverability=settings.email_check_deliverability
            and not settings.email_allow_test_domains,
            test_environment=settings.email_allow_test_domains,
            dns_resolver=(resolver or shared_resolver(settings.email_dns_timeout))
            if settings.email_check_deliverability and not settings.email_allow_test_domains
            else None,
        )
    except EmailUndeliverableError as exc:
        if exc.__cause__ is None or isinstance(
            exc.__cause__, (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer)
        ):
            raise EmailRuleError(
                422, "email_undeliverable", "This email domain cannot receive mail."
            ) from None
        logging.getLogger("app.accounts").warning("email_check_unavailable")
        raise EmailRuleError(
            503,
            "email_check_unavailable",
            "We couldn't check this email domain right now. Try again in a minute.",
        ) from None
    except EmailNotValidError:
        raise EmailRuleError(422, "invalid_email", "Enter a valid email address.") from None
    if (
        settings.email_check_deliverability
        and not settings.email_allow_test_domains
        and getattr(result, "mx", None) is None
    ):
        logging.getLogger("app.accounts").warning("email_check_unavailable")
        raise EmailRuleError(
            503,
            "email_check_unavailable",
            "We couldn't check this email domain right now. Try again in a minute.",
        )
    canonical = result.ascii_email.lower()
    if settings.email_block_disposable:
        domain = canonical.rsplit("@", 1)[1]
        parts = domain.split(".")
        if any(".".join(parts[i:]) in disposable_domains() for i in range(len(parts))):
            raise EmailRuleError(
                422, "email_domain_blocked", "Use a permanent email address for this account."
            )
    return canonical


def lookup_forms(raw: str) -> tuple[str, ...]:
    legacy = raw.strip().casefold()
    if not legacy or len(legacy) > 320 or "@" not in legacy or any(c.isspace() for c in legacy):
        raise ValueError("Enter a valid email address.")
    try:
        # test_environment is only a lookup aid. Creation has separate strict settings.
        result = validate_email(
            raw.strip(), allow_smtputf8=False, check_deliverability=False, test_environment=True
        )
        return tuple(
            dict.fromkeys((result.ascii_email.lower(), result.normalized.casefold(), legacy))
        )
    except EmailNotValidError:
        pass
    return (legacy,)
