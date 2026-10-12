"""ScanOptions: validation, algorithms, size bounds, empty files and globs."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from helpers import write

from dupefind import ScanOptions, find_duplicates, scan


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"algorithm": "nope"}, "unknown hash algorithm"),
        ({"algorithm": "shake_128"}, "no fixed digest size"),
        ({"partial_size": 0}, "partial_size"),
        ({"min_size": -1}, "min_size"),
        ({"min_size": 10, "max_size": 9}, "max_size"),
    ],
)
def test_invalid_options_raise_value_error(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ScanOptions(**kwargs)  # type: ignore[arg-type]


def test_a_bare_string_pattern_is_rejected() -> None:
    with pytest.raises(TypeError):
        ScanOptions(include="*.txt")  # type: ignore[arg-type]


def test_patterns_given_as_a_list_are_stored_as_a_tuple() -> None:
    assert ScanOptions(exclude=["a", "b"]).exclude == ("a", "b")  # type: ignore[arg-type]


@pytest.mark.parametrize("algorithm", ["md5", "sha1", "blake2b", "sha3_256"])
def test_digest_is_the_whole_file_hash_with_the_chosen_algorithm(
    tmp_path: Path, algorithm: str
) -> None:
    data = bytes(range(256)) * 100
    write(tmp_path / "a", data)
    write(tmp_path / "b", data)

    (group,) = scan(tmp_path, options=ScanOptions(algorithm=algorithm)).groups

    assert group.algorithm == algorithm
    assert group.digest == hashlib.new(algorithm, data).hexdigest()


def test_default_keys_stay_sha256_of_the_content(tmp_path: Path) -> None:
    write(tmp_path / "a", b"compatible")
    write(tmp_path / "b", b"compatible")

    assert list(find_duplicates(tmp_path)) == [hashlib.sha256(b"compatible").hexdigest()]


def test_min_and_max_size_are_inclusive(tmp_path: Path) -> None:
    for size in (1, 5, 9):
        write(tmp_path / f"a{size}", b"x" * size)
        write(tmp_path / f"b{size}", b"x" * size)

    groups = scan(tmp_path, options=ScanOptions(min_size=5, max_size=9)).groups

    assert sorted(group.size for group in groups) == [5, 9]


def test_empty_files_can_be_left_out(tmp_path: Path) -> None:
    write(tmp_path / "a", b"")
    write(tmp_path / "b", b"")

    assert len(scan(tmp_path).groups) == 1
    assert scan(tmp_path, options=ScanOptions(include_empty=False)).groups == []
    assert scan(tmp_path, options=ScanOptions(min_size=1)).groups == []


def test_include_keeps_only_matching_names(tmp_path: Path) -> None:
    write(tmp_path / "a.jpg", b"img")
    write(tmp_path / "b.jpg", b"img")
    write(tmp_path / "c.txt", b"img")

    (group,) = scan(tmp_path, options=ScanOptions(include=("*.jpg",))).groups

    assert [p.name for p in group.paths] == ["a.jpg", "b.jpg"]


def test_exclude_prunes_directories_and_files(tmp_path: Path) -> None:
    write(tmp_path / ".git" / "objects" / "x", b"same")
    write(tmp_path / "keep" / "x", b"same")
    write(tmp_path / "keep" / "x.tmp", b"same")
    write(tmp_path / "y", b"same")

    options = ScanOptions(exclude=(".git", "*.tmp"))
    (group,) = scan(tmp_path, options=options).groups

    assert group.paths == [tmp_path / "keep" / "x", tmp_path / "y"]


def test_pattern_with_a_slash_matches_the_relative_path(tmp_path: Path) -> None:
    write(tmp_path / "photos" / "raw" / "a", b"same")
    write(tmp_path / "photos" / "a", b"same")
    write(tmp_path / "raw" / "a", b"same")

    (group,) = scan(tmp_path, options=ScanOptions(exclude=("photos/raw",))).groups

    assert group.paths == [tmp_path / "photos" / "a", tmp_path / "raw" / "a"]


def test_files_that_differ_only_in_the_last_byte_are_not_duplicates(tmp_path: Path) -> None:
    body = b"z" * 100_000
    write(tmp_path / "a", body + b"1")
    write(tmp_path / "b", body + b"2")

    report = scan(tmp_path)

    assert report.groups == []
    assert report.stats.full_hashed == 2


def test_small_files_are_read_once(tmp_path: Path) -> None:
    write(tmp_path / "a", b"tiny")
    write(tmp_path / "b", b"tiny")

    report = scan(tmp_path)

    assert report.stats.partial_hashed == 2
    assert report.stats.full_hashed == 0
    assert report.stats.bytes_read == 8


def test_different_prefixes_stop_before_the_full_read(tmp_path: Path) -> None:
    write(tmp_path / "a", b"A" + b"z" * 50_000)
    write(tmp_path / "b", b"B" + b"z" * 50_000)

    report = scan(tmp_path, options=ScanOptions(partial_size=16))

    assert report.stats.full_hashed == 0
    assert report.stats.bytes_read == 32
