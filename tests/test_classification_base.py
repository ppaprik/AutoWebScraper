#======================================================================================================
# Unit tests for the classification provider interface and factory.
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.services.classification import (
    ClassificationProvider,
    ClassificationResult,
    NullProvider,
    create_provider,
    register_provider,
    PROVIDER_REGISTRY,
)


class TestClassificationResult:

    def test_empty_result_has_no_result(self):
        """An empty result reports has_result == False."""
        result = ClassificationResult()
        assert result.has_result is False
        assert result.labels == []
        assert result.scores == []
        assert result.primary_label is None
        assert result.primary_score == 0.0

    def test_populated_result_has_result(self):
        """A result with labels reports has_result == True."""
        result = ClassificationResult(
            labels=["Food", "History"],
            scores=[0.8, 0.6],
            primary_label="Food",
            primary_score=0.8,
        )
        assert result.has_result is True
        assert result.primary_label == "Food"


class TestNullProvider:

    @pytest.mark.asyncio
    async def test_returns_empty_result(self):
        """NullProvider always returns an empty classification."""
        provider = NullProvider(config={})
        result = await provider.classify(
            text="Any text here",
            candidate_labels=["Food", "History", "Tech"],
        )
        assert result.has_result is False
        assert result.labels == []
        assert result.primary_label is None

    @pytest.mark.asyncio
    async def test_includes_debug_info(self):
        """Raw response contains debug metadata."""
        provider = NullProvider(config={})
        result = await provider.classify(
            text="Hello world",
            candidate_labels=["X"],
        )
        assert result.raw_response is not None
        assert result.raw_response["provider"] == "null"
        assert result.raw_response["text_length"] == 11

    def test_provider_name(self):
        """NullProvider's name is 'none'."""
        provider = NullProvider(config={})
        assert provider.name == "none"

    @pytest.mark.asyncio
    async def test_warmup_and_shutdown_are_noop(self):
        """Default warmup/shutdown don't raise."""
        provider = NullProvider(config={})
        await provider.warmup()
        await provider.shutdown()


class TestFactory:

    def test_create_null_provider_explicitly(self):
        """Factory creates NullProvider when provider='none'."""
        provider = create_provider({"provider": "none"})
        assert isinstance(provider, NullProvider)

    def test_create_defaults_to_null_when_no_provider_key(self):
        """Factory defaults to NullProvider when config is empty."""
        provider = create_provider({})
        assert isinstance(provider, NullProvider)

    def test_unknown_provider_falls_back_to_null(self):
        """Factory falls back to NullProvider for unknown names."""
        provider = create_provider({"provider": "nonexistent_ai_12345"})
        assert isinstance(provider, NullProvider)

    def test_provider_name_is_case_insensitive(self):
        """Provider name lookups are case-insensitive."""
        provider = create_provider({"provider": "NONE"})
        assert isinstance(provider, NullProvider)

    def test_register_custom_provider(self):
        """Custom providers can be registered and instantiated."""

        class DummyProvider(ClassificationProvider):
            provider_name = "dummy_test"

            async def classify(self, text, candidate_labels, multi_label=True):
                return ClassificationResult(
                    labels=["dummy"],
                    scores=[1.0],
                    primary_label="dummy",
                    primary_score=1.0,
                )

        try:
            register_provider(DummyProvider)
            assert "dummy_test" in PROVIDER_REGISTRY

            provider = create_provider({"provider": "dummy_test"})
            assert isinstance(provider, DummyProvider)
            assert provider.name == "dummy_test"
        finally:
            # Clean up so other tests aren't affected
            PROVIDER_REGISTRY.pop("dummy_test", None)

    def test_failing_provider_falls_back_to_null(self):
        """If a provider's __init__ raises, factory returns NullProvider."""

        class BrokenProvider(ClassificationProvider):
            provider_name = "broken_test"

            def __init__(self, config):
                raise RuntimeError("Simulated init failure")

            async def classify(self, text, candidate_labels, multi_label=True):
                return ClassificationResult()

        try:
            register_provider(BrokenProvider)
            provider = create_provider({"provider": "broken_test"})
            assert isinstance(provider, NullProvider)
        finally:
            PROVIDER_REGISTRY.pop("broken_test", None)
