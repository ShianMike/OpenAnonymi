"""Bounded local OCR process; binary input and extracted text stay off disk."""

import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Event, Thread, Timer

from app.intake.process_limits import limit_windows_worker
from app.intake.validation import SourceValidationError
from app.workloads import render_slot

OCR_TIMEOUT_SECONDS = 45
MAX_REPLY_BYTES = 4 * 1024 * 1024  # Text plus at most ten bounded correction previews.


def extract_ocr(
    content: bytes, kind: str, pages: tuple[int, ...] = (), *, include_previews: bool = False
) -> dict:
    if not render_slot.acquire(blocking=False):
        raise SourceValidationError("Another file or PDF is being processed. Try again shortly.")
    process = None
    timer = None
    writer = None
    close_job = None
    timed_out = Event()
    try:
        # The worker needs runtime paths, not service credentials or content keys.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}
        }
        environment.update({"PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1", "OMP_THREAD_LIMIT": "1"})
        executable = sys.executable
        if sys.platform == "win32":
            # Bypass the venv redirector so the job contains the actual worker,
            # with no launcher child that can predate assignment or survive a kill.
            executable = sys._base_executable
            environment["__PYVENV_LAUNCHER__"] = sys.executable
        process = subprocess.Popen(
            [
                executable,
                "-X",
                "utf8",
                "-m",
                "app.intake.ocr_worker",
                *(["--previews"] if include_previews else []),
                kind,
                ",".join(str(index) for index in pages),
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        close_job = limit_windows_worker(process)

        def stop():
            timed_out.set()
            if close_job:
                close_job()
            try:
                if process.poll() is None:
                    process.kill()
            except OSError:
                pass

        timer = Timer(OCR_TIMEOUT_SECONDS, stop)
        timer.start()

        def send():
            try:
                process.stdin.write(content)
                process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass

        writer = Thread(target=send, daemon=True)
        writer.start()
        payload = process.stdout.read(MAX_REPLY_BYTES + 1)
        if len(payload) > MAX_REPLY_BYTES:
            process.kill()
            raise SourceValidationError("OCR text exceeds the import limit. Choose a smaller scan.")
        process.wait(timeout=2)
        if timed_out.is_set() or process.returncode:
            raise SourceValidationError(
                "OCR could not finish within its limits. Choose a clearer or smaller scan."
            )
        result = json.loads(payload)
        if result.get("error"):
            # Messages are fixed worker codes; never expose a decoder exception.
            messages = {
                "pixels": "Scan dimensions exceed the 8-million-pixel limit per page.",
                "pages": "OCR supports at most 10 scanned pages per file.",
                "format": "Choose a readable PNG, JPEG, TIFF or WebP image.",
                "empty": "OCR found no readable text. Choose a clearer scan or paste the text.",
                "text": "OCR text exceeds the 100,000-character or 1 MiB limit.",
            }
            raise SourceValidationError(
                messages.get(
                    result["error"],
                    "Local OCR is unavailable. Try a clearer scan or paste the text.",
                )
            )
        return result
    except SourceValidationError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError):
        if timed_out.is_set():
            raise SourceValidationError(
                "OCR could not finish within its limits. Choose a clearer or smaller scan."
            ) from None
        raise SourceValidationError(
            "Local OCR is unavailable. Try a clearer scan or paste the text."
        ) from None
    finally:
        if timer:
            timer.cancel()
        if process:
            if process.poll() is None:
                process.kill()
            process.wait()
            if writer:
                writer.join(timeout=2)
            try:
                process.stdin.close()
            except OSError:
                pass
            process.stdout.close()
        if close_job:
            close_job()
        render_slot.release()
