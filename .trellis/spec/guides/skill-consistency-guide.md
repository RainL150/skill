# Skill Consistency Guide

> **Purpose**: In a skill, the same contract is stated in several places. Change them together.

---

## The Layers That Must Agree

A skill is not layered like an app (API/service/DB). Its "layers" are parallel statements of
one contract:

| Layer | Where | States |
|-------|-------|--------|
| Contract / routing | `SKILL.md` frontmatter + command tables | what triggers the skill, what commands exist |
| Behavior | `scripts/*.py`, `*.mjs` | what actually runs |
| Detail | `references/`, `assets/`, `templates/` | the long-form how |
| Shortcut | alias skills (`stj` → `stock-trade-journal`) | a re-stated subset of the above |

Drift between any two of these is the dominant bug class here. Before finishing an edit,
walk the checklist for whatever you touched.

## When You Add / Rename / Delete a Script

`SKILL.md` references scripts in three forms — update all of them:

1. The script-list table (`stock-trade-journal/SKILL.md` "脚本清单").
2. The command tables (`命令 | 功能 | 示例`).
3. Every runnable invocation `cd .../scripts && python3 <name>.py …`.

Then check the shortcut skill: `stj/SKILL.md` re-states most of these invocations.

## When You Change a Flag or Default

Every `SKILL.md` code block that calls the script now shows a lie. Grep the flag name across
the skill and the shortcut, e.g.:

```bash
grep -rn "profile_review.py" stock-trade-journal stj
```

Deprecate rather than delete a flag when data or muscle memory depends on it — keep it
accepted but hidden with `help=argparse.SUPPRESS` (`record_trade.py:26`).

## When You Add a Trigger or Command

Frontmatter `triggers`/`when`/`examples`, the command table, and the routing logic
(`project-analyzer/SKILL.md:57-62`) are one unit. A new command that is not in the routing
logic will silently fall to the default branch.

## When You Change Storage

A DB change fans out across `db_schema.py` and the docs:

- Column / enum: DDL, the `CHECK` constraint, the `normalize_*` validator, **and** the schema
  table printed in `SKILL.md` (`stock-trade-journal/SKILL.md` documents `trades`, `positions`,
  `notes` and the allowed `note_type` values).
- Ship the migration that upgrades existing DBs in the same change (see
  [Data & Storage](../scripts/storage.md)).

## When SKILL.md Grows Past ~500 Lines

That is the signal detail belongs in `references/`, not the main file (validation warns at
500 lines; `project-analyzer/SKILL.md` is the cautionary example). Moving detail out is a
consistency fix, not a nicety.

## Keep Bundled References Self-Contained

`stock-trade-journal` vendors `references/invest-research-skills/`. If you update the
standalone research skills, the bundled copy does **not** update automatically — it is a
separate mechanism that silently drifts. When you change one, search for the other:

```bash
grep -rln "shared-research-context" stock-trade-journal
```

## Verify Before Done

```bash
# 1. Structure + trigger metadata + local links + script syntax:
python3 skill-evolution-loop/scripts/validate_skill.py <skill-dir>

# 2. Drift sweep — the changed symbol should appear everywhere it should, nowhere it shouldn't:
grep -rn "<changed-symbol>" <skill-dir> stj
```

A change is done when the spec, the prose, the code, and any shortcut all agree, and
`validate_skill.py` passes.
