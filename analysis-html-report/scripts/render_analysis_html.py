#!/usr/bin/env python3
"""Render Markdown analysis into the project-analyzer HTML report style."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ANALYZER_RENDERERS = [
    Path(__file__).resolve().with_name("md2html_project_analyzer.py"),
    Path("/Users/rainless/.ensoai/sources/src_mpyxnsz9_5tn4v95l/project-analyzer/scripts/md2html.py"),
    Path("/Users/rainless/.claude/skills/project-analyzer/scripts/md2html.py"),
]


def find_renderer() -> Path:
    for candidate in PROJECT_ANALYZER_RENDERERS:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Could not find project-analyzer md2html.py. Checked: "
        + ", ".join(str(p) for p in PROJECT_ANALYZER_RENDERERS)
    )


def keep_toc_visible_on_narrow_screens(html_text: str) -> str:
    """Project-analyzer hides the TOC below 920px; keep it visible for app panes."""
    old = """@media (max-width:920px){
    .layout{ grid-template-columns:1fr; padding:0 24px; }
    .toc{ display:none; } .content{ padding-top:36px; } }"""
    new = """@media (max-width:920px){
    .layout{ grid-template-columns:1fr; padding:0 24px; }
    .toc{ display:block; position:relative; top:auto; max-height:none; overflow:visible;
      padding:24px 0 10px; border-bottom:1px solid var(--border); }
    .toc ul{ display:flex; flex-wrap:wrap; gap:6px 14px; border-left:none; }
    .toc a{ padding:3px 0; margin-left:0; border-left:none; border-bottom:1px solid transparent; }
    .toc a.active{ border-left-color:transparent; border-bottom-color:var(--blue); }
    .toc li.lv3 a{ padding-left:0; }
    .content{ padding-top:24px; } }"""
    return html_text.replace(old, new)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: render_analysis_html.py input.md [output.html]", file=sys.stderr)
        return 2

    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.exists():
        print(f"input markdown not found: {src}", file=sys.stderr)
        return 2
    if src.suffix.lower() not in (".md", ".markdown"):
        print(f"input should be markdown: {src}", file=sys.stderr)
        return 2

    dst = (
        Path(sys.argv[2]).expanduser().resolve()
        if len(sys.argv) == 3
        else src.with_suffix(".html")
    )
    dst.parent.mkdir(parents=True, exist_ok=True)

    renderer = find_renderer()
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(renderer), str(src), str(dst)],
        text=True,
        capture_output=True,
        env=env,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        return result.returncode
    if not dst.exists() or dst.stat().st_size == 0:
        print(f"renderer did not create a non-empty HTML file: {dst}", file=sys.stderr)
        return 1

    html_text = dst.read_text(encoding="utf-8")
    patched = keep_toc_visible_on_narrow_screens(html_text)
    if patched != html_text:
        dst.write_text(patched, encoding="utf-8")

    print(f"HTML report: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
