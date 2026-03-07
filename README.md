# sigma-mem

Persistent agent teams that learn across sessions — using nothing but markdown files.

sigma-mem is a HATEOAS-navigated memory system for AI agents, built as an MCP server. It gives Claude (or any LLM) persistent identity, team coordination, and self-navigating memory retrieval.

## What it does

**Personal memory** — Compressed notation stores user preferences, project state, past decisions, and calibration across sessions. A HATEOAS state machine detects conversation context and surfaces only what's relevant.

**Team memory** — Agents have persistent identities with personal memory, shared team decisions, and expertise-weighted knowledge. Wake only the agents you need. Each session builds on the last.

**One-call boot** — An agent calls `recall("I'm tech-architect on sigma-review, reviewing auth")` and gets back everything: personal memory, team decisions, patterns, roster, and teammates. No multi-step setup.

## How it works

sigma-mem exposes memory as a navigable state machine via MCP:

```
recall("working on prompt-coach")
  → state: project_work
  → core memory + project context
  → available: get_project, get_decisions, log_decision, get_failures, log_failure

recall("I'm tech-architect on sigma-review, reviewing code")
  → state: team_work
  → core memory + agent boot (personal memory + team decisions + roster + teammates)
  → available: get_roster, get_team_decisions, get_agent_memory, wake_check, store_team_decision
```

States: `idle`, `project_work`, `team_work`, `correcting`, `debugging`, `returning`, `reviewing`, `philosophical`

Each state unlocks different actions. The gateway detects context using weighted keyword scoring and surfaces the right memory with the right tools.

## Key concepts

- **HATEOAS navigation** — Memory files contain `→ action` links. Follow them to navigate. The state machine advertises available actions after every call.
- **Compressed notation** — `C[detects perf, honest>polish, probes|3|26.3]` stores what would take a paragraph in one line. Optimized for LLM token efficiency.
- **Anti-memories** — `¬[developer(leader learning to build)]` explicitly stores what is NOT true, preventing hallucinated beliefs.
- **Integrity checks** — Checksums, confidence markers (`~` = tentative), and promotion lifecycle (observed once → confirmed across sessions).
- **Expertise-weighted decisions** — Team decisions carry attribution: who decided, from which domain, with dissenting context preserved.

## Installation

```bash
pip install sigma-mem
```

Requires [hateoas-agent](https://github.com/bjgilbert/hateoas-agent) >= 0.1.0.

## Usage

### As an MCP server (Claude Code)

Add to `~/.claude.json`:

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

Four modules, ~550 lines:

- `machine.py` — Declarative HATEOAS state machine (states, actions, handler bindings)
- `handlers.py` — All read/write operations for personal and team memory
- `integrity.py` — Checksums, confidence detection, anti-memory verification
- `server.py` — MCP server entry point

Built on [hateoas-agent](https://github.com/bjgilbert/hateoas-agent) for state machine and MCP serving.

## License

MIT
