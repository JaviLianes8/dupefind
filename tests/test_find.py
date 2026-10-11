from __future__ import annotations

from pathlib import Path

from dupefind import find_duplicates, iter_duplicates


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_identical_files_are_grouped_together(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.bin", b"hello world")
    b = _write(tmp_path / "b.bin", b"hello world")

    groups = find_duplicates(tmp_path)

    assert len(groups) == 1
    (paths,) = groups.values()
    assert sorted(paths) == sorted([a, b])


def test_unique_files_are_not_grouped(tmp_path: Path) -> None:
    _write(tmp_path / "a.bin", b"first")
    _write(tmp_path / "b.bin", b"second longer content")

    assert find_duplicates(tmp_path) == {}


def test_same_size_different_content_is_separated(tmp_path: Path) -> None:
    _write(tmp_path / "a.bin", b"aaaa")
    _write(tmp_path / "b.bin", b"bbbb")

    assert find_duplicates(tmp_path) == {}


def test_empty_directory_has_no_duplicates(tmp_path: Path) -> None:
    assert find_duplicates(tmp_path) == {}


def test_duplicates_are_found_across_nested_directories(tmp_path: Path) -> None:
    deep = tmp_path / "one" / "two"
    deep.mkdir(parents=True)
    a = _write(tmp_path / "top.bin", b"shared payload")
    b = _write(deep / "buried.bin", b"shared payload")

    (paths,) = find_duplicates(tmp_path).values()

    assert sorted(paths) == sorted([a, b])


def test_empty_files_are_duplicates_of_each_other(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.empty", b"")
    b = _write(tmp_path / "b.empty", b"")

    (paths,) = find_duplicates(tmp_path).values()

    assert sorted(paths) == sorted([a, b])


def test_keys_are_the_shared_full_hash(tmp_path: Path) -> None:
    _write(tmp_path / "a.bin", b"keyed by hash")
    _write(tmp_path / "b.bin", b"keyed by hash")

    (digest,) = find_duplicates(tmp_path)

    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


def test_three_way_duplicate_groups_all_paths(tmp_path: Path) -> None:
    paths = [_write(tmp_path / f"c{i}.bin", b"same") for i in range(3)]

    (found,) = find_duplicates(tmp_path).values()

    assert sorted(found) == sorted(paths)


def test_iter_duplicates_streams_matching_groups(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.bin", b"stream me")
    b = _write(tmp_path / "b.bin", b"stream me")
    _write(tmp_path / "lonely.bin", b"no twin here")

    results = list(iter_duplicates(tmp_path))

    assert len(results) == 1
    digest, paths = results[0]
    assert isinstance(digest, str)
    assert sorted(paths) == sorted([a, b])


def test_reading_leaves_files_untouched(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.bin", b"unchanged content")
    b = _write(tmp_path / "b.bin", b"unchanged content")

    find_duplicates(tmp_path)

    assert a.read_bytes() == b"unchanged content"
    assert b.read_bytes() == b"unchanged content"
    assert {p.name for p in tmp_path.iterdir()} == {"a.bin", "b.bin"}


def test_accepts_a_string_path(tmp_path: Path) -> None:
    _write(tmp_path / "a.bin", b"as string")
    _write(tmp_path / "b.bin", b"as string")

    assert len(find_duplicates(str(tmp_path))) == 1
