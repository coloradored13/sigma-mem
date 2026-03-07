"""Tests for integrity checks — checksums, confidence, anti-memories."""

from pathlib import Path

import pytest

from sigma_mem.integrity import (
    check_anti_memories,
    extract_confidence,
    verify_checksum,
    verify_file_integrity,
)


class TestVerifyChecksum:
    def test_comma_separated(self):
        block = "U[lead prod/eng, mgr eng, proj@21-02, kids, learn>del, ai teach+eff|6|26.3]"
        result = verify_checksum(block)
        assert result["valid"] is True
        assert result["expected"] == 6

    def test_pipe_and_comma_mixed(self):
        block = "C[detects perf, honest>polish, probes | !no steer to profile(caught) | no extrapolate(coach≠teach)|5|26.3]"
        result = verify_checksum(block)
        assert result["expected"] == 5

    def test_no_checksum(self):
        result = verify_checksum("plain text no brackets")
        assert result["valid"] is None

    def test_mismatch(self):
        block = "X[one, two|5|26.3]"
        result = verify_checksum(block)
        assert result["valid"] is False
        assert result["expected"] == 5
        assert result["actual"] == 2


class TestExtractConfidence:
    def test_tentative(self):
        assert extract_confidence("C~[something|1|26.3]") == "tentative"

    def test_confirmed(self):
        assert extract_confidence("C[something|1|26.3]") == "confirmed"

    def test_unknown(self):
        assert extract_confidence("some random line") == "unknown"


class TestCheckAntiMemories:
    def test_triggers_warning(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("¬[developer(leader learning to build) | teaching(coach mode≠teaching)]")
        warnings = check_anti_memories("developer", tmp_path)
        assert len(warnings) == 1
        assert "developer" in warnings[0]

    def test_no_match(self, tmp_path):
        mem = tmp_path / "MEMORY.md"
        mem.write_text("¬[developer(leader learning to build)]")
        warnings = check_anti_memories("something else", tmp_path)
        assert len(warnings) == 0

    def test_missing_file(self, tmp_path):
        warnings = check_anti_memories("anything", tmp_path)
        assert len(warnings) == 0


class TestVerifyFileIntegrity:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("U[a, b, c|3|26.3]\nC~[x, y|2|26.3]\n")
        report = verify_file_integrity(f)
        assert len(report["blocks"]) == 2
        assert len(report["warnings"]) == 0

    def test_mismatch_reported(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("U[a, b|5|26.3]\n")
        report = verify_file_integrity(f)
        assert len(report["warnings"]) == 1

    def test_missing_file(self, tmp_path):
        report = verify_file_integrity(tmp_path / "nope.md")
        assert "error" in report
