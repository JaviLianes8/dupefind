"""Hard links, junctions, symlinks and overlapping roots on a real filesystem."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from helpers import junction, symlink, write

from dupefind import ScanOptions, find_duplicates, scan


def test_hard_links_alone_are_not_duplicates(tmp_path: Path) -> None:
    original = write(tmp_path / "a.bin", b"linked content")
    os.link(original, tmp_path / "b.bin")

    report = scan(tmp_path)

    assert report.groups == []
    assert find_duplicates(tmp_path) == {}


def test_hard_links_become_aliases_of_one_file(tmp_path: Path) -> None:
    original = write(tmp_path / "a.bin", b"payload")
    os.link(original, tmp_path / "b.bin")
    copy = write(tmp_path / "c.bin", b"payload")

    (group,) = scan(tmp_path).groups

    assert group.paths == [original, copy]
    assert group.files[0].aliases == (tmp_path / "b.bin",)
    assert group.files[1].aliases == ()
    assert group.wasted_bytes == len(b"payload")


def test_hardlinks_option_reports_every_name(tmp_path: Path) -> None:
    original = write(tmp_path / "a.bin", b"linked content")
    os.link(original, tmp_path / "b.bin")

    (group,) = scan(tmp_path, options=ScanOptions(hardlinks=True)).groups

    assert group.paths == [tmp_path / "a.bin", tmp_path / "b.bin"]


def test_junction_is_not_followed_by_default(tmp_path: Path) -> None:
    real = tmp_path / "real"
    write(real / "data.bin", b"inside the junction target")
    junction(tmp_path / "jump", real)

    assert scan(tmp_path).groups == []
    assert scan(tmp_path, options=ScanOptions(hardlinks=True)).groups == []


def test_followed_junction_never_lists_a_file_as_its_own_copy(tmp_path: Path) -> None:
    real = tmp_path / "real"
    write(real / "data.bin", b"inside the junction target")
    junction(tmp_path / "jump", real)

    options = ScanOptions(follow_symlinks=True, hardlinks=True)
    assert scan(tmp_path, options=options).groups == []


def test_junction_loop_is_walked_once(tmp_path: Path) -> None:
    write(tmp_path / "a.bin", b"twin")
    write(tmp_path / "b.bin", b"twin")
    junction(tmp_path / "loop", tmp_path)

    (group,) = scan(tmp_path, options=ScanOptions(follow_symlinks=True)).groups

    assert len(group.files) == 2


def test_junction_given_as_root_is_followed(tmp_path: Path) -> None:
    real = tmp_path / "real"
    write(real / "a.bin", b"twin")
    write(real / "b.bin", b"twin")
    link = junction(tmp_path / "jump", real)

    (group,) = scan(link).groups

    assert group.paths == [link / "a.bin", link / "b.bin"]


def test_symlinked_file_is_skipped_by_default(tmp_path: Path) -> None:
    target = write(tmp_path / "target.bin", b"pointed at")
    symlink(tmp_path / "link.bin", target)

    assert scan(tmp_path).groups == []
    assert scan(tmp_path, options=ScanOptions(hardlinks=True)).groups == []


def test_followed_symlink_to_a_file_is_the_same_file(tmp_path: Path) -> None:
    target = write(tmp_path / "target.bin", b"pointed at")
    symlink(tmp_path / "link.bin", target)

    options = ScanOptions(follow_symlinks=True, hardlinks=True)
    assert scan(tmp_path, options=options).groups == []


def test_symlinked_directory_is_not_walked_by_default(tmp_path: Path) -> None:
    write(tmp_path / "real" / "a.bin", b"once")
    write(tmp_path / "other.bin", b"once")
    symlink(tmp_path / "alias", tmp_path / "real")

    (group,) = scan(tmp_path).groups

    assert group.paths == [tmp_path / "other.bin", tmp_path / "real" / "a.bin"]


def test_same_root_twice_is_scanned_once(tmp_path: Path) -> None:
    write(tmp_path / "solo.bin", b"only one")

    options = ScanOptions(hardlinks=True)
    assert scan(tmp_path, tmp_path, options=options).groups == []
    assert scan(tmp_path, tmp_path / "solo.bin", options=options).groups == []


def test_nested_roots_do_not_double_count(tmp_path: Path) -> None:
    write(tmp_path / "sub" / "a.bin", b"x" * 10)
    write(tmp_path / "b.bin", b"x" * 10)

    (group,) = scan(tmp_path / "sub", tmp_path).groups

    assert len(group.files) == 2


@pytest.mark.skipif(sys.platform != "win32", reason="needs a case-insensitive filesystem")
def test_root_spelled_in_another_case_is_the_same_tree(tmp_path: Path) -> None:
    write(tmp_path / "Tree" / "solo.bin", b"only one")
    upper = Path(str(tmp_path / "Tree").upper())

    options = ScanOptions(hardlinks=True)
    assert scan(tmp_path / "Tree", upper, options=options).groups == []
