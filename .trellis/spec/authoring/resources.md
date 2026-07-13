# Resources

> What belongs in each optional skill subdirectory.

Load only what an agent will actually read at runtime. Every file here is context cost.

---

## references/

Deep flows and knowledge, **one concern per file**, linked from `SKILL.md` on demand.

- `stock-trade-journal/references/*-flow.md` — one workflow each
  (`invest-research-flow.md`, `portfolio-watch-analysis-flow.md`,
  `pre-trade-interceptor-flow.md`, `profile-evolution-review-flow.md`).
- `project-analyzer/references/analysis-framework.md`, `output-templates.md` — detail lifted
  out of the main file.
- `skill-evolution-loop/references/{gates,case-format,review-rubric}.md`.

Rule: if `SKILL.md` links a reference, the target must exist (validation checks local
links). Keep each reference focused enough that the router can pull exactly one.

## Bundled Runtime References (self-containment)

A skill must run from its own directory, so bundle what it needs instead of depending on
another skill being installed. `stock-trade-journal` vendors an entire
`references/invest-research-skills/` tree (its own `sector-research`, `stock-fundamental`,
`shared-research-context`, `research-review`) and `stj/SKILL.md:193` states the rule
explicitly: "直接分析时不要依赖外部 `invest-research-skills` 是否安装".

## evals/

One trigger or behavior scenario per file, used to catch mis-fire / mis-behavior.

- `stock-trade-journal/references/invest-research-skills/sector-research/evals/*.md` —
  each names one condition (`quick-judgment.md`, `disclosure-mode.md`, `macro-steel.md`).
- `stock-fundamental/evals/*.md`, `research-review/evals/*.md` — same shape.

These back the "does it behave" gap that `validate_skill.py` cannot check. See
`skill-evolution-loop/references/case-format.md` and `scripts/run_case_replay.py`.

## assets/ and templates/

Static outputs and vendored files.

- `assets/`: `stock-trade-journal/assets/echarts.min.js` (vendored lib),
  `sector-research/assets/report-template.md` (output scaffold).
- `templates/`: `stock-trade-journal/templates/{trade-entry.md,stock-chart.html}`.

Vendored binaries/libs (like `echarts.min.js`) let the skill run offline; keep them in
`assets/`, not `scripts/`.

## profiles/

Replaceable, user-supplied inputs — **not** part of the main flow. `stock-trade-journal`
reads a profile only when the user explicitly asks
(`stock-trade-journal/SKILL.md:169-179`). Treat `profiles/<slug>.md` as external data:
select by user-named slug, never auto-apply one when several exist, and never let a profile
change script defaults or add DB fields.

## scripts/examples/

JSON fixtures for the skill's scripts, e.g.
`sector-research/scripts/examples/{cycle,valuation,sizing}-input.json`. Keep sample inputs
here so scripts can be exercised deterministically.

## agents/openai.yaml

Codex-host interface file. Optional, but if present it must be well-formed
(`validate_skill.py:50-69`):

- Must contain an `interface:` block.
- `default_prompt` must mention `$<skill-name>` (else hard error, `:67-68`).
- `display_name`, `short_description`, `default_prompt` are expected (warnings if missing).

Reference: `skill-evolution-loop/agents/openai.yaml`.
