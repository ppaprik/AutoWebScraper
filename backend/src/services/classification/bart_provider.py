# =============================================================================
# BartZeroShotProvider
# =============================================================================

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from typing import List

from backend.logging_config import get_logger
from backend.src.services.classification.base import (
    ClassificationProvider,
    ClassificationResult,
)


logger = get_logger("bart_provider")


#----------------------------------------------------------------------------------------------------
# Pinned model identity, never change these without a deliberate upgrade.
_MODEL_NAME: str = "facebook/bart-large-mnli"
_MODEL_REVISION: str = "d7645e127eaf1aefc7862fd59a17a5aa8558b8ce"


class BartZeroShotProvider(ClassificationProvider):
    """
    Zero-shot text classification backed by BART-large-MNLI running locally.

    Reads these keys from the [classification] section of .config:
        bart_inference_workers  int   Parallel inference threads (default 1)
        bart_max_words          int   Input truncation limit (default 500)
        confidence_threshold    float Minimum score to keep a label (default 0.4)
    """

    provider_name: str = "bart"

    def __init__(self, config: dict) -> None:
        super().__init__(config)

        # Number of threads that can run BART inference in parallel. Default 1 is the safest choice. Raise to 2-4 on beefy CPUs.
        inference_workers: int = int(config.get("bart_inference_workers", 1))

        # The transformers pipeline object. None until _ensure_model_loaded().
        self._pipeline = None

        # Guards model initialisation so only one thread downloads/loads even when multiple asyncio workers call classify() before warmup().
        self._load_lock: threading.Lock = threading.Lock()

        # Dedicated pool keeps blocking inference off the asyncio event loop.
        self._executor: concurrent.futures.ThreadPoolExecutor = (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=inference_workers,
                thread_name_prefix="bart_inference",
            )
        )

        # BART has a 1024-token hard limit. 500 words ≈ 700 tokens, leaving
        # room for the classification prompt tokens appended internally.
        self._max_words: int = int(config.get("bart_max_words", 500))

        # Labels with a score below this value are dropped from the result.
        self._confidence_threshold: float = float(
            config.get("confidence_threshold", 0.4)
        )


    #---------------------------------------------------------------------------
    # Internal helpers
    def _ensure_model_loaded(self) -> None:
        """
        Ensure the BART model is loaded.
        """
        # Fast path — model already loaded, no lock needed.
        if self._pipeline is not None:
            return

        with self._load_lock:
            # Re-check inside the lock: another thread may have loaded the
            # model while we were waiting to acquire it.
            if self._pipeline is not None:
                return

            logger.info(
                "bart_model_loading",
                model=_MODEL_NAME,
                revision=_MODEL_REVISION,
            )

            try:
                from transformers import pipeline as hf_pipeline
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is not installed. "
                    "Add it to requirements.txt and rebuild the image."
                ) from exc

            # TRANSFORMERS_CACHE is set to /model_cache in compose.yaml so the model persists in a named Docker volume across container restarts and rebuilds.
            cache_dir: str | None = os.environ.get("TRANSFORMERS_CACHE")

            self._pipeline = hf_pipeline(
                task="zero-shot-classification",
                model=_MODEL_NAME,
                revision=_MODEL_REVISION,
                device=-1,       # -1 = CPU only, no GPU
                cache_dir=cache_dir,
            )

            logger.info(
                "bart_model_loaded",
                cache_dir=cache_dir or "default",
            )

    def _run_inference_sync(
        self,
        text: str,
        candidate_labels: List[str],
        multi_label: bool,
    ) -> dict:
        """
        Execute synchronous BART inference.
        Called inside the ThreadPoolExecutor — must never await anything.
        """
        self._ensure_model_loaded()

        result: dict = self._pipeline(
            text,
            candidate_labels,
            multi_label=multi_label,
        )

        return result

    def _truncate_to_max_words(self, text: str) -> str:
        """
        Truncate text to the configured word limit.
        Preserves whole words — never cuts mid-word.
        """
        words: list[str] = text.split()

        if len(words) <= self._max_words:
            return text

        return " ".join(words[:self._max_words])


    #---------------------------------------------------------------------------
    # Public ClassificationProvider interface
    async def warmup(self) -> None:
        """
        Optional: pre-load the provider's model/connection. Called once during Celery worker initialization. Default is no-op.
        """
        logger.info("bart_warmup_starting")

        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(
                self._executor,
                self._ensure_model_loaded,
            )
            logger.info("bart_warmup_complete")
        except Exception as exc:
            logger.error("bart_warmup_failed", error=str(exc))
            raise

    async def classify(
        self,
        text: str,
        candidate_labels: List[str],
        multi_label: bool = True,
    ) -> ClassificationResult:
        """
        Classify text against a list of candidate labels.
        """
        if not text or not text.strip():
            return ClassificationResult()

        if not candidate_labels:
            return ClassificationResult()

        truncated_text: str = self._truncate_to_max_words(text)

        loop = asyncio.get_event_loop()

        try:
            raw: dict = await loop.run_in_executor(
                self._executor,
                lambda: self._run_inference_sync(
                    truncated_text,
                    candidate_labels,
                    multi_label,
                ),
            )
        except Exception as exc:
            logger.error(
                "bart_classification_failed",
                error=str(exc),
                text_length=len(text),
            )
            return ClassificationResult(
                raw_response={"error": str(exc), "provider": "bart"}
            )

        # BART pipeline output: {"labels": [...], "scores": [...], "sequence": "..."}
        # Labels are already sorted by score descending.
        raw_labels: List[str] = raw.get("labels", [])
        raw_scores: List[float] = raw.get("scores", [])

        # Keep only labels that meet the confidence threshold.
        filtered_pairs: list[tuple[str, float]] = [
            (label, score)
            for label, score in zip(raw_labels, raw_scores)
            if score >= self._confidence_threshold
        ]

        if not filtered_pairs:
            # No label was confident enough — caller decides what to do
            # (e.g. tag as Uncategorized).
            return ClassificationResult(raw_response=raw)

        result_labels: List[str] = [pair[0] for pair in filtered_pairs]
        result_scores: List[float] = [pair[1] for pair in filtered_pairs]

        return ClassificationResult(
            labels=result_labels,
            scores=result_scores,
            primary_label=result_labels[0],
            primary_score=result_scores[0],
            raw_response=raw,
        )

    async def shutdown(self) -> None:
        """Release the thread pool and unload the model on provider shutdown."""
        logger.info("bart_provider_shutting_down")
        self._executor.shutdown(wait=False)
        self._pipeline = None
