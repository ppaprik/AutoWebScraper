#======================================================================================================
# Standalone subprocess worker. Reads a JSON args dict from stdin,
# runs HTTP fetch + content extraction + optional classification,
# writes a JSON result dict to stdout.

# Invoked by ScraperManager via:
#     subprocess.run(["python", "-m", "backend.workers.page_worker"], ...)

# STDOUT: single JSON line (the result dict)
# STDERR: any errors/warnings (ignored by coordinator unless returncode != 0)
#======================================================================================================

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional


async def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Full fetch + extract + classify pipeline for one URL."""
    import aiohttp
    from backend.src.services.content_extractor import ContentExtractor

    url: str = args["url"]
    data_targets: List[str] = args.get("data_targets", ["text"])
    timeout_sec: int = int(args.get("timeout", 30))
    user_agent: str = args.get("user_agent", "WebScraper/1.0")
    max_retries: int = int(args.get("max_retries", 3))
    retry_delay: float = float(args.get("retry_delay", 2.0))
    classify_here: bool = bool(args.get("classify_in_process", True))
    classification_config: Dict = args.get("classification_config") or {}

    result: Dict[str, Any] = {
        "url": url,
        "success": False,
        "html": None,
        "content_blocks": None,
        "page_title": None,
        "http_status": None,
        "error": None,
        "labels": [],
        "classified": False,
    }


    #---------------------------------------------------------------------------
    # HTTP FETCH
    headers = {"User-Agent": user_agent}
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    html: Optional[str] = None

    for attempt in range(max_retries + 1):
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=timeout) as response:
                    result["http_status"] = response.status

                    if response.status == 200:
                        html = await response.text(errors="replace")
                        break

                    if response.status in (301, 302, 303, 307, 308):
                        result["error"] = f"Redirect {response.status}"
                        return result

                    if response.status >= 500 and attempt < max_retries:
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                        continue

                    result["error"] = f"HTTP {response.status}"
                    return result

        except Exception as exc:
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2 ** attempt))
                continue
            result["error"] = str(exc)
            return result

    if html is None:
        result["error"] = "No content received"
        return result

    result["html"] = html


    #---------------------------------------------------------------------------
    # CONTENT EXTRACTION
    try:
        extractor = ContentExtractor()
        result["content_blocks"] = extractor.extract(
            html, url=url, data_targets=data_targets
        )
        result["page_title"] = extractor.extract_title(html)
        result["success"] = True
    except Exception as exc:
        result["error"] = f"Extraction error: {exc}"
        return result


    #---------------------------------------------------------------------------
    # CLASSIFICATION (only if enabled and requested)
    if classify_here and result["content_blocks"] and classification_config:
        provider_name = classification_config.get("provider", "none")

        if provider_name != "none":
            try:
                from backend.src.services.classification.factory import (
                    create_provider,
                )

                provider = create_provider(classification_config)

                # Build text for classifier
                max_words = int(classification_config.get("max_words", 500))
                title_text = result["page_title"] or ""
                body_parts: List[str] = []
                word_count = 0

                for block in result["content_blocks"]:
                    if isinstance(block, dict):
                        text = block.get("content", "")
                    else:
                        text = str(block)

                    words = text.split()
                    remaining = max_words - word_count
                    if remaining <= 0:
                        break

                    body_parts.append(" ".join(words[:remaining]))
                    word_count += min(len(words), remaining)

                full_text = (
                    f"{title_text} {' '.join(body_parts)}".strip()
                )

                raw_labels_str = classification_config.get(
                    "candidate_labels", ""
                )
                if isinstance(raw_labels_str, str):
                    candidate_labels = [
                        lbl.strip()
                        for lbl in raw_labels_str.split(",")
                        if lbl.strip()
                    ]
                else:
                    candidate_labels = list(raw_labels_str)

                threshold = float(
                    classification_config.get("confidence_threshold", 0.4)
                )

                raw = await provider.classify(
                    text=full_text,
                    candidate_labels=candidate_labels,
                )

                result["labels"] = [
                    label
                    for label, score in zip(raw.labels, raw.scores)
                    if score >= threshold
                ]
                result["classified"] = True

            except Exception as exc:
                # Non-fatal error, page is saved without classification
                print(
                    f"[page_worker] classification failed: {exc}",
                    file=sys.stderr,
                )
                result["labels"] = []
                result["classified"] = False

    return result


def main() -> None:
    """Read args from stdin, run pipeline, write result to stdout."""
    try:
        raw_input = sys.stdin.read()
        args = json.loads(raw_input)
    except Exception as exc:
        error_result = {
            "url": "",
            "success": False,
            "html": None,
            "content_blocks": None,
            "page_title": None,
            "http_status": None,
            "error": f"Failed to parse input: {exc}",
            "labels": [],
            "classified": False,
        }
        print(json.dumps(error_result))
        sys.exit(0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(run(args))
    except Exception as exc:
        result = {
            "url": args.get("url", ""),
            "success": False,
            "html": None,
            "content_blocks": None,
            "page_title": None,
            "http_status": None,
            "error": f"Pipeline error: {exc}",
            "labels": [],
            "classified": False,
        }
    finally:
        loop.close()

    # Write result as single JSON line to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()
