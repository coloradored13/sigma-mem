# sigma-mem Code Quality, Security, and README Accuracy Review

Date: 2026-04-05
Reviewer: Codex (GPT-5.3-Codex)

## Scope

Reviewed all repository source modules and tests:
- `src/sigma_mem/__init__.py`
- `src/sigma_mem/server.py`
- `src/sigma_mem/machine.py`
- `src/sigma_mem/handlers.py`
- `src/sigma_mem/integrity.py`
- `src/sigma_mem/dream.py`
- `tests/test_*.py`
- `README.md`
- `pyproject.toml`

## Method

- Performed line-by-line read-through of source modules.
- Mapped action declarations in `machine.py` to concrete handlers in `handlers.py`.
- Checked path traversal protections around all file writes and reads.
- Verified README claims against code and repository contents.

## Findings

### ✅ Strengths

1. **Path traversal protections are consistently present** in personal and team file handlers via `Path.resolve()` and `is_relative_to(...)` checks, including symlink-aware team validation.
2. **Reserved navigation syntax is protected** for write operations (`→`-prefixed lines blocked) reducing accidental corruption of HATEOAS links.
3. **State machine wiring is complete and coherent** (all actions registered with handlers, with predictable `_state` outputs).
4. **Dream cycle is safely dry-run by default**, and `apply=True` only performs dedup removal, not destructive pruning/promotions.
5. **Test suite is substantial** (~2.6k LOC) and appears to cover core behavior surface.

### ⚠️ Code quality issues

1. **`_parse_agent_roster_entry` can produce false matches** by using `startswith(agent_name)`; this can match `agent` against `agent-2` prefixes. Recommend exact first-column matching.
2. **String-based state detection is simplistic and can over-trigger** (`"error"`, `"before"`, `"team"` are broad keywords). Consider word-boundary matching, tokenization, or weighted phrase-first logic.
3. **`handle_update_belief` uses raw substring replacement** (`content.replace(old, new, 1)`), which may replace partial inline segments unexpectedly. Consider line-anchored replacement.
4. **`handle_store_team_decision` multi-line append formatting** introduces optional context on a second indented line; parser assumptions are implicit. Consider explicit schema format validation.

### ⚠️ Security observations

1. **No authentication/authorization layer** (explicitly documented). This is acceptable for trusted local MCP but dangerous if exposed over untrusted bridge.
2. **Search APIs return raw matching lines** including possibly sensitive memory content; no redaction controls. Consider optional masking policy for secrets.
3. **Symlink handling is mostly safe** due to `resolve()` + boundary checks; this is good. However, direct open/read of all `*.md` files in memory directory means users should ensure directory hygiene.

### 📚 README accuracy findings (fixed)

1. README said **"Six modules"** but listed five concrete modules. Updated to **"Five primary modules"**.
2. README said **"293 tests across 7 test modules"**. Repository currently has **6 test modules** and `test_*.py` line count totals **2,633 LOC**; updated wording accordingly.

## Recommendations

1. Tighten roster agent parsing to exact-name column comparison.
2. Improve `_detect_state` with token/phrase boundaries to reduce accidental state jumps.
3. Make belief updates line-scoped (exact line equality) rather than substring replacement.
4. Add an optional `safe_search` mode to omit likely secret patterns.
5. Keep README counts generated from script output to avoid drift.

## Evidence commands

- `rg --files`
- `nl -ba src/sigma_mem/*.py`
- `python - <<'PY' ...` (count test modules and lines)

