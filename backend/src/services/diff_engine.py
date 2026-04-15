#======================================================================================================
# Computes and applies structured diffs between content block lists.
#======================================================================================================

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


class DiffEngine:
    """
    Computes and applies structured diffs between content block lists.
    """

    @staticmethod
    def compute_hash(content: Any) -> str:
        """Produce a SHA-256 hash of serialized content for comparison."""
        serialized = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_diff(old_content: Any, new_content: Any) -> Dict[str, List]:
        """
        Produce a structured diff between two content block lists.
        """
        diff: Dict[str, List] = {"added": [], "removed": [], "modified": []}

        old_blocks = old_content if isinstance(old_content, list) else [old_content]
        new_blocks = new_content if isinstance(new_content, list) else [new_content]

        # Build lookup maps by content text for matching
        old_by_text: Dict[str, Dict] = {}
        for block in old_blocks:
            if isinstance(block, dict):
                key = block.get("content", "")
                old_by_text[key] = block

        new_by_text: Dict[str, Dict] = {}
        for block in new_blocks:
            if isinstance(block, dict):
                key = block.get("content", "")
                new_by_text[key] = block

        # Removed: in old but not in new
        for key, block in old_by_text.items():
            if key not in new_by_text:
                diff["removed"].append(block)

        # Added: in new but not in old
        for key, block in new_by_text.items():
            if key not in old_by_text:
                diff["added"].append(block)

        # Modified: same position index but different content
        min_len = min(len(old_blocks), len(new_blocks))
        for i in range(min_len):
            old_block = old_blocks[i]
            new_block = new_blocks[i]

            if not isinstance(old_block, dict) or not isinstance(new_block, dict):
                continue

            old_text = old_block.get("content", "")
            new_text = new_block.get("content", "")
            old_type = old_block.get("type", "")
            new_type = new_block.get("type", "")

            if old_text == new_text and old_type == new_type:
                continue

            # Skip if already accounted for in added/removed
            if old_text in old_by_text and old_text not in new_by_text:
                continue
            if new_text in new_by_text and new_text not in old_by_text:
                continue

            diff["modified"].append({
                "index": i,
                "old": old_block,
                "new": new_block,
            })

        return diff

    @staticmethod
    def apply_diff(content: Any, diff: Dict[str, List]) -> List:
        """
        Apply a diff to content to produce the next version.
        Returns the updated list of content blocks.
        """
        blocks = list(content) if isinstance(content, list) else [content]

        # Apply modifications in place
        for mod in diff.get("modified", []):
            idx = mod.get("index", 0)
            if idx < len(blocks):
                blocks[idx] = mod["new"]

        # Remove deleted blocks by content match
        removed_texts = {
            block.get("content", "")
            for block in diff.get("removed", [])
            if isinstance(block, dict)
        }
        blocks = [
            b for b in blocks
            if not (isinstance(b, dict) and b.get("content", "") in removed_texts)
        ]

        # Append added blocks
        for block in diff.get("added", []):
            blocks.append(block)

        return blocks

    @staticmethod
    def has_changes(diff: Dict[str, List]) -> bool:
        """Check if a diff contains any actual changes."""
        return bool(
            diff.get("added")
            or diff.get("removed")
            or diff.get("modified")
        )

    @staticmethod
    def summarize(diff: Dict[str, List]) -> str:
        """Generate a human-readable summary of a diff."""
        added = len(diff.get("added", []))
        removed = len(diff.get("removed", []))
        modified = len(diff.get("modified", []))

        parts = []
        if added:
            parts.append(f"{added} added")
        if removed:
            parts.append(f"{removed} removed")
        if modified:
            parts.append(f"{modified} modified")

        if not parts:
            return "No changes"

        return f"{sum([added, removed, modified])} block(s) changed: {', '.join(parts)}"
