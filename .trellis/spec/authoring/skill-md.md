# SKILL.md Authoring

> How to write the `SKILL.md` body and frontmatter so the host activates and follows it.

---

## Progressive Disclosure

`SKILL.md` is a **router + workflow**, not a manual. Keep the main file to: what the skill
does, when to use it, the command/route table, and the step-by-step workflow. Push every
heavy detail (long templates, per-scenario flows, framework knowledge) into `references/`.

- `skill-evolution-loop/SKILL.md` states this directly: symptom "`SKILL.md` 很长" → fix
  "拆到 `references/`，主文件只保留路由和流程".
- `stock-trade-journal/SKILL.md` routes analysis work into
  `references/invest-research-flow.md`, `references/portfolio-watch-analysis-flow.md`, etc.,
  instead of inlining them.
- Counter-example to avoid: `project-analyzer/SKILL.md` inlines full output templates and
  runs ~1000 lines. Prefer the `stock-trade-journal` shape.

## Frontmatter Fields In Use

Only `name` and `description` are required (see [Skill Package](./skill-package.md)). The
optional fields actually used in this repo — keep to this set, don't invent new ones:

| Field | Shape | Seen in |
|-------|-------|---------|
| `triggers` | list of phrases / `/commands` | `project-analyzer`, `stock-trade-journal` |
| `when` | block describing activation cases | `stock-trade-journal` |
| `examples` | list of example invocations | `stock-trade-journal` |
| `allowed-tools` / `tools` | comma-list of permitted tools | `concept-research` (`allowed-tools`), `project-analyzer` (`tools`) |
| `model` | `sonnet` / `opus` / ... | `concept-research` |
| `license` | SPDX id | `concept-research` |
| `origin` | `local` | `project-analyzer` |
| `metadata` | `author`, `version`, `openclaw.{emoji,requires}` | `concept-research`, `stock-trade-journal` |

Note the existing inconsistency: some skills use `allowed-tools`, others `tools`. Match the
sibling skills you are editing; do not "fix" one in isolation and split the convention
further.

## description Carries the Trigger

The host routes on `description`, so it must say **what the skill is and when to fire**, not
just what it is. `concept-research` embeds trigger phrases right in the description
(`触发词：「研究一下 XX」…`). When a skill mis-fires or fails to fire, the description is the
first thing to tighten — see `skill-evolution-loop/SKILL.md` symptom table.

## Routing For Multi-Command Skills

When a skill exposes several sub-commands, give an explicit route table **and** the routing
logic:

- Command table: `stj/SKILL.md` and `stock-trade-journal/SKILL.md` list `命令 | 功能 | 示例`.
- Route logic: `project-analyzer/SKILL.md:57-62` maps keywords → output
  (`包含 modules → 模块拆解`, else → default report).

Keep the command table, the routing logic, and the actual `cd scripts && python3 …`
invocations in sync — they are the same contract stated three times. Drift between them is
the most common consistency bug here (see
[Skill Consistency Guide](../guides/skill-consistency-guide.md)).

## Shortcut Skills

`stj/` is a thin alias for `stock-trade-journal/`. It re-states the command surface and
defers full docs (`stj/SKILL.md` ends with "完整功能文档见 `/stock-trade-journal`"). If you
change a command or script in the main skill, update the shortcut too, or the two drift.

## Body Anti-Patterns

- Over-long `SKILL.md` (detail that belongs in `references/`).
- No "when to use" / "when not to use" section — every skill here has one
  (`concept-research` 什么时候用, `project-analyzer` When to Activate / 不适用).
- Claims with no evidence. `skill-evolution-loop` requires the generator to submit
  evidence, not self-declare "better"; carry that discipline into skill prose too.
