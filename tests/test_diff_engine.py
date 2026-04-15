#======================================================================================================
# Tests for the standalone diff computation engine.
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.services.diff_engine import DiffEngine


class TestDiffEngine:

    def test_compute_hash_deterministic(self):
        """Same content produces same hash."""
        content = [{"type": "paragraph", "content": "Hello"}]
        hash1 = DiffEngine.compute_hash(content)
        hash2 = DiffEngine.compute_hash(content)
        assert hash1 == hash2

    def test_compute_hash_different_content(self):
        """Different content produces different hashes."""
        hash1 = DiffEngine.compute_hash([{"content": "A"}])
        hash2 = DiffEngine.compute_hash([{"content": "B"}])
        assert hash1 != hash2

    def test_compute_diff_no_changes(self):
        """Identical content produces an empty diff."""
        content = [{"type": "paragraph", "content": "Same"}]
        diff = DiffEngine.compute_diff(content, content)
        assert not DiffEngine.has_changes(diff)

    def test_compute_diff_added_blocks(self):
        """New blocks appear in the 'added' list."""
        old = [{"type": "paragraph", "content": "Original"}]
        new = [
            {"type": "paragraph", "content": "Original"},
            {"type": "paragraph", "content": "New block"},
        ]

        diff = DiffEngine.compute_diff(old, new)
        added_contents = [b["content"] for b in diff["added"]]
        assert "New block" in added_contents

    def test_compute_diff_removed_blocks(self):
        """Removed blocks appear in the 'removed' list."""
        old = [
            {"type": "paragraph", "content": "Keep"},
            {"type": "paragraph", "content": "Remove"},
        ]
        new = [{"type": "paragraph", "content": "Keep"}]

        diff = DiffEngine.compute_diff(old, new)
        removed_contents = [b["content"] for b in diff["removed"]]
        assert "Remove" in removed_contents

    def test_apply_diff_adds_blocks(self):
        """Applying a diff with additions includes the new blocks."""
        old = [{"type": "paragraph", "content": "Original"}]
        diff = {
            "added": [{"type": "paragraph", "content": "Added"}],
            "removed": [],
            "modified": [],
        }

        result = DiffEngine.apply_diff(old, diff)
        contents = [b["content"] for b in result]
        assert "Original" in contents
        assert "Added" in contents

    def test_apply_diff_removes_blocks(self):
        """Applying a diff with removals excludes the deleted blocks."""
        old = [
            {"type": "paragraph", "content": "Keep"},
            {"type": "paragraph", "content": "Delete"},
        ]
        diff = {
            "added": [],
            "removed": [{"type": "paragraph", "content": "Delete"}],
            "modified": [],
        }

        result = DiffEngine.apply_diff(old, diff)
        contents = [b["content"] for b in result]
        assert "Keep" in contents
        assert "Delete" not in contents

    def test_apply_diff_modifies_blocks(self):
        """Applying a diff with modifications replaces the old blocks."""
        old = [
            {"type": "heading", "content": "Old Title"},
            {"type": "paragraph", "content": "Body"},
        ]
        diff = {
            "added": [],
            "removed": [],
            "modified": [
                {"index": 0, "old": {"type": "heading", "content": "Old Title"},
                 "new": {"type": "heading", "content": "New Title"}},
            ],
        }

        result = DiffEngine.apply_diff(old, diff)
        assert result[0]["content"] == "New Title"

    def test_has_changes(self):
        """has_changes correctly identifies empty and non-empty diffs."""
        empty = {"added": [], "removed": [], "modified": []}
        assert DiffEngine.has_changes(empty) is False

        with_added = {"added": [{"content": "x"}], "removed": [], "modified": []}
        assert DiffEngine.has_changes(with_added) is True

    def test_summarize(self):
        """Summarize produces a human-readable string."""
        diff = {
            "added": [{"content": "A"}, {"content": "B"}],
            "removed": [{"content": "C"}],
            "modified": [],
        }
        summary = DiffEngine.summarize(diff)
        assert "3 block(s) changed" in summary
        assert "2 added" in summary
        assert "1 removed" in summary

    def test_summarize_no_changes(self):
        """Summarize for empty diff says 'No changes'."""
        diff = {"added": [], "removed": [], "modified": []}
        assert DiffEngine.summarize(diff) == "No changes"
