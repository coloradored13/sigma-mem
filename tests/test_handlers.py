"""Tests for handlers — state detection, path validation, read/write ops."""

from pathlib import Path

import pytest

from sigma_mem.handlers import (
    _detect_state,
    _validate_path,
    handle_recall,
    handle_store_memory,
    handle_search_memory,
    handle_get_project,
    handle_update_belief,
)


class TestValidatePath:
    def test_valid_filename(self, tmp_path):
        result = _validate_path(tmp_path, "conv.md")
        assert result is not None
        assert result == (tmp_path / "conv.md").resolve()

    def test_traversal_blocked(self, tmp_path):
        result = _validate_path(tmp_path, "../../etc/passwd")
        assert result is None

    def test_absolute_path_blocked(self, tmp_path):
        result = _validate_path(tmp_path, "/etc/passwd")
        assert result is None


class TestDetectState:
    def test_correction_phrase(self, tmp_path):
        assert _detect_state("you're wrong about that", tmp_path) == "correcting"

    def test_single_word_not_enough_for_correction(self, tmp_path):
        # "actually" alone shouldn't trigger correcting with high confidence
        # unless paired with correction-like context
        state = _detect_state("actually let me debug this error", tmp_path)
        assert state == "debugging"  # debugging scores higher

    def test_debugging(self, tmp_path):
        assert _detect_state("I got a traceback in the logs", tmp_path) == "debugging"

    def test_returning(self, tmp_path):
        assert _detect_state("it's been a while, catch me up", tmp_path) == "returning"

    def test_project_by_name(self, tmp_path):
        projects = tmp_path / "projects.md"
        projects.write_text("*coach[webapp prompt refine|1|26.3]\n")
        assert _detect_state("working on coach", tmp_path) == "project_work"

    def test_idle_fallback(self, tmp_path):
        assert _detect_state("hello there", tmp_path) == "idle"

    def test_ambiguous_favors_higher_score(self, tmp_path):
        # "fix the bug" should be debugging not correcting
        assert _detect_state("fix the bug", tmp_path) == "debugging"


class TestHandleRecall:
    def test_returns_core_memory(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("U[test|1|26.3]\n→ action link\n")
        result = handle_recall("hello", tmp_path)
        assert "core_memory" in result
        assert "_state" in result

    def test_anti_memory_warnings(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("U[test|1|26.3]\n¬[developer(not a dev)]")
        result = handle_recall("developer stuff", tmp_path)
        assert len(result.get("anti_memory_warnings", [])) > 0


class TestHandleStoreMemory:
    def test_appends_entry(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("existing content\n→ action link\n")
        result = handle_store_memory("new entry", "conv.md", tmp_path)
        assert result["stored"] == "new entry"
        content = f.read_text()
        assert "new entry" in content
        assert "→ action link" in content  # actions preserved

    def test_path_traversal_blocked(self, tmp_path):
        result = handle_store_memory("hack", "../../etc/passwd", tmp_path)
        assert "error" in result

    def test_missing_file(self, tmp_path):
        result = handle_store_memory("entry", "nonexistent.md", tmp_path)
        assert "error" in result


class TestHandleUpdateBelief:
    def test_replaces_belief(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("C[old belief|1|26.3]\n")
        result = handle_update_belief("old belief", "new belief", tmp_path)
        assert "updated" in result
        assert "new belief" in mem.read_text()

    def test_old_not_found(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("C[something else|1|26.3]\n")
        result = handle_update_belief("nonexistent", "new", tmp_path)
        assert "error" in result


class TestHandleSearchMemory:
    def test_finds_matches(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("sigma-mem is cool\nother line\n")
        result = handle_search_memory("sigma", tmp_path)
        assert "conv.md" in result["matches"]

    def test_no_matches(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("nothing relevant here\n")
        result = handle_search_memory("zzzzz", tmp_path)
        assert len(result["matches"]) == 0
