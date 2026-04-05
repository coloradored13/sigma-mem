# sigma-mem

Persistent agent teams that learn across sessions — using nothing but markdown files.

sigma-mem is a HATEOAS-navigated memory system for AI agents, built as an MCP server. It gives Claude (or any LLM) persistent identity, team coordination, and self-navigating memory retrieval.

## What it does

**Personal memory** — Stores user preferences, project state, past decisions, and calibration across sessions using compressed notation. A HATEOAS state machine detects conversation context and surfaces only what's relevant.

**Team memory** — Agents have persistent identities with personal memory, shared team decisions, and expertise-weighted knowledge. Wake only the agents you need. Each session builds on the last.

**One-call boot** — An agent calls `recall("I'm tech-architect on sigma-review, reviewing auth")` and gets back everything: personal memory, team decisions, patterns, roster, and teammates. No multi-step setup.

**Dream consolidation** — A four-phase memory maintenance cycle that deduplicates entries, prunes stale research, promotes tentative beliefs to confirmed, and verifies index integrity. Runs as a dry-run by default; apply changes explicitly.

## How it works

sigma-mem exposes memory as a navigable state machine via MCP:

```
recall("working on prompt-coach")
  -> state: project_work
  -> core memory + project context
  -> available: get_project, get_decisions, log_decision, get_failures, log_failure,
                search_memory, store_memory, check_integrity, get_meta

recall("I'm tech-architect on sigma-review, reviewing code")
  -> state: team_work
  -> core memory + agent boot (personal memory + team decisions + roster + teammates)
  -> available: get_roster, get_team_decisions, get_team_patterns, get_agent_memory,
                wake_check, validate_system, store_team_decision, search_team_memory,
                store_agent_memory, store_team_pattern,
                get_project, get_decisions, get_failures, get_patterns,
                search_memory, store_memory, check_integrity, get_meta
```

States: `idle`, `project_work`, `team_work`, `correcting`, `debugging`, `returning`, `reviewing`, `philosophical`

Each state unlocks different actions. The gateway detects context using weighted keyword scoring and surfaces the right memory with the right tools. Four actions (`search_memory`, `store_memory`, `check_integrity`, `get_meta`) are available in every state.

## Key concepts

- **HATEOAS navigation** — Memory files contain `-> action` links. Follow them to navigate. The state machine advertises available actions after every call.
- **Compressed notation** — `C[detects perf, honest>polish, probes|3|26.3]` stores what would take a paragraph in one line. Optimized for LLM token efficiency.
- **Anti-memories** — `![developer(leader learning to build)]` explicitly stores what is NOT true, preventing hallucinated beliefs.
- **Integrity checks** — Checksums, confidence markers (`~` = tentative), and promotion lifecycle (observed once -> confirmed across sessions).
- **Expertise-weighted decisions** — Team decisions carry attribution: who decided, from which domain, with dissenting context preserved.
- **Dream consolidation** — Four-phase cycle: consolidate (merge duplicates), prune (expire stale R[] entries, remove resolved corrections), reorganize (promote C~[]->C[] beliefs, detect patterns), index (verify checksums and structural integrity). Scoped to personal memory, a specific team, or all.

## ΣComm notation

sigma-mem stores and retrieves memory using ΣComm, a compressed notation designed for LLM token efficiency. Instead of verbose prose, agents read and write structured shorthand:

```
C[detects perf, honest>polish, probes|3|26.3]     # confirmed belief, 3 observations, since March
C~[prefers-TDD|1|26.4]                             # tentative belief, 1 observation
¬[developer(leader learning to build)]              # anti-memory: explicitly NOT true
R[api-latency-p99=120ms|source:grafana|26.4.1]     # research entry with source and date
```

Agent-to-agent messages use the same notation with status codes and action advertisements:

```
✓ auth-review: jwt-expiry-no-validate(!), pwd-md5>bcrypt |¬ session-mgmt |→ fix-jwt, fix-hash |#2
! test-suite: 14/20 pass, 6 fail in auth-module |→ need-auth-fix-first |#6-fail
```

Key symbols: `|` separator, `>` preference, `→` leads-to/available actions, `¬` explicitly NOT, `!` critical, `~` tentative, `#N` item count (checksum).

The full specification including inbox infrastructure, workspace conventions, and a codebook for agent system prompts is in [docs/sigma-comm-protocol.md](docs/sigma-comm-protocol.md). For a human-readable decoder of memory file notation, see [docs/notation-reference.md](docs/notation-reference.md).

## Actions by state

| State | Context-specific actions |
|-------|------------------------|
| `idle` | `get_project`, `get_decisions`, `get_corrections`, `get_user_model`, `get_conversations`, `verify_beliefs`, `dream`, team read actions |
| `project_work` | `get_project`, `get_decisions`, `log_decision`, `get_failures`, `log_failure` |
| `team_work` | `get_roster`, `get_team_decisions`, `get_team_patterns`, `get_agent_memory`, `wake_check`, `validate_system`, `store_team_decision`, `search_team_memory`, `store_agent_memory`, `store_team_pattern`, `get_project`, `get_decisions`, `get_failures`, `get_patterns` |
| `correcting` | `get_corrections`, `log_correction`, `update_belief` |
| `debugging` | `get_project`, `get_failures`, `log_failure` |
| `returning` | `full_refresh`, `verify_beliefs`, `dream` |
| `reviewing` | `get_decisions`, `get_patterns`, `get_conversations`, `get_team_decisions`, `dream` |
| `philosophical` | `get_user_model`, `get_patterns` |
| *all states* | `search_memory`, `store_memory`, `check_integrity`, `get_meta` |

## Installation

```bash
pip install git+https://github.com/coloradored13/sigma-mem.git
```

Requires [hateoas-agent](https://github.com/coloradored13/hateoas-agent) >= 0.1.0.

## Usage

### As an MCP server

sigma-mem runs as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server. MCP is an open standard for connecting LLMs to external tools — the LLM client discovers available tools at runtime and calls them through the protocol, rather than having tools hardcoded into the application.

sigma-mem uses stdio transport: the MCP client (e.g., Claude Code) spawns the `sigma-mem` process and communicates over stdin/stdout. The server exposes `recall` as the gateway tool. After each call, the available tools update based on the detected state — so an LLM in `team_work` state sees team actions, while one in `correcting` state sees belief-update actions.

To connect from Claude Code, add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "sigma-mem": {
      "command": "sigma-mem",
      "args": []
    }
  }
}
```

Once configured, the LLM can call `recall("context description")` as a tool. The server detects the conversation context, returns relevant memories, and advertises the next set of available actions.

### Multi-agent access

MCP servers are session-level infrastructure — every agent in a Claude Code session shares access to the same MCP tools. When you spawn agents (via the Agent tool or TeamCreate), they inherit the parent session's MCP connections automatically.

This means a multi-agent team can coordinate through sigma-mem without any extra wiring:

```
Claude Code session starts
  └─ spawns sigma-mem process (stdio)

User starts a review
  └─ lead agent calls recall("starting review of auth module")
      └─ sigma-mem returns core memory + project context
  └─ lead spawns tech-architect agent
      └─ tech-architect calls recall("I'm tech-architect on sigma-review, reviewing auth")
          └─ sigma-mem detects team_work state, returns agent boot package
          └─ tech-architect now has: personal memory, team decisions, roster, teammates
  └─ lead spawns product-strategist agent
      └─ same pattern — each agent boots with its own identity and shared team context
```

No agent needs to know how sigma-mem is connected. They call `recall()` like any other tool, and the state machine handles context detection and memory routing.

### Security model

sigma-mem trusts all connected MCP clients (inherent to stdio transport). File access is restricted to the configured memory and teams directories via path validation, but there is no authentication layer. Do not expose the server to untrusted clients.

### Memory directory structure

```
~/.claude/memory/          # personal memory
  MEMORY.md                # core identity (always loaded)
  projects.md              # project state
  decisions.md             # past decisions
  corrections.md           # what was wrong and fixed
  patterns.md              # cross-cutting observations
  ...

~/.claude/teams/           # team memory
  {team-name}/
    shared/
      roster.md            # who's on the team, domains, wake-for rules
      decisions.md         # expertise-weighted team decisions
      patterns.md          # cross-agent observations
    agents/
      {agent-name}/
        memory.md          # personal identity, findings, calibration
```

### Custom directories

```bash
sigma-mem --memory-dir /path/to/memory --teams-dir /path/to/teams
```

## Architecture

Five modules, ~2,600 lines:

- `machine.py` — Declarative HATEOAS state machine (states, actions, handler bindings)
- `handlers.py` — All read/write operations for personal and team memory
- `dream.py` — Memory consolidation: dedup, prune, reorganize, and index verification
- `integrity.py` — Checksums, confidence detection, anti-memory verification
- `server.py` — MCP server entry point

295 tests across 6 test modules (~2,633 lines).

Built on [hateoas-agent](https://github.com/coloradored13/hateoas-agent) for state machine and MCP serving.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
