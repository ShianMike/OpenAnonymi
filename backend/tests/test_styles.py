"""Exact authored output fixtures, checked phone ranges and replacement invariants."""

from datetime import date
from uuid import UUID

import phonenumbers as phones
import pytest

from app.detection.dates import parse_date
from app.transformations import styles
from app.transformations.secrets import random_offset


@pytest.mark.parametrize(
    "value,pattern,expected",
    [
        ("Nóra Caldwell 😀", "full", "**** ******** 😀"),
        ("+1 (202) 555-0188", "last4", "+* (***) ***-0188"),
        ("AB-123", "last4", "**-***"),
        ("Nóra Anne-Marie 42", "first_letters", "N*** A***-M**** **"),
        ("nora.smith@example.test", "email_domain", "****.*****@example.test"),
        ("nora.smith@example.test", "email_first", "n***.*****@*******.test"),
        (
            "https://user:password@example.test:443/path?q=42#id",
            "url_host",
            "https://****:********@example.test:443/****?*=**#**",
        ),
        ("ghp_Fictional7token", "secret_prefix", "ghp_***************"),
        ("AKIAFICTIONAL1234567", "secret_prefix", "AKIA****************"),
        ("sk_live_Fictional7654", "secret_prefix", "sk_live_*************"),
        ("header.payload.signature", "secret_prefix", "******.*******.*********"),
    ],
)
def test_masks_exact(value, pattern, expected):
    assert styles.partial_mask(value, pattern) == expected


@pytest.mark.parametrize(
    "value,region,offset,expected",
    [
        ("2026-10-03", "US", 30, "2026-11-02"),
        ("03/10/2026", "GB", -30, "03/09/2026"),
        ("10/3/2026", "US", 30, "11/2/2026"),
        ("2024-2-29", "US", 365, "2025-2-28"),
        ("3rd October 2026", "GB", 30, "2nd November 2026"),
        ("OCT 03, 2026", "US", 30, "NOV 02, 2026"),
        ("october 3rd 2026", "US", -30, "september 3rd 2026"),
        ("11th October 2026", "GB", 30, "10th November 2026"),
        ("3RD OctOber 2026", "GB", 30, "2ND NovEmber 2026"),
    ],
)
def test_shift_preserves_stored_format(value, region, offset, expected):
    parsed = parse_date(value, region)
    assert parsed is not None
    assert styles.shift_date(value, parsed.format, offset) == expected


def test_shift_interval_and_boundaries():
    left, right = "2024-02-29", "2024-03-04"
    shifted = [
        date.fromisoformat(styles.shift_date(v, parse_date(v, "US").format, -365))
        for v in (left, right)
    ]
    assert (shifted[1] - shifted[0]).days == 4
    with pytest.raises(styles.StyleUnavailable) as error:
        styles.shift_date("1900-01-01", parse_date("1900-01-01", "US").format, -30)
    assert error.value.code == "date_shift_out_of_range"
    with pytest.raises(styles.StyleUnavailable):
        styles.shift_date("2026-10-03", None, 30)
    with pytest.raises(styles.StyleUnavailable):
        styles.shift_date("2026-10-03", parse_date("2026-10-03", "US").format, 29)


@pytest.mark.parametrize(
    "value,region,pattern,birth,expected",
    [
        ("2026-10-03", "US", "month_year", False, "2026-10"),
        ("03/10/2026", "GB", "month_year", False, "10/2026"),
        ("3rd OCT 2026", "GB", "month_year", False, "Oct 2026"),
        ("October 3, 2026", "US", "year", False, "2026"),
        ("2000-10-03", "US", "age_band", True, "aged 20–29"),
        ("2008-10-04", "US", "age_band", True, "aged under 18"),
        ("2007-10-03", "US", "age_band", True, "aged 18–19"),
        ("1936-10-03", "US", "age_band", True, "aged 90 or over"),
    ],
)
def test_generalize_exact(value, region, pattern, birth, expected):
    assert (
        styles.generalize_date(
            value, parse_date(value, region, birth=birth).format, pattern, date(2026, 10, 3)
        )
        == expected
    )


@pytest.mark.parametrize(
    "action,style,option,category",
    [
        ("keep", "partial_mask", "full", "person"),
        ("label", "generalize", "year", "date"),
        ("redact", "date_shift", None, "date"),
        ("label", "stand_in", None, "national_id"),
        ("redact", "partial_mask", "email_domain", "phone"),
        ("redact", "partial_mask", "full", "date"),
        ("label", "token", "full", "email"),
        ("redact", "generalize", None, "date"),
    ],
)
def test_invalid_style_matrix(action, style, option, category):
    with pytest.raises(styles.StyleUnavailable):
        styles.validate_style(action, style, option, category)


@pytest.mark.parametrize(
    "value,pattern",
    [
        ("not an email", "email_first"),
        ("https://[bad", "url_host"),
        ("Private\nkey", "full"),
        ("value\tvalue", "last4"),
    ],
)
def test_malformed_and_multiline_values(value, pattern):
    with pytest.raises(styles.StyleUnavailable):
        styles.partial_mask(value, pattern)


def test_birth_required_and_created_date_is_fixed():
    code = parse_date("2000-01-01", "US").format
    with pytest.raises(styles.StyleUnavailable):
        styles.generalize_date("2000-01-01", code, "age_band", date(2026, 10, 3))
    with pytest.raises(styles.StyleUnavailable):
        styles.generalize_date(
            "2100-01-01",
            parse_date("2100-01-01", "US", birth=True).format,
            "age_band",
            date(2026, 10, 3),
        )


def groups(count=20):
    return [
        styles.StandInGroup(
            UUID(int=i + 1), "person", f"PERSON_{i + 1:03}", ("Synthetic Original " + str(i),)
        )
        for i in range(count)
    ]


def test_standins_consistent_unique_source_excluded_and_seed_scoped():
    rows = groups()
    source = "\n".join(value for row in rows for value in row.originals)
    first = styles.stand_ins(bytes(32), rows, source, "US")
    assert first == styles.stand_ins(bytes(32), list(reversed(rows)), source, "US")
    assert len(set(first.values())) == len(rows) and None not in first.values()
    assert first != styles.stand_ins(bytes([1]) * 32, rows, source, "US")
    excluded = next(iter(first.values()))
    collision = styles.stand_ins(bytes(32), rows, source + "\n" + excluded.upper(), "US")
    assert excluded not in collision.values()
    assert all(not any(c in value for c in "\n\t\0") for value in first.values())


def test_exact_standin_fixtures_for_every_supported_category():
    categories = ("person", "organization", "location", "address", "email", "url", "phone")
    originals = (
        "Nora Caldwell",
        "Original Co",
        "Original Place",
        "1 Original St",
        "original@example.test",
        "https://original.test",
        "+44 7400 123456",
    )
    rows = [
        styles.StandInGroup(UUID(int=i + 1), category, category.upper() + "_001", (value,))
        for i, (category, value) in enumerate(zip(categories, originals, strict=True))
    ]
    expected = (
        "Fiora Flintdale",
        "Wise Pond Ltd",
        "Maplehaven",
        "3392 Pine Haven Road, Dawnhaven",
        "emina.pinegrove@example.net",
        "https://example.org/port-53223",
        "+447700900686",
    )
    assert styles.stand_ins(bytes(32), rows, " ".join(originals), "GB") == {
        row.id: value for row, value in zip(rows, expected, strict=True)
    }


def test_collision_limit_falls_back_to_token(monkeypatch):
    calls = []

    def repeated(seed, group, attempt, region):
        calls.append(attempt)
        return "Synthetic Original 0"

    monkeypatch.setattr(styles, "_candidate", repeated)
    row = groups(1)[0]
    assert styles.stand_ins(bytes(32), [row], "Synthetic Original 0", "US") == {row.id: None}
    assert calls == list(range(50))


def test_phone_original_collision_is_rejected_across_equivalent_formats(monkeypatch):
    row = styles.StandInGroup(UUID(int=1), "phone", "PHONE_001", ("+1 (202) 555-0188",))
    monkeypatch.setattr(styles, "_candidate", lambda *_args: "+12025550188")
    assert styles.stand_ins(bytes(32), [row], "Call +1 (202) 555-0188", "US") == {row.id: None}


@pytest.mark.parametrize(
    "original,region,country",
    [
        ("+1 202 555 0188", "US", 1),
        ("4165550188", "CA", 1),
        ("+44 7400 123456", "GB", 44),
        ("020 7946 1212", "GB", 44),
        ("+61 412 345 678", "AU", 61),
        ("02 9876 5432", "AU", 61),
    ],
)
def test_phone_candidates_stay_in_official_blocks(original, region, country):
    value = styles.phone_candidate(original, region, 123456)
    assert value is not None
    parsed = phones.parse(value, None)
    assert parsed.country_code == country
    national = str(parsed.national_number)
    if country == 1:
        assert national[3:6] == "555" and 100 <= int(national[-4:]) <= 199
    else:
        table = styles.data("fictional_phone_ranges")[region]
        assert any(
            national == row.get("number")
            or (
                national.startswith(row.get("prefix", "!"))
                and len(national) == len(row.get("prefix", "")) + row.get("digits", 0)
            )
            for row in table
        )
    formatted = styles.format_phone(value, original)
    assert formatted.startswith("+") == original.startswith("+")


def test_unverified_region_never_gets_phone_standin():
    assert styles.phone_candidate("+63 917 123 4567", "PH", 1) is None
    with pytest.raises(styles.StyleUnavailable, match="verified fictional"):
        styles.validate_style(
            "label", "stand_in", None, "phone", value="+63 917 123 4567", region="PH"
        )


def test_seed_offset_uniform_mapping_and_data_contract(monkeypatch):
    from app.transformations import secrets as stored

    choices = []
    for i in range(672):
        monkeypatch.setattr(
            stored.secrets, "randbelow", lambda limit, index=i: index if limit == 672 else -1
        )
        choices.append(random_offset())
    assert choices == list(range(-365, -29)) + list(range(30, 366))
    minimum = {
        "given_names": 200,
        "family_names": 200,
        "organization_first": 100,
        "organization_second": 100,
        "organization_suffixes": 6,
        "places": 300,
        "street_names": 200,
    }
    for name, count in minimum.items():
        bundled = styles.data(name)
        assert bundled["license"] == "CC0-1.0" and bundled["count"] >= count
        assert len(set(bundled["values"])) == bundled["count"]
