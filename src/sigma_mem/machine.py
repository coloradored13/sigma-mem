"""State machine definition for ΣMem — memory retrieval as HATEOAS navigation."""

from __future__ import annotations

from pathlib import Path

from hateoas_agent import StateMachine

from .handlers import (
    DEFAULT_MEMORY_DIR,
    DEFAULT_TEAMS_DIR,
    handle_check_integrity,
    handle_full_refresh,
    handle_get_agent_memory,
    handle_get_conversations,
    handle_get_corrections,
    handle_get_decisions,
    handle_get_failures,
    handle_get_meta,
    handle_get_patterns,
    handle_get_project,
    handle_get_roster,
    handle_get_team_decisions,
    handle_get_team_patterns,
    handle_get_user_model,
    handle_log_correction,
    handle_log_decision,
    handle_log_failure,
    handle_recall,
    handle_search_memory,
    handle_store_memory,
    handle_store_team_decision,
    handle_update_belief,
    handle_verify_beliefs,
    handle_wake_check,
)


def build_machine(
    memory_dir: Path = DEFAULT_MEMORY_DIR,
    teams_dir: Path = DEFAULT_TEAMS_DIR,
) -> StateMachine:
    """Build the ΣMem state machine.

    States represent conversation contexts. Actions are memory operations
    that are valid for each context. The gateway detects context and
    returns core identity memories.
    """
    mem = StateMachine("sigma_mem", gateway_name="recall")

    # --- Gateway ---
    mem.gateway(
        description=(
            "Recall memories relevant to the current conversation. "
            "Describe what's happening so the system can detect context "
            "and surface the right memories."
        ),
        params={"context": "string"},
        required=["context"],
    )

    # --- Universal actions (available in every state) ---
    mem.action(
        "search_memory",
        description="Search across all memory files for a term",
        from_states="*",
        params={"query": "string"},
        required=["query"],
    )
    mem.action(
        "store_memory",
        description="Append a new entry to a memory file",
        from_states="*",
        params={"entry": "string", "file": "string"},
        required=["entry", "file"],
    )
    mem.action(
        "check_integrity",
        description="Run integrity checks (checksums, confidence) across all memory files",
        from_states="*",
    )
    mem.action(
        "get_meta",
        description="Load the system evolution log — how this memory system has changed",
        from_states="*",
    )

    # --- Project work ---
    mem.action(
        "get_project",
        description="Load state for a specific project",
        from_states=["project_work", "idle", "debugging"],
        params={"name": "string"},
    )
    mem.action(
        "get_decisions",
        description="Load past decisions to avoid revisiting settled choices",
        from_states=["project_work", "idle", "reviewing"],
    )
    mem.action(
        "log_decision",
        description="Record a new architectural or design decision with rationale",
        from_states=["project_work"],
        params={"choice": "string", "rationale": "string", "alternatives": "string"},
        required=["choice", "rationale"],
    )
    mem.action(
        "get_failures",
        description="Load past failures to avoid repeating them",
        from_states=["project_work", "debugging"],
    )
    mem.action(
        "log_failure",
        description="Record an approach that didn't work and why",
        from_states=["project_work", "debugging"],
        params={"what": "string", "why": "string"},
        required=["what", "why"],
    )

    # --- Being corrected ---
    mem.action(
        "get_corrections",
        description="Load correction history to check if this is a repeat pattern",
        from_states=["correcting", "idle"],
    )
    mem.action(
        "log_correction",
        description="Record what was wrong and the fix applied",
        from_states=["correcting"],
        params={"error": "string", "fix": "string"},
        required=["error", "fix"],
    )
    mem.action(
        "update_belief",
        description="Modify a stored belief that has been corrected",
        from_states=["correcting"],
        params={"old": "string", "new": "string"},
        required=["old", "new"],
    )

    # --- Philosophical / deep conversation ---
    mem.action(
        "get_user_model",
        description="Load deep model of how the user thinks and communicates",
        from_states=["philosophical", "idle"],
    )
    mem.action(
        "get_patterns",
        description="Load cross-cutting patterns observed across conversations",
        from_states=["philosophical", "reviewing"],
    )

    # --- Reviewing past work ---
    mem.action(
        "get_conversations",
        description="Load conversation history and lessons learned",
        from_states=["reviewing", "returning", "idle"],
    )

    # --- Returning after a gap ---
    mem.action(
        "full_refresh",
        description="Load broad context — core memory, recent conversations, user model, projects",
        from_states=["returning"],
    )
    mem.action(
        "verify_beliefs",
        description="Surface stored beliefs (tentative and confirmed) for user verification",
        from_states=["returning", "idle"],
    )

    # --- Team work ---
    mem.action(
        "get_roster",
        description="Load team roster — who's on the team, their domains, and wake-for rules",
        from_states=["team_work", "idle"],
        params={"team_name": "string"},
        required=["team_name"],
    )
    mem.action(
        "get_team_decisions",
        description="Load expertise-weighted decisions from team shared memory",
        from_states=["team_work", "idle", "reviewing"],
        params={"team_name": "string"},
        required=["team_name"],
    )
    mem.action(
        "get_team_patterns",
        description="Load cross-agent patterns from team shared memory",
        from_states=["team_work", "idle"],
        params={"team_name": "string"},
        required=["team_name"],
    )
    mem.action(
        "get_agent_memory",
        description="Load a specific agent's personal memory from the team",
        from_states=["team_work"],
        params={"team_name": "string", "agent_name": "string"},
        required=["team_name", "agent_name"],
    )
    mem.action(
        "wake_check",
        description="Check which agents should be woken for a task based on roster domains",
        from_states=["team_work", "idle"],
        params={"task": "string", "team_name": "string"},
        required=["task", "team_name"],
    )
    mem.action(
        "store_team_decision",
        description="Record an expertise-weighted decision in team shared memory",
        from_states=["team_work"],
        params={
            "decision": "string",
            "by": "string",
            "context": "string",
            "team_name": "string",
        },
        required=["decision", "by", "team_name"],
    )

    # --- Register handlers ---
    # Bind handlers with memory_dir baked in via closures

    @mem.on_gateway
    def _recall(context=""):
        return handle_recall(context, memory_dir, teams_dir)

    @mem.on_action("search_memory")
    def _search(query=""):
        return handle_search_memory(query, memory_dir)

    @mem.on_action("store_memory")
    def _store(entry="", file="conv.md"):
        return handle_store_memory(entry, file, memory_dir)

    @mem.on_action("check_integrity")
    def _integrity():
        return handle_check_integrity(memory_dir)

    @mem.on_action("get_meta")
    def _meta():
        return handle_get_meta(memory_dir)

    @mem.on_action("get_project")
    def _project(name=""):
        return handle_get_project(name, memory_dir)

    @mem.on_action("get_decisions")
    def _decisions():
        return handle_get_decisions(memory_dir)

    @mem.on_action("log_decision")
    def _log_decision(choice="", rationale="", alternatives=""):
        return handle_log_decision(choice, rationale, alternatives, memory_dir)

    @mem.on_action("get_failures")
    def _failures():
        return handle_get_failures(memory_dir)

    @mem.on_action("log_failure")
    def _log_failure(what="", why=""):
        return handle_log_failure(what, why, memory_dir)

    @mem.on_action("get_corrections")
    def _corrections():
        return handle_get_corrections(memory_dir)

    @mem.on_action("log_correction")
    def _log_correction(error="", fix=""):
        return handle_log_correction(error, fix, memory_dir)

    @mem.on_action("update_belief")
    def _update_belief(old="", new=""):
        return handle_update_belief(old, new, memory_dir)

    @mem.on_action("get_user_model")
    def _user_model():
        return handle_get_user_model(memory_dir)

    @mem.on_action("get_patterns")
    def _patterns():
        return handle_get_patterns(memory_dir)

    @mem.on_action("get_conversations")
    def _conversations():
        return handle_get_conversations(memory_dir)

    @mem.on_action("full_refresh")
    def _refresh():
        return handle_full_refresh(memory_dir)

    @mem.on_action("verify_beliefs")
    def _verify():
        return handle_verify_beliefs(memory_dir)

    # --- Team handlers ---

    @mem.on_action("get_roster")
    def _roster(team_name=""):
        return handle_get_roster(team_name, teams_dir)

    @mem.on_action("get_team_decisions")
    def _team_decisions(team_name=""):
        return handle_get_team_decisions(team_name, teams_dir)

    @mem.on_action("get_team_patterns")
    def _team_patterns(team_name=""):
        return handle_get_team_patterns(team_name, teams_dir)

    @mem.on_action("get_agent_memory")
    def _agent_memory(team_name="", agent_name=""):
        return handle_get_agent_memory(team_name, agent_name, teams_dir)

    @mem.on_action("wake_check")
    def _wake_check(task="", team_name=""):
        return handle_wake_check(task, team_name, teams_dir)

    @mem.on_action("store_team_decision")
    def _store_team_decision(decision="", by="", context="", team_name=""):
        return handle_store_team_decision(decision, by, context, team_name, teams_dir)

    return mem
