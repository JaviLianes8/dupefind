"""Build the wheel, install it in a throwaway venv and drive the installed script.

Slow and needs the build backend, so it runs only with DUPEFIND_E2E=1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("DUPEFIND_E2E") != "1", reason="set DUPEFIND_E2E=1 to build and install"
)


def _run(*cmd: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, check=False
    )


def test_installed_wheel_end_to_end(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    built = _run(sys.executable, "-m", "build", "--wheel", "--outdir", dist, ROOT)
    assert built.returncode == 0, built.stderr
    (wheel,) = dist.glob("dupefind-*.whl")

    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    bindir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
    python = bindir / "python"
    assert _run(python, "-m", "pip", "install", "-q", wheel).returncode == 0
    script = bindir / ("dupefind.exe" if sys.platform == "win32" else "dupefind")

    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.bin").write_bytes(b"e2e" * 2000)
    (tree / "b.bin").write_bytes(b"e2e" * 2000)
    (tree / "c.bin").write_bytes(b"unique")

    version = _run(script, "--version")
    assert version.returncode == 0 and version.stdout.startswith("dupefind ")

    report = _run(script, tree, "--json")
    assert report.returncode == 0, report.stderr
    (group,) = json.loads(report.stdout)["groups"]
    assert len(group["files"]) == 2

    dry = _run(script, tree, "--delete", "--keep", "first")
    assert "[dry-run] delete" in dry.stdout
    assert (tree / "b.bin").exists()

    applied = _run(script, tree, "--delete", "--keep", "first", "--apply")
    assert applied.returncode == 0
    assert sorted(p.name for p in tree.iterdir()) == ["a.bin", "c.bin"]

    bad = _run(script, tree / "missing")
    assert bad.returncode == 1 and "error:" in bad.stderr and bad.stdout == ""

    typed = _run(
        python,
        "-c",
        "import dupefind, importlib.resources as r; "
        "print(r.files('dupefind').joinpath('py.typed').is_file())",
    )
    assert typed.stdout.strip() == "True"
