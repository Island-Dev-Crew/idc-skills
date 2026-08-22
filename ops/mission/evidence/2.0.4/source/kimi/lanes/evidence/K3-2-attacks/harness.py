"""K3-2 freshness/anti-rollback attack harness (disposable, /tmp only).

Reuses the repo's own FreshnessFixture (throwaway ed25519 key, local file
source, pinned executables = real python/git/ssh-keygen) to drive the EXTERNAL
launcher bootstrap/idc_verify_fresh.py against crafted index/checkpoint/
config/path fixtures. No network except explicit 127.0.0.1 mocks.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

sys.path.insert(0, "/tmp/K3-2/repo")
from tests.test_freshness import FreshnessFixture, _sign  # noqa: E402
from bootstrap import idc_verify_fresh as fresh  # noqa: E402

RESULTS: list[dict[str, str]] = []


def record(group: str, name: str, outcome: str, detail: str = "") -> None:
    RESULTS.append({"group": group, "name": name, "outcome": outcome, "detail": detail})
    print(f"[{outcome}] {group}/{name}: {detail[:300]}", flush=True)


def expect_reject(group: str, name: str, needle: str, fn) -> str:
    """Run fn(); PASS detail if FreshnessError containing needle, else FAIL."""
    try:
        result = fn()
    except fresh.FreshnessError as exc:
        if needle in str(exc):
            record(group, name, "HELD", f"rejected as expected: {exc}")
            return "HELD"
        record(group, name, "UNEXPECTED-REJECT", f"wrong error: {exc}")
        return "UNEXPECTED"
    except Exception as exc:  # noqa: BLE001
        record(group, name, "ERROR", f"{type(exc).__name__}: {exc}")
        return "ERROR"
    record(group, name, "BYPASS", f"call succeeded, report={str(result)[:200]}")
    return "BYPASS"


def expect_pass(group: str, name: str, fn) -> object:
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001
        record(group, name, "ERROR", f"{type(exc).__name__}: {exc}")
        return None
    record(group, name, "PASS", f"accepted, report={str(result)[:200]}")
    return result


def make_fixture() -> FreshnessFixture:
    root = Path(tempfile.mkdtemp(prefix="k32-fix-")) / "f"
    root.mkdir()
    return FreshnessFixture(root)


def git(fixture: FreshnessFixture, *args: str) -> str:
    return subprocess.run(
        [fixture.git, "-C", str(fixture.repo), *args],
        text=True, capture_output=True, check=True,
    ).stdout.strip()


def commit_all(fixture: FreshnessFixture, message: str) -> str:
    git(fixture, "add", ".")
    git(fixture, "commit", "-q", "-m", message)
    fixture.commit = git(fixture, "rev-parse", "HEAD")
    return fixture.commit


def set_release(fixture: FreshnessFixture, release: str, sequence: int) -> None:
    """Re-release the fixture repo as an OLDER (or newer) signed release."""
    manifest = fresh.load_canonical_json(
        fixture.manifest.read_bytes(), "manifest", fresh.MAX_MANIFEST_BYTES
    )
    manifest["release"] = release
    manifest["manifestSequence"] = sequence
    fixture.manifest.write_bytes(fresh.canonical_bytes(manifest))
    fixture.manifest_signature = _sign(
        fixture.manifest, fixture.private_key, fresh.MANIFEST_NAMESPACE
    )
    commit_all(fixture, f"release {release} seq {sequence}")
    fixture.entry = {
        "release": release,
        "manifestSequence": sequence,
        "manifestSHA256": fresh.sha256_bytes(fixture.manifest.read_bytes()),
        "verifierSHA256": fresh.sha256_bytes(fixture.verifier.read_bytes()),
        "launcherSHA256": fresh.sha256_bytes(fixture.launcher.read_bytes()),
        "gitCommit": fixture.commit,
    }
    fixture.write_index([fixture.entry])
    fixture.write_config()


def content_runner_for(release: str, sequence: int):
    def runner(*args: object) -> dict[str, object]:
        return {
            "schema": "idc-skill-integrity-report/v2",
            "contentReady": True,
            "score": "5/5",
            "profile": "release",
            "skillsChecked": 50,
            "authority": "content-only",
            "release": release,
            "manifestSequence": sequence,
        }
    return runner


def read_checkpoint(fixture: FreshnessFixture) -> dict[str, object] | None:
    if not fixture.checkpoint.exists():
        return None
    return fresh.load_canonical_json(
        fixture.checkpoint.read_bytes(), "checkpoint", fresh.MAX_CHECKPOINT_BYTES
    )


def write_raw_checkpoint(fixture: FreshnessFixture, value: dict[str, object]) -> None:
    fixture.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    fixture.checkpoint.write_bytes(fresh.canonical_bytes(value))
