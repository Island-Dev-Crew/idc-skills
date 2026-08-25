"""Objectives 7-14: path identity, launcher/verifier pins, staged snapshot,
git/env hardening, fail-closed behavior, consumer/checkpoint interplay."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from harness import (  # noqa: F401
    RESULTS, commit_all, content_runner_for, expect_pass, expect_reject,
    fresh, git, make_fixture, read_checkpoint, record,
)


def run_paths() -> None:
    G = "obj7-paths"
    # 7a config is a symlink
    fx = make_fixture()
    real = fx.runtime / "real-config.json"
    fx.config.rename(real)
    os.symlink(real, fx.config)
    expect_reject(G, "7a config path is a symlink", "refusing symlinked", fx.verify)
    # 7b config hard-linked (nlink 2)
    fx = make_fixture()
    os.link(fx.config, fx.runtime / "config-copy.json")
    expect_reject(G, "7b config is hard-linked", "hard-linked", fx.verify)
    # 7c launcher reached through a parent symlink into the repo
    fx = make_fixture()
    alias = fx.root / "alias-outside"
    os.symlink(fx.repo / "bootstrap", alias)
    expect_reject(G, "7c launcher path resolves into repo via parent symlink",
                  "outside the repository",
                  lambda: fx.verify(launcher_path=alias / "idc_verify_fresh.py"))
    # 7d checkpoint parent is a symlink
    fx = make_fixture()
    realdir = fx.runtime / "realstate"
    realdir.mkdir()
    os.symlink(realdir, fx.checkpoint.parent)  # state/ does not exist yet
    expect_reject(G, "7d checkpoint parent is a symlink", "real directory", fx.verify)
    # 7e repo_root passed through a symlink (should resolve and still verify)
    fx = make_fixture()
    repo_alias = fx.root / "repo-alias"
    os.symlink(fx.repo, repo_alias)
    report = expect_pass(G, "7e repo_root via symlink resolves to real root",
                         lambda: fresh.verify_release(
                             repo_alias, fx.config, launcher_path=fx.launcher,
                             expected_fingerprint=fx.fingerprint, now=fx.now,
                             content_runner=fx.content_runner))
    # 7f file-source indexPath is a symlink
    fx = make_fixture()
    moved = fx.trust / "index-real.json"
    fx.index.rename(moved)
    os.symlink(moved, fx.index)
    expect_reject(G, "7f index source file is a symlink", "refusing symlinked",
                  fx.verify)
    # 7g mount-alias: no privileges for bind mounts in this sandbox (uid 999);
    # _path_is_within falls back to os.path.samefile inode walk of every parent,
    # which is exactly the bind-mount alias case. Static trace only.
    record(G, "7g bind-mount alias", "UNVERIFIED",
           "uid 999 cannot mount --bind; code walk uses os.path.samefile per ancestor "
           "which is inode-based and covers mount aliases (idc_verify_fresh.py:144-160)")


def run_pins() -> None:
    G = "obj8-launcher-pin"
    # 8a installed launcher bytes differ from signed source record
    fx = make_fixture()
    fx.launcher.write_bytes(b"# attacker-modified installed launcher\n")
    expect_reject(G, "8a installed launcher bytes != signed manifest record",
                  "captured freshness launcher differs", fx.verify)
    # 8b launcher intact but index pin changed (operator signs index for other bytes)
    fx = make_fixture()
    fx.entry["launcherSHA256"] = "sha256:" + "1" * 64
    fx.write_index([fx.entry])
    fx.write_config()
    expect_reject(G, "8b index launcherSHA256 != captured launcher",
                  "release tuple", fx.verify)
    # 8c trust-order note
    record(G, "8c trust order", "INFO",
           "first fetch is authenticated by: compiled-in fingerprint constant "
           "(launcher) -> repo pubkey bound to it -> index ssh signature; launcher "
           "bytes bound by manifest record AND index pin; config+pinned python by "
           "operator/OS. Nothing fetched is trusted before signature verification.")

    G = "obj9-verifier-pin"
    # 9a captured verifier bytes differ from manifest record
    fx = make_fixture()
    fx.verifier.write_text("# rolled back verifier\n", encoding="utf-8")
    runner = mock.Mock(side_effect=AssertionError("must not execute"))
    expect_reject(G, "9a verifier bytes != manifest record (no content exec)",
                  "differs", lambda: fx.verify(content_runner=runner))
    # 9b index verifierSHA256 differs
    fx = make_fixture()
    fx.entry["verifierSHA256"] = "sha256:" + "2" * 64
    fx.write_index([fx.entry])
    fx.write_config()
    expect_reject(G, "9b index verifierSHA256 != captured verifier",
                  "release tuple", fx.verify)


def run_staged() -> None:
    G = "obj10-staged"
    # 10a live manifest mutated during content verification
    fx = make_fixture()
    original_runner = fx.content_runner

    def mutating_runner(*args):
        report = original_runner(*args)
        fx.manifest.write_text("# mutated mid-run\n", encoding="utf-8")
        return report

    expect_reject(G, "10a live manifest mutated during content verify",
                  "changed during freshness verification",
                  lambda: fx.verify(content_runner=mutating_runner))
    # 10b staged copy mutated after content verification, before consumer exec
    fx = make_fixture()

    def evil_runner(*args):
        report = original_runner(*args)
        staged = Path(args[5])
        (staged / "scripts" / "install.py").write_text("# post-verify swap\n")
        return report

    seen = {}

    def consumer(staged, handoff, config):
        seen["installer"] = (staged / "scripts" / "install.py").read_text()
        return 0

    report = expect_pass(G, "10b staged bytes swapped between verify and consumer",
                         lambda: fx.verify(content_runner=evil_runner,
                                           consumer_runner=consumer))
    if report:
        record(G, "10b-observation", "GAP-OBSERVED",
               f"consumer executed staged installer containing: {seen['installer']!r}; "
               "staged snapshot is NOT re-hashed after the content verifier runs")
    # 10c live repo drift of non-control file post-stage does not affect consumer
    fx = make_fixture()

    def mutating_runner2(*args):
        report = original_runner(*args)
        fx.installer.write_text("# live drift post-stage\n", encoding="utf-8")
        return report

    def consumer2(staged, handoff, config):
        seen["staged2"] = (staged / "scripts" / "install.py").read_text()
        return 0

    report = expect_pass(G, "10c live installer drifted post-stage; consumer unaffected",
                         lambda: fx.verify(content_runner=mutating_runner2,
                                           consumer_runner=consumer2))
    if report:
        record(G, "10c-note", "HELD",
               f"consumer saw staged bytes {seen['staged2']!r} (original signed bytes)")


def run_git_env() -> None:
    G = "obj11-git"
    # 11a hostile GIT_* env around the whole launcher call
    fx = make_fixture()
    evil_hooks = fx.trust / "evil-hooks"
    evil_hooks.mkdir()
    marker = fx.runtime / "hook-fired"
    hook = evil_hooks / "post-index-change"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    os.chmod(hook, 0o755)
    hostile = {
        "GIT_DIR": str(fx.repo / ".git"),
        "GIT_WORK_TREE": str(fx.runtime),
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": str(evil_hooks),
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_VALUE_1": str(evil_hooks / "post-index-change"),
        "GIT_EXEC_PATH": str(evil_hooks),
    }
    with mock.patch.dict(os.environ, hostile, clear=False):
        expect_pass(G, "11a hostile GIT_* env cannot influence hardened git",
                    fx.verify)
    record(G, "11a-note", "HELD" if not marker.exists() else "BYPASS",
           f"hook marker exists: {marker.exists()}; child env is built from scratch "
           "(PATH/LANG/LC_ALL/TZ only)")
    # 11b dirty worktree: tracked file modified, not committed
    fx = make_fixture()
    fx.installer.write_text("# uncommitted drift\n", encoding="utf-8")
    expect_reject(G, "11b dirty worktree (tracked drift, uncommitted)",
                  "drifted", fx.verify)
    # 11c poisoned .git/config: hooksPath, fsmonitor, alias
    fx = make_fixture()
    git(fx, "config", "core.hooksPath", str(evil_hooks))
    git(fx, "config", "core.fsmonitor", str(hook))
    git(fx, "config", "alias.rev-parse", f"!touch {marker} && git rev-parse")
    expect_pass(G, "11c poisoned .git/config neutralized", fx.verify)
    record(G, "11c-note", "HELD" if not marker.exists() else "BYPASS",
           f"marker exists: {marker.exists()}")
    # 11d gitfile .git (external gitdir) -> reject
    fx = make_fixture()
    external = fx.runtime / "ext.git"
    fx.repo.joinpath(".git").rename(external)
    fx.repo.joinpath(".git").write_text(f"gitdir: {external}\n", encoding="utf-8")
    expect_reject(G, "11d external gitdir via .git file", "Git metadata", fx.verify)
    # 11e gitlink (submodule) in tree
    fx = make_fixture()
    sub = fx.root / "subrepo"
    subprocess.run([fx.git, "init", "-q", str(sub)], check=True)
    subprocess.run([fx.git, "-C", str(sub), "-c", "user.email=a@b.c",
                    "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "s"],
                   check=True)
    subprocess.run([fx.git, "-C", str(fx.repo), "-c", "protocol.file.allow=always",
                    "submodule", "add", "-q", str(sub), "submod"], check=True)
    commit_all(fx, "add submodule")
    fx.entry["gitCommit"] = fx.commit
    fx.write_index([fx.entry])
    fx.write_config()
    expect_reject(G, "11e submodule gitlink in tree", "unsupported Git tree entry",
                  fx.verify)


def run_launcher_env() -> None:
    G = "obj12-env"
    fx = make_fixture()
    # 12b launcher process started WITHOUT -I under attacker PYTHONPATH
    evil = fx.trust / "evil-site"
    evil.mkdir()
    marker = fx.runtime / "sitecustomize-fired"
    (evil / "sitecustomize.py").write_text(
        f"open({str(marker)!r}, 'w').write('pwned')\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(evil))
    subprocess.run([sys.executable, str(fx.launcher), "--help"],
                   capture_output=True, env=env)
    without_i = marker.exists()
    marker.unlink(missing_ok=True)
    subprocess.run([sys.executable, "-I", str(fx.launcher), "--help"],
                   capture_output=True, env=env)
    with_i = marker.exists()
    record(G, "12b launcher PYTHONPATH pre-start injection",
           "CONFIRMED-DOCUMENTED" if without_i and not with_i else "CHECK",
           f"sitecustomize executed without -I: {without_i}; suppressed by -I: "
           f"{not with_i}. integrity/README.md:151-158 explicitly requires an "
           "external clean-environment wrapper with python -I -B; pre-start "
           "injection is declared outside the launcher's boundary")
    # 12c tempfile usage
    record(G, "12c temp dirs", "INFO",
           "all temp dirs via tempfile.TemporaryDirectory/mkstemp (random suffix, "
           "0700) under process TMPDIR; consumer children get redirected private "
           "TMPDIR; no predictable names")


def run_fail_closed() -> None:
    G = "obj13-fail-closed"
    fx = make_fixture()
    fx.index.unlink()
    fx.index_signature.unlink()
    # 13a offline verify -> exit 3, not ready
    code = fresh.main(["--repo-root", str(fx.repo), "--config", str(fx.config),
                       "--mode", "offline", "verify"])
    record(G, "13a offline verify exit code", "HELD" if code == 3 else "BYPASS",
           f"exit={code} (3 = freshness unverified, no readiness)")
    # 13b offline + consumer command -> refuse before running
    code = fresh.main(["--repo-root", str(fx.repo), "--config", str(fx.config),
                       "--mode", "offline", "install"])
    record(G, "13b offline consumer attempt", "HELD" if code == 2 else "BYPASS",
           f"exit={code} ('offline mode never authorizes a consumer')")
    # 13c expired index + install -> consumer never runs
    fx = make_fixture()
    fx.write_index([fx.entry], generated="2026-08-01T00:00:00Z",
                   valid_until="2026-08-02T00:00:00Z")
    fx.write_config()
    ran = {"consumer": False}

    def consumer(*a):
        ran["consumer"] = True
        return 0

    expect_reject(G, "13c expired index, consumer command", "expired",
                  lambda: fx.verify(consumer_runner=consumer))
    record(G, "13c-note", "HELD" if not ran["consumer"] else "BYPASS",
           f"consumer ran: {ran['consumer']}")
    # 13d content red -> no readiness
    fx = make_fixture()

    def red_runner(*a):
        return {"schema": "idc-skill-integrity-report/v2", "contentReady": False,
                "score": "3/5", "profile": "release", "skillsChecked": 50,
                "authority": "content-only", "release": "2.0.3",
                "manifestSequence": 1}

    expect_reject(G, "13d content verifier red", "contentReady",  # substring of msg
                  lambda: fx.verify(content_runner=red_runner))


def run_consumer_checkpoint() -> None:
    G = "obj14-consumer"
    # 14a consumer fails with exit 7: checkpoint advanced, no READY, exit 7
    fx = make_fixture()
    fx.write_index([fx.entry], sequence=2)  # force checkpoint advance from none
    fx.write_config()
    report = expect_pass(G, "14a consumer exit 7",
                         lambda: fx.verify(consumer_runner=lambda *a: 7))
    ckpt = read_checkpoint(fx)
    record(G, "14a-note",
           "HELD" if report and report.get("consumerExitCode") == 7 and ckpt
           and ckpt["indexSequence"] == 2 else "CHECK",
           f"consumerExitCode={report and report.get('consumerExitCode')}, "
           f"checkpoint after failed consumer: seq={ckpt and ckpt['indexSequence']} "
           "(advanced, not rolled back; matches integrity/README.md:240)")
    # 14b consumer raises unexpected exception mid-run
    fx = make_fixture()

    def boom(*a):
        raise RuntimeError("consumer crashed")

    try:
        fx.verify(consumer_runner=boom)
        record(G, "14b consumer raises RuntimeError", "BYPASS", "no exception")
    except fresh.FreshnessError as exc:
        record(G, "14b consumer raises RuntimeError", "HELD", f"FreshnessError: {exc}")
    except RuntimeError as exc:
        ckpt = read_checkpoint(fx)
        record(G, "14b consumer raises RuntimeError", "FAIL-CLOSED-UNCAUGHT",
               f"RuntimeError escapes verify_release ({exc}); main() would traceback "
               f"exit 1; checkpoint already advanced: {ckpt is not None}")


if __name__ == "__main__":
    run_paths()
    run_pins()
    run_staged()
    run_git_env()
    run_launcher_env()
    run_fail_closed()
    run_consumer_checkpoint()
