# Thinking Guides

> **Purpose**: Expand your thinking to catch things you might not have considered.

Most bugs in this repo are not hard-logic failures — they are **drift**: a script gets a new
flag but `SKILL.md` still shows the old one; a note type is added to the DB but not to the
docs table; the `stj` shortcut falls behind `stock-trade-journal`. These guides help you ask
the right questions before editing.

---

## Available Guides

| Guide | Purpose | When to Use |
|-------|---------|-------------|
| [Skill Consistency Guide](./skill-consistency-guide.md) | Keep `SKILL.md`, scripts, references, and shortcut skills in sync | Any change that touches more than one of them |
| [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md) | Reuse existing helpers instead of duplicating logic | Before writing a new script or helper |

---

## Thinking Triggers

### Think About Skill Consistency When…

- [ ] You add, rename, or delete a script → command tables and every `cd scripts && python3`
      invocation may be stale.
- [ ] You change a script flag or default → every `SKILL.md` code block that calls it may lie.
- [ ] You add a frontmatter `trigger` / command → the routing table and examples may not match.
- [ ] You add a DB column or enum value → `db_schema.py`, the `CHECK`, `normalize_*`, and the
      docs table must all move together.
- [ ] You edit a skill that has a shortcut (`stj` → `stock-trade-journal`) → the shortcut may
      drift.

→ Read [Skill Consistency Guide](./skill-consistency-guide.md)

### Think About Code Reuse When…

- [ ] You are about to parse a ts_code, touch storage, or write a validator that might exist.
- [ ] You see the same logic in 3+ places.
- [ ] You add a value to a Python `Literal` / closed set — check every branch that switches
      on it.

→ Read [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md)

---

## Pre-Modification Rule (CRITICAL)

> **Before changing ANY name, flag, path, or value, search first.**

```bash
grep -rn "value_to_change" <skill-dir>
```

This single habit prevents most drift bugs — the changed symbol usually appears in
`SKILL.md`, a shortcut skill, and several scripts at once.

---

**Core Principle**: In a skill repo, the spec, the prose, and the code are three statements
of the same contract. A change is not done until all three agree — and
`validate_skill.py` passes.
