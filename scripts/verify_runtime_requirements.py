#!/usr/bin/env python3
"""Validate the signed Forge runtime contract and the active Python floor."""

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA = "idc-runtime-requirements/v1"
VERSION_RE = re.compile(r"([0-9]+)\.([0-9]+)\Z")


class RuntimeRequirementError(RuntimeError):
    pass


def _exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeRequirementError("%s keys differ" % label)


def _version(value, label):
    if not isinstance(value, str):
        raise RuntimeRequirementError("%s must be a version string" % label)
    match = VERSION_RE.fullmatch(value)
    if match is None:
        raise RuntimeRequirementError("%s must be major.minor" % label)
    return int(match.group(1)), int(match.group(2))


def validate_contract(data, current_python):
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeRequirementError("invalid runtime requirements: %s" % exc) from exc
    _exact_keys(value, {"schema", "python", "bash", "platforms"}, "runtime contract")
    if value["schema"] != SCHEMA:
        raise RuntimeRequirementError("runtime contract schema differs")
    _exact_keys(value["python"], {"minimum", "tested"}, "python requirement")
    _exact_keys(value["bash"], {"minimum", "tested"}, "bash requirement")
    _exact_keys(value["platforms"], {"macos", "windows"}, "platform requirement")
    python_minimum = _version(value["python"]["minimum"], "python.minimum")
    bash_minimum = _version(value["bash"]["minimum"], "bash.minimum")
    for runtime in ("python", "bash"):
        tested = value[runtime]["tested"]
        if not isinstance(tested, list) or not tested:
            raise RuntimeRequirementError("%s.tested must be a non-empty array" % runtime)
        parsed = [_version(item, "%s.tested" % runtime) for item in tested]
        if parsed != sorted(set(parsed)):
            raise RuntimeRequirementError("%s.tested must be unique and sorted" % runtime)
    if python_minimum < (3, 10):
        raise RuntimeRequirementError("the signed Python floor may not be below 3.10")
    if bash_minimum < (3, 2):
        raise RuntimeRequirementError("the signed Bash floor may not be below 3.2")
    if tuple(current_python[:2]) < python_minimum:
        raise RuntimeRequirementError(
            "Python %d.%d is below the signed minimum %d.%d"
            % (current_python[0], current_python[1], python_minimum[0], python_minimum[1])
        )
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "runtime-requirements.json",
    )
    args = parser.parse_args(argv)
    try:
        validate_contract(args.contract.read_bytes(), sys.version_info)
    except (OSError, RuntimeRequirementError) as exc:
        print("RUNTIME REFUSED - %s" % exc, file=sys.stderr)
        return 2
    print("RUNTIME OK - Python %d.%d meets signed floor" % sys.version_info[:2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
