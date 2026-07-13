#!/usr/bin/env python3
"""Basic structural verification for project-analyzer-style HTML reports."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED_SNIPPETS = [
    "<!doctype html>",
    "<style>",
    '<nav class="toc">',
    '<main class="content">',
    "IntersectionObserver",
]

FORBIDDEN_PATTERNS = [
    r"cdn\.jsdelivr\.net/npm/mermaid",
    r"unpkg\.com/mermaid",
    r"<script[^>]+src=",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_html_report.py report.html", file=sys.stderr)
        return 2

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print(f"HTML file not found: {path}", file=sys.stderr)
        return 2

    data = path.read_text(encoding="utf-8")
    errors: list[str] = []

    for snippet in REQUIRED_SNIPPETS:
        if snippet not in data:
            errors.append(f"missing required snippet: {snippet}")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, data, re.I):
            errors.append(f"forbidden runtime dependency matched: {pattern}")

    toc_items = len(re.findall(r'<li class="lv[23]"><a href="#', data))
    if toc_items == 0:
        errors.append("no h2/h3 table-of-contents entries found")

    if ".mermaid-svg" not in data:
        errors.append("missing mermaid-svg CSS class; expected project-analyzer style template")

    if errors:
        print("HTML verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"HTML verification passed: {path}")
    print(f"TOC entries: {toc_items}")
    print(f"Size: {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
