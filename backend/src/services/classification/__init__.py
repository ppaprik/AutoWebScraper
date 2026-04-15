#======================================================================================================
# backend/src/services/classification/__init__.py
# Public exports for the classification subpackage.
#======================================================================================================

from backend.src.services.classification.base import (
    ClassificationProvider,
    ClassificationResult,
)
from backend.src.services.classification.bart_provider import BartZeroShotProvider
from backend.src.services.classification.factory import (
    PROVIDER_REGISTRY,
    create_provider,
    register_provider,
)
from backend.src.services.classification.http_api_provider import HttpApiProvider
from backend.src.services.classification.null_provider import NullProvider

__all__ = [
    "BartZeroShotProvider",
    "ClassificationProvider",
    "ClassificationResult",
    "HttpApiProvider",
    "NullProvider",
    "PROVIDER_REGISTRY",
    "create_provider",
    "register_provider",
]
