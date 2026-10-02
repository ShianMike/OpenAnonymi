"""Deterministic, bounded suggestions over one immutable Unicode source."""

import re
from dataclasses import dataclass

import phonenumbers

from app.contracts import MAX_CODE_POINTS, FindingCategory, SourceSpan

DETECTOR_VERSION = "1"
MAX_SUGGESTIONS = 1_000
MAX_PHONE_DIGITS = 20_000

# This intentionally recognizes common ASCII mailbox syntax. Exact matched text
# stays in the encrypted source and is never copied into a finding row.
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9](?:[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{0,62}[A-Za-z0-9])?"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.){1,10}"
    r"[A-Za-z]{2,63}(?![A-Za-z0-9-])"
)


class DetectionLimitError(RuntimeError):
    """A safe, content-free limit failure; this is not a zero-match result."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Suggestion:
    span: SourceSpan
    category: FindingCategory
    rule_id: str
    rule_version: str
    reason: str


def _append(result: list[Suggestion], suggestion: Suggestion) -> None:
    if len(result) >= MAX_SUGGESTIONS:
        raise DetectionLimitError("too_many_suggestions")
    result.append(suggestion)


def detect_suggestions(
    source: str, categories: set[FindingCategory], phone_region: str
) -> list[Suggestion]:
    """Return stable code-point spans without approving any review action."""
    if len(source) > MAX_CODE_POINTS:
        raise DetectionLimitError("source_too_large")
    if not categories.issubset(
        {
            FindingCategory.EMAIL,
            FindingCategory.PHONE,
            FindingCategory.PERSON,
            FindingCategory.ORGANIZATION,
            FindingCategory.LOCATION,
            FindingCategory.IDENTIFIER,
        }
    ):
        raise ValueError("Choose supported automatic suggestion categories.")
    if phone_region not in phonenumbers.SUPPORTED_REGIONS:
        raise ValueError("Choose a supported phone region.")

    result: list[Suggestion] = []
    email_spans: list[tuple[int, int]] = []
    if FindingCategory.EMAIL in categories:
        for match in EMAIL_PATTERN.finditer(source):
            local = source[match.start() : source.index("@", match.start(), match.end())]
            if ".." in local:
                continue
            email_spans.append((match.start(), match.end()))
            _append(
                result,
                Suggestion(
                    span=SourceSpan(start=match.start(), end=match.end()),
                    category=FindingCategory.EMAIL,
                    rule_id="email.common_syntax",
                    rule_version="1",
                    reason="Matches common email address syntax.",
                ),
            )

    if FindingCategory.PHONE in categories:
        if sum(character.isdigit() for character in source) > MAX_PHONE_DIGITS:
            raise DetectionLimitError("too_many_phone_candidates")
        matcher = phonenumbers.PhoneNumberMatcher(
            source,
            phone_region,
            leniency=phonenumbers.Leniency.VALID,
            max_tries=MAX_PHONE_DIGITS + 1,
            min_candidate_length=7,
        )
        for match in matcher:
            start, end = match.start, match.end
            digits = sum(character.isdigit() for character in source[start:end])
            if not 7 <= digits <= 15:
                continue
            if start and (source[start - 1].isalnum() or source[start - 1] in "_@"):
                continue
            if end < len(source) and (source[end].isalnum() or source[end] in "_@"):
                continue
            if any(
                start < email_end and email_start < end for email_start, email_end in email_spans
            ):
                continue
            _append(
                result,
                Suggestion(
                    span=SourceSpan(start=start, end=end),
                    category=FindingCategory.PHONE,
                    rule_id="phone.libphonenumber_valid",
                    rule_version=phonenumbers.__version__,
                    reason=f"Valid phone number with {phone_region} as the default region.",
                ),
            )

    from app.detection.identifiers import detect_identifiers
    from app.detection.local_nlp import detect_entities

    result.extend(detect_entities(source, categories))
    if FindingCategory.IDENTIFIER in categories:
        result.extend(detect_identifiers(source))
    if len(result) > MAX_SUGGESTIONS:
        raise DetectionLimitError("too_many_suggestions")
    return sorted(result, key=lambda item: (item.span.start, item.span.end, item.category.value))
