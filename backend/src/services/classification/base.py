#======================================================================================================
# Classification provider base class
#======================================================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClassificationResult:
    """
    Result of a classification request.
    """
    labels: List[str] = field(default_factory=list)
    scores: List[float] = field(default_factory=list)
    primary_label: Optional[str] = None
    primary_score: float = 0.0
    raw_response: Optional[dict] = None

    @property
    def has_result(self) -> bool:
        """True if at least one confident label was assigned."""
        return bool(self.labels)


class ClassificationProvider(ABC):
    """
    Base class for classification providers.
    """

    #: Unique identifier used in .config to select this provider.
    provider_name: str = "base"

    def __init__(self, config: dict) -> None:
        """
        Initialize the provider.
        """
        self._config = config

    @abstractmethod
    async def classify(
        self,
        text: str,
        candidate_labels: List[str],
        multi_label: bool = True,
    ) -> ClassificationResult:
        """
        Classify text against a list of candidate labels.
        """
        raise NotImplementedError

    async def warmup(self) -> None:
        """
        Optional: pre-load the provider's model/connection. Called once during Celery worker initialization. Default is no-op.
        """
        return None

    async def shutdown(self) -> None:
        """
        Optional: release resources, close connections. Called when the provider is being replaced or the app is shutting down. Default is no-op.
        """
        return None

    @property
    def name(self) -> str:
        """Return the provider's unique name."""
        return self.provider_name
