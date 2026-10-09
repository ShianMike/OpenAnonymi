"""Observe real unsupported image parsers inside the bounded native OCR process."""
import subprocess

import pytest

from app.intake import ocr
from app.intake.validation import SourceValidationError
from tests.ocr_fixtures import image_sample

MARKER = b"OA_UNSUPPORTED_IMAGE_PARSER_ENTERED"
OBSERVE = """
import sys
from PIL import Image
Image.init()
codec = sys.argv[1]
sys.argv = ['worker', *sys.argv[2:]]
factory, accept = Image.OPEN[codec]
def observed(*args, **kwargs):
    sys.stderr.write('OA_UNSUPPORTED_IMAGE_PARSER_ENTERED\\n')
    sys.stderr.flush()
    return factory(*args, **kwargs)
Image.register_open(codec, observed, accept)
from app.intake.ocr_worker import main
main()
"""


def observe_rejected_codec(monkeypatch, codec):
    actual, processes = ocr.subprocess.Popen, []

    def observe(arguments, **kwargs):
        # Preserve actual input, stdout, environment, timeouts and OS limits.
        # Only the original decoder factory receives a content-free stderr marker.
        process = actual([arguments[0], "-X", "utf8", "-c", OBSERVE, codec, *arguments[-2:]],
                         **{**kwargs, "stderr": subprocess.PIPE})
        processes.append(process)
        return process

    monkeypatch.setattr(ocr.subprocess, "Popen", observe)
    with pytest.raises(SourceValidationError, match="readable PNG, JPEG, TIFF or WebP"):
        ocr.extract_ocr(image_sample(codec), "image")
    assert len(processes) == 1 and processes[0].returncode == 0
    try:
        return MARKER in processes[0].stderr.read()
    finally:
        processes[0].stderr.close()


@pytest.mark.parametrize("codec", ("BMP", "GIF"))
def test_unsupported_codecs_are_rejected_without_entering_their_real_parser(monkeypatch, codec):
    assert not observe_rejected_codec(monkeypatch, codec)
