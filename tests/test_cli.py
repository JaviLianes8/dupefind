"""The command line tool and the JSON report, driven in process on real trees."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from helpers import write

from dupefind import SCHEMA_VERSION, report_to_dict, scan
from dupefind._cli import main, parse_size


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = main(list(argv), stdout=out)
    return code, out.getvalue()


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    return write(tmp_path / "a.bin", b"twin data"), write(tmp_path / "b.bin", b"twin data")


def test_text_report_lists_groups(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = _pair(tmp_path)

    code, out = _run(str(tmp_path))

    assert code == 0
    assert out.splitlines() == [out.splitlines()[0], str(a), str(b), ""]
    assert out.startswith("# 9 bytes x 2 files, sha256:")
    assert "1 groups, 2 files, 9 bytes reclaimable, 0 issues" in capsys.readouterr().err


def test_json_report_round_trips(tmp_path: Path) -> None:
    a, _ = _pair(tmp_path)

    code, out = _run(str(tmp_path), "--json", "--algorithm", "md5")

    doc = json.loads(out)
    assert code == 0
    assert doc["schema"] == SCHEMA_VERSION == 1
    assert doc["actions"] is None
    (group,) = doc["groups"]
    assert group["algorithm"] == "md5"
    assert group["files"][0]["path"] == str(a)
    assert doc["stats"]["groups"] == 1


def test_report_to_dict_matches_the_cli(tmp_path: Path) -> None:
    _pair(tmp_path)
    _, out = _run(str(tmp_path), "--json")

    assert json.loads(out) == report_to_dict(scan(tmp_path))


def test_delete_without_apply_is_a_dry_run(tmp_path: Path) -> None:
    a, b = _pair(tmp_path)

    code, out = _run(str(tmp_path), "--delete", "--keep", "first")

    assert code == 0
    assert f"[dry-run] delete {b} (keep {a})" in out
    assert a.exists() and b.exists()


def test_delete_with_apply_keeps_one(tmp_path: Path) -> None:
    a, b = _pair(tmp_path)

    code, out = _run(str(tmp_path), "--delete", "--keep", "first", "--apply", "--json")

    assert code == 0
    assert json.loads(out)["actions"][0]["status"] == "done"
    assert a.exists() and not b.exists()


def test_hardlink_with_apply_links_files(tmp_path: Path) -> None:
    a, b = _pair(tmp_path)

    assert _run(str(tmp_path), "--hardlink", "--apply", "-q")[0] == 0
    assert a.samefile(b)


@pytest.mark.parametrize(
    "argv",
    [
        ["--apply"],
        ["--delete", "--hardlink"],
        ["--algorithm", "nope"],
        ["--min-size", "lots"],
        ["--keep", "largest"],
    ],
)
def test_bad_arguments_exit_1_on_stderr(
    tmp_path: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), *argv])

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err


def test_missing_path_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "absent")])

    assert exc.value.code == 1
    assert "no such file or directory" in capsys.readouterr().err


def test_filters_and_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pair(tmp_path)
    write(tmp_path / "x.tmp", b"twin data")

    _, out = _run(str(tmp_path), "--exclude", "*.tmp", "--min-size", "1K", "-q")

    assert out == ""
    assert capsys.readouterr().err == ""


def test_help_shows_runnable_examples(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "dupefind . --delete --keep oldest --apply" in text
    assert "Nothing is changed unless --apply" in text


@pytest.mark.parametrize(
    ("text", "value"),
    [("0", 0), ("10", 10), ("1K", 1024), ("2m", 2 << 20), ("1GiB", 1 << 30), ("3KB", 3072)],
)
def test_parse_size(text: str, value: int) -> None:
    assert parse_size(text) == value
