# Scripts

> Conventions for the Python/Node code that backs a skill.

---

## Overview

Skills that do more than prompt the model keep runnable code in `scripts/`. Two skills set
the pattern:

- `stock-trade-journal/scripts/` — a family of Python CLIs over a shared SQLite schema,
  plus one Node server (`live_server.mjs`).
- `skill-evolution-loop/scripts/` — stdlib-only Python validators.

Prefer a script over prose whenever logic is repeatable and verifiable
(`skill-evolution-loop/SKILL.md` Phase 3: "优先跑确定性检查"). A script that always produces
the same output is worth more than instructions the model re-derives each time.

## Guidelines Index

| Guide | Description |
|-------|-------------|
| [Python Conventions](./python.md) | Shebang, argparse, `main()`, `--json`, `--workspace`, imports, deps |
| [Data & Storage](./storage.md) | SQLite-as-record, single schema owner, idempotent migrations, paths |
| [STJ Dashboard Contract](./dashboard.md) | Cross-layer data/API/AI/storage signatures, errors and release tests |

## Quick Rules

- Standard library first. Add a third-party dependency only when essential, and declare it
  in the skill's `requirements.txt`.
- Every script is a standalone CLI invoked as `cd <skill>/scripts && python3 <name>.py …`.
- Scripts import their siblings by bare module name, so they must be run from `scripts/`.
- Offer `--json` for any output another tool or the agent will parse.
