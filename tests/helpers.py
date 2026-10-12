"""Builders for real temporary trees: files, hard links, junctions and symlinks."""

from __future__ import annotations

import getpass
import hashlib
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from dupefind import DuplicateGroup


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def junction(link: Path, target: Path) -> Path:
    """Create a Windows directory junction, or skip the test elsewhere."""
    if sys.platform != "win32":
        pytest.skip("junctions exist only on Windows")
    import _winapi

    _winapi.CreateJunction(str(target), str(link))
    return link


def symlink(link: Path, target: Path) -> Path:
    """Create a symlink, or skip when the platform or account does not allow it."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not permitted here: {exc}")
    return link


@contextmanager
def unreadable(path: Path) -> Iterator[None]:
    """Make ``path`` unreadable for the current user for the duration of the block."""
    if sys.platform == "win32":
        user = os.environ.get("USERNAME") or getpass.getuser()
        subprocess.run(
            ["icacls", str(path), "/deny", f"{user}:(RD)"], check=True, capture_output=True
        )
        try:
            yield
        finally:
            subprocess.run(
                ["icacls", str(path), "/remove:d", user], check=True, capture_output=True
            )
    else:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root can read anything")
        mode = path.stat().st_mode
        path.chmod(0)
        try:
            yield
        finally:
            path.chmod(mode)


def oracle(*roots: Path, hardlinks: bool = False) -> set[frozenset[frozenset[str]]]:
    """Brute force: hash every regular file in full and group equal contents.

    Links are not followed. Each element of a group is the set of names of one file:
    all its hard links, or just one name when ``hardlinks`` is true.
    """
    names: dict[object, list[str]] = defaultdict(list)
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _is_link(Path(dirpath, d))]
            for name in filenames:
                path = Path(dirpath, name)
                if not _is_link(path):
                    info = path.stat()
                    key = str(path) if hardlinks else (info.st_dev, info.st_ino)
                    names[key].append(str(path))
    by_digest: dict[str, list[frozenset[str]]] = defaultdict(list)
    for group in names.values():
        digest = hashlib.sha256(Path(group[0]).read_bytes()).hexdigest()
        by_digest[digest].append(frozenset(group))
    return {frozenset(files) for files in by_digest.values() if len(files) >= 2}


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    info = os.lstat(path)
    return getattr(info, "st_reparse_tag", 0) == 0xA0000003


def as_sets(groups: Iterable[DuplicateGroup]) -> set[frozenset[frozenset[str]]]:
    """Turn groups into the oracle's shape: per file, the set of all its names."""
    return {
        frozenset(frozenset(str(p) for p in (f.path, *f.aliases)) for f in group.files)
        for group in groups
    }
