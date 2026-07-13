# Python Conventions

> How Python scripts under a skill's `scripts/` directory are written.

Reference implementations: `stock-trade-journal/scripts/record_trade.py`, `db_schema.py`,
and `skill-evolution-loop/scripts/validate_skill.py`.

---

## Script Skeleton

Every executable script follows the same shape:

```python
#!/usr/bin/env python3
"""One-line purpose (Chinese is fine)."""

from __future__ import annotations   # when using PEP 604 / builtin generics

import argparse
...

def main() -> None:        # or -> int for exit codes
    p = argparse.ArgumentParser(description="…")
    ...
    args = p.parse_args()
    ...

if __name__ == "__main__":
    main()                 # validators use: raise SystemExit(main())
```

- Shebang `#!/usr/bin/env python3` and a module docstring
  (`record_trade.py:1-4`, `validate_skill.py:1-2`).
- Type hints throughout; `from __future__ import annotations` where builtin generics or
  `X | None` are used (`validate_skill.py:3`).
- Logic lives in `main()`, guarded by `if __name__ == "__main__":`. Exit-code scripts return
  `int` and use `raise SystemExit(main())` (`validate_skill.py:189-193`).

## argparse Per Script

Each script parses its own flags. Established conventions:

- `--json` for machine-readable output — offered by `validate_skill.py`,
  `query_positions.py`, `analyze_holdings.py`, `profile_review.py`. In JSON mode print
  `json.dumps(result, ensure_ascii=False, indent=2)` (`validate_skill.py:180-181`) so
  Chinese stays readable.
- `--workspace` for data location, defaulting to an env var then a home path:
  `default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal"))`
  (`record_trade.py:18-21`).
- Constrained values use `choices=[...]` (`record_trade.py:23` `side` BUY/SELL).
- Deprecated flags stay accepted but hidden with `help=argparse.SUPPRESS`
  (`record_trade.py:26` `--reason`), never silently dropped.

## Standard Library First

Default to stdlib: `argparse`, `sqlite3`, `pathlib`, `os`, `json`, `re`, `ast`,
`subprocess`, `datetime`. `validate_skill.py` is deliberately "stdlib-only". Add a
third-party package only when essential and declare it in the skill's `requirements.txt`
(only `stock-trade-journal` has one, for `ib_insync`).

## Sibling Imports → Run From scripts/

Scripts import each other by bare module name, e.g. `record_trade.py:11`:

```python
from db_schema import add_note, ensure_db, get_position, parse_ts_code, update_position_after_trade
from journal_markdown import append_trade_md
```

There is no package `__init__.py` in these skill `scripts/` dirs, so scripts only resolve
when the working directory is `scripts/`. That is why every `SKILL.md` invocation is
`cd ~/.claude/skills/<skill>/scripts && python3 <name>.py …`. Keep new scripts in the same
directory and import siblings the same way.

## Output Style

- User-facing runs print a short structured block with status emoji
  (`record_trade.py:115-123`: `✅ 交易已记录…`, then indented fields).
- Do not mix human text into `--json` output — branch on the flag and print only JSON in
  JSON mode.

## Node Scripts

Node helpers use ESM `.mjs` and are launched with env-var config, e.g.
`stock-trade-journal/scripts/live_server.mjs`:

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && PORT=8787 node live_server.mjs
```

Config comes from env vars (`PORT`, `HOST`, `STJ_WORKSPACE`, `STJ_DB`, …), matching the
Python `--workspace`/`STJ_WORKSPACE` convention.
