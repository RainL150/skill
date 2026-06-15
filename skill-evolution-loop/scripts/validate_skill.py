#!/usr/bin/env python3
"""Validate a Codex/Claude skill directory with stdlib-only checks."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

MAX_DESCRIPTION = 1024
MAX_SKILL_LINES = 500
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, list[str]]:
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text, ["SKILL.md has no YAML frontmatter block"]

    raw, body = match.group(1), match.group(2)
    data: dict[str, str] = {}
    for key in ("name", "description", "allowed-tools"):
        found = re.search(rf"^{re.escape(key)}:\s*(.*?)(?=^\w[\w-]*:|\Z)", raw, re.MULTILINE | re.DOTALL)
        if found:
            value = found.group(1).strip()
            value = re.sub(r"\s+", " ", value).strip("\"'")
            data[key] = value
    return data, body, []


def local_markdown_links(text: str) -> list[str]:
    links: list[str] = []
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if "#" in target:
            target = target.split("#", 1)[0]
        if target:
            links.append(target)
    return links


def validate_openai_yaml(skill_dir: Path, skill_name: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = skill_dir / "agents" / "openai.yaml"
    if not path.exists():
        warnings.append("agents/openai.yaml missing")
        return errors, warnings

    text = read_text(path)
    if "interface:" not in text:
        errors.append("agents/openai.yaml missing interface block")
    if "display_name:" not in text:
        warnings.append("agents/openai.yaml missing interface.display_name")
    if "short_description:" not in text:
        warnings.append("agents/openai.yaml missing interface.short_description")
    if "default_prompt:" not in text:
        warnings.append("agents/openai.yaml missing interface.default_prompt")
    elif f"${skill_name}" not in text:
        errors.append(f"agents/openai.yaml default_prompt must mention ${skill_name}")
    return errors, warnings


def check_script_syntax(path: Path) -> str | None:
    if path.suffix == ".py":
        try:
            ast.parse(read_text(path), filename=str(path))
        except SyntaxError as exc:
            return f"{exc.msg} at line {exc.lineno}"
    elif path.suffix == ".sh":
        result = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=path.parent,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip()
    return None


def validate_skill(skill_dir: Path, strict: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_dir.exists():
        return [f"skill directory does not exist: {skill_dir}"], []
    if not skill_md.exists():
        return [f"missing SKILL.md in {skill_dir}"], []

    text = read_text(skill_md)
    frontmatter, body, fm_errors = parse_frontmatter(text)
    errors.extend(fm_errors)

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if not name:
        errors.append("frontmatter missing name")
    elif not NAME_RE.match(name):
        errors.append(f"invalid skill name: {name}")
    elif name != skill_dir.name:
        errors.append(f"frontmatter name '{name}' does not match directory '{skill_dir.name}'")

    if not description:
        errors.append("frontmatter missing description")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(f"description is {len(description)} chars; max is {MAX_DESCRIPTION}")

    if not body.strip():
        errors.append("SKILL.md body is empty")

    line_count = len(text.splitlines())
    if line_count > MAX_SKILL_LINES:
        msg = f"SKILL.md has {line_count} lines; recommended max is {MAX_SKILL_LINES}"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    if text.count("```") % 2 != 0:
        errors.append("SKILL.md has an odd number of fenced code markers")

    for rel in local_markdown_links(text):
        if not (skill_dir / rel).exists():
            errors.append(f"SKILL.md link target missing: {rel}")

    for md in skill_dir.rglob("*.md"):
        if md == skill_md:
            continue
        md_text = read_text(md)
        if md_text.count("```") % 2 != 0:
            errors.append(f"{md.relative_to(skill_dir)} has an odd number of fenced code markers")

    for bad_name in ("README.md", "CHANGELOG.md", "INSTALLATION_GUIDE.md", "QUICK_REFERENCE.md"):
        if (skill_dir / bad_name).exists():
            warnings.append(f"extra documentation file may be noise for a skill: {bad_name}")

    for script in (skill_dir / "scripts").glob("*") if (skill_dir / "scripts").exists() else []:
        if script.is_file():
            failure = check_script_syntax(script)
            if failure:
                errors.append(f"script syntax failed for {script.relative_to(skill_dir)}: {failure}")

    yaml_errors, yaml_warnings = validate_openai_yaml(skill_dir, name or skill_dir.name)
    errors.extend(yaml_errors)
    warnings.extend(yaml_warnings)

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path, help="Path to the skill directory")
    parser.add_argument("--strict", action="store_true", help="Treat style warnings as errors")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    errors, warnings = validate_skill(args.skill_dir.resolve(), strict=args.strict)
    if args.strict:
        errors.extend(warnings)
        warnings = []

    result = {
        "skill_dir": str(args.skill_dir),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['status']} — {args.skill_dir}")
        for error in errors:
            print(f"ERROR: {error}")
        for warning in warnings:
            print(f"WARN: {warning}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
