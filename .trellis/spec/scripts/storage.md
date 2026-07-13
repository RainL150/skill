# Data & Storage

> How skills that persist data manage SQLite, migrations, and workspace paths.

Reference implementation: `stock-trade-journal/scripts/db_schema.py` (owns the whole
storage layer).

---

## SQLite Is the System of Record; Markdown Mirrors It

Structured data lives in SQLite; a human-readable Markdown copy is written alongside
("双写存储: SQLite + Markdown", `stock-trade-journal/SKILL.md`). `record_trade.py` writes the
DB row (`:76-89`) and then appends `append_trade_md(md_path, row)` (`:110`). The DB is
authoritative; Markdown is a mirror for humans, never read back as truth.

## One Schema Owner

`db_schema.py` is the **only** module that defines tables and exposes accessors
(`ensure_db`, `get_position`, `add_note`, `get_notes`, `update_position_after_trade`, …).
Other scripts import those helpers; they never run `CREATE TABLE` or raw DDL themselves
(`record_trade.py:11` imports from `db_schema`). Add or change storage in one place.

## Idempotent Creation + Forward-Only Migration

Any entrypoint may call `ensure_db(db_path)`, so it must be safe to call repeatedly and must
self-heal an old database. The pattern in `db_schema.py`:

- `CREATE TABLE IF NOT EXISTS` for every table (`:76-180`).
- Add a column via `ALTER TABLE … ADD COLUMN` wrapped in try/except `OperationalError`
  (`:218-232`) — "already exists" is swallowed.
- Remove/reshape a column via rename-to-`*_legacy` → recreate → copy rows → drop legacy
  (`_migrate_trades_note_only`, `:241-305`).
- Migrations run inside `ensure_db` and re-create indexes afterward (`:184-189`), because a
  table rebuild drops old indexes.
- Backfills dedupe before inserting (`_note_exists`, `:414-442`).

Rule: never require users to reset their DB. A schema change ships with the migration that
upgrades existing databases in place.

## Centralize Constrained Enums

When a column is a closed set, define it once and validate in one function:

- `NOTE_TYPES = ("trade_decision", "watch_observation", "holding_review")` (`db_schema.py:32`).
- Enforced in the DB via `CHECK (note_type IN (...))` (`:171-174`).
- Enforced in code via `normalize_note_type()` raising `ValueError` on unknown input
  (`:47-52`).

Adding a fourth note type means editing exactly those three spots — not hunting inline
string checks across scripts. See the
[Code Reuse Guide](../guides/code-reuse-thinking-guide.md).

## Workspace Paths

Data lives under a workspace root, resolved from env then home:

```
{workspace}/results/trade-journal/
├── db/trades.db          # SQLite
└── records/<ts_code>.md  # per-symbol Markdown mirror
```

- Root default: `STJ_WORKSPACE` env → `~/.trade-journal` (`record_trade.py:18-21`,
  `stj/SKILL.md`).
- Overrides: `--workspace` flag, or `STJ_DB` / `STJ_WORKSPACE` env for the Node server.
- `ensure_db` creates the parent dir (`os.makedirs(..., exist_ok=True)`, `db_schema.py:71`)
  so callers never pre-create directories.

## Connection Conventions

- `conn.row_factory = sqlite3.Row` for dict-style access (`db_schema.py:73`); accessors
  return `dict(row)`.
- `conn.commit()` after writes; migrations commit at each stage.
