"""Tests for dream consolidation — all four phases, personal + team scope."""

from datetime import date

import pytest

from sigma_mem.dream import (
    _consolidate_personal,
    _consolidate_team,
    _extract_leading_date,
    _extract_research_dates,
    _extract_research_section,
    _extract_section_refreshed_date,
    _find_duplicates,
    _find_promotable_beliefs,
    _find_stale_dated_entries,
    _find_stale_research,
    _find_systemic_patterns,
    _find_team_canonical_patterns,
    _index_personal,
    _index_team,
    _normalize_for_dedup,
    _prune_personal,
    _prune_team,
    _reorganize_personal,
    _reorganize_team,
    dream,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_dir(tmp_path):
    """Personal memory directory with representative content."""
    d = tmp_path / "memory"
    d.mkdir()
    (d / "MEMORY.md").write_text(
        "U[test user|1|26.3]\n"
        "C~[tentative belief about testing]\n"
        "C[confirmed belief|2|26.3]\n"
        "¬[developer(not a dev)]\n"
        "R[some research|26.1.1]\n"
    )
    (d / "decisions.md").write_text(
        "26.3.7|use-postgres|why: fast\n"
        "26.3.7|use-postgres|why: fast\n"  # duplicate
        "26.3.10|use-redis|why: caching\n"
    )
    (d / "corrections.md").write_text(
        "25.6.1|old correction|fixed long ago\n"
        "26.3.20|recent correction|just fixed\n"
    )
    (d / "patterns.md").write_text(
        "C~[tentative belief about testing]\n"
        "convergence: agents agree on arch\n"
        "convergence: agents agree on arch\n"  # duplicate
    )
    (d / "conv.md").write_text("26.3.7|discussed arch\n")
    (d / "failures.md").write_text(
        "25.5.1|tried X|nope\n"
        "26.3.18|tried Y|also nope\n"
    )
    (d / "meta.md").write_text("v0.1: initial\n")
    (d / "projects.md").write_text("*sigma-mem[memory MCP|1|26.3]\n")
    (d / "user.md").write_text("prefers simple\n")
    (d / "rosetta.md").write_text("notation guide\n")
    return d


@pytest.fixture
def teams_dir(tmp_path):
    """Teams directory with one team, two agents, and some duplicates."""
    d = tmp_path / "teams"
    team = d / "test-team"
    shared = team / "shared"
    shared.mkdir(parents=True)
    agents_ta = team / "agents" / "tech-architect"
    agents_ta.mkdir(parents=True)
    agents_ux = team / "agents" / "ux-researcher"
    agents_ux.mkdir(parents=True)
    inboxes = team / "inboxes"
    inboxes.mkdir(parents=True)

    (shared / "roster.md").write_text(
        "tech-architect |domain: architecture |wake-for: code review\n"
        "ux-researcher |domain: usability |wake-for: user-facing changes\n"
    )
    (shared / "decisions.md").write_text(
        "# team decisions\n\n"
        "arch:use-HATEOAS |by:tech-architect |weight:primary\n"
        "arch:use-HATEOAS |by:tech-architect |weight:primary\n"  # duplicate
        "cache:use-redis |by:tech-architect |weight:primary\n"
    )
    (shared / "patterns.md").write_text(
        "# patterns\n\n"
        "convergence:all-found-same-bug |agents: all\n"
        "convergence:all-found-same-bug |agents: all\n"  # duplicate
        "new-pattern:something-unique |agents: ta,ux\n"
    )
    (agents_ta / "memory.md").write_text(
        "# tech-architect memory\n\n"
        "## research\n"
        "R[OWASP-agentic-top10: ASI01-goal-hijack, ASI02-tool-misuse]\n"
        "R[MCP-security: cmd-injection-43-percent]\n"
        "refreshed: 25.1.1\n"  # stale — section-level date
    )
    (agents_ux / "memory.md").write_text(
        "# ux-researcher memory\n\n"
        "## research\n"
        "R[usability-patterns: topic-content]\n"
        "refreshed: 26.3.20\n"  # current — section-level date
    )
    (inboxes / "tech-architect.md").write_text(
        "## unread\n"
        "msg from ux\n"
        "## read\n"
        "old msg 1\n"
        "old msg 2\n"
    )
    (inboxes / "ux-researcher.md").write_text("## unread\n")

    return d


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestNormalizeForDedup:
    def test_strips_leading_date(self):
        assert _normalize_for_dedup("26.3.7|use-postgres|why: fast") == "use-postgres|why: fast"

    def test_strips_trailing_date(self):
        assert "26.3" not in _normalize_for_dedup("some entry|26.3.7]")

    def test_lowercases(self):
        assert _normalize_for_dedup("USE-POSTGRES") == "use-postgres"

    def test_collapses_whitespace(self):
        assert _normalize_for_dedup("a   b   c") == "a b c"


class TestExtractLeadingDate:
    def test_standard_format(self):
        result = _extract_leading_date("26.3.7|choice|why: reason")
        assert result == date(2026, 3, 7)

    def test_no_date(self):
        assert _extract_leading_date("no date here") is None

    def test_empty_line(self):
        assert _extract_leading_date("") is None


class TestExtractSectionRefreshedDate:
    def test_finds_ymd_date(self):
        content = "## research\nR[topic:stuff]\nrefreshed: 26.3.18 | next: 26.4\n"
        assert _extract_section_refreshed_date(content) == date(2026, 3, 18)

    def test_finds_iso_date(self):
        content = "## research\nrefreshed: 2026-03-14\n"
        assert _extract_section_refreshed_date(content) == date(2026, 3, 14)

    def test_no_research_section(self):
        assert _extract_section_refreshed_date("just content\n") is None

    def test_stops_at_next_section(self):
        content = "## research\nR[stuff]\n## other\nrefreshed: 26.3.18\n"
        assert _extract_section_refreshed_date(content) is None

    def test_finds_parenthetical_date_in_header(self):
        content = "## research: cognitive-enhancement-meta-analysis (26.3.21)\nR[1]: stuff\n"
        assert _extract_section_refreshed_date(content) == date(2026, 3, 21)

    def test_finds_parenthetical_date_with_prefix(self):
        content = "## research (rerun 26.3.13)\nR[topic]: stuff\n"
        assert _extract_section_refreshed_date(content) == date(2026, 3, 13)

    def test_refreshed_line_takes_priority_over_header_date(self):
        content = (
            "## research: topic (26.3.10)\n"
            "R[stuff]\n"
            "refreshed: 26.3.22\n"
        )
        assert _extract_section_refreshed_date(content) == date(2026, 3, 22)

    def test_multiple_research_headers_last_date_wins(self):
        content = (
            "## research\n"
            "R[first]\n"
            "## research (rerun 26.3.13)\n"
            "R[second]\n"
            "## other\n"
        )
        assert _extract_section_refreshed_date(content) == date(2026, 3, 13)


class TestExtractResearchDates:
    def test_finds_r_blocks_with_inline_dates(self):
        content = "R[26.3.22] some research\nR[25.1.1] old research\nnot research"
        results = _extract_research_dates(content)
        assert len(results) == 2
        assert results[0][1] == date(2026, 3, 22)
        assert results[1][1] == date(2025, 1, 1)

    def test_inline_refreshed_key_iso(self):
        content = "R[cloud-arch-wms:Manhattan 250 microservices|refreshed:2026-03-14]\n"
        results = _extract_research_dates(content)
        assert len(results) == 1
        assert results[0][1] == date(2026, 3, 14)

    def test_inline_refreshed_key_ymd(self):
        content = "R[topic:stuff|refreshed:26.3.14]\n"
        results = _extract_research_dates(content)
        assert len(results) == 1
        assert results[0][1] == date(2026, 3, 14)

    def test_falls_back_to_section_date(self):
        content = (
            "## research\n"
            "R[topic-without-date: some content]\n"
            "R[another-topic: more content]\n"
            "refreshed: 26.3.18 | next: 26.4\n"
        )
        results = _extract_research_dates(content)
        assert len(results) == 2
        # Both should inherit the section-level date
        assert results[0][1] == date(2026, 3, 18)
        assert results[1][1] == date(2026, 3, 18)

    def test_embedded_date_in_topic_name(self):
        content = "R[fed-policy-26.3.10]: FFR 3.50-3.75%\n"
        results = _extract_research_dates(content)
        assert len(results) == 1
        assert results[0][1] == date(2026, 3, 10)

    def test_no_date_anywhere(self):
        content = "R[something without date]\n"
        results = _extract_research_dates(content)
        assert len(results) == 1
        assert results[0][1] is None

    def test_fallback_date_used_when_no_section_date(self):
        content = "R[topic]: some content\n"
        results = _extract_research_dates(content, fallback_date=date(2026, 3, 21))
        assert len(results) == 1
        assert results[0][1] == date(2026, 3, 21)

    def test_section_date_takes_priority_over_fallback(self):
        content = (
            "## research\n"
            "R[topic]: stuff\n"
            "refreshed: 26.3.22\n"
        )
        results = _extract_research_dates(content, fallback_date=date(2026, 3, 1))
        assert len(results) == 1
        assert results[0][1] == date(2026, 3, 22)

    def test_numbered_r_blocks_use_section_date(self):
        """R[1]:, R[2]: etc. should inherit section-level date."""
        content = (
            "## research: cognitive-enhancement (26.3.21)\n"
            "R[1]: DeepMind cognitive profile mapping\n"
            "R[2]: Metacognition paradox\n"
            "R[3]: FORMAT vs COGNITIVE transfer\n"
        )
        results = _extract_research_dates(content)
        assert len(results) == 3
        for _, d in results:
            assert d == date(2026, 3, 21)


# ---------------------------------------------------------------------------
# Phase 1: Consolidate
# ---------------------------------------------------------------------------


class TestFindDuplicates:
    def test_finds_exact_duplicates(self):
        lines = ["line A", "line B", "line A", "line C"]
        dupes = _find_duplicates(lines)
        assert len(dupes) == 1
        assert dupes[0]["count"] == 2

    def test_no_duplicates(self):
        lines = ["line A", "line B", "line C"]
        assert _find_duplicates(lines) == []

    def test_skips_headers_and_action_links(self):
        lines = ["# header", "→ action", "real line", "real line"]
        dupes = _find_duplicates(lines)
        assert len(dupes) == 1

    def test_skips_short_fragments(self):
        lines = ["ab", "ab"]
        assert _find_duplicates(lines) == []

    def test_date_normalized_duplicates(self):
        lines = [
            "26.3.7|use-postgres|why: fast",
            "26.3.10|use-postgres|why: fast",
        ]
        dupes = _find_duplicates(lines)
        assert len(dupes) == 1


class TestConsolidatePersonal:
    def test_finds_duplicates_in_decisions(self, mem_dir):
        result = _consolidate_personal(mem_dir)
        assert "decisions.md" in result
        assert len(result["decisions.md"]) >= 1

    def test_finds_duplicates_in_patterns(self, mem_dir):
        result = _consolidate_personal(mem_dir)
        assert "patterns.md" in result

    def test_empty_dir_no_crash(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert _consolidate_personal(d) == {}


class TestConsolidateTeam:
    def test_finds_team_duplicates(self, teams_dir):
        result = _consolidate_team(teams_dir, "test-team")
        assert "shared/decisions.md" in result or "shared/patterns.md" in result

    def test_missing_team(self, teams_dir):
        result = _consolidate_team(teams_dir, "nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Phase 2: Prune
# ---------------------------------------------------------------------------


class TestExtractResearchSection:
    def test_extracts_section(self):
        content = "## intro\nstuff\n## research\nR[topic]\nrefreshed: 26.3.18\n## other\nmore"
        section = _extract_research_section(content)
        assert "R[topic]" in section
        assert "## other" not in section

    def test_no_section_returns_none(self):
        assert _extract_research_section("just content\n") is None

    def test_includes_non_r_lines(self):
        content = "## research\nR[topic]\nrefreshed: 26.3.18\nnotes here\n## end"
        section = _extract_research_section(content)
        assert "notes here" in section


class TestFindStaleResearch:
    def test_finds_old_research(self):
        content = "R[25.1.1] very old\nR[26.3.20] recent\n"
        stale = _find_stale_research(content, max_age_days=30)
        assert len(stale) >= 1
        old_entry = [s for s in stale if s["reason"] == "expired"]
        assert len(old_entry) >= 1

    def test_no_stale_when_recent(self):
        today = date.today()
        d = f"{today.year % 100}.{today.month}.{today.day}"
        content = f"R[{d}] fresh\n"
        stale = _find_stale_research(content, max_age_days=30)
        assert len(stale) == 0

    def test_no_date_flagged(self):
        content = "R[something without date]\n"
        stale = _find_stale_research(content)
        assert len(stale) == 1
        assert stale[0]["reason"] == "no_date_found"

    def test_research_section_only_skips_non_research_r_blocks(self):
        content = (
            "## findings\n"
            "R[review-finding]: some DA challenge\n"
            "R[calibration-note]: another entry\n"
            "## research\n"
            "R[domain-topic]: actual research\n"
            "refreshed: 25.1.1\n"
            "## past findings\n"
            "R[old-finding]: not research\n"
        )
        # Without section filter — finds all 4 R[] blocks (all stale via section date 25.1.1)
        all_results = _find_stale_research(content)
        assert len(all_results) == 4

        # With section filter — only the 1 in ## research
        section_results = _find_stale_research(content, research_section_only=True)
        assert len(section_results) == 1
        # Should resolve date from section-level refreshed line (not no_date_found)
        assert section_results[0]["reason"] == "expired"

    def test_research_section_only_preserves_header_date(self):
        """When header has parenthetical date, R[] blocks should inherit it."""
        content = (
            "## findings\n"
            "R[finding]: not research\n"
            "## research: cognitive-enhancement (25.1.1)\n"
            "R[1]: DeepMind mapping\n"
            "R[2]: Metacognition paradox\n"
            "## calibration\n"
            "R[cal]: not research\n"
        )
        results = _find_stale_research(content, research_section_only=True)
        assert len(results) == 2
        for r in results:
            assert r["reason"] == "expired"
            assert r["date"] == "2025-01-01"

    def test_research_section_only_no_date_is_flagged(self):
        """R[] blocks with genuinely no date should still be flagged."""
        content = (
            "## research\n"
            "R[topic-without-any-date]: stuff\n"
            "## other\n"
        )
        results = _find_stale_research(content, research_section_only=True)
        assert len(results) == 1
        assert results[0]["reason"] == "no_date_found"


class TestFindStaleDatedEntries:
    def test_finds_old_entries(self):
        content = "25.1.1|old thing|reason\n26.3.20|recent thing|reason\n"
        stale = _find_stale_dated_entries(content, max_age_days=90)
        assert len(stale) >= 1

    def test_skips_headers(self):
        content = "# Header\n25.1.1|old|reason\n"
        stale = _find_stale_dated_entries(content, max_age_days=90)
        assert len(stale) == 1  # Only the data line, not the header


class TestPrunePersonal:
    def test_finds_stale_research_in_memory(self, mem_dir):
        result = _prune_personal(mem_dir)
        assert "MEMORY.md" in result
        assert "stale_research" in result["MEMORY.md"]

    def test_finds_old_corrections(self, mem_dir):
        result = _prune_personal(mem_dir)
        assert "corrections.md" in result
        assert "old_entries" in result["corrections.md"]

    def test_finds_old_failures(self, mem_dir):
        result = _prune_personal(mem_dir)
        assert "failures.md" in result


class TestPruneTeam:
    def test_finds_stale_agent_research(self, teams_dir):
        result = _prune_team(teams_dir, "test-team")
        assert "stale_agent_research" in result
        stale_names = [a["agent"] for a in result["stale_agent_research"]]
        assert "tech-architect" in stale_names

    def test_finds_clearable_inboxes(self, teams_dir):
        result = _prune_team(teams_dir, "test-team")
        assert "clearable_inboxes" in result
        clearable_names = [c["inbox"] for c in result["clearable_inboxes"]]
        assert "tech-architect" in clearable_names

    def test_missing_team(self, teams_dir):
        result = _prune_team(teams_dir, "nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Phase 3: Reorganize
# ---------------------------------------------------------------------------


class TestFindPromotableBeliefs:
    def test_finds_cross_file_tentative(self, mem_dir):
        # C~[tentative belief about testing] appears in MEMORY.md and patterns.md
        promotable = _find_promotable_beliefs(mem_dir)
        assert len(promotable) >= 1
        beliefs = [p["belief"] for p in promotable]
        assert any("tentative" in b for b in beliefs)

    def test_no_promotion_for_single_file(self, tmp_path):
        d = tmp_path / "mem"
        d.mkdir()
        (d / "a.md").write_text("C~[unique belief]\n")
        assert _find_promotable_beliefs(d) == []


class TestFindSystemicPatterns:
    def test_detects_recurring_topics(self, tmp_path):
        d = tmp_path / "mem"
        d.mkdir()
        (d / "corrections.md").write_text(
            "26.3.1|permissions|fixed\n"
            "26.3.5|permissions|fixed again\n"
            "26.3.10|permissions|still broken\n"
        )
        (d / "failures.md").write_text("")
        systemic = _find_systemic_patterns(d)
        assert len(systemic) >= 1

    def test_no_systemic_below_threshold(self, tmp_path):
        d = tmp_path / "mem"
        d.mkdir()
        (d / "corrections.md").write_text("26.3.1|thing|fixed\n")
        (d / "failures.md").write_text("")
        assert _find_systemic_patterns(d) == []


class TestFindTeamCanonicalPatterns:
    def test_finds_repeated_patterns(self, teams_dir):
        canonical = _find_team_canonical_patterns(teams_dir, "test-team")
        assert len(canonical) >= 1

    def test_missing_team(self, teams_dir):
        assert _find_team_canonical_patterns(teams_dir, "nope") == []


class TestReorganizePersonal:
    def test_returns_promotable_and_systemic(self, mem_dir):
        result = _reorganize_personal(mem_dir)
        assert "promotable_beliefs" in result

    def test_empty_when_nothing_to_do(self, tmp_path):
        d = tmp_path / "mem"
        d.mkdir()
        (d / "corrections.md").write_text("")
        (d / "failures.md").write_text("")
        assert _reorganize_personal(d) == {}


class TestReorganizeTeam:
    def test_returns_canonical_candidates(self, teams_dir):
        result = _reorganize_team(teams_dir, "test-team")
        assert "canonical_pattern_candidates" in result


# ---------------------------------------------------------------------------
# Phase 4: Index
# ---------------------------------------------------------------------------


class TestIndexPersonal:
    def test_counts_files_and_lines(self, mem_dir):
        result = _index_personal(mem_dir)
        assert result["total_lines"] > 0
        assert len(result["files"]) > 0

    def test_reports_confidence_distribution(self, mem_dir):
        result = _index_personal(mem_dir)
        dist = result["confidence_distribution"]
        assert "confirmed" in dist or "tentative" in dist

    def test_reports_checksum_stats(self, mem_dir):
        result = _index_personal(mem_dir)
        for f in result["files"]:
            assert "checksums_verified" in f
            assert "checksum_failures" in f


class TestIndexTeam:
    def test_counts_shared_files(self, teams_dir):
        result = _index_team(teams_dir, "test-team")
        assert len(result["shared_files"]) > 0

    def test_counts_agent_memories(self, teams_dir):
        result = _index_team(teams_dir, "test-team")
        assert len(result["agent_memories"]) == 2

    def test_counts_inboxes(self, teams_dir):
        result = _index_team(teams_dir, "test-team")
        assert len(result["inboxes"]) == 2

    def test_missing_team(self, teams_dir):
        result = _index_team(teams_dir, "nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Main entry point: dream()
# ---------------------------------------------------------------------------


class TestDreamDryRun:
    def test_personal_scope(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="personal")
        assert result["mode"] == "dry_run"
        assert result["scope"] == "personal"
        assert "personal" in result
        assert "teams" not in result
        assert "summary" in result

    def test_team_scope(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="team", team_name="test-team")
        assert "teams" in result
        assert "test-team" in result["teams"]
        assert "personal" not in result

    def test_all_scope(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="all")
        assert "personal" in result
        assert "teams" in result

    def test_all_scope_discovers_teams(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="all")
        assert "test-team" in result["teams"]

    def test_skips_empty_teams(self, mem_dir, teams_dir):
        # Create an empty team directory (no shared/ subdir)
        empty_team = teams_dir / "empty-phantom"
        empty_team.mkdir()
        result = dream(mem_dir, teams_dir, scope="all")
        assert "empty-phantom" not in result.get("teams", {})

    def test_summary_counts_proposals(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="all")
        summary = result["summary"]
        assert summary["actions_proposed"] > 0
        assert summary["actions_applied"] == 0  # dry run

    def test_includes_date(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="personal")
        assert "date" in result

    def test_personal_index_always_present(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="personal")
        assert "index" in result["personal"]


class TestDreamApply:
    def test_apply_removes_duplicates(self, mem_dir, teams_dir):
        # Verify duplicates exist before
        decisions_content = (mem_dir / "decisions.md").read_text()
        assert decisions_content.count("use-postgres") == 2

        result = dream(mem_dir, teams_dir, scope="personal", apply=True)

        # Verify duplicates removed after
        decisions_content = (mem_dir / "decisions.md").read_text()
        assert decisions_content.count("use-postgres") == 1
        assert "applied" in result["personal"]
        assert result["summary"]["actions_applied"] > 0

    def test_apply_removes_team_duplicates(self, mem_dir, teams_dir):
        team_decisions = teams_dir / "test-team" / "shared" / "decisions.md"
        assert team_decisions.read_text().count("use-HATEOAS") == 2

        result = dream(
            mem_dir, teams_dir, scope="team", team_name="test-team", apply=True
        )

        assert team_decisions.read_text().count("use-HATEOAS") == 1
        assert "applied" in result["teams"]["test-team"]

    def test_apply_provides_index_after(self, mem_dir, teams_dir):
        result = dream(mem_dir, teams_dir, scope="personal", apply=True)
        assert "index_after" in result["personal"]

    def test_dry_run_does_not_modify_files(self, mem_dir, teams_dir):
        before = (mem_dir / "decisions.md").read_text()
        dream(mem_dir, teams_dir, scope="personal", apply=False)
        after = (mem_dir / "decisions.md").read_text()
        assert before == after


# ---------------------------------------------------------------------------
# Integration: dream action via machine
# ---------------------------------------------------------------------------


class TestDreamViaMachine:
    def test_dream_action_registered(self, mem_dir, teams_dir):
        from sigma_mem.machine import build_machine

        machine = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        all_names = machine.get_all_action_names()
        assert "dream" in all_names

    def test_dream_action_reachable_from_idle(self, mem_dir, teams_dir):
        from sigma_mem.machine import build_machine

        machine = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        actions = machine.get_actions_for_state("idle")
        action_names = {a.name for a in actions}
        assert "dream" in action_names

    def test_dream_action_reachable_from_returning(self, mem_dir, teams_dir):
        from sigma_mem.machine import build_machine

        machine = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        actions = machine.get_actions_for_state("returning")
        action_names = {a.name for a in actions}
        assert "dream" in action_names

    def test_dream_handler_invocation(self, mem_dir, teams_dir):
        from sigma_mem.machine import build_machine

        machine = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        handler = machine.get_handler("dream")
        result = handler(scope="personal")
        assert result["_state"] == "idle"
        assert result["mode"] == "dry_run"
        assert "personal" in result

    def test_dream_handler_apply_via_string(self, mem_dir, teams_dir):
        from sigma_mem.machine import build_machine

        machine = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        handler = machine.get_handler("dream")
        result = handler(scope="personal", apply="true")
        assert result["mode"] == "apply"

    def test_dream_handler_apply_false_string(self, mem_dir, teams_dir):
        from sigma_mem.machine import build_machine

        machine = build_machine(memory_dir=mem_dir, teams_dir=teams_dir)
        handler = machine.get_handler("dream")
        result = handler(scope="personal", apply="false")
        assert result["mode"] == "dry_run"
