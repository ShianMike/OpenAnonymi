"""CPU named entity suggestions. Source text never leaves this process."""

import re
from functools import lru_cache
from threading import Lock

from app.contracts import FindingCategory, SourceSpan
from app.detection.rules import MAX_SUGGESTIONS, DetectionLimitError, Suggestion, resolve_overlaps

MODEL = "en_core_web_sm"
SUPPORTED_LANGUAGES = ("en",)
NER_CATEGORIES = {FindingCategory.PERSON, FindingCategory.ORGANIZATION, FindingCategory.LOCATION}
_lock = Lock()
CHUNK_POINTS = 6_000
CONTEXT_POINTS = 512


def chunks(source):
    """Overlapping context bounds neural activations while preserving source offsets."""
    step = CHUNK_POINTS - 2 * CONTEXT_POINTS
    for core in range(0, len(source), step):
        start = max(0, core - CONTEXT_POINTS)
        end = min(len(source), core + step + CONTEXT_POINTS)
        yield start, source[start:end]


@lru_cache(maxsize=1)
def pipeline():
    try:
        import spacy

        nlp = spacy.load(MODEL, exclude=["tagger", "parser", "attribute_ruler", "lemmatizer"])
        nlp.max_length = 100_001
        if "ner" not in nlp.pipe_names:
            raise OSError("NER pipeline unavailable")
        return nlp
    except (ImportError, OSError):
        raise DetectionLimitError("local_model_unavailable") from None


def detect_entities(source: str, categories: set[FindingCategory], language="en") -> list[Suggestion]:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("Choose a supported language.")
    if not categories.intersection(NER_CATEGORIES):
        return []
    # Keep code-point offsets while preventing Markdown punctuation from hiding names.
    # ponytail: mask common Markdown delimiters for NER; use a mapped parser if escaped names need support.
    analysis_source = source.translate(str.maketrans('#*>`|[]', '       ')) if re.search(
        r'(?m)^ {0,3}(?:#{1,6} |>|\||[-*] \[)|\*\*\S|`\S', source
    ) else source
    # Share loaded weights, serialize bounded CPU inference, and discard each Doc.
    with _lock:
        nlp = pipeline()
        result = {}
        mapping = {
                "PERSON": FindingCategory.PERSON,
                "ORG": FindingCategory.ORGANIZATION,
                "GPE": FindingCategory.LOCATION,
                "LOC": FindingCategory.LOCATION,
                "FAC": FindingCategory.LOCATION,
        }
        for offset, chunk in chunks(analysis_source):
            with nlp.memory_zone():
                doc = nlp(chunk)
                for entity in doc.ents:
                    category = mapping.get(entity.label_)
                    if category not in categories or category is None:
                        continue
                    start, end = offset + entity.start_char, offset + entity.end_char
                    while start < end and analysis_source[start].isspace():
                        start += 1
                    while end > start and (analysis_source[end - 1].isspace() or analysis_source[end - 1] == ':'):
                        end -= 1
                    if start == end:
                        continue
                    # Never mark a word fragment manufactured at a chunk edge.
                    if (entity.start_char == 0 and start and source[start-1].isalnum() and source[start].isalnum()) or (entity.end_char == len(chunk) and end < len(source) and source[end-1].isalnum() and source[end].isalnum()):
                        continue
                    key = (start, end, category)
                    if key not in result and len(result) >= MAX_SUGGESTIONS:
                        raise DetectionLimitError("too_many_suggestions")
                    result[key] = Suggestion(
                        SourceSpan(start=start, end=end),
                        category,
                        f"local.{MODEL}.{entity.label_.lower()}",
                        nlp.meta["version"],
                        f"English local model suggests a {category.value}; inspect its context and correct misses.",
                    )
        # Once a full person name is recognized, cover its other exact occurrences too.
        # Single first names remain contextual; common words must not spread across the draft.
        names = {}
        for item in result.values():
            value = source[item.span.start:item.span.end]
            if item.category == FindingCategory.PERSON and len(value) <= 100 and re.fullmatch(
                r"[^\W\d_]+(?:[-'][^\W\d_]+)*(?:[ \t]+[^\W\d_]+(?:[-'][^\W\d_]+)*)+", value
            ):
                names.setdefault(value, item)
        for value, item in names.items():
            for match in re.finditer(r'(?<!\w)' + re.escape(value) + r'(?!\w)', source):
                key = (match.start(), match.end(), item.category)
                if key not in result:
                    if len(result) >= MAX_SUGGESTIONS:
                        raise DetectionLimitError('too_many_suggestions')
                    result[key] = Suggestion(SourceSpan(start=match.start(), end=match.end()),
                        item.category, item.rule_id, item.rule_version, item.reason)
        return sorted(resolve_overlaps(list(result.values())), key=lambda item:(item.span.start,item.span.end))
