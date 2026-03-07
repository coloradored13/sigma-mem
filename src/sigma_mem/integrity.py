"""Integrity checks for memory blocks — checksums, confidence, anti-memories."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def verify_checksum(block: str) -> dict[str, Any]:
    """Verify item count checksum in a compressed block like C[...|5|26.3].

    Items are split on both | and , separators. Note: some blocks use
    conceptual counts (e.g. number of projects) that may not match
    delimiter-based splitting — mismatches should be investigated, not
    auto-corrected.

    Returns dict with 'valid', 'expected', 'actual', and 'items'.
    """
    # Match block pattern: PREFIX[content|count|date]
    match = re.search(r"\[(.+)\|(\d+)\|[\d.]+\]$", block.strip())
    if not match:
        return {"valid": None, "reason": "no checksum found"}

    content = match.group(1)
    expected = int(match.group(2))
    # Items can be separated by | or , — count all of them
    items = [item.strip() for item in re.split(r"[|,]", content) if item.strip()]
    actual = len(items)

    return {
        "valid": actual == expected,
        "expected": expected,
        "actual": actual,
        "items": items,
    }


def extract_confidence(block: str) -> str:
    """Detect confidence level of a block.

    Returns 'confirmed', 'tentative', or 'unknown'.
    """
    stripped = block.strip()
    if stripped.startswith("C~") or stripped.startswith("~["):
        return "tentative"
    if stripped.startswith("C[") or stripped.startswith("C:"):
        return "confirmed"
    return "unknown"


def check_anti_memories(query: str, memory_dir: Path) -> list[str]:
    """Check if a query might trigger a known anti-memory.

    Returns list of warnings if the query touches anti-memory territory.
    """
    mem_file = memory_dir / "MEMORY.md"
    if not mem_file.exists():
        return []

    content = mem_file.read_text()
    warnings = []

    # Find ¬ block
    for line in content.splitlines():
        if not line.startswith("¬"):
            continue
        # Extract anti-memory entries
        match = re.search(r"¬\[(.+)\]", line)
        if not match:
            continue
        entries = match.group(1).split("|")
        for entry in entries:
            entry = entry.strip()
            # Extract the key term before the parenthetical
            key = entry.split("(")[0].strip().lower()
            if key and key in query.lower():
                warnings.append(f"Anti-memory triggered: {entry}")

    return warnings


def verify_file_integrity(filepath: Path) -> dict[str, Any]:
    """Run integrity checks on an entire memory file.

    Returns a report of all blocks, their checksums, and confidence levels.
    """
    if not filepath.exists():
        return {"error": f"File not found: {filepath}"}

    content = filepath.read_text()
    report = {"file": filepath.name, "blocks": [], "warnings": []}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("→"):
            continue

        # Check checksums on bracket blocks
        if "[" in line and "]" in line:
            checksum = verify_checksum(line)
            confidence = extract_confidence(line)
            block_report = {
                "line": line[:80] + ("..." if len(line) > 80 else ""),
                "confidence": confidence,
                "checksum": checksum,
            }
            report["blocks"].append(block_report)

            if checksum["valid"] is False:
                report["warnings"].append(
                    f"Checksum mismatch: expected {checksum['expected']}, "
                    f"got {checksum['actual']} in: {line[:60]}..."
                )

    return report
