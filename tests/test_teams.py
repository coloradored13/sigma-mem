"""Tests for team memory handlers — roster, decisions, agent memory, wake check."""

from pathlib import Path

import pytest

from sigma_mem.handlers import (
    _detect_agent_identity,
    _detect_state,
    _detect_team_from_context,
    _get_team_names,
    _validate_team_name,
    handle_get_agent_memory,
    handle_get_roster,
    handle_get_team_decisions,
    handle_get_team_patterns,
    handle_recall,
    handle_store_team_decision,
    handle_wake_check,
)


@pytest.fixture
def team_dir(tmp_path):
    """Create a minimal team directory structure."""
    team = tmp_path / "test-team"
    shared = team / "shared"
    shared.mkdir(parents=True)
    agents = team / "agents" / "tech-architect"
    agents.mkdir(parents=True)

    (shared / "roster.md").write_text(
        "tech-architect |domain: architecture,security |wake-for: code review,system design\n"
        "ux-researcher |domain: usability |wake-for: user-facing changes\n"
        "\n→ actions:\n→ test action\n"
    )
    (shared / "decisions.md").write_text(
        "# team decisions\n\narch:use-HATEOAS |by:tech-architect |weight:primary\n"
        "\n→ actions:\n→ new decision → append\n"
    )
    (shared / "patterns.md").write_text(
        "# patterns\n\nconvergence:all-found-same-bug |agents: all\n"
        "\n→ actions:\n→ new pattern → append\n"
    )
    (agents / "memory.md").write_text(
        "# tech-architect memory\n\n## past findings\nreview-1: found path traversal\n"
        "\n→ actions:\n→ review again → check past findings\n"
    )
    return tmp_path


class TestGetTeamNames:
    def test_finds_teams(self, team_dir):
        names = _get_team_names(team_dir)
        assert "test-team" in names

    def test_empty_dir(self, tmp_path):
        assert _get_team_names(tmp_path) == []

    def test_missing_dir(self, tmp_path):
        assert _get_team_names(tmp_path / "nonexistent") == []


class TestDetectTeamFromContext:
    def test_finds_team(self, team_dir):
        assert _detect_team_from_context("working with test-team", team_dir) == "test-team"

    def test_no_match(self, team_dir):
        assert _detect_team_from_context("just coding", team_dir) is None


class TestDetectStateTeam:
    def test_team_keywords(self, tmp_path):
        assert _detect_state("wake the team for a review", tmp_path, tmp_path) == "team_work"

    def test_team_name_match(self, team_dir):
        mem_dir = team_dir / "memory"
        mem_dir.mkdir()
        assert _detect_state("working with test-team", mem_dir, team_dir) == "team_work"


class TestGetRoster:
    def test_reads_roster(self, team_dir):
        result = handle_get_roster("test-team", team_dir)
        assert "tech-architect" in result["roster"]
        assert result["_state"] == "team_work"

    def test_missing_team(self, team_dir):
        result = handle_get_roster("nonexistent", team_dir)
        assert "error" in result


class TestGetTeamDecisions:
    def test_reads_decisions(self, team_dir):
        result = handle_get_team_decisions("test-team", team_dir)
        assert "HATEOAS" in result["decisions"]
        assert result["_state"] == "team_work"


class TestGetTeamPatterns:
    def test_reads_patterns(self, team_dir):
        result = handle_get_team_patterns("test-team", team_dir)
        assert "convergence" in result["patterns"]


class TestGetAgentMemory:
    def test_reads_agent(self, team_dir):
        result = handle_get_agent_memory("test-team", "tech-architect", team_dir)
        assert "path traversal" in result["memory"]
        assert result["agent"] == "tech-architect"

    def test_missing_agent(self, team_dir):
        result = handle_get_agent_memory("test-team", "nonexistent", team_dir)
        assert "error" in result


class TestWakeCheck:
    def test_matches_agents(self, team_dir):
        result = handle_wake_check("need a code review", "test-team", team_dir)
        assert result["wake_count"] >= 1
        agents = [r["agent"] for r in result["wake"]]
        assert "tech-architect" in agents

    def test_no_match(self, team_dir):
        result = handle_wake_check("something unrelated entirely", "test-team", team_dir)
        assert result["wake_count"] == 0


class TestStoreTeamDecision:
    def test_stores_decision(self, team_dir):
        result = handle_store_team_decision(
            "use-postgres", "tech-architect", "product agreed",
            "test-team", team_dir,
        )
        assert result["stored"] == "use-postgres"
        content = (team_dir / "test-team" / "shared" / "decisions.md").read_text()
        assert "use-postgres" in content
        assert "|by:tech-architect" in content
        assert "product agreed" in content
        # Actions preserved
        assert "→ new decision" in content

    def test_missing_team(self, team_dir):
        result = handle_store_team_decision("x", "y", "", "nonexistent", team_dir)
        assert "error" in result

    def test_custom_weight(self, team_dir):
        result = handle_store_team_decision(
            "use-redis", "ux-researcher", "dissenting view",
            "test-team", team_dir, weight="dissent",
        )
        assert result["stored"] == "use-redis"
        content = (team_dir / "test-team" / "shared" / "decisions.md").read_text()
        assert "|weight:dissent" in content

    def test_advisory_weight(self, team_dir):
        result = handle_store_team_decision(
            "consider-caching", "product-strategist", "",
            "test-team", team_dir, weight="advisory",
        )
        content = (team_dir / "test-team" / "shared" / "decisions.md").read_text()
        assert "|weight:advisory" in content


class TestDetectAgentIdentity:
    def test_im_pattern(self, team_dir):
        result = _detect_agent_identity(
            "I'm tech-architect on the sigma team", "test-team", team_dir
        )
        assert result == "tech-architect"

    def test_i_am_pattern(self, team_dir):
        result = _detect_agent_identity(
            "I am the tech-architect reviewing code", "test-team", team_dir
        )
        assert result == "tech-architect"

    def test_fallback_name_match(self, team_dir):
        result = _detect_agent_identity(
            "tech-architect here for the review", "test-team", team_dir
        )
        assert result == "tech-architect"

    def test_no_match(self, team_dir):
        result = _detect_agent_identity(
            "just a random context", "test-team", team_dir
        )
        assert result is None


class TestAgentBoot:
    def test_full_boot(self, team_dir):
        mem_dir = team_dir / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall(
            "I'm tech-architect on test-team reviewing code", mem_dir, team_dir
        )
        assert result["_state"] == "team_work"
        assert result["detected_team"] == "test-team"
        assert result["agent_identity"] == "tech-architect"

        boot = result["agent_boot"]
        assert boot["agent"] == "tech-architect"
        assert boot["team"] == "test-team"
        assert "path traversal" in boot["personal_memory"]
        assert "HATEOAS" in boot["team_decisions"]
        assert "convergence" in boot["team_patterns"]
        assert "tech-architect" in boot["roster"]
        assert isinstance(boot["teammates"], list)

    def test_lead_doesnt_get_agent_boot(self, team_dir):
        mem_dir = team_dir / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall("working with test-team", mem_dir, team_dir)
        assert result["_state"] == "team_work"
        assert "agent_boot" not in result
        assert "team_roster" in result


class TestRecallWithTeam:
    def test_surfaces_team_info(self, team_dir):
        mem_dir = team_dir / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall("working with test-team on review", mem_dir, team_dir)
        assert result["_state"] == "team_work"
        assert result["detected_team"] == "test-team"
        assert "tech-architect" in result["team_roster"]

    def test_no_team_context(self, team_dir):
        mem_dir = team_dir / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall("just working on code", mem_dir, team_dir)
        assert "detected_team" not in result


class TestValidateTeamName:
    def test_valid_name(self, team_dir):
        result = _validate_team_name(team_dir, "test-team")
        assert result is not None
        assert result.name == "test-team"

    def test_traversal_blocked(self, team_dir):
        assert _validate_team_name(team_dir, "../../etc") is None

    def test_absolute_path_in_name(self, team_dir):
        assert _validate_team_name(team_dir, "/etc/passwd") is None


class TestStoreTeamDecisionTraversal:
    def test_traversal_blocked_in_team_name(self, team_dir):
        result = handle_store_team_decision("x", "y", "", "../../etc", team_dir)
        assert "error" in result

    def test_valid_team_still_works(self, team_dir):
        result = handle_store_team_decision(
            "test-decision", "tester", "", "test-team", team_dir
        )
        assert result["stored"] == "test-decision"


class TestDetectAgentIdentityNoFalsePositive:
    def test_third_person_reference_not_matched(self, team_dir):
        result = _detect_agent_identity(
            "reviewing tech-architect's code for issues", "test-team", team_dir
        )
        assert result is None

    def test_discussing_agent_not_matched(self, team_dir):
        result = _detect_agent_identity(
            "what did tech-architect find in the last review?", "test-team", team_dir
        )
        assert result is None

    def test_traversal_blocked(self, team_dir):
        result = _detect_agent_identity(
            "I'm tech-architect", "../../etc", team_dir
        )
        assert result is None


class TestWakeCheckFullPhrase:
    def test_single_word_doesnt_match_phrase_trigger(self, team_dir):
        result = handle_wake_check("let me review the logs", "test-team", team_dir)
        assert result["wake_count"] == 0

    def test_full_phrase_still_matches(self, team_dir):
        result = handle_wake_check("need a code review of the module", "test-team", team_dir)
        agents = [r["agent"] for r in result["wake"]]
        assert "tech-architect" in agents

    def test_exact_trigger_matches(self, team_dir):
        result = handle_wake_check("system design discussion", "test-team", team_dir)
        agents = [r["agent"] for r in result["wake"]]
        assert "tech-architect" in agents
