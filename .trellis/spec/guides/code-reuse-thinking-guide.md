# Code Reuse Thinking Guide

> **Purpose**: Before writing a new script or helper, check whether it already exists.

---

## The Problem

Duplicated logic is the #1 source of inconsistency bugs. When you re-parse a code, re-open a
DB, or re-implement a validator instead of reusing the existing one, bug fixes stop
propagating and behavior diverges.

## Before Writing New Code

### Step 1: Search First

```bash
grep -rn "def parse_ts_code" stock-trade-journal   # does a helper already exist?
grep -rn "ensure_db" stock-trade-journal            # who already owns this?
```

### Step 2: Ask

| Question | If yes… |
|----------|---------|
| Does a helper already do this? | Import it; don't re-implement |
| Is this storage / schema logic? | It belongs in `db_schema.py`, not your script |
| Am I parsing a ts_code inline? | Use `parse_ts_code()` |
| Am I re-checking a note_type by string? | Use `normalize_note_type()` |

## Single Source of Truth (this repo)

- **Storage & schema** → `db_schema.py` only. Scripts import `ensure_db`, `get_position`,
  `add_note`, … and never run their own DDL (`record_trade.py:11`).
- **Code parsing** → `parse_ts_code()` (`db_schema.py:549-573`) maps `AAPL.US`/`0700.HK`/
  `600519.SH` to `(symbol, market, exchange)`. Don't re-split on `.` inline.
- **Closed enums** → defined once (`NOTE_TYPES`), enforced by a `CHECK` and a
  `normalize_*` function. See [Data & Storage](../scripts/storage.md).

## Shortcut Skills Are Duplication You Own

`stj/` deliberately restates `stock-trade-journal`'s command surface. That is intentional
duplication — which means it needs active syncing. When you change the main skill's commands
or invocations, update the shortcut in the same edit, or it drifts. Treat it like any other
copy of a contract.

## Gotcha: Python if/elif Has No Exhaustive Check

Python does not warn when an `if/elif/else` chain misses a new value. When you add a value to
a closed set (a `Literal`, or a set like `NOTE_TYPES`), every chain that switches on it can
silently fall through `else` to a wrong default.

```python
# BAD: a new market falls through to the wrong default
if market == "US":  exchange = "NASDAQ"
else:               exchange = "HKEX"      # SH/SZ silently wrong

# GOOD: table lookup with an explicit fallback (db_schema.parse_ts_code)
market_exchange = {"US": "NASDAQ", "HK": "HKEX", "SH": "SSE", "SZ": "SZSE"}
exchange = market_exchange.get(market, market)
```

**Prevention**: when you extend a closed set, `grep` for every branch that switches on it and
add the new case explicitly. Prefer a dict lookup over a long `if/elif` chain.

## When To Abstract

- **Abstract** when the same logic appears 3+ times, is complex enough to have bugs, or is
  storage/parsing that must stay identical everywhere.
- **Don't** abstract a trivial one-off — that just adds indirection.

## Checklist Before Done

- [ ] Grepped for an existing helper before writing a new one.
- [ ] No inline ts_code parsing or DDL that `db_schema.py` already owns.
- [ ] New enum values added to the definition, the `CHECK`, and the validator together.
- [ ] Shortcut skill (`stj`) updated if the main skill's surface changed.
