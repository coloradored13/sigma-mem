# Notation Reference

A decoder for reading sigma-mem memory files. Ask your LLM to "decode" or "translate" any line from a memory file and it will explain in plain English — but this reference lets you read them yourself.

## Symbols

| Symbol | Meaning |
|--------|---------|
| `>` | preference/over |
| `\|` | separator |
| `@` | at/time/location |
| `→` | leads-to/next |
| `+` | and |
| `!` | critical |
| `?` | open question |
| `^` | file reference |
| `¬` | NOT (anti-memory) |
| `~` | tentative |

## Status markers

| Marker | Meaning |
|--------|---------|
| `*` | active |
| `✓` | done |
| `◌` | pending |
| `-` | inactive/off |

## Confidence markers

| Marker | Meaning |
|--------|---------|
| `~` | Tentative — observed once, single source. e.g., `C~[prefers-TDD]` |
| *(none)* | Confirmed — observed across multiple conversations. e.g., `C[prefers-TDD]` |

Tentative beliefs are promoted to confirmed by the dream consolidation cycle when they appear across multiple sessions.

## Entry types

| Prefix | What it stores | Example |
|--------|---------------|---------|
| `C[]` | Calibration — interaction tuning, behavioral observations | `C[detects perf, honest>polish, probes\|3\|26.3]` |
| `R[]` | Research — findings with source and date | `R[api-latency-p99=120ms\|source:grafana\|26.4.1]` |
| `¬[]` | Anti-memory — explicitly NOT true | `¬[developer(leader learning to build)]` |

## Section prefixes

Memory files organize entries under section prefixes:

| Prefix | Domain |
|--------|--------|
| `U` | User profile |
| `X` | Preferences |
| `P` | Project |
| `C` | Calibration (interaction tuning) |
| `S` | Self-awareness |
| `R` | Reasoning heuristics |
| `D` | Debug patterns |
| `A` | Architecture |
| `T` | Tech reference (`T.react`, `T.ts`, `T.vite`, etc.) |
| `H` | History (`H.YY-MM-DD`) |
| `L` | Lessons learned |
| `W` | Workflow patterns |
| `E` | Error patterns (`E.js`, `E.py`, `E.gen`) |
| `F` | Framework gotchas |
| `Q` | Quality checks |
| `B` | Build/deploy |
| `K` | Testing |
| `N` | State management |
| `G` | Git patterns |
| `I` | Interaction style |
| `V` | Value heuristics |
| `Ω` | Prompt engineering |
| `Z` | Platform/environment |
| `Δ` | Database |
| `Π` | API design |
| `Φ` | Performance |
| `Ψ` | Security |
| `Y` | UX/design |
| `J` | Auth |
| `Λ` | Meta-cognition |

## Reading a memory line

```
C[detects perf, honest>polish, probes|3|26.3]
```

Reading left to right:
- `C` — calibration entry
- `[...]` — the content
- `detects perf` — this user detects performative responses
- `honest>polish` — prefers honesty over polish
- `probes` — tends to probe/test
- `|3` — observed 3 times
- `|26.3` — since March 2026

## Dates

Dates use `YY.M.D` format: `26.3.14` = March 14, 2026. The short format saves tokens in files that accumulate many dated entries.
