"""
Tests for HLS documentation integrity.

Validates that the HLS integration checklist and runbook documents exist and contain
all required sections and minimum content so that they remain useful and complete
as the codebase evolves.
"""

import os
import re
import pytest

DOCS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "docs", "architecture"
)

CHECKLIST_PATH = os.path.join(DOCS_DIR, "HLS_INTEGRATION_CHECKLIST.md")
RUNBOOK_PATH = os.path.join(DOCS_DIR, "HLS_RUNBOOK.md")
HLS_PATH = os.path.join(DOCS_DIR, "HLS.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def read_doc(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def headings(text: str) -> list[str]:
    """Return all markdown headings (any level) stripped of leading #s and spaces."""
    return [
        re.sub(r"^#+\s+", "", line).strip()
        for line in text.splitlines()
        if re.match(r"^#{1,6}\s+", line)
    ]


def checkbox_count(text: str) -> int:
    """Count the number of markdown task-list items (- [ ] or - [x])."""
    return len(re.findall(r"^\s*-\s+\[[ xX]\]", text, re.MULTILINE))


# ---------------------------------------------------------------------------
# Existence tests
# ---------------------------------------------------------------------------


def test_checklist_file_exists():
    assert os.path.isfile(CHECKLIST_PATH), (
        f"HLS integration checklist not found at {CHECKLIST_PATH}"
    )


def test_runbook_file_exists():
    assert os.path.isfile(RUNBOOK_PATH), (
        f"HLS runbook not found at {RUNBOOK_PATH}"
    )


# ---------------------------------------------------------------------------
# Integration checklist content tests
# ---------------------------------------------------------------------------


class TestChecklistContent:
    @pytest.fixture(scope="class")
    def checklist(self):
        return read_doc(CHECKLIST_PATH)

    REQUIRED_HEADINGS = [
        "Prerequisites",
        "Sign-Off Criteria",
        "Test Results Template",
        "Related Documents",
    ]

    REQUIRED_PHASE_PATTERNS = [
        r"Phase 1",
        r"Phase 2",
        r"Phase 3",
        r"Phase 4",
        r"Phase 5",
        r"Phase 6",
        r"Phase 7",
    ]

    def test_title_present(self, checklist):
        assert "HLS Integration Test Checklist" in checklist

    @pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
    def test_required_heading_present(self, checklist, heading):
        all_headings = headings(checklist)
        assert any(heading in h for h in all_headings), (
            f"Required section '{heading}' not found in checklist headings: {all_headings}"
        )

    @pytest.mark.parametrize("pattern", REQUIRED_PHASE_PATTERNS)
    def test_phase_section_present(self, checklist, pattern):
        assert re.search(pattern, checklist), (
            f"Expected section matching '{pattern}' not found in checklist"
        )

    def test_minimum_checkbox_count(self, checklist):
        # Checkboxes appear in Prerequisites and Sign-Off sections; table rows
        # for test steps use a Pass column instead of inline checkboxes.
        count = checkbox_count(checklist)
        assert count >= 15, (
            f"Checklist should have at least 15 checkbox items, found {count}"
        )

    def test_ios_playback_coverage(self, checklist):
        assert "iOS" in checklist or "AVPlayer" in checklist or "Safari" in checklist

    def test_browser_playback_coverage(self, checklist):
        assert "hls.js" in checklist or "browser" in checklist.lower()

    def test_latency_targets_mentioned(self, checklist):
        assert re.search(r"\d+\s*s", checklist), (
            "Checklist should mention latency targets with numeric values"
        )

    def test_lan_tests_present(self, checklist):
        assert "LAN" in checklist

    def test_wan_tests_present(self, checklist):
        assert "WAN" in checklist

    def test_sign_off_section_has_checkboxes(self, checklist):
        sign_off_block = checklist.split("Sign-Off Criteria")[-1].split("##")[0]
        assert checkbox_count(sign_off_block) >= 5, (
            "Sign-off section should have at least 5 checkbox items"
        )

    def test_links_to_runbook(self, checklist):
        assert "HLS_RUNBOOK.md" in checklist

    def test_links_to_hls_overview(self, checklist):
        assert "HLS.md" in checklist


# ---------------------------------------------------------------------------
# Runbook content tests
# ---------------------------------------------------------------------------


class TestRunbookContent:
    @pytest.fixture(scope="class")
    def runbook(self):
        return read_doc(RUNBOOK_PATH)

    REQUIRED_SECTIONS = [
        "Starting the Pipeline",
        "Stopping",
        "Health Check",
        "Log",
        "Troubleshoot",
        "Rollback",
    ]

    def test_title_present(self, runbook):
        assert "Runbook" in runbook

    @pytest.mark.parametrize("keyword", REQUIRED_SECTIONS)
    def test_required_section_present(self, runbook, keyword):
        assert keyword.lower() in runbook.lower(), (
            f"Runbook must contain a section about '{keyword}'"
        )

    def test_start_commands_present(self, runbook):
        assert "systemctl start" in runbook or "python3 streamer.py" in runbook

    def test_nginx_referenced(self, runbook):
        assert "nginx" in runbook.lower()

    def test_playlist_health_check_present(self, runbook):
        assert "playlist" in runbook.lower()

    def test_contains_code_blocks(self, runbook):
        code_blocks = re.findall(r"```", runbook)
        assert len(code_blocks) >= 6, (
            f"Runbook should have at least 3 code blocks (6 fences), found {len(code_blocks) // 2}"
        )

    def test_troubleshooting_covers_black_screen(self, runbook):
        assert "black screen" in runbook.lower() or "spinner" in runbook.lower()

    def test_troubleshooting_covers_stale_playlist(self, runbook):
        assert "stale" in runbook.lower()

    def test_troubleshooting_covers_high_latency(self, runbook):
        assert "latency" in runbook.lower()

    def test_rollback_procedure_has_git_steps(self, runbook):
        rollback_section = runbook.split("Rollback")[-1]
        assert "git" in rollback_section.lower(), (
            "Rollback section should mention git commands"
        )

    def test_links_to_checklist(self, runbook):
        assert "HLS_INTEGRATION_CHECKLIST.md" in runbook

    def test_links_to_hls_overview(self, runbook):
        assert "HLS.md" in runbook


# ---------------------------------------------------------------------------
# HLS.md cross-reference tests
# ---------------------------------------------------------------------------


class TestHlsOverviewReferences:
    @pytest.fixture(scope="class")
    def hls_doc(self):
        return read_doc(HLS_PATH)

    def test_references_checklist(self, hls_doc):
        assert "HLS_INTEGRATION_CHECKLIST.md" in hls_doc

    def test_references_runbook(self, hls_doc):
        assert "HLS_RUNBOOK.md" in hls_doc
