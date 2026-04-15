#======================================================================================================
# Classification provider that returns no labels.
#======================================================================================================

from __future__ import annotations

from typing import List

from backend.src.services.classification.base import (
    ClassificationProvider,
    ClassificationResult,
)


class NullProvider(ClassificationProvider):
    """
    Classification provider that returns no labels.
    """

    provider_name: str = "none"

    async def classify(
        self,
        text: str,
        candidate_labels: List[str],
        multi_label: bool = True,
    ) -> ClassificationResult:
        """Always returns an empty result — no labels assigned."""
        return ClassificationResult(
            labels=[],
            scores=[],
            primary_label=None,
            primary_score=0.0,
            raw_response={"provider": "null", "text_length": len(text)},
        )
