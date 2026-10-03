"""The installed CPU model and syntax/checksum rules, with real Unicode spans."""

from itertools import pairwise

import pytest

from app.contracts import FindingCategory
from app.detection.identifiers import detect_identifiers
from app.detection.local_nlp import detect_entities, pipeline
from app.detection.rules import DetectionLimitError, detect_suggestions


def test_actual_named_entities_offline_and_spans(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests.sessions.Session,
        "request",
        lambda *a, **k: pytest.fail("Document detection must remain local"),
    )
    source = "😀 Nora Caldwell works at Microsoft in London. Sarah Johnson lives in Berlin. Alice Smith traveled to Paris."
    categories = {FindingCategory.PERSON, FindingCategory.ORGANIZATION, FindingCategory.LOCATION}
    detected = detect_entities(source, categories)
    assert {
        (item.category.value, source[item.span.start : item.span.end]) for item in detected
    } == {
        ("person", "Nora Caldwell"),
        ("organization", "Microsoft"),
        ("location", "London"),
        ("person", "Sarah Johnson"),
        ("location", "Berlin"),
        ("person", "Alice Smith"),
        ("location", "Paris"),
    }
    assert all(
        item.rule_id.startswith("local.en_core_web_sm.") and item.rule_version == "3.8.0"
        for item in detected
    )
    assert "ner" in pipeline().pipe_names
    assert all(
        item.category == FindingCategory.LOCATION
        for item in detect_entities(source, {FindingCategory.LOCATION})
    )
    assert detect_entities(source, {FindingCategory.EMAIL}) == []


def test_identifiers_only_valid_syntax_checksums():
    source = "😀 Network 192.0.2.17; invalid 999.1.1.1. Sample card 4111 1111 1111 1111. Wrong 4111 1111 1111 1112."
    assert [source[item.span.start : item.span.end] for item in detect_identifiers(source)] == [
        "192.0.2.17",
        "4111 1111 1111 1111",
    ]
    assert len(detect_suggestions(source, {FindingCategory.IDENTIFIER}, "PH")) == 2
    assert detect_suggestions(source, set(), "PH") == []
    with pytest.raises(DetectionLimitError):
        detect_identifiers("192.0.2.1 " * 1001)


def test_missing_model_is_explicit_failure(monkeypatch):
    import spacy

    pipeline.cache_clear()

    def unavailable(*_args, **_kwargs):
        raise OSError("missing package")

    monkeypatch.setattr(spacy, "load", unavailable)
    try:
        with pytest.raises(DetectionLimitError, match="local_model_unavailable"):
            detect_entities("A fictional person", {FindingCategory.PERSON})
    finally:
        pipeline.cache_clear()


def test_chunk_context_preserves_unicode_offsets_without_duplicate_entities():
    from app.detection.local_nlp import CHUNK_POINTS, CONTEXT_POINTS, chunks

    padding = 'neutral notes. ' * 330
    source = '😀 ' + padding + 'Nora Caldwell works at Microsoft in London. ' + 'neutral notes. ' * 500
    windows = list(chunks(source))
    assert len(windows) >= 2 and all(len(text) <= CHUNK_POINTS for _,text in windows)
    assert all(start + len(text) >= following for (start,text),(following,_) in pairwise(windows))
    assert len(windows[0][1]) >= 2*CONTEXT_POINTS
    detected = detect_entities(source, {FindingCategory.PERSON})
    names = [item for item in detected if source[item.span.start:item.span.end] == 'Nora Caldwell']
    assert len(names) == 1 and names[0].span.start == source.index('Nora Caldwell')
