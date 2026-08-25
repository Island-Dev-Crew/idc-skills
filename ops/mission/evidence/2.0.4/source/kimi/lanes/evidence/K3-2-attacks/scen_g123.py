"""Objectives 1-3: whole-tree replay, index/monotonic attacks, checkpoint attacks."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from harness import (  # noqa: F401
    RESULTS, commit_all, content_runner_for, expect_pass, expect_reject,
    fresh, make_fixture, read_checkpoint, record, set_release, git,
    write_raw_checkpoint,
)


def run() -> None:
    # ---- Objective 0 baseline: valid current release passes ----
    fx = make_fixture()
    report = expect_pass("obj0-baseline", "valid 2.0.3 release verify", fx.verify)
    assert report and report["readyToRun"] is True

    # ---- Objective 1: whole-tree replay of OLDER signed release ----
    # 1a: repo rolled back to a fully signed 2.0.2; index lists 2.0.2 as the ONLY
    # (newest) entry; first run (no checkpoint); bootstrap digest pins that index.
    fx = make_fixture()
    set_release(fx, "2.0.2", 1)
    report = expect_pass(
        "obj1-replay", "1a older-but-signed 2.0.2 as pinned current index, no checkpoint",
        lambda: fx.verify(content_runner=content_runner_for("2.0.2", 1)),
    )
    if report:
        record("obj1-replay", "1a-note",
               "BY-DESIGN", "launcher accepts older signed content when the external "
               "index (operator-pinned bootstrap digest) authorizes it; index is the authority")

    # 1b: same rollback, but a checkpoint from a NEWER index exists.
    fx = make_fixture()  # 2.0.3, seq1, index seq1
    fx.verify()  # checkpoint at indexSequence 1
    # operator moves to index seq2 (same release entry re-published)
    fx.write_index([fx.entry], sequence=2)
    fx.verify()  # checkpoint at indexSequence 2
    # attacker now replays whole old world: repo rolled back to 2.0.2 + old index seq1
    set_release(fx, "2.0.2", 1)  # rewrites index seq1 + config; checkpoint (seq2) stays
    expect_reject(
        "obj1-replay", "1b replay older index+repo against seq2 checkpoint",
        "replayed a lower indexSequence",
        lambda: fx.verify(content_runner=content_runner_for("2.0.2", 1)),
    )

    # 1c: single index attempting internal rollback: newest entry older than history.
    fx = make_fixture()
    older = dict(fx.entry, release="2.0.2", manifestSequence=1)
    newer = dict(fx.entry, release="2.0.3", manifestSequence=2)
    fx.write_index([newer, older], sequence=3)  # descending order
    fx.write_config()
    expect_reject("obj1-replay", "1c index with descending manifestSequence order",
                  "strictly increasing", fx.verify)
    # ascending but repo matches the OLDER entry, not newest
    fx.write_index([older, newer], sequence=3)
    fx.write_config()
    expect_reject("obj1-replay", "1d repo at older entry while newest is newer",
                  "release tuple", fx.verify)

    # 1e: replay with checkpoint DELETED (first-run path) using operator-pinned
    # bootstrap digest of the OLD index -> accepted (operator pin is the trust root).
    fx = make_fixture()
    old_index_bytes = fx.index.read_bytes()
    fx.verify()  # checkpoint written
    fx.checkpoint.unlink()
    # config bootstrap digest still pins the current index bytes -> replay passes
    expect_pass("obj1-replay", "1e checkpoint deleted, index==pinned bootstrap digest",
                fx.verify)
    # but replay of a DIFFERENT older index after checkpoint deletion:
    fx.write_index([dict(fx.entry, gitCommit="0" * 40)], sequence=1)
    fx.write_config()  # config bootstrap digest tracks CURRENT index file by default;
    # operator would NOT repin; emulate honest operator: restore original bootstrap digest
    fx.write_config(bootstrap_digest=fresh.sha256_bytes(old_index_bytes))
    expect_reject("obj1-replay", "1f checkpoint deleted, index != pinned bootstrap digest",
                  "first-run index", fx.verify)

    # ---- Objective 2: sequence/history attacks ----
    fx = make_fixture()
    # 2a: index entry with LOWER manifestSequence than the repo manifest
    low = dict(fx.entry, manifestSequence=1)
    manifest = fresh.load_canonical_json(fx.manifest.read_bytes(), "m", fresh.MAX_MANIFEST_BYTES)
    manifest["manifestSequence"] = 2
    fx.manifest.write_bytes(fresh.canonical_bytes(manifest))
    from tests.test_freshness import _sign
    fx.manifest_signature = _sign(fx.manifest, fx.private_key, fresh.MANIFEST_NAMESPACE)
    commit_all(fx, "bump manifest seq to 2")
    fx.entry = dict(fx.entry, manifestSequence=2,
                    manifestSHA256=fresh.sha256_bytes(fx.manifest.read_bytes()),
                    gitCommit=fx.commit)
    fx.write_index([dict(fx.entry, manifestSequence=1)])  # index says seq 1
    fx.write_config()
    expect_reject("obj2-sequence", "2a index manifestSequence below repo manifest",
                  "release tuple",
                  lambda: fx.verify(content_runner=content_runner_for("2.0.3", 2)))

    # 2b: indexSequence 0 / below config floor
    fx = make_fixture()
    fx.write_index([fx.entry], sequence=0)
    fx.write_config()
    expect_reject("obj2-sequence", "2b indexSequence=0", "integer between 1", fx.verify)
    fx = make_fixture()
    import json as _json
    cfg = _json.loads(fx.config.read_text(encoding="utf-8"))
    cfg["minimumIndexSequence"] = 2
    fx.config.write_bytes(fresh.canonical_bytes(cfg))
    expect_reject("obj2-sequence", "2b2 index below configured floor",
                  "index floor", fx.verify)

    # 2c: history truncation after two accepted releases
    fx = make_fixture()  # entry A (2.0.3 seq1) index seq1
    entry_a = dict(fx.entry)
    fx.verify()
    set_release(fx, "2.0.4", 2)  # repo now 2.0.4; index rewritten seq1 -> bump to seq2
    entry_b = dict(fx.entry)
    fx.write_index([entry_a, entry_b], sequence=2)
    fx.write_config()
    expect_pass("obj2-sequence", "2c0 advance to index seq2 [A,B]",
                lambda: fx.verify(content_runner=content_runner_for("2.0.4", 2)))
    # attacker truncates history: index seq3 lists ONLY B (still matches repo!)
    fx.write_index([entry_b], sequence=3)
    fx.write_config()
    expect_reject("obj2-sequence", "2c1 removed prior release from index history",
                  "rewrote or removed accepted history",
                  lambda: fx.verify(content_runner=content_runner_for("2.0.4", 2)))
    # 2d: entry reorder within index
    fx = make_fixture()
    a = dict(fx.entry, release="2.0.2", manifestSequence=1)
    b = dict(fx.entry, release="2.0.3", manifestSequence=2)
    fx.write_index([b, a], sequence=2)
    fx.write_config()
    expect_reject("obj2-sequence", "2d entry reorder", "strictly increasing", fx.verify)
    # 2e: duplicate sequence / duplicate release name
    fx.write_index([a, dict(a, gitCommit="1" * 40)], sequence=2)
    fx.write_config()
    expect_reject("obj2-sequence", "2e1 duplicate manifestSequence",
                  "strictly increasing", fx.verify)
    fx.write_index([a, dict(a, manifestSequence=2)], sequence=2)
    fx.write_config()
    expect_reject("obj2-sequence", "2e2 duplicate release name",
                  "unique release names", fx.verify)

    # ---- Objective 3: equivocation + checkpoint rollback/forward ----
    # 3a: same indexSequence, different digest (end-to-end)
    fx = make_fixture()
    fx.verify()
    fx.write_index([fx.entry], sequence=1, generated="2026-08-19T11:00:01Z")
    # NOTE: config bootstrap digest irrelevant now (checkpoint exists)
    expect_reject("obj3-checkpoint", "3a same-sequence different-digest equivocation",
                  "equivocation", fx.verify)
    # 3b: checkpoint rolled BACK to seq1 snapshot, current index seq2 re-presented
    fx = make_fixture()
    fx.verify()
    ckpt1 = fx.checkpoint.read_bytes()
    fx.write_index([fx.entry], sequence=2)
    fx.verify()  # checkpoint now seq2
    fx.checkpoint.write_bytes(ckpt1)  # roll checkpoint back to seq1
    expect_pass("obj3-checkpoint", "3b1 rolled-back checkpoint + newer index re-accepted",
                fx.verify)
    record("obj3-checkpoint", "3b1-note", "BY-DESIGN",
           "restoring an older checkpoint only re-accepts already-signed newer indexes; "
           "it cannot authorize anything older")
    # now present the OLD seq1 index against rolled-back... roll back again then old index
    fx.checkpoint.write_bytes(ckpt1)
    fx.write_index([fx.entry], sequence=1, generated="2026-08-19T11:00:02Z")
    expect_reject("obj3-checkpoint", "3b2 rolled-back checkpoint + same-seq new digest",
                  "equivocation", fx.verify)
    # 3c: checkpoint rolled FORWARD beyond any real index (attacker-crafted, seq 99)
    fx = make_fixture()
    fx.verify()
    write_raw_checkpoint(fx, {
        "schema": fresh.CHECKPOINT_SCHEMA,
        "indexSequence": 99,
        "indexSHA256": fresh.sha256_bytes(fx.index.read_bytes()),
        "releases": [fx.entry],
    })
    expect_reject("obj3-checkpoint", "3c forward-rolled checkpoint blocks current index",
                  "replayed a lower indexSequence", fx.verify)
    record("obj3-checkpoint", "3c-note", "AVAILABILITY-ONLY",
           "crafting a forward checkpoint requires write access to the protected state "
           "dir; effect is denial of service, not rollback")
    # 3d: checkpoint file symlink / hardlink / dangling symlink
    fx = make_fixture()
    fx.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    target = fx.runtime / "elsewhere.json"
    target.write_bytes(fx.index.read_bytes())
    os.symlink(target, fx.checkpoint)
    expect_reject("obj3-checkpoint", "3d1 checkpoint is a symlink",
                  "symlink", fx.verify)
    fx.checkpoint.unlink()
    os.link(target, fx.checkpoint)  # hardlink => nlink 2
    expect_reject("obj3-checkpoint", "3d2 checkpoint is hard-linked",
                  "hard-linked", fx.verify)
    fx.checkpoint.unlink()
    target.unlink()
    os.symlink(target, fx.checkpoint)  # dangling
    expect_reject("obj3-checkpoint", "3d3 checkpoint dangling symlink",
                  "dangling symlink", fx.verify)


if __name__ == "__main__":
    run()
