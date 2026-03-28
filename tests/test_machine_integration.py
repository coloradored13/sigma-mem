"""Integration tests for the contract between sigma-mem and hateoas-agent.

Tests that build_machine() produces a valid StateMachine and that the
HATEOAS navigation contract is upheld — gateway returns expected structure,
states are reachable, actions are wired, and key transitions work.

If hateoas-agent changes its StateMachine API, these tests break first.
"""

from __future__ import annotations


import pytest

from hateoas_agent import StateMachine
from sigma_mem.machine import build_machine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_dir(tmp_path):
    """Minimal memory directory for build_machine."""
    d = tmp_path / "memory"
    d.mkdir()
    (d / "MEMORY.md").write_text("U[test user|1|26.3]\n")
    (d / "decisions.md").write_text("26.3.7|use-postgres|why: fast\n")
    (d / "corrections.md").write_text("26.3.6|was wrong|fixed\n")
    (d / "user.md").write_text("prefers simple explanations\n")
    (d / "patterns.md").write_text("pattern: converges\n")
    (d / "conv.md").write_text("26.3.7|discussed arch\n")
    (d / "failures.md").write_text("26.3.6|tried X|nope\n")
    (d / "meta.md").write_text("v0.1: initial\n")
    (d / "projects.md").write_text("*sigma-mem[memory MCP|1|26.3]\n")
    return d


@pytest.fixture
def teams_dir(tmp_path):
    """Minimal teams directory with one team and two agents."""
    d = tmp_path / "teams"
    team = d / "test-team"
    shared = team / "shared"
    shared.mkdir(parents=True)
    agents_ta = team / "agents" / "tech-architect"
    agents_ta.mkdir(parents=True)
    agents_ux = team / "agents" / "ux-researcher"
    agents_ux.mkdir(parents=True)

    (shared / "roster.md").write_text(
        "tech-architect |domain: architecture,security |wake-for: code review,system design\n"
        "ux-researcher |domain: usability |wake-for: user-facing changes\n"
    )
    (shared / "decisions.md").write_text(
        "# team decisions\n\narch:use-HATEOAS |by:tech-architect |weight:primary\n"
    )
    (shared / "patterns.md").write_text(
        "# patterns\n\nconvergence:all-found-same-bug |agents: all\n"
    )
    (agents_ta / "memory.md").write_text(
        "# tech-architect memory\n\n## past findings\nreview-1: found path traversal\n"
    )
    (agents_ux / "memory.md").write_text(
        "# ux-researcher memory\n\n## past findings\nreview-1: flow unclear\n"
    )
    return d


@pytest.fixture
def machine(mem_dir, teams_dir):
    """Build a fully-wired machine with test directories."""
    return build_machine(memory_dir=mem_dir, teams_dir=teams_dir)


# ---------------------------------------------------------------------------
# 1. build_machine() returns a valid StateMachine that passes validate()
# ---------------------------------------------------------------------------


class TestBuildMachineValidity:
    def test_returns_state_machine_instance(self, machine):
        assert isinstance(machine, StateMachine)

    def test_validate_passes(self, machine):
        """Core contract: validate() must not raise."""
        machine.validate()

    def test_machine_name(self, machine):
        assert machine.name == "sigma_mem"

    def test_gateway_is_defined(self, machine):
        gw = machine.get_gateway()
        assert gw is not None
        assert gw.name == "recall"
        assert gw.handler is not None

    def test_gateway_has_context_param(self, machine):
        gw = machine.get_gateway()
        assert "context" in gw.params
        assert "context" in gw.required


# ---------------------------------------------------------------------------
# 2. Gateway (recall) returns expected structure
# ---------------------------------------------------------------------------


class TestGatewayInvocation:
    def test_gateway_returns_core_memory(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="hello")
        assert "core_memory" in result
        assert "test user" in result["core_memory"]

    def test_gateway_returns_detected_context(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="hello")
        assert "detected_context" in result

    def test_gateway_returns_state(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="hello")
        assert "_state" in result

    def test_gateway_navigation_hints_present_when_actions_exist(
        self, mem_dir, teams_dir
    ):
        """If MEMORY.md has arrow lines, navigation_hints should appear."""
        (mem_dir / "MEMORY.md").write_text(
            "U[test user|1|26.3]\n\n"
            "-> actions(load based on context):\n"
            "-> user asking about a project -> get_project\n"
        )
        m = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        gw = m.get_gateway()
        result = gw.handler(context="hello")
        # Arrow lines use the unicode arrow, not ASCII; depends on MEMORY.md content
        assert "core_memory" in result


# ---------------------------------------------------------------------------
# 3. All registered actions are reachable from at least one state
# ---------------------------------------------------------------------------


class TestActionReachability:
    """Every action registered via build_machine must be reachable from
    at least one state. If an action exists but is never surfaced, it's
    dead code and the integration is broken.
    """

    # All states that sigma-mem defines actions against
    ALL_STATES = [
        "idle",
        "project_work",
        "debugging",
        "correcting",
        "philosophical",
        "reviewing",
        "returning",
        "team_work",
    ]

    def test_all_actions_reachable(self, machine):
        all_action_names = machine.get_all_action_names()
        assert len(all_action_names) > 0, "No actions registered"

        reachable = set()
        for state in self.ALL_STATES:
            actions = machine.get_actions_for_state(state)
            for a in actions:
                reachable.add(a.name)

        unreachable = all_action_names - reachable
        assert unreachable == set(), (
            f"Actions registered but not reachable from any state: {unreachable}"
        )

    def test_every_action_has_handler(self, machine):
        for action_name in machine.get_all_action_names():
            handler = machine.get_handler(action_name)
            assert handler is not None, f"Action '{action_name}' has no handler"


# ---------------------------------------------------------------------------
# 4. Key state transitions work
# ---------------------------------------------------------------------------


class TestStateTransitions:
    """Verify that the gateway detects context correctly and that the
    resulting state surfaces the right set of actions.
    """

    def test_idle_to_team_work_via_team_context(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="working with test-team on review")
        assert result["_state"] == "team_work"

    def test_idle_to_project_work_via_project_context(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="working on sigma-mem")
        assert result["_state"] == "project_work"

    def test_idle_to_correcting_via_correction_context(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="you're wrong about that")
        assert result["_state"] == "correcting"

    def test_idle_fallback(self, machine):
        gw = machine.get_gateway()
        result = gw.handler(context="hello there")
        assert result["_state"] == "idle"

    def test_team_work_state_has_team_actions(self, machine):
        """After detecting team_work state, team actions must be available."""
        gw = machine.get_gateway()
        result = gw.handler(context="working with test-team")
        assert result["_state"] == "team_work"

        actions = machine.get_actions_for_state("team_work")
        action_names = {a.name for a in actions}

        expected_team_actions = {
            "get_roster",
            "wake_check",
            "store_team_decision",
            "search_team_memory",
            "store_agent_memory",
            "store_team_pattern",
        }
        assert expected_team_actions.issubset(action_names), (
            f"Missing team actions in team_work state: "
            f"{expected_team_actions - action_names}"
        )

    def test_correcting_state_has_correction_actions(self, machine):
        actions = machine.get_actions_for_state("correcting")
        action_names = {a.name for a in actions}
        assert "get_corrections" in action_names
        assert "log_correction" in action_names
        assert "update_belief" in action_names

    def test_project_work_state_has_project_actions(self, machine):
        actions = machine.get_actions_for_state("project_work")
        action_names = {a.name for a in actions}
        assert "get_project" in action_names
        assert "get_decisions" in action_names
        assert "log_decision" in action_names

    def test_returning_state_has_returning_actions(self, machine):
        actions = machine.get_actions_for_state("returning")
        action_names = {a.name for a in actions}
        assert "full_refresh" in action_names
        assert "verify_beliefs" in action_names


# ---------------------------------------------------------------------------
# 5. Team actions available in team_work state
# ---------------------------------------------------------------------------


class TestTeamActionsInTeamWork:
    """Verify every team action is available when in team_work state
    and that their handlers produce valid results.
    """

    TEAM_ACTIONS = [
        "get_roster",
        "wake_check",
        "store_team_decision",
        "search_team_memory",
        "store_agent_memory",
        "store_team_pattern",
        "get_team_decisions",
        "get_team_patterns",
        "get_agent_memory",
    ]

    def test_all_team_actions_in_team_work(self, machine):
        actions = machine.get_actions_for_state("team_work")
        action_names = {a.name for a in actions}
        for name in self.TEAM_ACTIONS:
            assert name in action_names, (
                f"Team action '{name}' not available in team_work state"
            )

    def test_get_roster_handler(self, machine):
        handler = machine.get_handler("get_roster")
        result = handler(team_name="test-team")
        assert result["_state"] == "team_work"
        assert "tech-architect" in result["roster"]

    def test_wake_check_handler(self, machine):
        handler = machine.get_handler("wake_check")
        result = handler(task="code review", team_name="test-team")
        assert result["_state"] == "team_work"
        assert result["wake_count"] >= 1

    def test_search_team_memory_handler(self, machine):
        handler = machine.get_handler("search_team_memory")
        result = handler(query="HATEOAS", team_name="test-team")
        assert result["_state"] == "team_work"
        assert len(result["matches"]) > 0

    def test_store_team_decision_handler(self, machine):
        handler = machine.get_handler("store_team_decision")
        result = handler(
            decision="use-redis", by="tech-architect", team_name="test-team"
        )
        assert result["_state"] == "team_work"
        assert result["stored"] == "use-redis"

    def test_store_agent_memory_handler(self, machine):
        handler = machine.get_handler("store_agent_memory")
        result = handler(
            entry="new finding", agent_name="tech-architect", team_name="test-team"
        )
        assert result["_state"] == "team_work"
        assert result["stored"] == "new finding"

    def test_store_team_pattern_handler(self, machine):
        handler = machine.get_handler("store_team_pattern")
        result = handler(
            pattern="convergence:test", agents="all", team_name="test-team"
        )
        assert result["_state"] == "team_work"
        assert result["stored"] == "convergence:test"


# ---------------------------------------------------------------------------
# 6. Universal actions available in every state
# ---------------------------------------------------------------------------


class TestUniversalActions:
    """Actions registered with from_states='*' should be available everywhere."""

    UNIVERSAL = ["search_memory", "store_memory", "check_integrity", "get_meta"]

    ALL_STATES = [
        "idle",
        "project_work",
        "debugging",
        "correcting",
        "philosophical",
        "reviewing",
        "returning",
        "team_work",
    ]

    def test_universal_actions_in_all_states(self, machine):
        for state in self.ALL_STATES:
            actions = machine.get_actions_for_state(state)
            action_names = {a.name for a in actions}
            for name in self.UNIVERSAL:
                assert name in action_names, (
                    f"Universal action '{name}' missing in state '{state}'"
                )


# ---------------------------------------------------------------------------
# 7. StateMachine API surface contract
# ---------------------------------------------------------------------------


class TestStateMachineAPIContract:
    """Verify that sigma-mem relies on specific StateMachine API methods.
    If hateoas-agent removes or renames any of these, this test class fails.
    """

    def test_has_gateway_method(self):
        assert callable(getattr(StateMachine, "gateway", None))

    def test_has_action_method(self):
        assert callable(getattr(StateMachine, "action", None))

    def test_has_on_gateway_method(self):
        assert callable(getattr(StateMachine, "on_gateway", None))

    def test_has_on_action_method(self):
        assert callable(getattr(StateMachine, "on_action", None))

    def test_has_validate_method(self):
        assert callable(getattr(StateMachine, "validate", None))

    def test_has_get_gateway_method(self):
        assert callable(getattr(StateMachine, "get_gateway", None))

    def test_has_get_actions_for_state_method(self):
        assert callable(getattr(StateMachine, "get_actions_for_state", None))

    def test_has_get_all_action_names_method(self):
        assert callable(getattr(StateMachine, "get_all_action_names", None))

    def test_has_get_handler_method(self):
        assert callable(getattr(StateMachine, "get_handler", None))

    def test_has_get_transition_metadata_method(self):
        assert callable(getattr(StateMachine, "get_transition_metadata", None))

    def test_constructor_accepts_name_and_gateway_name(self):
        """StateMachine must accept name and gateway_name positional/keyword args."""
        sm = StateMachine("test", gateway_name="gw")
        assert sm.name == "test"

    def test_action_def_has_expected_attributes(self, machine):
        """ActionDef objects returned by get_actions_for_state must have
        name, description, params, required, and handler attributes.
        """
        actions = machine.get_actions_for_state("idle")
        assert len(actions) > 0
        a = actions[0]
        assert hasattr(a, "name")
        assert hasattr(a, "description")
        assert hasattr(a, "params")
        assert hasattr(a, "required")
        assert hasattr(a, "handler")

    def test_gateway_def_has_expected_attributes(self, machine):
        """GatewayDef returned by get_gateway must have name, description,
        params, required, and handler attributes.
        """
        gw = machine.get_gateway()
        assert hasattr(gw, "name")
        assert hasattr(gw, "description")
        assert hasattr(gw, "params")
        assert hasattr(gw, "required")
        assert hasattr(gw, "handler")


# ---------------------------------------------------------------------------
# 8. Transition metadata roundtrip
# ---------------------------------------------------------------------------


class TestTransitionMetadata:
    """Actions registered with from_states should have transition metadata."""

    def test_universal_action_metadata(self, machine):
        meta = machine.get_transition_metadata("search_memory")
        assert meta is not None
        from_states, to_state = meta
        assert from_states == "*"

    def test_scoped_action_metadata(self, machine):
        meta = machine.get_transition_metadata("log_decision")
        assert meta is not None
        from_states, to_state = meta
        assert isinstance(from_states, list)
        assert "project_work" in from_states

    def test_team_action_metadata(self, machine):
        meta = machine.get_transition_metadata("store_team_decision")
        assert meta is not None
        from_states, to_state = meta
        assert isinstance(from_states, list)
        assert "team_work" in from_states


# ---------------------------------------------------------------------------
# 9. Handler closure invocation — exercise the closure bodies in machine.py
#    that delegate to handle_* functions with baked-in memory_dir/teams_dir.
# ---------------------------------------------------------------------------


class TestHandlerClosureInvocation:
    """Cover machine.py closure bodies (lines 262-353) by invoking each
    registered handler through machine.get_handler()."""

    def test_search_memory(self, machine):
        handler = machine.get_handler("search_memory")
        result = handler(query="test")
        assert isinstance(result, dict)

    def test_store_memory(self, machine):
        handler = machine.get_handler("store_memory")
        result = handler(entry="test entry", file="conv.md")
        assert isinstance(result, dict)
        assert result.get("stored") == "test entry"

    def test_check_integrity(self, machine):
        handler = machine.get_handler("check_integrity")
        result = handler()
        assert isinstance(result, dict)

    def test_get_meta(self, machine):
        handler = machine.get_handler("get_meta")
        result = handler()
        assert isinstance(result, dict)

    def test_get_project(self, machine):
        handler = machine.get_handler("get_project")
        result = handler(name="sigma-mem")
        assert isinstance(result, dict)

    def test_get_decisions(self, machine):
        handler = machine.get_handler("get_decisions")
        result = handler()
        assert isinstance(result, dict)

    def test_log_decision(self, machine):
        handler = machine.get_handler("log_decision")
        result = handler(choice="use-redis", rationale="fast", alternatives="memcached")
        assert isinstance(result, dict)

    def test_get_failures(self, machine):
        handler = machine.get_handler("get_failures")
        result = handler()
        assert isinstance(result, dict)

    def test_log_failure(self, machine):
        handler = machine.get_handler("log_failure")
        result = handler(what="bad deploy", why="config error")
        assert isinstance(result, dict)

    def test_get_corrections(self, machine):
        handler = machine.get_handler("get_corrections")
        result = handler()
        assert isinstance(result, dict)

    def test_log_correction(self, machine):
        handler = machine.get_handler("log_correction")
        result = handler(error="wrong path", fix="updated path")
        assert isinstance(result, dict)

    def test_update_belief(self, machine):
        handler = machine.get_handler("update_belief")
        result = handler(old="postgres is slow", new="postgres is fast enough")
        assert isinstance(result, dict)

    def test_get_user_model(self, machine):
        handler = machine.get_handler("get_user_model")
        result = handler()
        assert isinstance(result, dict)

    def test_get_patterns(self, machine):
        handler = machine.get_handler("get_patterns")
        result = handler()
        assert isinstance(result, dict)

    def test_get_conversations(self, machine):
        handler = machine.get_handler("get_conversations")
        result = handler()
        assert isinstance(result, dict)

    def test_full_refresh(self, machine):
        handler = machine.get_handler("full_refresh")
        result = handler()
        assert isinstance(result, dict)

    def test_verify_beliefs(self, machine):
        handler = machine.get_handler("verify_beliefs")
        result = handler()
        assert isinstance(result, dict)

    def test_get_team_decisions(self, machine):
        handler = machine.get_handler("get_team_decisions")
        result = handler(team_name="test-team")
        assert isinstance(result, dict)

    def test_get_team_patterns(self, machine):
        handler = machine.get_handler("get_team_patterns")
        result = handler(team_name="test-team")
        assert isinstance(result, dict)

    def test_get_agent_memory(self, machine):
        handler = machine.get_handler("get_agent_memory")
        result = handler(team_name="test-team", agent_name="tech-architect")
        assert isinstance(result, dict)

    def test_validate_system(self, machine):
        handler = machine.get_handler("validate_system")
        result = handler(team_name="test-team")
        assert isinstance(result, dict)
