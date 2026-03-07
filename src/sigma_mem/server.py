"""ΣMem MCP Server — memory retrieval as HATEOAS navigation.

Start with `recall`, describe your context, and the system surfaces
relevant memories with state-dependent actions for reading and writing.

Usage:
    sigma-mem                           # uses ~/.claude/memory/ + ~/.claude/teams/
    sigma-mem --memory-dir /path/to/dir # custom memory directory
    sigma-mem --teams-dir /path/to/dir  # custom teams directory
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .handlers import DEFAULT_MEMORY_DIR, DEFAULT_TEAMS_DIR
from .machine import build_machine


def main():
    parser = argparse.ArgumentParser(description="ΣMem memory MCP server")
    parser.add_argument(
        "--memory-dir",
        type=Path,
        default=DEFAULT_MEMORY_DIR,
        help=f"Path to memory directory (default: {DEFAULT_MEMORY_DIR})",
    )
    parser.add_argument(
        "--teams-dir",
        type=Path,
        default=DEFAULT_TEAMS_DIR,
        help=f"Path to teams directory (default: {DEFAULT_TEAMS_DIR})",
    )
    args = parser.parse_args()

    machine = build_machine(memory_dir=args.memory_dir, teams_dir=args.teams_dir)

    from hateoas_agent.mcp_server import serve

    serve(machine, name="sigma-mem")


if __name__ == "__main__":
    main()
