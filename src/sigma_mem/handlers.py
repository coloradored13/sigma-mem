"""File handlers for reading/writing compressed memory files."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .integrity import check_anti_memories, verify_file_integrity

# Default directories
DEFAULT_MEMORY_DIR = Path.home() / ".claude" / "memory"
DEFAULT_TEAMS_DIR = Path.home() / ".claude" / "teams"


def _today() -> str:
    """Return today's date as YY.M.D format."""
    d = date.today()
    return f"{d.year % 100}.{d.month}.{d.day}"


def _validate_path(memory_dir: Path, filename: str) -> Path | None:
    """Validate that filename resolves within memory_dir. Returns resolved path or None."""
    filepath = (memory_dir / filename).resolve()
    if not filepath.is_relative_to(memory_dir.resolve()):
        return None
    return filepath


def _read_file(memory_dir: Path, filename: str) -> str:
    """Read a memory file, return contents or error message."""
    filepath = _validate_path(memory_dir, filename)
    if filepath is None:
        return f"Invalid path: {filename}"
    if not filepath.exists():
        return f"File not found: {filename}"
    return filepath.read_text()


def _split_content_and_actions(content: str) -> tuple[str, list[str]]:
    """Split file into memory content and action links."""
    lines = content.splitlines()
    memory_lines = []
    action_lines = []
    for line in lines:
        if line.strip().startswith("→"):
            action_lines.append(line.strip())
        else:
            memory_lines.append(line)
    return "\n".join(memory_lines).strip(), action_lines


# --- Gateway handler ---


def handle_recall(
    context: str = "",
    memory_dir: Path = DEFAULT_MEMORY_DIR,
    teams_dir: Path = DEFAULT_TEAMS_DIR,
) -> dict[str, Any]:
    """Gateway: detect conversation context and return core memories.

    Always returns the core identity from MEMORY.md.
    The _state returned drives which actions become available.
    If a team is detected in context, surfaces team info too.
    """
    # Check anti-memories first
    warnings = check_anti_memories(context, memory_dir)

    # Read core memory
    core = _read_file(memory_dir, "MEMORY.md")
    core_content, core_actions = _split_content_and_actions(core)

    # Detect state from context
    state = _detect_state(context, memory_dir, teams_dir)

    result: dict[str, Any] = {
        "core_memory": core_content,
        "detected_context": state,
        "_state": state,
    }

    if warnings:
        result["anti_memory_warnings"] = warnings

    if core_actions:
        result["navigation_hints"] = core_actions

    # If team context detected, surface team info
    if state == "team_work":
        team_name = _detect_team_from_context(context, teams_dir)
        if team_name:
            result["detected_team"] = team_name

            # Check if caller is identifying as a specific agent
            agent_name = _detect_agent_identity(context, team_name, teams_dir)

            if agent_name:
                # Agent boot: load everything they need in one call
                result["agent_identity"] = agent_name
                result["agent_boot"] = _build_agent_boot(
                    team_name, agent_name, teams_dir
                )
            else:
                # Lead/user: just surface the roster
                roster = _read_team_file(teams_dir, team_name, "shared/roster.md")
                if roster:
                    result["team_roster"] = roster
        else:
            result["available_teams"] = _get_team_names(teams_dir)

    return result


def _detect_state(
    context: str,
    memory_dir: Path = DEFAULT_MEMORY_DIR,
    teams_dir: Path = DEFAULT_TEAMS_DIR,
) -> str:
    """Detect conversation state from context description using weighted scoring.

    Each state has weighted keywords. Phrases score higher than single words.
    Highest-scoring state wins. Ties go to the first in definition order.
    """
    ctx = context.lower()

    # (keyword, weight) — phrases get higher weight than single words
    state_signals: dict[str, list[tuple[str, int]]] = {
        "team_work": [
            ("team review", 3), ("wake the team", 3), ("agent team", 3),
            ("team decision", 3), ("roster", 2), ("team memory", 2),
            ("team", 1), ("agents", 1),
        ],
        "correcting": [
            ("you're wrong", 3), ("that's incorrect", 3), ("no, that's not", 3),
            ("actually it's", 2), ("incorrect", 2), ("you got that wrong", 3),
            ("wrong", 1), ("no,", 1), ("correct that", 2),
        ],
        "debugging": [
            ("traceback", 3), ("stack trace", 3), ("error message", 2),
            ("debug", 2), ("broken", 2), ("bug", 1), ("fix", 1), ("error", 1),
        ],
        "returning": [
            ("been a while", 3), ("catch me up", 3), ("what's new", 2),
            ("coming back", 2), ("refresh my memory", 3), ("where were we", 3),
        ],
        "reviewing": [
            ("last time we", 3), ("remember when", 2), ("previously", 2),
            ("look back", 2), ("history of", 2), ("past decisions", 3),
            ("before", 1),
        ],
        "project_work": [
            ("working on", 2), ("build", 1), ("feature", 1),
            ("implement", 2), ("project", 1), ("code", 1),
        ],
        "philosophical": [
            ("what if", 2), ("why do you", 2), ("how do you think", 3),
            ("philosophy", 3), ("what does it mean", 3), ("feel about", 2),
        ],
    }

    # Score each state
    scores: dict[str, int] = {}
    for state, signals in state_signals.items():
        score = sum(weight for keyword, weight in signals if keyword in ctx)
        if score > 0:
            scores[state] = score

    # Check for known project names (strong signal)
    project_names = _get_project_names(memory_dir)
    if any(name in ctx for name in project_names):
        scores["project_work"] = scores.get("project_work", 0) + 3

    # Check for known team names (strong signal)
    team_names = _get_team_names(teams_dir)
    if any(name in ctx for name in team_names):
        scores["team_work"] = scores.get("team_work", 0) + 3

    if not scores:
        return "idle"

    return max(scores, key=scores.get)


def _get_team_names(teams_dir: Path) -> list[str]:
    """Get known team names from the teams directory."""
    if not teams_dir.exists():
        return []
    return [d.name for d in sorted(teams_dir.iterdir()) if d.is_dir()]


def _detect_team_from_context(context: str, teams_dir: Path) -> str | None:
    """Find which team is being referenced in the context, if any."""
    ctx = context.lower()
    for name in _get_team_names(teams_dir):
        if name in ctx:
            return name
    return None


def _detect_agent_identity(
    context: str, team_name: str, teams_dir: Path
) -> str | None:
    """Detect if the caller is identifying as a specific agent on a team.

    Looks for patterns like "I'm tech-architect" or "I am the ux-researcher"
    and cross-references against the team roster.
    """
    ctx = context.lower()
    team_dir = teams_dir / team_name / "agents"
    if not team_dir.exists():
        return None

    agent_names = [d.name for d in sorted(team_dir.iterdir()) if d.is_dir()]
    for name in agent_names:
        # Check for identity patterns
        if any(pattern in ctx for pattern in [
            f"i'm {name}", f"i am {name}", f"i'm the {name}",
            f"i am the {name}", f"as {name}", f"agent {name}",
            f"{name} here", f"{name} reporting",
        ]):
            return name

    # Fallback: check if agent name appears at all in context
    for name in agent_names:
        if name in ctx:
            return name

    return None


def _get_project_names(memory_dir: Path) -> list[str]:
    """Extract known project names from projects.md."""
    filepath = memory_dir / "projects.md"
    if not filepath.exists():
        return []
    content = filepath.read_text().lower()
    names = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("→"):
            continue
        # Extract first word/identifier before [ or |
        for sep in ["[", "|"]:
            if sep in line:
                name = line.split(sep)[0].strip().lstrip("*")
                if name and len(name) > 2:
                    names.append(name)
                break
    return names


def _build_agent_boot(
    team_name: str, agent_name: str, teams_dir: Path
) -> dict[str, Any]:
    """Build a complete boot package for an agent — everything they need in one call.

    Returns personal memory, team decisions, team patterns, roster,
    and a list of teammate names for cross-reference.
    """
    boot: dict[str, Any] = {"team": team_name, "agent": agent_name}

    # Personal memory
    personal = _read_team_file(teams_dir, team_name, f"agents/{agent_name}/memory.md")
    if personal:
        mem, actions = _split_content_and_actions(personal)
        boot["personal_memory"] = mem
        boot["personal_actions"] = actions

    # Team shared context
    decisions = _read_team_file(teams_dir, team_name, "shared/decisions.md")
    if decisions:
        mem, _ = _split_content_and_actions(decisions)
        boot["team_decisions"] = mem

    patterns = _read_team_file(teams_dir, team_name, "shared/patterns.md")
    if patterns:
        mem, _ = _split_content_and_actions(patterns)
        boot["team_patterns"] = mem

    roster = _read_team_file(teams_dir, team_name, "shared/roster.md")
    if roster:
        mem, _ = _split_content_and_actions(roster)
        boot["roster"] = mem

    # List teammates for cross-reference awareness
    agents_dir = teams_dir / team_name / "agents"
    if agents_dir.exists():
        boot["teammates"] = [
            d.name for d in sorted(agents_dir.iterdir())
            if d.is_dir() and d.name != agent_name
        ]

    return boot


# --- State-specific action handlers ---


def handle_get_project(name: str = "", memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load project state from projects.md."""
    content = _read_file(memory_dir, "projects.md")
    mem, actions = _split_content_and_actions(content)

    # Filter to specific project if name provided
    if name:
        lines = [l for l in mem.splitlines() if name.lower() in l.lower()]
        mem = "\n".join(lines) if lines else f"No project matching '{name}' found"

    return {"projects": mem, "navigation": actions, "_state": "project_work"}


def handle_get_decisions(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load past decisions from decisions.md."""
    content = _read_file(memory_dir, "decisions.md")
    mem, actions = _split_content_and_actions(content)
    return {"decisions": mem, "navigation": actions, "_state": "project_work"}


def handle_get_corrections(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load correction history from corrections.md."""
    content = _read_file(memory_dir, "corrections.md")
    mem, actions = _split_content_and_actions(content)
    return {"corrections": mem, "navigation": actions, "_state": "correcting"}


def handle_get_user_model(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load deep user model from user.md."""
    content = _read_file(memory_dir, "user.md")
    mem, actions = _split_content_and_actions(content)
    return {"user_model": mem, "navigation": actions, "_state": "philosophical"}


def handle_get_patterns(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load cross-cutting patterns from patterns.md."""
    content = _read_file(memory_dir, "patterns.md")
    mem, actions = _split_content_and_actions(content)
    return {"patterns": mem, "navigation": actions, "_state": "philosophical"}


def handle_get_conversations(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load conversation history from conv.md."""
    content = _read_file(memory_dir, "conv.md")
    mem, actions = _split_content_and_actions(content)
    return {"conversations": mem, "navigation": actions, "_state": "reviewing"}


def handle_get_failures(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load failure log from failures.md."""
    content = _read_file(memory_dir, "failures.md")
    mem, actions = _split_content_and_actions(content)
    return {"failures": mem, "navigation": actions, "_state": "debugging"}


def handle_get_meta(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load system evolution log from meta.md."""
    content = _read_file(memory_dir, "meta.md")
    mem, actions = _split_content_and_actions(content)
    return {"meta": mem, "navigation": actions, "_state": "idle"}


def handle_full_refresh(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load broad context for returning after a gap."""
    core = _read_file(memory_dir, "MEMORY.md")
    conv = _read_file(memory_dir, "conv.md")
    user = _read_file(memory_dir, "user.md")
    projects = _read_file(memory_dir, "projects.md")

    return {
        "core": core,
        "recent_conversations": conv,
        "user_model": user,
        "projects": projects,
        "_state": "returning",
    }


def handle_verify_beliefs(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Surface stored beliefs for user verification."""
    core = _read_file(memory_dir, "MEMORY.md")

    # Extract tentative beliefs (C~ lines)
    tentative = [l for l in core.splitlines() if "~[" in l or l.strip().startswith("C~")]
    # Extract confirmed beliefs
    confirmed = [l for l in core.splitlines() if l.strip().startswith("C[")]

    return {
        "tentative_beliefs": tentative,
        "confirmed_beliefs": confirmed,
        "instruction": "Surface these to the user and ask: 'still accurate?'",
        "_state": "returning",
    }


def handle_check_integrity(memory_dir: Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Run integrity checks across all memory files."""
    reports = []
    for md_file in sorted(memory_dir.glob("*.md")):
        report = verify_file_integrity(md_file)
        reports.append(report)
    return {"integrity_reports": reports, "_state": "idle"}


# --- Write handlers ---


def handle_store_memory(
    entry: str, file: str = "conv.md", memory_dir: Path = DEFAULT_MEMORY_DIR
) -> dict[str, Any]:
    """Append a new entry to a memory file."""
    filepath = _validate_path(memory_dir, file)
    if filepath is None:
        return {"error": f"Invalid path: {file}", "_state": "idle"}
    if not filepath.exists():
        return {"error": f"File not found: {file}", "_state": "idle"}

    content = filepath.read_text()
    mem_content, actions = _split_content_and_actions(content)

    # Append the new entry before action links
    new_content = mem_content + f"\n{entry}\n"
    if actions:
        new_content += "\n" + "\n".join(actions) + "\n"

    filepath.write_text(new_content)
    return {"stored": entry, "file": file, "_state": "idle"}


def handle_log_correction(
    error: str, fix: str, memory_dir: Path = DEFAULT_MEMORY_DIR
) -> dict[str, Any]:
    """Log a correction to corrections.md."""
    entry = f"{_today()}|{error}|{fix}"
    return handle_store_memory(entry, "corrections.md", memory_dir)


def handle_log_decision(
    choice: str, rationale: str, alternatives: str = "",
    memory_dir: Path = DEFAULT_MEMORY_DIR,
) -> dict[str, Any]:
    """Log a decision to decisions.md."""
    entry = f"{_today()}|{choice}|why: {rationale}"
    if alternatives:
        entry += f"|alt: {alternatives}"
    return handle_store_memory(entry, "decisions.md", memory_dir)


def handle_log_failure(
    what: str, why: str, memory_dir: Path = DEFAULT_MEMORY_DIR
) -> dict[str, Any]:
    """Log a failed approach to failures.md."""
    entry = f"{_today()}|{what}|{why}"
    return handle_store_memory(entry, "failures.md", memory_dir)


def handle_update_belief(
    old: str, new: str, memory_dir: Path = DEFAULT_MEMORY_DIR
) -> dict[str, Any]:
    """Update a stored belief in MEMORY.md."""
    filepath = memory_dir / "MEMORY.md"
    if not filepath.exists():
        return {"error": "MEMORY.md not found", "_state": "correcting"}

    content = filepath.read_text()
    if old not in content:
        return {"error": f"Old belief not found: {old}", "_state": "correcting"}

    content = content.replace(old, new, 1)
    filepath.write_text(content)
    return {"updated": {"old": old, "new": new}, "_state": "correcting"}


# --- Team handlers ---


def _read_team_file(teams_dir: Path, team_name: str, relative_path: str) -> str | None:
    """Safely read a file from a team directory."""
    team_dir = teams_dir / team_name
    filepath = (team_dir / relative_path).resolve()
    if not filepath.is_relative_to(team_dir.resolve()):
        return None
    if not filepath.exists():
        return None
    return filepath.read_text()


def handle_get_roster(
    team_name: str, teams_dir: Path = DEFAULT_TEAMS_DIR
) -> dict[str, Any]:
    """Load team roster with domains and wake-for rules."""
    content = _read_team_file(teams_dir, team_name, "shared/roster.md")
    if content is None:
        return {"error": f"Roster not found for team: {team_name}", "_state": "team_work"}
    mem, actions = _split_content_and_actions(content)
    return {"team": team_name, "roster": mem, "navigation": actions, "_state": "team_work"}


def handle_get_team_decisions(
    team_name: str, teams_dir: Path = DEFAULT_TEAMS_DIR
) -> dict[str, Any]:
    """Load expertise-weighted team decisions."""
    content = _read_team_file(teams_dir, team_name, "shared/decisions.md")
    if content is None:
        return {"error": f"No decisions found for team: {team_name}", "_state": "team_work"}
    mem, actions = _split_content_and_actions(content)
    return {"team": team_name, "decisions": mem, "navigation": actions, "_state": "team_work"}


def handle_get_team_patterns(
    team_name: str, teams_dir: Path = DEFAULT_TEAMS_DIR
) -> dict[str, Any]:
    """Load cross-agent patterns from team shared memory."""
    content = _read_team_file(teams_dir, team_name, "shared/patterns.md")
    if content is None:
        return {"error": f"No patterns found for team: {team_name}", "_state": "team_work"}
    mem, actions = _split_content_and_actions(content)
    return {"team": team_name, "patterns": mem, "navigation": actions, "_state": "team_work"}


def handle_get_agent_memory(
    team_name: str, agent_name: str, teams_dir: Path = DEFAULT_TEAMS_DIR
) -> dict[str, Any]:
    """Load a specific agent's personal memory."""
    content = _read_team_file(teams_dir, team_name, f"agents/{agent_name}/memory.md")
    if content is None:
        return {
            "error": f"No memory found for agent '{agent_name}' on team '{team_name}'",
            "_state": "team_work",
        }
    mem, actions = _split_content_and_actions(content)
    return {
        "team": team_name,
        "agent": agent_name,
        "memory": mem,
        "navigation": actions,
        "_state": "team_work",
    }


def handle_wake_check(
    task: str, team_name: str, teams_dir: Path = DEFAULT_TEAMS_DIR
) -> dict[str, Any]:
    """Check which agents should be woken for a given task."""
    content = _read_team_file(teams_dir, team_name, "shared/roster.md")
    if content is None:
        return {"error": f"Roster not found for team: {team_name}", "_state": "team_work"}

    task_lower = task.lower()
    recommendations = []
    for line in content.splitlines():
        if "|wake-for:" not in line:
            continue
        # Parse: agent_name |domain: ... |wake-for: trigger1,trigger2
        parts = line.split("|")
        agent_name = parts[0].strip()
        wake_for = ""
        for part in parts:
            if "wake-for:" in part:
                wake_for = part.split("wake-for:")[1].strip()
                break
        triggers = [t.strip() for t in wake_for.split(",")]
        matched = [t for t in triggers if any(word in task_lower for word in t.split())]
        if matched:
            recommendations.append({"agent": agent_name, "matched": matched})

    return {
        "team": team_name,
        "task": task,
        "wake": recommendations,
        "wake_count": len(recommendations),
        "_state": "team_work",
    }


def handle_store_team_decision(
    decision: str, by: str, context: str = "",
    team_name: str = "", teams_dir: Path = DEFAULT_TEAMS_DIR,
) -> dict[str, Any]:
    """Store an expertise-weighted decision in team shared memory."""
    team_dir = teams_dir / team_name / "shared"
    filepath = team_dir / "decisions.md"
    if not filepath.exists():
        return {"error": f"Decisions file not found for team: {team_name}", "_state": "team_work"}

    content = filepath.read_text()
    mem_content, actions = _split_content_and_actions(content)

    entry = f"\n{decision} |by:{by} |weight:primary"
    if context:
        entry += f"\n  |ctx: {context}"

    new_content = mem_content + entry + "\n"
    if actions:
        new_content += "\n" + "\n".join(actions) + "\n"

    filepath.write_text(new_content)
    return {"stored": decision, "by": by, "team": team_name, "_state": "team_work"}


def handle_search_memory(
    query: str, memory_dir: Path = DEFAULT_MEMORY_DIR
) -> dict[str, Any]:
    """Search across all memory files for a term."""
    results = {}
    for md_file in sorted(memory_dir.glob("*.md")):
        content = md_file.read_text()
        matches = [l.strip() for l in content.splitlines() if query.lower() in l.lower()]
        if matches:
            results[md_file.name] = matches

    warnings = check_anti_memories(query, memory_dir)

    return {
        "query": query,
        "matches": results,
        "anti_memory_warnings": warnings,
        "_state": "idle",
    }
