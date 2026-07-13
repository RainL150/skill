---
name: analysis-html-report
description: Render analysis results as the same self-contained editorial HTML style used by project-analyzer. Use when the user asks to output an analysis/report/research result as a nice HTML page, project-analyzer-style HTML, webpage, printable HTML, or both Markdown and HTML.
---

# Analysis HTML Report

This skill converts an already-written analysis result into the polished HTML format used by `project-analyzer`.

It is a rendering/output skill, not a research skill. Do the actual analysis with the relevant domain skill or normal workflow first, save the final content as Markdown, then render that Markdown to HTML.

## When To Use

Use this skill when the user asks for:

- "用 project-analyzer 那种 HTML"
- "输出成好看的网页"
- "分析结果指定成 HTML"
- "md 和 html 都要"
- "可打印/可分享的单文件 HTML"

Do not use it when the user only wants a short chat answer and did not ask for a saved artifact.

## Output Contract

Always generate Markdown first, then render HTML from the exact same Markdown source.

Default filenames:

- Markdown: `<topic>-analysis.md`
- HTML: `<topic>-analysis.html`

If the user gives a path, respect it. If they ask for "both", keep both files. If they only ask for HTML, keep the Markdown source unless it is clearly temporary and the user asked not to keep it.

## Markdown Authoring Rules

Write Markdown that renders well in the project-analyzer editorial HTML style:

- Start with one `#` title.
- Use `##` and `###` headings; they become the left-side table of contents.
- Use normal Markdown tables for structured comparisons.
- Use blockquotes for callouts or plain-language notes.
- Use fenced code blocks with no language for ASCII wireframes; the renderer preserves alignment with `pre.wireframe`.
- Use fenced `mermaid` blocks only when Node/npx can render them during build. Never add Mermaid CDN scripts.
- Keep the analysis content complete in Markdown; HTML must not contain extra facts absent from the Markdown source.

## Render Command

Preferred command:

```bash
cd <this-skill-directory>
python3 scripts/render_analysis_html.py input.md output.html
```

The wrapper first uses the packaged `scripts/md2html_project_analyzer.py` renderer, then falls back to local `project-analyzer/scripts/md2html.py` if needed. It produces a self-contained HTML file with inline CSS, a sticky TOC, and Mermaid diagrams rendered at build time when available. If Mermaid rendering fails, the renderer falls back to readable source blocks.

Unlike the upstream project-analyzer template, this wrapper keeps the TOC visible in narrow app/browser panes by moving it above the content instead of hiding it below 920px.

## Verification Checklist

After rendering, verify:

1. HTML file exists and is non-empty.
2. It contains `<!doctype html>`, `<nav class="toc">`, `<main class="content">`, and inline `<style>`.
3. There are no runtime Mermaid CDN imports or external JavaScript dependencies.
4. H2/H3 headings appear in the TOC.
5. If a Mermaid block was used, either an inline `.mermaid-svg` exists or a readable fallback `<pre class="mermaid">` exists.

Useful local check:

```bash
cd <this-skill-directory>
python3 scripts/verify_html_report.py output.html
```

## Response Pattern

When done, tell the user:

- Markdown path, if kept.
- HTML path.
- Whether verification passed.
- Any limitations, such as Mermaid falling back to source because `npx` or Chromium failed.
