"""Dream — ΣComm-aware memory consolidation for sigma-mem.

Four-phase consolidation modeled after biological memory consolidation:
1. Consolidate — merge duplicate entries across memory files
2. Prune — expire stale R[] entries, remove resolved corrections
3. Reorganize — promote C~[]→C[] beliefs, detect patterns
4. Index — verify checksums, count totals, report integrity

Dry-run by default: produces a report of proposed changes.
With apply=True, executes the changes.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from .integrity import extract_confidence, verify_checksum


def _today() -> date:
    return date.today()


def _parse_date(date_str: str) -> date | None:
    """Parse YY.M.D or YYYY-MM-DD into a date object."""
    try:
        s = date_str.strip()
        if "-" in s:
            parts = s.split("-")
            if len(parts) != 3:
                return None
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        parts = s.split(".")
        if len(parts) != 3:
            return None
        return date(2000 + int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def _extract_leading_date(line: str) -> date | None:
    """Extract a date from the start of a line like '26.3.7|choice|why: ...'."""
    stripped = line.strip()
    if not stripped:
        return None
    # Match YY.M.D at start
    match = re.match(r"^(\d{2}\.\d{1,2}\.\d{1,2})", stripped)
    if match:
        return _parse_date(match.group(1))
    return None


def _extract_section_refreshed_date(content: str) -> date | None:
    """Extract the section-level date from a ## research section.

    Date resolution order:
    1. Standalone 'refreshed: YY.M.D' line within the section (highest priority)
    2. Parenthetical date in section header: ## research: topic (26.3.21)

    Agent research sections typically have a standalone line like:
        refreshed: 26.3.18 | next: 26.4
    This date applies to all R[] blocks in the section.
    """
    in_research = False
    header_date: date | None = None
    for line in content.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("## research"):
            in_research = True
            # Check for parenthetical date in header: (26.3.21) or (rerun 26.3.13)
            match = re.search(r"\((?:.*?)(\d{2}\.\d{1,2}\.\d{1,2})\)", stripped)
            if match:
                header_date = _parse_date(match.group(1))
            continue
        if in_research and stripped.startswith("##"):
            break
        if in_research and "refreshed:" in stripped:
            # refreshed: line takes priority over header date
            # Try YY.M.D format
            match = re.search(r"refreshed:\s*(\d{2}\.\d{1,2}\.\d{1,2})", stripped)
            if match:
                return _parse_date(match.group(1))
            # Try YYYY-MM-DD format
            match = re.search(r"refreshed:\s*(\d{4}-\d{2}-\d{2})", stripped)
            if match:
                return _parse_date(match.group(1))
    # Fall back to header date if no refreshed: line found
    return header_date


def _extract_research_dates(
    content: str, fallback_date: date | None = None
) -> list[tuple[str, date | None]]:
    """Extract R[] blocks and their dates from content.

    Date resolution order per R[] block:
    1. Inline YY.M.D at start: R[26.3.22]
    2. Inline refreshed: key: R[topic:...|refreshed:2026-03-14] or |refreshed:26.3.14]
    3. Section-level refreshed: date (applies to all R[] blocks without own date)
    4. Caller-provided fallback_date (for when section header was stripped)
    """
    section_date = _extract_section_refreshed_date(content)
    if section_date is None:
        section_date = fallback_date
    results = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("R["):
            continue

        parsed = None

        # 1. Inline YY.M.D at start: R[26.3.22]
        match = re.match(r"R\[(\d{2}\.\d{1,2}\.\d{1,2})\]", stripped)
        if match:
            parsed = _parse_date(match.group(1))

        # 2. Inline refreshed: key (YYYY-MM-DD or YY.M.D)
        if parsed is None:
            match = re.search(
                r"refreshed:\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{1,2}\.\d{1,2})",
                stripped,
            )
            if match:
                parsed = _parse_date(match.group(1))

        # 3. Any YY.M.D embedded in block (e.g. R[fed-policy-26.3.10]:...)
        if parsed is None:
            match = re.search(r"(\d{2}\.\d{1,2}\.\d{1,2})", stripped)
            if match:
                parsed = _parse_date(match.group(1))

        # 4. Fall back to section-level refreshed date
        if parsed is None:
            parsed = section_date

        results.append((stripped, parsed))
    return results


def _normalize_for_dedup(line: str) -> str:
    """Normalize a line for duplicate detection — lowercase, strip dates and whitespace."""
    s = line.strip().lower()
    # Strip leading date
    s = re.sub(r"^\d{2}\.\d{1,2}\.\d{1,2}\|?", "", s)
    # Strip trailing date references
    s = re.sub(r"\|\d{2}\.\d{1,2}\.\d{1,2}\]?$", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Phase 1: Consolidate — find duplicates
# ---------------------------------------------------------------------------


def _find_duplicates(lines: list[str]) -> list[dict[str, Any]]:
    """Find duplicate or near-duplicate lines. Returns groups of duplicates."""
    seen: dict[str, list[int]] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("→"):
            continue
        key = _normalize_for_dedup(stripped)
        if key and len(key) > 5:  # Skip very short fragments
            seen.setdefault(key, []).append(i)

    duplicates = []
    for key, indices in seen.items():
        if len(indices) > 1:
            duplicates.append(
                {
                    "normalized": key[:80],
                    "lines": [lines[i].strip() for i in indices],
                    "line_numbers": indices,
                    "count": len(indices),
                }
            )
    return duplicates


def _consolidate_personal(memory_dir: Path) -> dict[str, Any]:
    """Phase 1 for personal memory: find duplicates across files."""
    results: dict[str, Any] = {}

    for filename in ["patterns.md", "decisions.md", "corrections.md", "conv.md"]:
        filepath = memory_dir / filename
        if not filepath.exists():
            continue
        lines = filepath.read_text().splitlines()
        dupes = _find_duplicates(lines)
        if dupes:
            results[filename] = dupes

    return results


def _consolidate_team(teams_dir: Path, team_name: str) -> dict[str, Any]:
    """Phase 1 for team memory: find duplicates in shared files."""
    team_base = (teams_dir / team_name).resolve()
    if not team_base.exists():
        return {"error": f"Team not found: {team_name}"}

    results: dict[str, Any] = {}

    for filename in ["shared/decisions.md", "shared/patterns.md"]:
        filepath = team_base / filename
        if not filepath.exists():
            continue
        lines = filepath.read_text().splitlines()
        dupes = _find_duplicates(lines)
        if dupes:
            results[filename] = dupes

    return results


# ---------------------------------------------------------------------------
# Phase 2: Prune — identify stale entries
# ---------------------------------------------------------------------------


def _extract_research_section(content: str) -> str | None:
    """Extract just the ## research section from content.

    Returns the section content, or None if no ## research section exists.
    Agent memory files have R[] blocks scattered across findings, calibration,
    and review sections — only the ## research section contains domain research.
    """
    lines = content.splitlines()
    in_research = False
    section_lines = []
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("## research"):
            in_research = True
            continue
        if in_research and stripped.startswith("##"):
            break
        if in_research:
            section_lines.append(line)
    if not in_research:
        return None
    return "\n".join(section_lines)


def _find_stale_research(
    content: str, max_age_days: int = 30, research_section_only: bool = False
) -> list[dict[str, Any]]:
    """Find R[] blocks older than max_age_days.

    Args:
        content: File content to scan.
        max_age_days: Threshold for staleness.
        research_section_only: If True, only scan within ## research section.
            Use for team agent memories where R[] blocks appear in findings,
            calibration, and other non-research sections.
    """
    fallback_date: date | None = None
    if research_section_only:
        # Extract section-level date from FULL content before stripping header
        fallback_date = _extract_section_refreshed_date(content)
        section = _extract_research_section(content)
        if section is None:
            return []
        content = section

    today = _today()
    stale = []
    for line, parsed_date in _extract_research_dates(
        content, fallback_date=fallback_date
    ):
        if parsed_date is None:
            stale.append({"line": line[:80], "reason": "no_date_found"})
        elif (today - parsed_date).days > max_age_days:
            stale.append(
                {
                    "line": line[:80],
                    "date": str(parsed_date),
                    "age_days": (today - parsed_date).days,
                    "reason": "expired",
                }
            )
    return stale


def _find_stale_dated_entries(
    content: str, max_age_days: int = 90
) -> list[dict[str, Any]]:
    """Find dated entries (YY.M.D|...) older than max_age_days."""
    today = _today()
    stale = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("→"):
            continue
        entry_date = _extract_leading_date(stripped)
        if entry_date and (today - entry_date).days > max_age_days:
            stale.append(
                {
                    "line": stripped[:80],
                    "date": str(entry_date),
                    "age_days": (today - entry_date).days,
                }
            )
    return stale


def _prune_personal(memory_dir: Path) -> dict[str, Any]:
    """Phase 2 for personal memory: identify stale entries."""
    results: dict[str, Any] = {}

    # Stale research in any file
    for filename in ["MEMORY.md", "patterns.md", "decisions.md"]:
        filepath = memory_dir / filename
        if not filepath.exists():
            continue
        content = filepath.read_text()
        stale_r = _find_stale_research(content)
        if stale_r:
            results.setdefault(filename, {})["stale_research"] = stale_r

    # Old corrections (>90 days — likely resolved)
    corrections_path = memory_dir / "corrections.md"
    if corrections_path.exists():
        stale_corrections = _find_stale_dated_entries(
            corrections_path.read_text(), max_age_days=90
        )
        if stale_corrections:
            results.setdefault("corrections.md", {})["old_entries"] = stale_corrections

    # Old failures (>90 days)
    failures_path = memory_dir / "failures.md"
    if failures_path.exists():
        stale_failures = _find_stale_dated_entries(
            failures_path.read_text(), max_age_days=90
        )
        if stale_failures:
            results.setdefault("failures.md", {})["old_entries"] = stale_failures

    return results


def _prune_team(teams_dir: Path, team_name: str) -> dict[str, Any]:
    """Phase 2 for team memory: identify stale agent research and cleared inboxes."""
    team_base = (teams_dir / team_name).resolve()
    if not team_base.exists():
        return {"error": f"Team not found: {team_name}"}

    results: dict[str, Any] = {}

    # Check agent research freshness
    agents_dir = team_base / "agents"
    if agents_dir.exists():
        stale_agents = []
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            mem_file = agent_dir / "memory.md"
            if not mem_file.exists():
                continue
            content = mem_file.read_text()
            stale_r = _find_stale_research(content, research_section_only=True)
            if stale_r:
                stale_agents.append(
                    {
                        "agent": agent_dir.name,
                        "stale_research": stale_r,
                    }
                )
        if stale_agents:
            results["stale_agent_research"] = stale_agents

    # Check for cleared inbox content (## read sections with content)
    inboxes_dir = team_base / "inboxes"
    if inboxes_dir.exists():
        clearable = []
        for inbox_file in sorted(inboxes_dir.glob("*.md")):
            content = inbox_file.read_text()
            in_read = False
            read_lines = 0
            for line in content.splitlines():
                stripped = line.strip().lower()
                if stripped.startswith("## read") or stripped.startswith("## cleared"):
                    in_read = True
                    continue
                if in_read and stripped.startswith("##"):
                    break
                if in_read and stripped and not stripped.startswith("#"):
                    read_lines += 1
            if read_lines > 0:
                clearable.append(
                    {
                        "inbox": inbox_file.stem,
                        "read_lines": read_lines,
                    }
                )
        if clearable:
            results["clearable_inboxes"] = clearable

    return results


# ---------------------------------------------------------------------------
# Phase 3: Reorganize — promote beliefs, detect systemic patterns
# ---------------------------------------------------------------------------


def _find_promotable_beliefs(memory_dir: Path) -> list[dict[str, Any]]:
    """Find C~[] beliefs that could be promoted to C[] based on evidence.

    A belief is promotable if:
    - It's tentative (C~ or ~[)
    - It appears in multiple files or has been referenced multiple times
    """
    tentative: dict[str, list[str]] = {}  # normalized → [file1, file2, ...]

    for md_file in sorted(memory_dir.glob("*.md")):
        content = md_file.read_text()
        for line in content.splitlines():
            stripped = line.strip()
            conf = extract_confidence(stripped)
            if conf == "tentative":
                key = _normalize_for_dedup(stripped)
                if key:
                    tentative.setdefault(key, []).append(md_file.name)

    # Promotable = appears in 2+ files
    promotable = []
    for key, files in tentative.items():
        if len(files) >= 2:
            promotable.append(
                {
                    "belief": key[:80],
                    "found_in": list(set(files)),
                    "occurrences": len(files),
                }
            )

    return promotable


def _find_systemic_patterns(memory_dir: Path) -> list[dict[str, Any]]:
    """Detect corrections/failures that recur ≥3 times (systemic per §9)."""
    themes: dict[str, list[str]] = {}

    for filename in ["corrections.md", "failures.md"]:
        filepath = memory_dir / filename
        if not filepath.exists():
            continue
        for line in filepath.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("→"):
                continue
            # Extract the topic (first segment after date)
            parts = stripped.split("|")
            if len(parts) >= 2:
                topic = _normalize_for_dedup(parts[1])
                if topic and len(topic) > 3:
                    themes.setdefault(topic, []).append(f"{filename}:{stripped[:60]}")

    systemic = []
    for topic, occurrences in themes.items():
        if len(occurrences) >= 3:
            systemic.append(
                {
                    "topic": topic[:60],
                    "count": len(occurrences),
                    "entries": occurrences[:5],  # Cap at 5 examples
                }
            )

    return systemic


def _find_team_canonical_patterns(
    teams_dir: Path, team_name: str
) -> list[dict[str, Any]]:
    """Find team patterns that appear across multiple reviews (canonical candidates)."""
    team_base = (teams_dir / team_name).resolve()
    if not team_base.exists():
        return []

    patterns_file = team_base / "shared" / "patterns.md"
    if not patterns_file.exists():
        return []

    content = patterns_file.read_text()
    # Count pattern themes by normalized key
    themes: dict[str, list[str]] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("→"):
            continue
        key = _normalize_for_dedup(stripped)
        if key and len(key) > 5:
            themes.setdefault(key, []).append(stripped[:80])

    canonical = []
    for key, entries in themes.items():
        if len(entries) >= 2:
            canonical.append(
                {
                    "pattern": key[:60],
                    "count": len(entries),
                    "entries": entries[:3],
                }
            )

    return canonical


def _reorganize_personal(memory_dir: Path) -> dict[str, Any]:
    """Phase 3 for personal memory."""
    results: dict[str, Any] = {}

    promotable = _find_promotable_beliefs(memory_dir)
    if promotable:
        results["promotable_beliefs"] = promotable

    systemic = _find_systemic_patterns(memory_dir)
    if systemic:
        results["systemic_patterns"] = systemic

    return results


def _reorganize_team(teams_dir: Path, team_name: str) -> dict[str, Any]:
    """Phase 3 for team memory."""
    results: dict[str, Any] = {}

    canonical = _find_team_canonical_patterns(teams_dir, team_name)
    if canonical:
        results["canonical_pattern_candidates"] = canonical

    return results


# ---------------------------------------------------------------------------
# Phase 4: Index — integrity snapshot
# ---------------------------------------------------------------------------


def _index_personal(memory_dir: Path) -> dict[str, Any]:
    """Phase 4 for personal memory: integrity snapshot."""
    file_stats: list[dict[str, Any]] = []
    total_lines = 0
    checksum_issues = 0
    confidence_counts: dict[str, int] = {}

    for md_file in sorted(memory_dir.glob("*.md")):
        content = md_file.read_text()
        lines = content.splitlines()
        line_count = len(lines)
        total_lines += line_count

        file_checksums = 0
        file_checksum_failures = 0
        for line in lines:
            stripped = line.strip()
            if "[" in stripped and "]" in stripped:
                conf = extract_confidence(stripped)
                confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
                cs = verify_checksum(stripped)
                if cs["valid"] is not None:
                    file_checksums += 1
                    if not cs["valid"]:
                        file_checksum_failures += 1
                        checksum_issues += 1

        file_stats.append(
            {
                "file": md_file.name,
                "lines": line_count,
                "checksums_verified": file_checksums,
                "checksum_failures": file_checksum_failures,
            }
        )

    return {
        "files": file_stats,
        "total_lines": total_lines,
        "total_checksum_issues": checksum_issues,
        "confidence_distribution": confidence_counts,
    }


def _index_team(teams_dir: Path, team_name: str) -> dict[str, Any]:
    """Phase 4 for team memory: integrity snapshot."""
    team_base = (teams_dir / team_name).resolve()
    if not team_base.exists():
        return {"error": f"Team not found: {team_name}"}

    shared_stats: list[dict[str, Any]] = []
    shared_dir = team_base / "shared"
    if shared_dir.exists():
        for md_file in sorted(shared_dir.glob("*.md")):
            lines = md_file.read_text().splitlines()
            shared_stats.append({"file": md_file.name, "lines": len(lines)})

    agent_stats: list[dict[str, Any]] = []
    agents_dir = team_base / "agents"
    if agents_dir.exists():
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            mem_file = agent_dir / "memory.md"
            if mem_file.exists():
                lines = mem_file.read_text().splitlines()
                agent_stats.append(
                    {
                        "agent": agent_dir.name,
                        "memory_lines": len(lines),
                    }
                )

    inbox_stats: list[dict[str, Any]] = []
    inboxes_dir = team_base / "inboxes"
    if inboxes_dir.exists():
        for inbox_file in sorted(inboxes_dir.glob("*.md")):
            lines = inbox_file.read_text().splitlines()
            inbox_stats.append(
                {
                    "inbox": inbox_file.stem,
                    "lines": len(lines),
                }
            )

    return {
        "shared_files": shared_stats,
        "agent_memories": agent_stats,
        "inboxes": inbox_stats,
    }


# ---------------------------------------------------------------------------
# Apply — execute proposed changes (when apply=True)
# ---------------------------------------------------------------------------


def _remove_lines(filepath: Path, line_indices: set[int]) -> int:
    """Remove lines at given indices from a file. Returns count removed."""
    if not filepath.exists() or not line_indices:
        return 0
    lines = filepath.read_text().splitlines()
    new_lines = [line for i, line in enumerate(lines) if i not in line_indices]
    removed = len(lines) - len(new_lines)
    if removed > 0:
        filepath.write_text("\n".join(new_lines) + "\n")
    return removed


def _apply_consolidation(
    memory_dir: Path, consolidation: dict[str, Any]
) -> dict[str, int]:
    """Remove duplicate lines, keeping the first occurrence."""
    removed: dict[str, int] = {}
    for filename, dupes in consolidation.items():
        filepath = memory_dir / filename
        indices_to_remove: set[int] = set()
        for dupe in dupes:
            # Keep first, remove rest
            for idx in dupe["line_numbers"][1:]:
                indices_to_remove.add(idx)
        count = _remove_lines(filepath, indices_to_remove)
        if count > 0:
            removed[filename] = count
    return removed


def _apply_team_consolidation(
    teams_dir: Path, team_name: str, consolidation: dict[str, Any]
) -> dict[str, int]:
    """Remove duplicate lines from team files."""
    team_base = (teams_dir / team_name).resolve()
    removed: dict[str, int] = {}
    for relative_path, dupes in consolidation.items():
        filepath = team_base / relative_path
        indices_to_remove: set[int] = set()
        for dupe in dupes:
            for idx in dupe["line_numbers"][1:]:
                indices_to_remove.add(idx)
        count = _remove_lines(filepath, indices_to_remove)
        if count > 0:
            removed[relative_path] = count
    return removed


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def dream(
    memory_dir: Path,
    teams_dir: Path,
    scope: str = "all",
    team_name: str = "",
    apply: bool = False,
) -> dict[str, Any]:
    """Run the dream consolidation cycle.

    Args:
        memory_dir: Path to personal memory directory.
        teams_dir: Path to teams directory.
        scope: "personal", "team", or "all".
        team_name: Required when scope includes team. If empty and scope is
            "all" or "team", processes all teams found in teams_dir.
        apply: If True, execute safe changes (dedup only). If False, dry-run.

    Returns:
        Dream journal — structured report of all phases.
    """
    journal: dict[str, Any] = {
        "mode": "apply" if apply else "dry_run",
        "scope": scope,
        "date": str(_today()),
    }

    # --- Personal memory ---
    if scope in ("personal", "all"):
        personal: dict[str, Any] = {}

        consolidation = _consolidate_personal(memory_dir)
        if consolidation:
            personal["consolidate"] = consolidation

        prune = _prune_personal(memory_dir)
        if prune:
            personal["prune"] = prune

        reorganize = _reorganize_personal(memory_dir)
        if reorganize:
            personal["reorganize"] = reorganize

        index = _index_personal(memory_dir)
        personal["index"] = index

        # Apply safe changes
        if apply and consolidation:
            applied = _apply_consolidation(memory_dir, consolidation)
            if applied:
                personal["applied"] = {"dedup_removed": applied}
                # Re-index after changes
                personal["index_after"] = _index_personal(memory_dir)

        journal["personal"] = personal

    # --- Team memory ---
    if scope in ("team", "all"):
        team_names: list[str] = []
        if team_name:
            # Validate team_name to prevent path traversal
            resolved = (teams_dir / team_name).resolve()
            if not resolved.is_relative_to(teams_dir.resolve()):
                return {"error": f"Invalid team name: {team_name}"}
            team_names = [team_name]
        elif teams_dir.exists():
            team_names = [
                d.name
                for d in sorted(teams_dir.iterdir())
                if d.is_dir() and (d / "shared").exists()
            ]

        teams: dict[str, Any] = {}
        for tn in team_names:
            team_report: dict[str, Any] = {}

            consolidation = _consolidate_team(teams_dir, tn)
            if consolidation:
                team_report["consolidate"] = consolidation

            prune = _prune_team(teams_dir, tn)
            if prune:
                team_report["prune"] = prune

            reorganize = _reorganize_team(teams_dir, tn)
            if reorganize:
                team_report["reorganize"] = reorganize

            index = _index_team(teams_dir, tn)
            team_report["index"] = index

            # Apply safe changes
            if apply and consolidation and "error" not in consolidation:
                applied = _apply_team_consolidation(teams_dir, tn, consolidation)
                if applied:
                    team_report["applied"] = {"dedup_removed": applied}
                    team_report["index_after"] = _index_team(teams_dir, tn)

            teams[tn] = team_report

        journal["teams"] = teams

    # --- Summary ---
    journal["summary"] = _build_summary(journal)

    return journal


def _build_summary(journal: dict[str, Any]) -> dict[str, Any]:
    """Build a human-readable summary of the dream journal."""
    summary: dict[str, Any] = {"actions_proposed": 0, "actions_applied": 0}

    personal = journal.get("personal", {})
    if personal:
        consolidate = personal.get("consolidate", {})
        prune = personal.get("prune", {})
        reorganize = personal.get("reorganize", {})

        dedup_count = sum(
            sum(d["count"] - 1 for d in dupes) for dupes in consolidate.values()
        )
        stale_count = sum(
            len(v.get("stale_research", [])) + len(v.get("old_entries", []))
            for v in prune.values()
        )
        promotable_count = len(reorganize.get("promotable_beliefs", []))
        systemic_count = len(reorganize.get("systemic_patterns", []))

        summary["personal"] = {
            "duplicates_found": dedup_count,
            "stale_entries": stale_count,
            "promotable_beliefs": promotable_count,
            "systemic_patterns": systemic_count,
        }
        summary["actions_proposed"] += dedup_count + stale_count

        applied = personal.get("applied", {})
        if applied:
            summary["actions_applied"] += sum(applied.get("dedup_removed", {}).values())

    teams = journal.get("teams", {})
    for tn, team_report in teams.items():
        consolidate = team_report.get("consolidate", {})
        prune = team_report.get("prune", {})
        reorganize = team_report.get("reorganize", {})

        dedup_count = sum(
            sum(d["count"] - 1 for d in dupes)
            for dupes in consolidate.values()
            if isinstance(dupes, list)
        )
        stale_agents = len(prune.get("stale_agent_research", []))
        clearable = len(prune.get("clearable_inboxes", []))
        canonical = len(reorganize.get("canonical_pattern_candidates", []))

        summary.setdefault("teams", {})[tn] = {
            "duplicates_found": dedup_count,
            "stale_agent_research": stale_agents,
            "clearable_inboxes": clearable,
            "canonical_candidates": canonical,
        }
        summary["actions_proposed"] += dedup_count + clearable

        applied = team_report.get("applied", {})
        if applied:
            summary["actions_applied"] += sum(applied.get("dedup_removed", {}).values())

    return summary
