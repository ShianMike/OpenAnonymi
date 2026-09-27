import pytest

from app.intake.validation import SourceValidationError, validate_source


def test_source_limits_and_one_time_bom_handling_preserve_content():
    original = "\ufeffA😀\r\n東京"
    validated = validate_source(original)
    assert validated.text == "A😀\r\n東京"
    assert validated.initial_bom_removed
    assert validated.code_points == len(validated.text)
    assert validated.utf8_bytes == len(validated.text.encode("utf-8"))
    assert validate_source("x" * 100_000).code_points == 100_000
    with pytest.raises(SourceValidationError, match="character limit"):
        validate_source("x" * 100_001)
    with pytest.raises(SourceValidationError, match="1 MiB"):
        validate_source("x" * 1_048_577)


@pytest.mark.parametrize("source", ["", " \r\n\t", "\ufeff", "a\x00b", "\ud800"])
def test_invalid_source_is_rejected_without_echoing_input(source):
    with pytest.raises(SourceValidationError) as error:
        validate_source(source)
    if source:
        assert source not in str(error.value)
