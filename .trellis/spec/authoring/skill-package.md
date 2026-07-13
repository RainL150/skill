# Skill Package

> Directory layout, naming, frontmatter, and packaging rules for a skill.

The rules below are enforced by `skill-evolution-loop/scripts/validate_skill.py`. When in
doubt, read that script — it is the source of truth, not this doc.

---

## Directory = Name

Each skill is one top-level directory. The directory name **must equal** the frontmatter
`name`, and must match `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$` (lowercase, kebab-case).

- `validate_skill.py:15` (`NAME_RE`) and `:111-112` enforce the match.
- Examples: `concept-research/` → `name: concept-research`; `stock-trade-journal/` →
  `name: stock-trade-journal`.

## Required Frontmatter

Only two keys are required:

| Key | Rule | Evidence |
|-----|------|----------|
| `name` | matches dir name and `NAME_RE` | `validate_skill.py:107-112` |
| `description` | non-empty, ≤ 1024 chars | `validate_skill.py:114-117` (`MAX_DESCRIPTION`) |

`description` is what the host uses to decide activation, so it must carry trigger intent,
not just a summary — see [SKILL.md Authoring](./skill-md.md). All other frontmatter fields
are optional and documented in that file.

## SKILL.md Body Rules

- Non-empty body (`validate_skill.py:119-120`).
- Fenced code markers must be balanced — an odd number of triple-backtick fences fails
  validation (`:130-131`). This also applies to every other `.md` in the skill (`:137-142`).
- Every local Markdown link target must exist (`:133-135`). External `http(s)`/`mailto`/`#`
  links are ignored.
- Keep it under ~500 lines. Over that is a warning (`--strict` makes it an error,
  `:122-128`, `MAX_SKILL_LINES=500`).

**Anti-pattern in this repo:** `project-analyzer/SKILL.md` is ~1000 lines because full
output templates and per-phase detail live in the main file. New skills should move that
kind of detail into `references/` (as `stock-trade-journal` does) rather than copy the
project-analyzer shape.

## Optional Directories

```
<skill-name>/
├── SKILL.md            # required: router + workflow
├── references/         # deep flows, one concern per file
├── scripts/            # Python/Node helpers (see scripts/ specs)
├── assets/             # static files, output templates, vendored libs
├── templates/          # output scaffolds
├── evals/              # one trigger/behavior scenario per file
├── profiles/           # replaceable user-supplied inputs
└── agents/openai.yaml  # Codex host interface (optional)
```

See [Resources](./resources.md) for what belongs in each.

## Do Not Add Noise Files

`validate_skill.py:144-146` warns on `README.md`, `CHANGELOG.md`, `INSTALLATION_GUIDE.md`,
and `QUICK_REFERENCE.md` inside a skill — the host agent never reads them, so they only
inflate context.

Exception: a `README.md` / `requirements.txt` is acceptable only when a real external
dependency or human-facing setup demands it. `stock-trade-journal/` keeps both because it
needs `ib_insync` for IBKR sync (`stock-trade-journal/requirements.txt`). Do not add them
by habit.

## Scripts Must Parse

Every file under `scripts/` is syntax-checked: `.py` via `ast.parse`, `.sh` via `bash -n`
(`validate_skill.py:72-88, 148-152`). A broken script fails the whole package.

## Validate Before Done

```bash
python3 skill-evolution-loop/scripts/validate_skill.py <skill-dir>          # human output
python3 skill-evolution-loop/scripts/validate_skill.py <skill-dir> --json   # machine output
python3 skill-evolution-loop/scripts/validate_skill.py <skill-dir> --strict # warnings → errors
```

Validation proves the package structure and trigger metadata are sane. It does **not**
prove the model will behave — real behavior still needs an eval or forward-test (see
[evals in Resources](./resources.md) and `skill-evolution-loop` Phase 3).
