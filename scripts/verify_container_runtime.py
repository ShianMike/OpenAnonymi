"""Actual synthetic API/NLP/OCR/PDF workload inside the production image's cgroup.

Run in CI after bootstrap, with backend/tests mounted at /app/tests for the
existing genuine raster/PDF fixtures. stdout contains only content-free evidence.
--http-only checks the same HTTP flow locally without claiming Linux resource caps.
"""

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument("--api", default="http://127.0.0.1:8080/api/v1")
parser.add_argument("--origin", default="https://app.example.invalid")
parser.add_argument("--http-only", action="store_true")
args = parser.parse_args()
assert args.api.startswith(("http://127.0.0.1:", "http://localhost:"))
sys.path.append(str(Path.cwd()))

from tests.ocr_fixtures import TEXT, image_sample, scanned_pdf


def call(path, body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
    request = Request(args.api + path, data=data, headers={
        "Origin": args.origin, "Content-Type": "application/json", **(headers or {})})
    with urlopen(request, timeout=60) as response:
        return response.status, response.headers, response.read()


def native_inventory():
    import pypdfium2
    import tesserocr
    from PIL import features

    binaries, sboms = [], []
    for name in ("Pillow", "tesserocr", "pypdfium2"):
        distribution = importlib.metadata.distribution(name)
        for relative in distribution.files or ():
            if "/sboms/" in str(relative) and str(relative).endswith(".json"):
                path = distribution.locate_file(relative)
                sboms.append({"package": name, "file": str(relative),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "data": json.loads(path.read_text("utf-8"))})
            if any(part in str(relative).lower() for part in (".so", ".dll", ".pyd", ".dylib")):
                path = distribution.locate_file(relative)
                if path.is_file():
                    binaries.append({"package": name, "file": str(relative),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assets = Path("app/assets/ocr")
    models = json.loads((assets / "manifest.json").read_text("utf-8"))["files"]
    for item in models:
        assert hashlib.sha256((assets / item["filename"]).read_bytes()).hexdigest() == item["sha256"]
    return {"platform": platform.system(), "python": platform.python_version(),
        "packages": {name: importlib.metadata.version(name) for name in ("Pillow", "tesserocr", "pypdfium2")},
        "tesseract_linked_version_report": tesserocr.tesseract_version(),
        "pillow_linked_versions": {name: features.version(name) for name in features.get_supported()},
        "pdfium_version": str(pypdfium2.PDFIUM_INFO), "binary_hashes": binaries, "sboms": sboms,
        "packaged_models": models, "native_patch_status_certified": False}


inventory, caps = None, None
if not args.http_only:
    assert sys.platform == "linux"
    inventory = native_inventory()
    # Exercise the actual installed limiter in an independent child. Never put
    # RLIMIT_AS on the running API or this fixture-generating controller.
    probe = subprocess.run([sys.executable, "-c", """
import json, os, resource, socket
from app.intake.process_limits import limit_linux_worker
limit_linux_worker()
limits = {name: resource.getrlimit(getattr(resource, 'RLIMIT_' + name)) for name in ('AS', 'CPU', 'CORE')}
assert limits == {'AS': (402653184, 402653184), 'CPU': (40, 40), 'CORE': (0, 0)}
try:
    bytearray(512 * 1024 * 1024)
except MemoryError:
    with open('/proc/' + str(os.getppid()) + '/environ', 'rb') as parent:
        parent_setting_readable = b'PRIVACY_REVIEW_CONTENT_KEYS=' in parent.read()
    with socket.create_connection(('127.0.0.1', 8080), timeout=1):
        loopback_connect_allowed = True
    print(json.dumps({'actual_limits': limits, 'excess_allocation_rejected': True,
        'parent_service_setting_readable': parent_setting_readable,
        'loopback_connect_allowed': loopback_connect_allowed,
        'process_security_isolation_verified': False}))
else:
    raise AssertionError('OCR memory limit did not reject allocation')
"""], capture_output=True, timeout=10, check=True)
    caps = json.loads(probe.stdout)
    cgroup = Path("/sys/fs/cgroup")
    assert int((cgroup / "memory.max").read_text("utf-8")) == 512 * 1024 * 1024

status, response_headers, content = call("/auth/sign-in", {
    "email": os.environ.get("CI_RUNTIME_EMAIL", "ci-smoke@openanonymi.vercel.app"),
    "password": os.environ.get("CI_RUNTIME_PASSWORD", "synthetic-ci-password")})
assert status == 200
identity = json.loads(content)
headers = {"Cookie": response_headers["Set-Cookie"].split(";", 1)[0],
    "X-CSRF-Token": identity["csrf_token"]}
workspace = identity["memberships"][0]["workspace_id"]

status, _, content = call("/documents", {"workspace_id": workspace,
    "source": "Maya Chen visited Microsoft in Manila.", "categories": ["person", "organization", "location"],
    "phone_region": "PH", "language": "en", "retention_days": 3}, headers)
assert status == 201
version = json.loads(content)["version"]
status, _, content = call(f"/documents/{version['document_id']}/scan", {"expected": version}, headers)
scan = json.loads(content)
assert status == 200 and scan["status"] == "completed"
assert any(item["rule_id"].startswith("local.en_core_web_sm.") for item in scan["suggestions"])
checks = ["actual NLP inference warms the retained API model"]

for extension, sample, expected in [
    *[(kind.lower(), image_sample(kind), TEXT) for kind in ("PNG", "JPEG", "TIFF", "WEBP")],
    ("tiff", image_sample("TIFF", frames=2), TEXT + "\n\n" + TEXT),
    ("pdf", scanned_pdf(), TEXT),
]:
    boundary = "ci-" + uuid4().hex
    prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"workspace_id\"\r\n\r\n"
        f"{workspace}\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"fictional.{extension}\"\r\nContent-Type: application/octet-stream\r\n\r\n")
    payload = prefix.encode("ascii") + sample + f"\r\n--{boundary}--\r\n".encode("ascii")
    status, _, content = call("/documents/import-preview", payload,
        {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert status == 200 and json.loads(content)["text"] == expected
    checks.append("actual " + extension + (" multi-frame" if expected != TEXT else "") + " OCR preview")

status, _, content = call("/documents", {"workspace_id": workspace, "source": "Reviewed fictional check",
    "categories": [], "phone_region": "PH", "retention_days": 3}, headers)
assert status == 201
version = json.loads(content)["version"]
base = f"/documents/{version['document_id']}"
status, _, content = call(base + "/scan", {"expected": version}, headers)
assert status == 200
version = json.loads(content)["version"]
assert call(base + "/complete", {"expected": version, "confirmed_preview": True}, headers)[0] == 200
status, output_headers, pdf = call(base + "/exports/pdf", {"expected": version, "event_id": str(uuid4())}, headers)
assert status == 200 and output_headers["Content-Type"] == "application/pdf"
from pypdf import PdfReader

assert " ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).strip() == "Reviewed fictional check"
checks.append("actual confirmed reviewed PDF bytes and canonical text")
assert call("/health/ready")[0] == 200

memory = None
if not args.http_only:
    memory = {name: int((cgroup / ("memory." + name)).read_text("utf-8")) for name in ("max", "current", "peak")}
    events = dict(line.split() for line in (cgroup / "memory.events").read_text("utf-8").splitlines())
    memory["oom"] = int(events["oom"])
    memory["oom_kill"] = int(events["oom_kill"])
    assert memory["peak"] < memory["max"] and memory["oom"] == memory["oom_kill"] == 0
print(json.dumps({"synthetic_only": True, "checks": checks, "all_passed": True,
    "native_inventory": inventory, "linux_caps": caps, "cgroup_memory_bytes": memory}), flush=True)
