"""Deterministic, bounded suggestions over one immutable Unicode source."""

import re
from dataclasses import dataclass

import phonenumbers

from app.contracts import AUTOMATIC_CATEGORIES, MAX_CODE_POINTS, FindingCategory, SourceSpan

DETECTOR_VERSION = "2"
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
    date_format: str | None = None


def _append(result: list[Suggestion], suggestion: Suggestion) -> None:
    if len(result) >= MAX_SUGGESTIONS:
        raise DetectionLimitError("too_many_suggestions")
    result.append(suggestion)


def detect_suggestions(
    source: str, categories: set[FindingCategory], phone_region: str, language: str = "en"
) -> list[Suggestion]:
    """Return stable code-point spans without approving any review action."""
    if len(source) > MAX_CODE_POINTS:
        raise DetectionLimitError("source_too_large")
    if not categories.issubset(AUTOMATIC_CATEGORIES):
        raise ValueError("Choose supported automatic suggestion categories.")
    if phone_region not in phonenumbers.SUPPORTED_REGIONS:
        raise ValueError("Choose a supported phone region.")

    result: list[Suggestion] = []
    if FindingCategory.EMAIL in categories:
        for match in EMAIL_PATTERN.finditer(source):
            local = source[match.start() : source.index("@", match.start(), match.end())]
            domain = source[match.start() + len(local) + 1:match.end()]
            if ".." in local or len(match[0]) > 254 or re.fullmatch(r"[0-9]+x\.(?:png|jpg|jpeg|gif|svg|webp|avif|ico)", domain, re.IGNORECASE):
                continue
            _append(
                result,
                Suggestion(
                    span=SourceSpan(start=match.start(), end=match.end()),
                    category=FindingCategory.EMAIL,
                    rule_id="email.common_syntax",
                    rule_version="2",
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

    from app.detection.addresses import detect_addresses
    from app.detection.dates import detect_dates
    from app.detection.iban import detect_iban
    from app.detection.identifiers import detect_identifiers
    from app.detection.local_nlp import detect_entities
    from app.detection.national_ids import detect_national_ids
    from app.detection.secrets import detect_secrets
    from app.detection.web import detect_urls, detect_web_identifiers

    entities = detect_entities(source, categories, language)
    result.extend(entities)
    if FindingCategory.IDENTIFIER in categories:
        result.extend(detect_identifiers(source))
        result.extend(detect_web_identifiers(source))
        result.extend(detect_iban(source))
    if FindingCategory.DATE in categories:
        result.extend(detect_dates(source, phone_region))
    if FindingCategory.URL in categories:
        result.extend(detect_urls(source))
    if FindingCategory.SECRET in categories:
        result.extend(detect_secrets(source))
    if FindingCategory.NATIONAL_ID in categories:
        result.extend(detect_national_ids(source))
    if FindingCategory.ADDRESS in categories:
        result.extend(detect_addresses(source, entities if language == "en" else ()))
    result = resolve_overlaps(result)
    if len(result) > MAX_SUGGESTIONS:
        raise DetectionLimitError("too_many_suggestions")
    return sorted(result, key=lambda item: (item.span.start, item.span.end, item.category.value))


PRECEDENCE = {category: index for index, category in enumerate((FindingCategory.SECRET, FindingCategory.NATIONAL_ID, FindingCategory.EMAIL, FindingCategory.URL, FindingCategory.IDENTIFIER, FindingCategory.PHONE, FindingCategory.DATE, FindingCategory.ADDRESS, FindingCategory.PERSON, FindingCategory.ORGANIZATION, FindingCategory.LOCATION))}


def resolve_overlaps(suggestions: list[Suggestion]):
    """Longest first, category precedence, earlier start; custom rules are added later."""
    priority = sorted(suggestions, key=lambda item: (-(item.span.end - item.span.start), PRECEDENCE.get(item.category, 99), item.span.start, item.rule_id))
    accepted = []
    for item in priority:
        if not any(item.span.start < other.span.end and other.span.start < item.span.end for other in accepted):
            accepted.append(item)
    return accepted
