"""Tests for handlers — state detection, path validation, read/write ops."""

import pytest

from sigma_mem.handlers import (
    _check_notation,
    _detect_state,
    _validate_path,
    handle_full_refresh,
    handle_get_conversations,
    handle_get_corrections,
    handle_get_decisions,
    handle_get_meta,
    handle_get_patterns,
    handle_get_user_model,
    handle_log_correction,
    handle_log_decision,
    handle_log_failure,
    handle_recall,
    handle_search_memory,
    handle_store_memory,
    handle_update_belief,
    handle_verify_beliefs,
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

    def test_returns_protocol_field(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("U[test|1|26.3]\n")
        result = handle_recall("hello", tmp_path)
        assert "protocol" in result
        assert "pipe-separated" in result["protocol"]

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
        result = handle_update_belief("C[old belief|1|26.3]", "C[new belief|2|26.4]", tmp_path)
        assert "updated" in result
        assert "C[new belief|2|26.4]" in mem.read_text()

    def test_rejects_non_belief_old(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("C[old belief|1|26.3]\nsome plain text\n")
        result = handle_update_belief("some plain text", "injected", tmp_path)
        assert "error" in result
        assert "some plain text" in mem.read_text()  # unchanged

    def test_old_not_found(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("C[something else|1|26.3]\n")
        result = handle_update_belief("C[nonexistent]", "C[new]", tmp_path)
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


class TestNotationCheck:
    def test_compressed_entry_no_warning(self):
        assert _check_notation("topic|detail|why: reason") is None

    def test_short_plain_english_no_warning(self):
        assert _check_notation("quick note") is None

    def test_long_plain_english_warns(self):
        entry = "This is a plain English sentence that does not use any pipe separators at all"
        warning = _check_notation(entry)
        assert warning is not None
        assert "pipe-separated" in warning

    def test_long_entry_with_pipes_no_warning(self):
        entry = (
            "topic|this has many words but uses pipe separators so it should be fine"
        )
        assert _check_notation(entry) is None

    def test_store_memory_includes_format_warning(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("existing\n")
        entry = (
            "This is a plain English sentence without any compressed notation or pipes"
        )
        result = handle_store_memory(entry, "conv.md", tmp_path)
        assert "stored" in result
        assert "format_warning" in result

    def test_store_memory_no_warning_for_compressed(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("existing\n")
        result = handle_store_memory("topic|detail|why: reason", "conv.md", tmp_path)
        assert "stored" in result
        assert "format_warning" not in result


class TestArrowPrefixProtection:
    def test_arrow_prefixed_entry_rejected(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("existing content\n")
        result = handle_store_memory("→ see issue #42 for context", "conv.md", tmp_path)
        assert "error" in result
        # Original content unchanged
        assert "existing content" in f.read_text()
        assert "issue #42" not in f.read_text()

    def test_inline_arrow_allowed(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("existing content\n")
        result = handle_store_memory("found issue |→ fix next", "conv.md", tmp_path)
        assert "stored" in result
        assert "fix next" in f.read_text()

    def test_multiline_with_arrow_line_rejected(self, tmp_path):
        f = tmp_path / "conv.md"
        f.write_text("existing content\n")
        result = handle_store_memory("line one\n→ line two", "conv.md", tmp_path)
        assert "error" in result


@pytest.fixture
def mem_dir(tmp_path):
    """Create a minimal memory directory with common files."""
    (tmp_path / "MEMORY.md").write_text(
        "U[test user|1|26.3]\nC[confirmed belief|1|26.3]\nC~[tentative guess|1|26.3]\n"
    )
    (tmp_path / "decisions.md").write_text("26.3.7|use-postgres|why: fast\n")
    (tmp_path / "corrections.md").write_text("26.3.6|was wrong|fixed it\n")
    (tmp_path / "user.md").write_text("prefers simple explanations\n")
    (tmp_path / "patterns.md").write_text("pattern: converges on same bugs\n")
    (tmp_path / "conv.md").write_text("26.3.7|discussed architecture\n")
    (tmp_path / "failures.md").write_text("26.3.6|tried X|didn't work\n")
    (tmp_path / "meta.md").write_text("v0.1: initial system\n")
    (tmp_path / "projects.md").write_text("sigma-mem: memory MCP server\n")
    return tmp_path


class TestHandleGetDecisions:
    def test_reads_decisions(self, mem_dir):
        result = handle_get_decisions(mem_dir)
        assert "use-postgres" in result["decisions"]
        assert result["_state"] == "project_work"

    def test_missing_file(self, tmp_path):
        result = handle_get_decisions(tmp_path)
        assert "File not found" in result["decisions"]


class TestHandleGetCorrections:
    def test_reads_corrections(self, mem_dir):
        result = handle_get_corrections(mem_dir)
        assert "was wrong" in result["corrections"]
        assert result["_state"] == "correcting"


class TestHandleGetUserModel:
    def test_reads_user_model(self, mem_dir):
        result = handle_get_user_model(mem_dir)
        assert "simple explanations" in result["user_model"]
        assert result["_state"] == "philosophical"


class TestHandleGetPatterns:
    def test_reads_patterns(self, mem_dir):
        result = handle_get_patterns(mem_dir)
        assert "converges" in result["patterns"]
        assert result["_state"] == "philosophical"


class TestHandleGetConversations:
    def test_reads_conversations(self, mem_dir):
        result = handle_get_conversations(mem_dir)
        assert "architecture" in result["conversations"]
        assert result["_state"] == "reviewing"


class TestHandleGetMeta:
    def test_reads_meta(self, mem_dir):
        result = handle_get_meta(mem_dir)
        assert "initial system" in result["meta"]
        assert result["_state"] == "idle"


class TestHandleFullRefresh:
    def test_loads_all_files(self, mem_dir):
        result = handle_full_refresh(mem_dir)
        assert "test user" in result["core"]
        assert "architecture" in result["recent_conversations"]
        assert "simple explanations" in result["user_model"]
        assert "sigma-mem" in result["projects"]
        assert result["_state"] == "returning"

    def test_missing_files_returns_error_strings(self, tmp_path):
        result = handle_full_refresh(tmp_path)
        assert "File not found" in result["core"]
        assert result["_state"] == "returning"


class TestHandleVerifyBeliefs:
    def test_extracts_beliefs(self, mem_dir):
        result = handle_verify_beliefs(mem_dir)
        assert len(result["confirmed_beliefs"]) >= 1
        assert len(result["tentative_beliefs"]) >= 1
        assert any("confirmed belief" in b for b in result["confirmed_beliefs"])
        assert any("tentative guess" in b for b in result["tentative_beliefs"])
        assert result["_state"] == "returning"

    def test_empty_memory(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text("just some text\n")
        result = handle_verify_beliefs(tmp_path)
        assert result["confirmed_beliefs"] == []
        assert result["tentative_beliefs"] == []


class TestHandleLogCorrection:
    def test_logs_formatted_entry(self, mem_dir):
        result = handle_log_correction("said X", "should be Y", mem_dir)
        assert result["stored"]
        content = (mem_dir / "corrections.md").read_text()
        assert "said X" in content
        assert "should be Y" in content


class TestHandleLogDecision:
    def test_logs_with_rationale(self, mem_dir):
        result = handle_log_decision("use-redis", "faster caching", "", mem_dir)
        assert result["stored"]
        content = (mem_dir / "decisions.md").read_text()
        assert "use-redis" in content
        assert "faster caching" in content

    def test_logs_with_alternatives(self, mem_dir):
        handle_log_decision("use-redis", "fast", "memcached,local", mem_dir)
        content = (mem_dir / "decisions.md").read_text()
        assert "alt: memcached,local" in content


class TestHandleLogFailure:
    def test_logs_failure(self, mem_dir):
        result = handle_log_failure("tried caching", "too complex", mem_dir)
        assert result["stored"]
        content = (mem_dir / "failures.md").read_text()
        assert "tried caching" in content
        assert "too complex" in content
