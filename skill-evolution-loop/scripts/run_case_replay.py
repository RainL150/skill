#!/usr/bin/env python3
"""Replay deterministic routing metadata cases for a skill.

This does not invoke a model. It checks whether trigger/no-trigger case terms are
represented in the skill's metadata and therefore catches obvious routing gaps.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter_text(skill_md: Path) -> str:
    text = read_text(skill_md)
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"{skill_md} has no frontmatter")
    return re.sub(r"\s+", " ", match.group(1)).lower()


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw = read_text(path).strip()
    if not raw:
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("case JSON must be a list")
    return data


def contains_any(haystack: str, terms: list[str]) -> bool:
    return any(term.lower() in haystack for term in terms)


def validate_case(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("id", "prompt", "expect"):
        if field not in case:
            errors.append(f"missing {field}")
    if case.get("expect") not in ("trigger", "no-trigger"):
        errors.append("expect must be 'trigger' or 'no-trigger'")
    for list_field in ("trigger_terms", "avoid_terms"):
        if list_field in case and not isinstance(case[list_field], list):
            errors.append(f"{list_field} must be a list")
    return errors


def evaluate_case(case: dict[str, Any], metadata: str) -> tuple[bool, str]:
    expect = case["expect"]
    if expect == "trigger":
        terms = [str(term) for term in case.get("trigger_terms", [])]
        if not terms:
            return False, "trigger case has no trigger_terms"
        if contains_any(metadata, terms):
            return True, "at least one trigger_term appears in skill metadata"
        return False, "none of trigger_terms appear in skill metadata"

    avoid_terms = [str(term) for term in case.get("avoid_terms", [])]
    if not avoid_terms:
        return True, "no avoid_terms supplied; schema-only no-trigger case"
    if contains_any(metadata, avoid_terms):
        return False, "at least one avoid_term appears in skill metadata"
    return True, "no avoid_terms appear in skill metadata"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path, help="Path to skill directory")
    parser.add_argument("cases", type=Path, help="JSON or JSONL cases")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    skill_md = args.skill_dir / "SKILL.md"
    if not skill_md.exists():
        print(f"ERROR: missing {skill_md}", file=sys.stderr)
        return 1

    metadata = parse_frontmatter_text(skill_md)
    cases = load_cases(args.cases)
    rows: list[dict[str, Any]] = []
    failures = 0

    for case in cases:
        case_errors = validate_case(case)
        if case_errors:
            passed = False
            reason = "; ".join(case_errors)
        else:
            passed, reason = evaluate_case(case, metadata)
        if not passed:
            failures += 1
        rows.append({
            "id": case.get("id", "<missing>"),
            "expect": case.get("expect", "<missing>"),
            "pass": passed,
            "reason": reason,
        })

    result = {
        "skill_dir": str(args.skill_dir),
        "cases": str(args.cases),
        "status": "PASS" if failures == 0 else "FAIL",
        "total": len(rows),
        "failures": failures,
        "results": rows,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['status']} — {len(rows)} case(s), {failures} failure(s)")
        for row in rows:
            status = "PASS" if row["pass"] else "FAIL"
            print(f"{status}: {row['id']} [{row['expect']}] — {row['reason']}")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
