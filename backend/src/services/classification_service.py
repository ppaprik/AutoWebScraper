#======================================================================================================
# Classification service
# Classify a page given its title and content blocks.
#======================================================================================================

from __future__ import annotations

import threading
from typing import List, Optional

from backend.config import get_app_config
from backend.logging_config import get_logger
from backend.src.services.classification.base import ClassificationProvider, ClassificationResult
from backend.src.services.classification.factory import create_provider


logger = get_logger("classification_service")


#----------------------------------------------------------------------------------------------------
# Module-level singleton state
_provider: Optional[ClassificationProvider] = None
_init_lock: threading.Lock = threading.Lock()


def _get_or_create_provider() -> ClassificationProvider:
    """
    Return the process-level provider, creating it on first call.
    Thread-safe via double-checked locking.
    """
    global _provider

    if _provider is not None:
        return _provider

    with _init_lock:
        if _provider is not None:
            return _provider

        config_dict = get_app_config().classification_config_dict
        _provider = create_provider(config_dict)
        logger.info(
            "classification_provider_initialized",
            provider=_provider.name,
        )

    return _provider


class ClassificationService:
    """
    Classify a page given its title and content blocks.
    """

    def __init__(self) -> None:
        self._app_config = get_app_config()

    @property
    def _provider(self) -> ClassificationProvider:
        return _get_or_create_provider()

    @property
    def is_enabled(self) -> bool:
        return self._provider.name != "none"

    def build_classification_text(
        self,
        title: Optional[str],
        content_blocks: List[dict],
    ) -> str:
        max_words: int = self._app_config.classification_max_words
        parts: List[str] = []
        word_count: int = 0

        # Title counts toward the word budget
        if title and title.strip():
            title_words = title.strip().split()
            remaining = max_words - word_count
            parts.append(" ".join(title_words[:remaining]))
            word_count += min(len(title_words), remaining)

        # Add content blocks until we hit the word budget
        for block in content_blocks:
            if word_count >= max_words:
                break

            text = block.get("content", "")
            if not text or not text.strip():
                continue

            # Skip pure code blocks — they hurt classification accuracy
            if block.get("type") == "code_block":
                continue

            words = text.strip().split()
            remaining = max_words - word_count
            parts.append(" ".join(words[:remaining]))
            word_count += min(len(words), remaining)

        return " ".join(parts)

    async def classify(
        self,
        title: Optional[str],
        content_blocks: List[dict],
    ) -> ClassificationResult:
        """
        Classify a page given its title and content blocks.
        """
        if not self.is_enabled:
            return ClassificationResult()

        text = self.build_classification_text(title, content_blocks)

        if not text.strip():
            return ClassificationResult()

        candidate_labels = self._app_config.classification_candidate_labels

        if not candidate_labels:
            return ClassificationResult()

        try:
            result = await self._provider.classify(
                text=text,
                candidate_labels=candidate_labels,
                multi_label=True,
            )
            return result
        except Exception as exc:
            logger.error(
                "classification_error",
                error=str(exc),
                text_length=len(text),
            )
            return ClassificationResult()

    async def warmup(self) -> None:
        """
        Optional: pre-load the provider's model/connection. Called once during Celery worker initialization.
        """
        provider = _get_or_create_provider()
        await provider.warmup()


def get_classification_service() -> ClassificationService:
    """
    Return the singleton ClassificationService instance.
    """
    return ClassificationService()


async def warmup_classification_service() -> None:
    """
    Initialize and warm up the classification provider.
    """
    service = get_classification_service()
    provider_name = service._provider.name

    if provider_name == "none":
        logger.info("classification_disabled_skipping_warmup")
        return

    logger.info("classification_warmup_starting", provider=provider_name)

    try:
        await service.warmup()
        logger.info("classification_warmup_complete", provider=provider_name)
    except Exception as exc:
        logger.warning("classification_warmup_failed", error=str(exc))
