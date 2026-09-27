"""Source span operations. Python indexes Unicode code points."""

from app.contracts import SourceSpan


def slice_source(source: str, span: SourceSpan) -> str:
    if span.end > len(source):
        raise ValueError("span exceeds source length")
    return source[span.start : span.end]
