#======================================================================================================
# Classification provider factory.
#======================================================================================================

from __future__ import annotations

from typing import Dict, Type

from backend.logging_config import get_logger
from backend.src.services.classification.base import ClassificationProvider
from backend.src.services.classification.bart_provider import BartZeroShotProvider
from backend.src.services.classification.http_api_provider import HttpApiProvider
from backend.src.services.classification.null_provider import NullProvider

logger = get_logger("classification_factory")


# Registry mapping provider_name -> provider class.
# New providers register themselves by being added to this dict.
PROVIDER_REGISTRY: Dict[str, Type[ClassificationProvider]] = {
    "none": NullProvider,
    "http_api": HttpApiProvider,
    "bart": BartZeroShotProvider,
}


def register_provider(provider_class: Type[ClassificationProvider]) -> None:
    """
    Register a new provider class under its provider_name.
    Called by provider modules on import to make themselves available.
    """
    name = provider_class.provider_name

    if name in PROVIDER_REGISTRY:
        logger.warning("provider_already_registered", name=name)
        return

    PROVIDER_REGISTRY[name] = provider_class
    logger.info("provider_registered", name=name)


def create_provider(config: dict) -> ClassificationProvider:
    """
    Create a new ClassificationProvider instance based on the provider_name
    in the config dict.
    """
    provider_name: str = (config.get("provider") or "none").strip().lower()

    provider_class = PROVIDER_REGISTRY.get(provider_name)

    if provider_class is None:
        logger.warning(
            "unknown_provider_falling_back_to_null",
            requested=provider_name,
            available=list(PROVIDER_REGISTRY.keys()),
        )
        return NullProvider(config)

    try:
        provider = provider_class(config)
        logger.info("provider_created", name=provider.name)
        return provider
    except Exception as exc:
        logger.error(
            "provider_init_failed_falling_back_to_null",
            provider=provider_name,
            error=str(exc),
        )
        return NullProvider(config)
