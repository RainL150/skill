# Project Specs

> Coding guidelines for this repository. Read the relevant layer before writing code.

---

## What This Repo Is

This is a **collection of Agent Skills** for Claude Code / OpenAI Codex. Each top-level
directory is one self-contained skill (`concept-research/`, `project-analyzer/`,
`skill-evolution-loop/`, `stj/`, `stock-trade-journal/`). A skill is a `SKILL.md` file
with YAML frontmatter, plus optional `references/`, `scripts/`, `assets/`, `templates/`,
`evals/`, `profiles/`, and `agents/` directories.

There is **no application build, server, or framework** here. "Shipping" means: a valid
skill package that a host agent loads, whose `SKILL.md` routes correctly and whose scripts
run standalone. The reference contract for a valid package is enforced by
`skill-evolution-loop/scripts/validate_skill.py`.

## Spec Layers

| Layer | Covers | Read when |
|-------|--------|-----------|
| [authoring/](./authoring/index.md) | `SKILL.md`, frontmatter, packaging, resource dirs | Creating or editing any skill |
| [scripts/](./scripts/index.md) | Python/Node scripts and data storage behind a skill | Writing or changing script logic |
| [guides/](./guides/index.md) | Cross-cutting thinking guides (consistency, reuse) | Before batch edits or when something feels repetitive |

## Language Convention

`SKILL.md` bodies, comments, and user-facing output in this repo are **Chinese-first**.
Identifiers, directory names, frontmatter keys, file paths, and CLI flags stay **English**
(kebab-case dirs, snake_case Python). This diverges from the generic Trellis "English only"
template on purpose — these specs describe the repo as it actually is. Keep new skills
consistent with the surrounding Chinese-first prose.
