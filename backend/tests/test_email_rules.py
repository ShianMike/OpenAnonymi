"""Hermetic DNS matrix using the actual pinned email-validator implementation."""

import dns.exception
import dns.resolver
import dns.rrset
import pytest
from pydantic import ValidationError

from app.accounts.email_rules import EmailRuleError, creation_email, lookup_forms
from app.config import Settings


def settings(**values):
    return Settings(
        database_url="postgresql+psycopg://synthetic:unused@localhost/review",
        allowed_origins=["https://review.example.com"],
        _env_file=None,
        **values,
    )


class Resolver:
    def __init__(self, **answers):
        self.answers = answers

    def resolve(self, domain, kind):
        value = self.answers.get(kind, dns.resolver.NoAnswer())
        if isinstance(value, Exception):
            raise value
        return dns.rrset.from_text(domain, 60, "IN", kind, *value)


@pytest.mark.parametrize(
    "raw",
    [
        "name",
        "a@localhost",
        "a@singlelabel",
        "a@[1.2.3.4]",
        "a@[IPv6:2001:db8::1]",
        '"quoted local"@mail-fixture.com',
        "a@foo.invalid",
        "a@foo.test",
        "a@foo.local",
        "a@foo.onion",
        "用户@mail-fixture.com",
        "Name <a@mail-fixture.com>",
    ],
)
def test_creation_rejects_unsafe_or_reserved_syntax_even_without_dns(raw):
    with pytest.raises(EmailRuleError) as error:
        creation_email(raw, settings(email_check_deliverability=False))
    assert (error.value.status, error.value.code) == (422, "invalid_email")


@pytest.mark.parametrize(
    "resolver,code,status",
    [
        (Resolver(MX=["0 ."]), "email_undeliverable", 422),
        (Resolver(MX=dns.resolver.NXDOMAIN()), "email_undeliverable", 422),
        (Resolver(), "email_undeliverable", 422),
        (Resolver(A=["8.8.8.8"], TXT=['"v=spf1 -all"']), "email_undeliverable", 422),
        (Resolver(MX=dns.exception.Timeout()), "email_check_unavailable", 503),
        (Resolver(MX=dns.resolver.NoNameservers()), "email_check_unavailable", 503),
        (Resolver(MX=RuntimeError("private-domain-canary")), "email_check_unavailable", 503),
    ],
)
def test_dns_failure_classification_never_includes_resolver_values(resolver, code, status, caplog):
    with pytest.raises(EmailRuleError) as error:
        creation_email("person@mail-fixture.com", settings(), resolver=resolver)
    assert (error.value.status, error.value.code) == (status, code)
    assert "mail-fixture.com" not in str(error.value) and "canary" not in str(error.value)
    if status == 503:
        assert [record.message for record in caplog.records] == ["email_check_unavailable"]


@pytest.mark.parametrize(
    "resolver",
    [
        Resolver(MX=["10 mx.mail-fixture.com."]),
        Resolver(A=["8.8.8.8"]),
        Resolver(AAAA=["2001:4860:4860::8888"]),
    ],
)
def test_mx_and_public_address_fallbacks_are_accepted(resolver):
    assert (
        creation_email("Person@mail-fixture.com", settings(), resolver=resolver)
        == "person@mail-fixture.com"
    )


def test_idna_canonical_and_legacy_forms_and_optional_blocklist():
    cfg = settings(email_check_deliverability=False)
    assert creation_email("PERSON@bücher.de", cfg) == "person@xn--bcher-kva.de"
    assert set(lookup_forms("PERSON@bücher.de")) == {"person@bücher.de", "person@xn--bcher-kva.de"}
    assert lookup_forms("OLD@example.invalid") == ("old@example.invalid",)
    assert creation_email("person@sub.mailinator.com", cfg) == "person@sub.mailinator.com"
    with pytest.raises(EmailRuleError, match="permanent"):
        creation_email(
            "person@sub.mailinator.com",
            settings(email_check_deliverability=False, email_block_disposable=True),
        )


def test_production_refuses_test_domain_and_outbox_allowances(tmp_path):
    for values in (
        {"email_allow_test_domains": True},
        {"dev_mail_outbox": tmp_path / ".local-dev/outbox"},
    ):
        with pytest.raises(ValidationError, match="forbidden in production"):
            settings(environment="production", **values)
    with pytest.raises(ValidationError, match=".local-dev"):
        settings(dev_mail_outbox=tmp_path / "public-outbox")
    assert (
        creation_email("fixture@openanonymi.test", settings(email_allow_test_domains=True))
        == "fixture@openanonymi.test"
    )
