"""Tests for team memory handlers — roster, decisions, agent memory, wake check."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from sigma_mem.handlers import (
    _check_agent_research,
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
    handle_validate_system,
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


@pytest.fixture
def team_dir_with_research(tmp_path):
    """Create a team directory with research sections and inboxes."""
    team = tmp_path / "test-team"
    shared = team / "shared"
    shared.mkdir(parents=True)
    inboxes = team / "inboxes"
    inboxes.mkdir(parents=True)

    # Agent with current research
    arch_dir = team / "agents" / "tech-architect"
    arch_dir.mkdir(parents=True)

    today = date.today()
    today_ymd = f"{today.year % 100}.{today.month}.{today.day}"
    (arch_dir / "memory.md").write_text(
        "# tech-architect memory\n\n## past findings\nreview-1: found path traversal\n\n"
        f"## research\nrefreshed: {today_ymd}\n- security patterns in Python\n- OWASP top 10\n"
    )
    (inboxes / "tech-architect.md").write_text("## unread\n\n## read\n")

    # Agent with stale research (60 days old)
    ux_dir = team / "agents" / "ux-researcher"
    ux_dir.mkdir(parents=True)

    stale_date = today - timedelta(days=60)
    stale_ymd = f"{stale_date.year % 100}.{stale_date.month}.{stale_date.day}"
    (ux_dir / "memory.md").write_text(
        "# ux-researcher memory\n\n## past findings\nreview-1: accessibility issue\n\n"
        f"## research\nrefreshed: {stale_ymd}\n- usability heuristics\n"
    )
    (inboxes / "ux-researcher.md").write_text("## unread\n\n## read\n")

    # Agent with no research section at all
    qa_dir = team / "agents" / "code-quality-analyst"
    qa_dir.mkdir(parents=True)
    (qa_dir / "memory.md").write_text(
        "# code-quality-analyst memory\n\n## past findings\nreview-1: lint issues\n"
    )
    (inboxes / "code-quality-analyst.md").write_text("## unread\n\n## read\n")

    (shared / "roster.md").write_text(
        "tech-architect |domain: architecture,security |wake-for: code review,system design\n"
        "ux-researcher |domain: usability |wake-for: user-facing changes,code review\n"
        "code-quality-analyst |domain: quality |wake-for: code review,refactor\n"
    )
    (shared / "decisions.md").write_text("# team decisions\n")
    (shared / "patterns.md").write_text("# patterns\n")

    return tmp_path


class TestWakeCheckResearchStatus:
    def test_current_research_included(self, team_dir_with_research):
        result = handle_wake_check("code review", "test-team", team_dir_with_research)
        arch = next(r for r in result["wake"] if r["agent"] == "tech-architect")
        assert arch["research_status"] == "current"
        assert arch["research_refreshed"] is not None

    def test_missing_research_flagged(self, team_dir_with_research):
        result = handle_wake_check("code review", "test-team", team_dir_with_research)
        qa = next(r for r in result["wake"] if r["agent"] == "code-quality-analyst")
        assert qa["research_status"] == "missing"
        assert qa["research_refreshed"] is None
        assert any("code-quality-analyst" in w and "no domain research" in w
                    for w in result["research_warnings"])

    def test_stale_research_flagged(self, team_dir_with_research):
        result = handle_wake_check("code review", "test-team", team_dir_with_research)
        ux = next(r for r in result["wake"] if r["agent"] == "ux-researcher")
        assert ux["research_status"] == "stale"
        assert ux["research_refreshed"] is not None
        assert any("ux-researcher" in w and "stale" in w
                    for w in result["research_warnings"])

    def test_no_warnings_when_all_current(self, team_dir_with_research):
        """When only agents with current research match, no warnings."""
        result = handle_wake_check("system design", "test-team", team_dir_with_research)
        # Only tech-architect matches "system design"
        assert result["wake_count"] == 1
        assert result["wake"][0]["research_status"] == "current"
        assert "research_warnings" not in result


class TestValidateSystem:
    def test_catches_missing_agent_files(self, team_dir_with_research):
        """Agents without definition files are flagged."""
        # Create a temporary agents_dir with only one definition
        agents_def_dir = team_dir_with_research / "agent_defs"
        agents_def_dir.mkdir()
        (agents_def_dir / "tech-architect.md").write_text("# tech-architect\n")
        # ux-researcher and code-quality-analyst have no definition files

        result = handle_validate_system(
            "test-team", team_dir_with_research, agents_def_dir
        )
        assert result["valid"] is False
        assert result["issue_count"] >= 2
        # Check specific missing definitions
        missing_def = [i for i in result["issues"] if "missing definition" in i]
        assert len(missing_def) == 2
        agent_names_missing = [i.split(":")[0] for i in missing_def]
        assert "ux-researcher" in agent_names_missing
        assert "code-quality-analyst" in agent_names_missing

    def test_catches_missing_research(self, team_dir_with_research):
        """Agents without ## research section are flagged."""
        agents_def_dir = team_dir_with_research / "agent_defs"
        agents_def_dir.mkdir(exist_ok=True)
        for name in ["tech-architect", "ux-researcher", "code-quality-analyst"]:
            (agents_def_dir / f"{name}.md").write_text(f"# {name}\n")

        result = handle_validate_system(
            "test-team", team_dir_with_research, agents_def_dir
        )
        # code-quality-analyst has no research
        research_issues = [i for i in result["issues"] if "research" in i.lower()]
        agent_names = [i.split(":")[0] for i in research_issues]
        assert "code-quality-analyst" in agent_names

    def test_catches_missing_memory(self, tmp_path):
        """Agents in roster but without memory files are flagged."""
        team = tmp_path / "test-team"
        shared = team / "shared"
        shared.mkdir(parents=True)
        # Create roster referencing an agent that has no agent dir
        (shared / "roster.md").write_text(
            "ghost-agent |domain: testing |wake-for: test\n"
        )
        agents_def_dir = tmp_path / "agent_defs"
        agents_def_dir.mkdir()
        (agents_def_dir / "ghost-agent.md").write_text("# ghost\n")

        result = handle_validate_system("test-team", tmp_path, agents_def_dir)
        assert result["valid"] is False
        memory_issues = [i for i in result["issues"] if "missing memory" in i]
        assert len(memory_issues) == 1
        assert "ghost-agent" in memory_issues[0]

    def test_catches_missing_inbox(self, tmp_path):
        """Agents without inbox files are flagged."""
        team = tmp_path / "test-team"
        shared = team / "shared"
        shared.mkdir(parents=True)
        agent_dir = team / "agents" / "solo-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "memory.md").write_text(
            "# solo\n\n## research\nrefreshed: 26.3.1\n- stuff\n"
        )
        (shared / "roster.md").write_text(
            "solo-agent |domain: testing |wake-for: test\n"
        )
        agents_def_dir = tmp_path / "agent_defs"
        agents_def_dir.mkdir()
        (agents_def_dir / "solo-agent.md").write_text("# solo\n")

        result = handle_validate_system("test-team", tmp_path, agents_def_dir)
        inbox_issues = [i for i in result["issues"] if "missing inbox" in i]
        assert len(inbox_issues) == 1
        assert "solo-agent" in inbox_issues[0]

    def test_valid_system_passes(self, tmp_path):
        """A fully valid system returns valid=True with no issues."""
        team = tmp_path / "test-team"
        shared = team / "shared"
        shared.mkdir(parents=True)
        agent_dir = team / "agents" / "complete-agent"
        agent_dir.mkdir(parents=True)
        inboxes = team / "inboxes"
        inboxes.mkdir(parents=True)

        today = date.today()
        today_ymd = f"{today.year % 100}.{today.month}.{today.day}"
        (agent_dir / "memory.md").write_text(
            f"# complete\n\n## research\nrefreshed: {today_ymd}\n- research notes\n"
        )
        (inboxes / "complete-agent.md").write_text("## unread\n\n## read\n")
        (shared / "roster.md").write_text(
            "complete-agent |domain: testing |wake-for: test\n"
        )
        agents_def_dir = tmp_path / "agent_defs"
        agents_def_dir.mkdir()
        (agents_def_dir / "complete-agent.md").write_text("# complete\n")

        result = handle_validate_system("test-team", tmp_path, agents_def_dir)
        assert result["valid"] is True
        assert result["issue_count"] == 0
        assert len(result["issues"]) == 0
