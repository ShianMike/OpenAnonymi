"""Check tracked release paths and prove secret-scan fixture exceptions stay narrow."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_FILES = {
    ".dockerignore", ".gitattributes", ".gitignore", ".gitleaks.toml", "Dockerfile",
    "heroku.yml", "README.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md",
    "SECURITY.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md",
}
SCRIPTS = {
    "run_backend_shard.py", "verify_frontend_config.py", "verify_container_runtime.py",
    "check_public_repository.py",
}
DOCS = {"DEVELOPMENT.md", "DEPLOYMENT.md"}


def allowed(name):
    path = Path(name)
    parts = path.parts
    if any(part in {".local-dev", ".venv", "node_modules", "__pycache__", "dist"}
           for part in parts):
        return False
    if ".private." in name or path.suffix in {".key", ".pem", ".dump", ".sql", ".sqlite"}:
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if len(parts) == 1:
        return name in ROOT_FILES
    if parts[0] == "scripts":
        return len(parts) == 2 and parts[1] in SCRIPTS
    if parts[0] == "docs":
        return len(parts) == 2 and parts[1] in DOCS
    return parts[0] in {".github", "backend", "frontend"}


def check_scanner(executable):
    config = Path(".gitleaks.toml").resolve()
    with tempfile.TemporaryDirectory(prefix="oa-secret-check-") as directory:
        root = Path(directory)
        sample = root / "backend/tests/test_detection_corpus.py"
        sample.parent.mkdir(parents=True)
        sample.write_text("token=Fictional7654\n", encoding="utf-8")
        report = root.parent / (root.name + "-report.json")
        command = [str(Path(executable).resolve()), "dir", ".", "--config", str(config), "--redact",
                   "--no-banner", "--log-level", "error", "--report-path", str(report)]
        try:
            result = subprocess.run(command, cwd=root, capture_output=True, timeout=30, check=False)
            assert result.returncode == 0, "Exact synthetic fixture exception did not work"
            canary = hashlib.sha256(b"public-repository-canary").hexdigest()
            sample.write_text("token=ghp_" + canary[:36] + "\napi_key=" + canary + "\n", encoding="utf-8")
            (root / "outside.py").write_text("token=Fictional7654\n", encoding="utf-8")
            result = subprocess.run(command, cwd=root, capture_output=True, timeout=30, check=False)
            assert result.returncode == 1, "Secret scanner did not reject canaries"
            findings = json.loads(report.read_text(encoding="utf-8"))
            assert {item["RuleID"] for item in findings
                    if Path(item["File"]).name == sample.name} >= {
                "github-pat", "generic-api-key",
            }, "Fixture paths must still reject new credentials"
            detected = {Path(item["File"]).name for item in findings}
            assert detected == {
                "test_detection_corpus.py", "outside.py",
            }, "Fixture allowance leaked outside its exact value and path: " + repr(detected)
        finally:
            report.unlink(missing_ok=True)


def main():
    assert all(not allowed(name) for name in (
        ".env", "backend/.env.production", "docs/privacy-review-build/evidence.json",
        "scripts/capture_private.py", "backend/db.private.json", ".local-dev/state.json",
    ))
    assert all(allowed(name) for name in (
        "backend/.env.example", "frontend/src/App.tsx", "docs/DEVELOPMENT.md", "LICENSE",
    ))
    files = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")[:-1]
    unexpected = [name for name in files if not allowed(name)]
    assert not unexpected, "Non-public release paths are tracked: " + ", ".join(unexpected)
    assert ROOT_FILES.issubset(files), "Required public root documents are missing"
    check_scanner(sys.argv[1])
    print(f"Public file boundaries and secret-scan isolation passed ({len(files)} tracked files).")


if __name__ == "__main__":
    main()
