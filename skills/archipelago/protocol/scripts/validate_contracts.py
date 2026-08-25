#!/usr/bin/env python3
"""ARCHIPELAGO P1 gate-contract validator.
Usage:
  python3 scripts/validate_contracts.py                    # validate bundled examples
  python3 scripts/validate_contracts.py <artifact.json>... # validate every named artifact
Exit nonzero on any failure — suitable as a mission-control gate command (shell-agnostic, no &&).
"""
import datetime as dt
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = {
    "idea.lock": "idea.lock.schema.json",
    "plan.lock": "plan.lock.schema.json",
    "build-instantiation-brief": "build-instantiation-brief.schema.json",
    "evidence-bundle": "evidence-bundle.schema.json",
    "bundle": "evidence-bundle.schema.json",
    "state.extension": "state.extension.schema.json",
    "state": "state.extension.schema.json",
}

def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value

def load_json(path):
    return json.loads(path.read_text(), object_pairs_hook=_reject_duplicate_keys)

def schema_for(path: Path):
    for key, s in MAP.items():
        if key in path.name:
            return load_json(ROOT / "schemas" / s)
    sys.exit(f"no schema mapping for {path.name}")

def _type_ok(value, expected):
    if isinstance(expected, list):
        return any(_type_ok(value, item) for item in expected)
    return {
        "null": value is None,
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in {int, float},
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(expected, False)


def _resolve(schema, reference):
    if not reference.startswith("#/"):
        raise ValueError(f"external schema reference is forbidden: {reference}")
    value = schema
    for raw in reference[2:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        value = value[key]
    return value


def _validate(rule, value, root, path="<root>"):
    errors = []
    if "$ref" in rule:
        errors.extend(_validate(_resolve(root, rule["$ref"]), value, root, path))
    for item in rule.get("allOf", []):
        errors.extend(_validate(item, value, root, path))
    if "type" in rule and not _type_ok(value, rule["type"]):
        return [f"{path}: expected {rule['type']}"]
    if "const" in rule and value != rule["const"]:
        errors.append(f"{path}: must equal {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{path}: value is outside the enum")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{path}: shorter than minLength")
        if "pattern" in rule and re.search(rule["pattern"], value) is None:
            errors.append(f"{path}: does not match required pattern")
        if rule.get("format") == "date-time":
            try:
                parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("timezone missing")
            except ValueError:
                errors.append(f"{path}: invalid date-time")
    if type(value) in {int, float}:
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in rule and value > rule["maximum"]:
            errors.append(f"{path}: above maximum")
        if "exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"]:
            errors.append(f"{path}: not above exclusiveMinimum")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            errors.append(f"{path}: fewer than minItems")
        item_rule = rule.get("items")
        if isinstance(item_rule, dict):
            for index, item in enumerate(value):
                errors.extend(_validate(item_rule, item, root, f"{path}/{index}"))
    if isinstance(value, dict):
        properties = rule.get("properties", {})
        for required in rule.get("required", []):
            if required not in value:
                errors.append(f"{path}: missing required property {required!r}")
        if rule.get("additionalProperties") is False:
            for unknown in sorted(set(value) - set(properties)):
                errors.append(f"{path}: unknown property {unknown!r}")
        for key, item in value.items():
            if key in properties:
                errors.extend(_validate(properties[key], item, root, f"{path}/{key}"))
    return errors


def check(schema, inst, label):
    errs = _validate(schema, inst, schema)
    if errs:
        print(f"[FAIL] {label}")
        for e in errs:
            print(f"   - {e}")
        return False
    print(f"[PASS] {label}")
    return True

if len(sys.argv) > 1:
    ok = True
    for raw in sys.argv[1:]:
        p = Path(raw)
        try:
            ok &= check(schema_for(p), load_json(p), p.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            print(f"[FAIL] {p.name}\n   - {exc}")
            ok = False
    sys.exit(0 if ok else 1)

ok = True
for ex in sorted((ROOT / "examples").glob("*.json")):
    try:
        ok &= check(schema_for(ex), load_json(ex), f"examples/{ex.name}")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"[FAIL] examples/{ex.name}\n   - {exc}")
        ok = False
sys.exit(0 if ok else 1)
