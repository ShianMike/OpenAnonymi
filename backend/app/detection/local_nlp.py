"""CPU English named entity suggestions. Source text never leaves this process."""

from functools import lru_cache
from threading import Lock

from app.contracts import FindingCategory, SourceSpan
from app.detection.rules import MAX_SUGGESTIONS, DetectionLimitError, Suggestion

MODEL = "en_core_web_sm"
NER_CATEGORIES = {FindingCategory.PERSON, FindingCategory.ORGANIZATION, FindingCategory.LOCATION}
_lock = Lock()


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


def detect_entities(source: str, categories: set[FindingCategory]) -> list[Suggestion]:
    if not categories.intersection(NER_CATEGORIES):
        return []
    # Share loaded weights, serialize bounded CPU inference, and discard each Doc.
    with _lock:
        nlp = pipeline()
        with nlp.memory_zone():
            doc = nlp(source)
            result = []
            mapping = {
                "PERSON": FindingCategory.PERSON,
                "ORG": FindingCategory.ORGANIZATION,
                "GPE": FindingCategory.LOCATION,
                "LOC": FindingCategory.LOCATION,
                "FAC": FindingCategory.LOCATION,
            }
            for entity in doc.ents:
                category = mapping.get(entity.label_)
                if category not in categories or category is None:
                    continue
                if len(result) >= MAX_SUGGESTIONS:
                    raise DetectionLimitError("too_many_suggestions")
                result.append(
                    Suggestion(
                        SourceSpan(start=entity.start_char, end=entity.end_char),
                        category,
                        f"local.{MODEL}.{entity.label_.lower()}",
                        nlp.meta["version"],
                        f"English local model suggests a {category.value}; inspect its context and correct misses.",
                    )
                )
            return result
