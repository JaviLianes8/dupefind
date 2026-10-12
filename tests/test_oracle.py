"""Seeded random trees compared with a brute-force full-hash oracle."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest
from helpers import as_sets, oracle, write

from dupefind import ScanOptions, apply_actions, plan_actions, scan


def _random_tree(root: Path, seed: int) -> None:
    rng = random.Random(seed)
    blobs = [rng.randbytes(rng.choice([0, 1, 7, 4095, 4096, 4097, 9000])) for _ in range(8)]
    # Near twins: same size and prefix, different last byte.
    blobs += [blob[:-1] + bytes([blob[-1] ^ 1]) for blob in blobs if len(blob) > 4096]
    dirs = [root / f"d{i}" / f"e{rng.randrange(3)}" for i in range(4)] + [root]
    made: list[Path] = []
    for index in range(40):
        path = write(rng.choice(dirs) / f"f{index}.bin", rng.choice(blobs))
        made.append(path)
    for index in range(6):
        os.link(rng.choice(made), rng.choice(dirs) / f"h{index}.bin")
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(root / "d0"), str(root / "j0"))


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("hardlinks", [False, True])
def test_scan_matches_the_brute_force_oracle(tmp_path: Path, seed: int, hardlinks: bool) -> None:
    _random_tree(tmp_path, seed)

    report = scan(tmp_path, options=ScanOptions(hardlinks=hardlinks, partial_size=4096))

    assert report.issues == []
    assert as_sets(report.groups) == oracle(tmp_path, hardlinks=hardlinks)


@pytest.mark.parametrize("seed", range(4))
def test_partial_size_never_changes_the_verdict(tmp_path: Path, seed: int) -> None:
    _random_tree(tmp_path, seed)
    expected = oracle(tmp_path)

    for partial in (1, 64, 4096, 1 << 20):
        groups = scan(tmp_path, options=ScanOptions(partial_size=partial)).groups
        assert as_sets(groups) == expected


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_actions_keep_every_distinct_content(tmp_path: Path, seed: int, action: str) -> None:
    _random_tree(tmp_path, seed)
    contents = {p.read_bytes() for p in tmp_path.rglob("*.bin")}

    plan = plan_actions(scan(tmp_path).groups, action=action, keep="newest")  # type: ignore[arg-type]
    results = apply_actions(plan, dry_run=False)

    assert {r.status for r in results} <= {"done"}
    assert {p.read_bytes() for p in tmp_path.rglob("*.bin")} == contents
    assert scan(tmp_path).groups == []
