#======================================================================================================
# Export service
#======================================================================================================

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Sequence


class ExportService:
    """
    Transforms scrape result data into downloadable export formats.
    """

    @staticmethod
    def to_json(results: Sequence[Any], pretty: bool = True) -> str:
        export_data: List[Dict[str, Any]] = []

        for result in results:
            entry = {
                "url": result.url,
                "http_status": result.http_status,
                "page_title": result.page_title,
                "content": result.content,
                "content_length": result.content_length,
                "content_hash": result.content_hash,
                "error": result.error,
                "scraped_at": (
                    result.created_at.isoformat() if result.created_at else None
                ),
            }
            export_data.append(entry)

        indent = 2 if pretty else None
        return json.dumps(export_data, indent=indent, ensure_ascii=False)

    @staticmethod
    def to_csv(results: Sequence[Any]) -> str:
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header
        writer.writerow([
            "url",
            "http_status",
            "page_title",
            "content_length",
            "content_hash",
            "error",
            "scraped_at",
            "content_blocks",
        ])

        # Data rows
        for result in results:
            content_json = ""
            if result.content:
                content_json = json.dumps(result.content, ensure_ascii=False)

            writer.writerow([
                result.url,
                result.http_status or "",
                result.page_title or "",
                result.content_length,
                result.content_hash or "",
                result.error or "",
                result.created_at.isoformat() if result.created_at else "",
                content_json,
            ])

        return output.getvalue()

    @staticmethod
    def flatten_content_blocks(content: List[Dict]) -> str:
        """
        Flatten a list of content blocks into plain text.
        Useful for full-text search or simple text export.
        """
        parts: List[str] = []

        for block in content:
            block_type = block.get("type", "")
            text = block.get("content", "")

            if not text:
                continue

            if block_type == "heading":
                level = block.get("level", 1)
                prefix = "#" * level
                parts.append(f"{prefix} {text}")
            elif block_type == "code_block":
                language = block.get("language", "")
                parts.append(f"```{language}\n{text}\n```")
            elif block_type == "blockquote":
                parts.append(f"> {text}")
            else:
                parts.append(text)

        return "\n\n".join(parts)
