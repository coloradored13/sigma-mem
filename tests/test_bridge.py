"""Tests for Issue-14: team memory bridge — enriched boot, team search, team writes."""

import pytest

from sigma_mem.handlers import (
    _count_inbox_unread,
    _get_team_inbox_summary,
    _get_workspace_summary,
    _parse_agent_roster_entry,
    handle_recall,
    handle_search_team_memory,
    handle_store_agent_memory,
    handle_store_team_pattern,
)


@pytest.fixture
def bridge_team(tmp_path):
    """Team directory with inboxes and workspace for bridge tests."""
    team = tmp_path / "test-team"
    shared = team / "shared"
    shared.mkdir(parents=True)
    agents_ta = team / "agents" / "tech-architect"
    agents_ta.mkdir(parents=True)
    agents_ux = team / "agents" / "ux-researcher"
    agents_ux.mkdir(parents=True)
    inboxes = team / "inboxes"
    inboxes.mkdir()

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
    (shared / "workspace.md").write_text(
        "# workspace — sigma-mem v0.2 review\n## status: active\n## task\nreview the bridge\n"
    )
    (agents_ta / "memory.md").write_text(
        "# tech-architect memory\n\n## past findings\nreview-1: found path traversal\n"
        "\n→ actions:\n→ review again → check past findings\n"
    )
    (agents_ux / "memory.md").write_text(
        "# ux-researcher memory\n\n## past findings\nreview-1: flow unclear\n"
    )
    (inboxes / "tech-architect.md").write_text(
        "# inbox — tech-architect\n\n## processed\n"
        "✓ lead(26.3.7): assigned task |#1\n\n"
        "## unread\n"
        "◌ ux-researcher(26.3.7): found overlap in findings |#2\n"
        "◌ lead(26.3.7): new review round |#3\n\n---\n"
    )
    (inboxes / "ux-researcher.md").write_text(
        "# inbox — ux-researcher\n\n## processed\n\n## unread\n\n---\n"
    )
    return tmp_path


# --- Roster parsing ---


class TestParseAgentRosterEntry:
    def test_extracts_domain_and_wake_for(self):
        roster = (
            "tech-architect |domain: architecture,security |wake-for: code review,system design\n"
            "ux-researcher |domain: usability |wake-for: user-facing changes\n"
        )
        entry = _parse_agent_roster_entry(roster, "tech-architect")
        assert entry["domain"] == "architecture,security"
        assert entry["wake_for"] == "code review,system design"

    def test_extracts_different_agent(self):
        roster = (
            "tech-architect |domain: architecture |wake-for: code review\n"
            "ux-researcher |domain: usability,accessibility |wake-for: user-facing changes\n"
        )
        entry = _parse_agent_roster_entry(roster, "ux-researcher")
        assert entry["domain"] == "usability,accessibility"

    def test_unknown_agent_returns_empty(self):
        roster = "tech-architect |domain: architecture |wake-for: code review\n"
        assert _parse_agent_roster_entry(roster, "nonexistent") == {}


# --- Inbox parsing ---


class TestCountInboxUnread:
    def test_counts_unread(self, bridge_team):
        count = _count_inbox_unread(bridge_team, "test-team", "tech-architect")
        assert count == 2

    def test_zero_unread(self, bridge_team):
        count = _count_inbox_unread(bridge_team, "test-team", "ux-researcher")
        assert count == 0

    def test_missing_inbox(self, bridge_team):
        count = _count_inbox_unread(bridge_team, "test-team", "nonexistent")
        assert count == 0


class TestGetTeamInboxSummary:
    def test_returns_all_agents(self, bridge_team):
        summary = _get_team_inbox_summary(bridge_team, "test-team")
        assert summary is not None
        assert summary["tech-architect"] == 2
        assert summary["ux-researcher"] == 0

    def test_missing_inboxes_dir(self, tmp_path):
        team = tmp_path / "empty-team"
        team.mkdir()
        assert _get_team_inbox_summary(tmp_path, "empty-team") is None

    def test_invalid_team(self, bridge_team):
        assert _get_team_inbox_summary(bridge_team, "../../etc") is None


# --- Workspace parsing ---


class TestGetWorkspaceSummary:
    def test_extracts_task_and_status(self, bridge_team):
        summary = _get_workspace_summary(bridge_team, "test-team")
        assert summary is not None
        assert "sigma-mem v0.2 review" in summary
        assert "active" in summary

    def test_no_workspace(self, tmp_path):
        team = tmp_path / "no-ws"
        (team / "shared").mkdir(parents=True)
        assert _get_workspace_summary(tmp_path, "no-ws") is None

    def test_workspace_status_only(self, tmp_path):
        team = tmp_path / "status-only"
        shared = team / "shared"
        shared.mkdir(parents=True)
        (shared / "workspace.md").write_text("# workspace\n## status: complete\n")
        summary = _get_workspace_summary(tmp_path, "status-only")
        assert summary == "status: complete"


# --- Enriched agent boot ---


class TestEnrichedAgentBoot:
    def test_boot_includes_domain(self, bridge_team):
        mem_dir = bridge_team / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall(
            "I'm tech-architect on test-team reviewing code", mem_dir, bridge_team
        )
        boot = result["agent_boot"]
        assert "agent_domain" in boot
        assert boot["agent_domain"]["domain"] == "architecture,security"
        assert boot["agent_domain"]["wake_for"] == "code review,system design"

    def test_boot_includes_inbox_unread(self, bridge_team):
        mem_dir = bridge_team / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall(
            "I'm tech-architect on test-team reviewing code", mem_dir, bridge_team
        )
        boot = result["agent_boot"]
        assert boot["inbox_unread"] == 2

    def test_boot_includes_workspace(self, bridge_team):
        mem_dir = bridge_team / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall(
            "I'm tech-architect on test-team reviewing code", mem_dir, bridge_team
        )
        boot = result["agent_boot"]
        assert "workspace" in boot
        assert "sigma-mem v0.2 review" in boot["workspace"]

    def test_boot_zero_inbox_still_present(self, bridge_team):
        mem_dir = bridge_team / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall(
            "I'm ux-researcher on test-team reviewing code", mem_dir, bridge_team
        )
        boot = result["agent_boot"]
        assert boot["inbox_unread"] == 0


# --- Enriched lead path ---


class TestEnrichedLeadPath:
    def test_lead_gets_workspace(self, bridge_team):
        mem_dir = bridge_team / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall("working with test-team on review", mem_dir, bridge_team)
        assert "agent_boot" not in result
        assert "team_workspace" in result
        assert "sigma-mem v0.2 review" in result["team_workspace"]

    def test_lead_gets_inbox_summary(self, bridge_team):
        mem_dir = bridge_team / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("U[test|1|26.3]\n")
        result = handle_recall("working with test-team on review", mem_dir, bridge_team)
        assert "team_inbox_summary" in result
        assert result["team_inbox_summary"]["tech-architect"] == 2
        assert result["team_inbox_summary"]["ux-researcher"] == 0


# --- Search team memory ---


class TestSearchTeamMemory:
    def test_finds_in_shared(self, bridge_team):
        result = handle_search_team_memory("HATEOAS", "test-team", bridge_team)
        assert "shared/decisions.md" in result["matches"]

    def test_finds_in_agent_memory(self, bridge_team):
        result = handle_search_team_memory("path traversal", "test-team", bridge_team)
        assert "agents/tech-architect/memory.md" in result["matches"]

    def test_finds_in_inboxes(self, bridge_team):
        result = handle_search_team_memory("overlap", "test-team", bridge_team)
        assert "inboxes/tech-architect.md" in result["matches"]

    def test_no_matches(self, bridge_team):
        result = handle_search_team_memory("zzzznonexistent", "test-team", bridge_team)
        assert len(result["matches"]) == 0

    def test_invalid_team(self, bridge_team):
        result = handle_search_team_memory("test", "../../etc", bridge_team)
        assert "error" in result

    def test_returns_team_work_state(self, bridge_team):
        result = handle_search_team_memory("test", "test-team", bridge_team)
        assert result["_state"] == "team_work"

    def test_searches_across_multiple_agents(self, bridge_team):
        result = handle_search_team_memory("past findings", "test-team", bridge_team)
        assert "agents/tech-architect/memory.md" in result["matches"]
        assert "agents/ux-researcher/memory.md" in result["matches"]


# --- Store agent memory ---


class TestStoreAgentMemory:
    def test_appends_entry(self, bridge_team):
        result = handle_store_agent_memory(
            "review-2: found injection", "tech-architect", "test-team", bridge_team
        )
        assert result["stored"] == "review-2: found injection"
        assert result["agent"] == "tech-architect"
        content = (
            bridge_team / "test-team" / "agents" / "tech-architect" / "memory.md"
        ).read_text()
        assert "review-2: found injection" in content
        # Existing content preserved
        assert "path traversal" in content
        # Actions preserved
        assert "→ review again" in content

    def test_arrow_prefix_rejected(self, bridge_team):
        result = handle_store_agent_memory(
            "→ bad entry", "tech-architect", "test-team", bridge_team
        )
        assert "error" in result

    def test_invalid_team(self, bridge_team):
        result = handle_store_agent_memory(
            "entry", "tech-architect", "../../etc", bridge_team
        )
        assert "error" in result

    def test_missing_agent(self, bridge_team):
        result = handle_store_agent_memory(
            "entry", "nonexistent", "test-team", bridge_team
        )
        assert "error" in result

    def test_traversal_in_agent_name(self, bridge_team):
        result = handle_store_agent_memory(
            "entry", "../../etc/passwd", "test-team", bridge_team
        )
        assert "error" in result


# --- Store team pattern ---


class TestStoreTeamPattern:
    def test_stores_pattern(self, bridge_team):
        result = handle_store_team_pattern(
            "convergence:bridge-gap",
            "tech-architect,ux-researcher",
            "test-team",
            bridge_team,
        )
        assert result["stored"] == "convergence:bridge-gap"
        content = (bridge_team / "test-team" / "shared" / "patterns.md").read_text()
        assert "convergence:bridge-gap" in content
        assert "|agents: tech-architect,ux-researcher" in content
        # Existing content preserved
        assert "all-found-same-bug" in content
        # Actions preserved
        assert "→ new pattern" in content

    def test_stores_without_agents(self, bridge_team):
        result = handle_store_team_pattern(
            "observation:tests-stable", "", "test-team", bridge_team
        )
        assert result["stored"] == "observation:tests-stable"
        content = (bridge_team / "test-team" / "shared" / "patterns.md").read_text()
        assert "observation:tests-stable" in content
        assert (
            "|agents:"
            not in content.split("observation:tests-stable")[1].split("\n")[0]
        )

    def test_invalid_team(self, bridge_team):
        result = handle_store_team_pattern("pattern", "", "../../etc", bridge_team)
        assert "error" in result

    def test_missing_patterns_file(self, tmp_path):
        team = tmp_path / "no-patterns"
        (team / "shared").mkdir(parents=True)
        result = handle_store_team_pattern("pattern", "", "no-patterns", tmp_path)
        assert "error" in result
