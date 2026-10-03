"""Exercise the real Vite build's public-environment boundary with synthetic values."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.example.invalid/api/v1"


def main():
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm, "npm is required"
    base = {
        key: value for key, value in os.environ.items() if not key.startswith("VITE_")
    }
    base["VERCEL"] = "1"
    invalid = [
        ("missing API URL", {}),
        ("relative API URL", {"VITE_API_BASE_URL": "/api/v1"}),
        ("HTTP API URL", {"VITE_API_BASE_URL": "http://api.example.invalid/api/v1"}),
        (
            "unexpected API path",
            {"VITE_API_BASE_URL": "https://api.example.invalid/other/api/v1"},
        ),
        (
            "URL credentials",
            {
                "VITE_API_BASE_URL": "https://synthetic:synthetic@api.example.invalid/api/v1"
            },
        ),
        ("URL query", {"VITE_API_BASE_URL": API + "?secret=synthetic"}),
        (
            "extra public variable",
            {
                "VITE_API_BASE_URL": API,
                "VITE_SYNTHETIC_SECRET": "synthetic-secret-canary",
            },
        ),
        (
            "prefixed metadata variable",
            {
                "VITE_API_BASE_URL": API,
                "VITE_VERCEL_SYNTHETIC_SECRET": "synthetic-secret-canary",
            },
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="oa-config-") as output:
        command = [npm, "exec", "--", "vite", "build", "--outDir", output]
        for name, values in invalid:
            result = subprocess.run(
                command,
                cwd=ROOT / "frontend",
                env={**base, **values},
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert result.returncode != 0, f"Build accepted {name}"
            assert "synthetic-secret-canary" not in result.stdout + result.stderr
        result = subprocess.run(
            command,
            cwd=ROOT / "frontend",
            env={
                **base,
                "VITE_API_BASE_URL": API,
                "VITE_VERCEL_OBSERVABILITY_CLIENT_CONFIG": "synthetic-provider-secret-canary",
            },
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, "Valid production build failed"
        assert (
            "https://api.example.invalid" in (Path(output) / "index.html").read_text()
        )
        assert all(
            "synthetic-provider-secret-canary" not in asset.read_text(encoding="utf-8")
            for asset in Path(output).rglob("*.js")
        )
    print(
        "Passed 9 real Vite production-configuration checks; no supplied secret values printed."
    )


if __name__ == "__main__":
    main()
