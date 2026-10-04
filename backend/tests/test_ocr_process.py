"""Real process cancellation, secret-free worker environment and shared admission."""

import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.exports.errors import PdfUnavailable
from app.exports.pdf import generate_pdf
from app.intake import ocr
from app.intake.process_limits import limit_windows_worker
from app.intake.validation import SourceValidationError
from app.workloads import render_slot
from tests.ocr_fixtures import TEXT, image_sample


def test_actual_timeout_reaps_worker_and_releases_render_slot(monkeypatch):
    actual = ocr.subprocess.Popen
    processes = []

    def observe(*args, **kwargs):
        value = actual(*args, **kwargs)
        processes.append(value)
        return value

    monkeypatch.setattr(ocr.subprocess, "Popen", observe)
    monkeypatch.setattr(ocr, "OCR_TIMEOUT_SECONDS", 0.001)
    with pytest.raises(SourceValidationError, match="limits"):
        ocr.extract_ocr(image_sample(), "image")
    assert len(processes) == 1 and processes[0].poll() is not None
    assert processes[0].stdin.closed and processes[0].stdout.closed
    monkeypatch.setattr(ocr, "OCR_TIMEOUT_SECONDS", 45)
    assert ocr.extract_ocr(image_sample(), "image")["text"] == TEXT


def test_real_worker_has_no_service_secrets_filename_or_content_in_arguments(monkeypatch):
    actual = ocr.subprocess.Popen
    observed = []
    monkeypatch.setenv("PRIVACY_REVIEW_CONTENT_KEYS", "private-config-canary")
    monkeypatch.setenv("DATABASE_URL", "private-database-canary")

    def observe(*args, **kwargs):
        observed.append((args[0], kwargs["env"]))
        return actual(*args, **kwargs)

    monkeypatch.setattr(ocr.subprocess, "Popen", observe)
    assert ocr.extract_ocr(image_sample(), "image")["text"] == TEXT
    arguments, environment = observed[0]
    assert "nora@example.test" not in str(arguments)
    assert "PRIVACY_REVIEW_CONTENT_KEYS" not in environment and "DATABASE_URL" not in environment
    assert environment["OMP_THREAD_LIMIT"] == "1"


def test_ocr_and_pdf_use_one_shared_admission_slot():
    assert render_slot.acquire(blocking=False)
    try:
        with pytest.raises(SourceValidationError, match="being processed"):
            ocr.extract_ocr(image_sample(), "image")
        with pytest.raises(PdfUnavailable, match="busy"):
            generate_pdf("Reviewed canary", datetime.now(UTC))
    finally:
        render_slot.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job-object resource limit")
def test_actual_windows_job_rejects_excess_memory_and_child_processes():
    for operation in (
        "bytearray(512 * 1024 * 1024)",
        "subprocess.run([sys.executable, '-c', 'pass'], check=True)",
    ):
        environment = {
            "__PYVENV_LAUNCHER__": sys.executable,
            "SYSTEMROOT": os.environ["SYSTEMROOT"],
        }
        process = subprocess.Popen(
            [sys._base_executable, "-c", "import sys, subprocess; sys.stdin.read(); " + operation],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        close = limit_windows_worker(process)
        try:
            process.stdin.close()
            assert process.wait(timeout=5) != 0
            assert process.stdout.read() == b""
        finally:
            close()
            close()  # Cancellation and finally can race; closure must be idempotent.
            process.wait(timeout=5)
            process.stdout.close()
