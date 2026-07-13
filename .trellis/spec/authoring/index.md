# Authoring Skills

> How to structure and write a skill in this repository.

---

## Overview

A skill is a directory whose only required file is `SKILL.md`. Everything else is optional
and loaded on demand. The guiding principle is **progressive disclosure**: `SKILL.md` stays
a lean router + workflow, and heavy detail lives in `references/`.

The machine-checkable contract for a package lives in
`skill-evolution-loop/scripts/validate_skill.py`. Run it before considering a skill done:

```bash
python3 skill-evolution-loop/scripts/validate_skill.py <skill-dir>
```

## Guidelines Index

| Guide | Description |
|-------|-------------|
| [Skill Package](./skill-package.md) | Directory layout, naming, required frontmatter, packaging rules |
| [SKILL.md Authoring](./skill-md.md) | Progressive disclosure, frontmatter fields, routing, trigger design |
| [Resources](./resources.md) | `references/`, `assets/`, `templates/`, `evals/`, `profiles/`, `agents/` |

## Quick Rules

- One skill = one top-level directory named exactly like its frontmatter `name`.
- `SKILL.md` should stay under ~500 lines; push detail into `references/`.
- Do not add `README.md` / `CHANGELOG.md` / install guides inside a skill unless a real
  external dependency forces it (see [Skill Package](./skill-package.md)).
- A skill must run from its own directory. Bundle runtime references instead of depending
  on a sibling skill being installed.
