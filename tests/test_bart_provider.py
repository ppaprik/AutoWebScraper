#======================================================================================================
# Unit tests for BartZeroShotProvider.
#
# The BART model is never actually loaded in these tests — all calls to
# transformers.pipeline are intercepted by unittest.mock so the suite runs
# without torch or transformers installed and finishes in milliseconds.
#======================================================================================================

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.classification.bart_provider import (
    BartZeroShotProvider,
    _MODEL_NAME,
    _MODEL_REVISION,
)
from backend.src.services.classification.base import ClassificationResult
from backend.src.services.classification.factory import (
    PROVIDER_REGISTRY,
    create_provider,
)


#----------------------------------------------------------------------------------------------------
# Helpers
def _make_pipeline_mock(
    labels: list[str] | None = None,
    scores: list[float] | None = None,
) -> MagicMock:
    """
    Build a mock that behaves like a transformers zero-shot-classification
    pipeline — callable, returns {"labels": [...], "scores": [...], ...}.
    """
    if labels is None:
        labels = ["Technology", "Food"]
    if scores is None:
        scores = [0.85, 0.62]

    pipeline_output = {
        "labels": labels,
        "scores": scores,
        "sequence": "test sequence text",
    }

    return MagicMock(return_value=pipeline_output)


#----------------------------------------------------------------------------------------------------
# Fixtures
@pytest.fixture
def provider() -> BartZeroShotProvider:
    """Provider with default config and no model loaded."""
    return BartZeroShotProvider(config={})


@pytest.fixture
def provider_low_threshold() -> BartZeroShotProvider:
    """Provider with threshold=0.0 so every label passes filtering."""
    return BartZeroShotProvider(config={"confidence_threshold": "0.0"})


@pytest.fixture
def provider_50_words() -> BartZeroShotProvider:
    """Provider with a very low word limit to test truncation."""
    return BartZeroShotProvider(config={"bart_max_words": "50"})


#----------------------------------------------------------------------------------------------------
# Configuration tests
class TestProviderConfiguration:

    def test_provider_name_is_bart(self, provider: BartZeroShotProvider) -> None:
        """provider_name is always 'bart'."""
        assert provider.name == "bart"

    def test_default_max_words(self, provider: BartZeroShotProvider) -> None:
        """Default word limit is 500."""
        assert provider._max_words == 500

    def test_custom_max_words(self) -> None:
        """Custom bart_max_words overrides the default."""
        p = BartZeroShotProvider(config={"bart_max_words": "300"})
        assert p._max_words == 300

    def test_default_confidence_threshold(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Default threshold is 0.4."""
        assert provider._confidence_threshold == pytest.approx(0.4)

    def test_custom_confidence_threshold(self) -> None:
        """Custom confidence_threshold overrides the default."""
        p = BartZeroShotProvider(config={"confidence_threshold": "0.7"})
        assert p._confidence_threshold == pytest.approx(0.7)

    def test_default_inference_workers(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Default executor has 1 worker."""
        assert provider._executor._max_workers == 1

    def test_custom_inference_workers(self) -> None:
        """Custom bart_inference_workers sets pool size."""
        p = BartZeroShotProvider(config={"bart_inference_workers": "3"})
        assert p._executor._max_workers == 3

    def test_pipeline_starts_as_none(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Model is not loaded at construction time."""
        assert provider._pipeline is None


#----------------------------------------------------------------------------------------------------
# Text truncation tests
class TestTextTruncation:

    def test_short_text_is_not_truncated(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Text under the word limit is returned unchanged."""
        text = "Hello world"
        assert provider._truncate_to_max_words(text) == text

    def test_long_text_is_truncated(
        self, provider_50_words: BartZeroShotProvider
    ) -> None:
        """Text over the word limit is cut exactly at the word boundary."""
        text = " ".join([f"word{i}" for i in range(200)])
        result = provider_50_words._truncate_to_max_words(text)
        assert len(result.split()) == 50

    def test_exactly_at_limit_is_not_truncated(
        self, provider_50_words: BartZeroShotProvider
    ) -> None:
        """Text at exactly the word limit is returned unchanged."""
        text = " ".join([f"word{i}" for i in range(50)])
        result = provider_50_words._truncate_to_max_words(text)
        assert len(result.split()) == 50

    def test_truncation_preserves_word_boundaries(
        self, provider_50_words: BartZeroShotProvider
    ) -> None:
        """Truncation never cuts mid-word — every token is a full word."""
        text = " ".join([f"word{i}" for i in range(100)])
        result = provider_50_words._truncate_to_max_words(text)
        for word in result.split():
            assert word.startswith("word")


#----------------------------------------------------------------------------------------------------
# classify() guard clause tests (no model needed)
class TestClassifyGuards:

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_result(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Empty string short-circuits before touching the model."""
        result = await provider.classify("", ["Food", "Tech"])
        assert result.has_result is False
        assert result.labels == []

    @pytest.mark.asyncio
    async def test_whitespace_only_text_returns_empty_result(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Whitespace-only input is treated the same as empty string."""
        result = await provider.classify("   \n\t  ", ["Food"])
        assert result.has_result is False

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_result(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Empty candidate list short-circuits before touching the model."""
        result = await provider.classify("Some meaningful text here.", [])
        assert result.has_result is False


#----------------------------------------------------------------------------------------------------
# classify() with mocked inference
class TestClassifyWithMockedModel:

    @pytest.mark.asyncio
    async def test_high_confidence_labels_are_returned(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Labels above the threshold appear in the result."""
        provider._pipeline = _make_pipeline_mock(
            labels=["Technology", "Food"],
            scores=[0.85, 0.62],
        )

        result = await provider.classify(
            text="A new programming language was released.",
            candidate_labels=["Technology", "Food", "History"],
        )

        assert result.has_result is True
        assert result.primary_label == "Technology"
        assert result.primary_score == pytest.approx(0.85)
        assert "Technology" in result.labels
        assert "Food" in result.labels

    @pytest.mark.asyncio
    async def test_low_confidence_labels_are_filtered_out(
        self, provider: BartZeroShotProvider
    ) -> None:
        """Labels below the threshold are removed from the result."""
        provider._pipeline = _make_pipeline_mock(
            labels=["Technology", "Food", "History"],
            scores=[0.85, 0.35, 0.12],   # Food (0.35) and History (0.12) below 0.4
        )

        result = await provider.classify(
            text="A new programming language was released.",
            candidate_labels=["Technology", "Food", "History"],
        )

        assert result.has_result is True
        assert result.labels == ["Technology"]
        assert "Food" not in result.labels
        assert "History" not in result.labels

    @pytest.mark.asyncio
    async def test_all_labels_below_threshold_returns_empty(
        self, provider: BartZeroShotProvider
    ) -> None:
        """When every score is below threshold, result has no labels."""
        provider._pipeline = _make_pipeline_mock(
            labels=["Technology", "Food"],
            scores=[0.20, 0.15],
        )

        result = await provider.classify(
            text="Some ambiguous text.",
            candidate_labels=["Technology", "Food"],
        )

        assert result.has_result is False
        assert result.primary_label is None
        # raw_response is still populated so callers can inspect raw scores.
        assert result.raw_response is not None

    @pytest.mark.asyncio
    async def test_low_threshold_keeps_all_labels(
        self, provider_low_threshold: BartZeroShotProvider
    ) -> None:
        """With threshold=0.0 every returned label survives filtering."""
        provider_low_threshold._pipeline = _make_pipeline_mock(
            labels=["Technology", "Food", "History"],
            scores=[0.85, 0.10, 0.05],
        )

        result = await provider_low_threshold.classify(
            text="Some text.",
            candidate_labels=["Technology", "Food", "History"],
        )

        assert len(result.labels) == 3

    @pytest.mark.asyncio
    async def test_primary_label_is_highest_scoring(
        self, provider: BartZeroShotProvider
    ) -> None:
        """primary_label is always the label with the highest confidence."""
        provider._pipeline = _make_pipeline_mock(
            labels=["Space", "Science", "Technology"],
            scores=[0.91, 0.78, 0.55],
        )

        result = await provider.classify(
            text="Rocket launch to the moon scheduled for next year.",
            candidate_labels=["Space", "Science", "Technology"],
        )

        assert result.primary_label == "Space"
        assert result.primary_score == pytest.approx(0.91)

    @pytest.mark.asyncio
    async def test_raw_response_is_attached(
        self, provider: BartZeroShotProvider
    ) -> None:
        """The raw BART output dict is attached to ClassificationResult."""
        provider._pipeline = _make_pipeline_mock(
            labels=["Food"],
            scores=[0.88],
        )

        result = await provider.classify(
            text="Delicious pasta recipe with fresh tomatoes.",
            candidate_labels=["Food"],
        )

        assert result.raw_response is not None
        assert "labels" in result.raw_response
        assert "scores" in result.raw_response

    @pytest.mark.asyncio
    async def test_inference_error_returns_empty_result(
        self, provider: BartZeroShotProvider
    ) -> None:
        """If the pipeline raises, classify() returns empty instead of crashing."""
        provider._pipeline = MagicMock(side_effect=RuntimeError("CUDA OOM"))

        result = await provider.classify(
            text="Some text that triggers an error.",
            candidate_labels=["Food"],
        )

        assert result.has_result is False
        assert result.raw_response is not None
        assert "error" in result.raw_response

    @pytest.mark.asyncio
    async def test_multi_label_false_is_forwarded_to_pipeline(
        self, provider: BartZeroShotProvider
    ) -> None:
        """multi_label=False is passed to the pipeline as a keyword argument."""
        mock_pipeline = _make_pipeline_mock(
            labels=["Technology"],
            scores=[0.95],
        )
        provider._pipeline = mock_pipeline

        result = await provider.classify(
            text="Python 3.12 released with major performance improvements.",
            candidate_labels=["Technology", "Food"],
            multi_label=False,
        )

        # _run_inference_sync always passes multi_label as a keyword arg:
        #   self._pipeline(text, candidate_labels, multi_label=multi_label)
        # Therefore it appears in call_args.kwargs, not in positional args.
        assert mock_pipeline.call_args is not None
        assert mock_pipeline.call_args.kwargs.get("multi_label") is False

        assert result.has_result is True


#----------------------------------------------------------------------------------------------------
# Warmup tests
class TestWarmup:

    @pytest.mark.asyncio
    async def test_warmup_loads_model(
        self, provider: BartZeroShotProvider
    ) -> None:
        """warmup() causes _ensure_model_loaded to run and pipeline to be set."""
        mock_pipeline = _make_pipeline_mock()

        def fake_load() -> None:
            provider._pipeline = mock_pipeline

        with patch.object(provider, "_ensure_model_loaded", side_effect=fake_load):
            await provider.warmup()

        assert provider._pipeline is mock_pipeline

    @pytest.mark.asyncio
    async def test_warmup_failure_raises(
        self, provider: BartZeroShotProvider
    ) -> None:
        """warmup() propagates errors so the caller knows loading failed."""
        with patch.object(
            provider,
            "_ensure_model_loaded",
            side_effect=RuntimeError("Model download failed"),
        ):
            with pytest.raises(RuntimeError, match="Model download failed"):
                await provider.warmup()


#----------------------------------------------------------------------------------------------------
# Shutdown tests
class TestShutdown:

    @pytest.mark.asyncio
    async def test_shutdown_unloads_pipeline(
        self, provider: BartZeroShotProvider
    ) -> None:
        """shutdown() sets the pipeline back to None."""
        provider._pipeline = MagicMock()
        await provider.shutdown()
        assert provider._pipeline is None

    @pytest.mark.asyncio
    async def test_shutdown_without_loaded_model_is_safe(
        self, provider: BartZeroShotProvider
    ) -> None:
        """shutdown() when the model was never loaded does not raise."""
        assert provider._pipeline is None
        await provider.shutdown()


#----------------------------------------------------------------------------------------------------
# Factory integration tests
class TestFactoryIntegration:

    def test_bart_is_in_registry(self) -> None:
        """'bart' is a registered key in PROVIDER_REGISTRY."""
        assert "bart" in PROVIDER_REGISTRY
        assert PROVIDER_REGISTRY["bart"] is BartZeroShotProvider

    def test_factory_creates_bart_provider(self) -> None:
        """Factory instantiates BartZeroShotProvider for provider='bart'."""
        provider = create_provider({"provider": "bart"})
        assert isinstance(provider, BartZeroShotProvider)

    def test_factory_passes_config_to_bart(self) -> None:
        """Factory forwards all config keys to the BART provider."""
        provider = create_provider({
            "provider": "bart",
            "bart_max_words": "200",
            "confidence_threshold": "0.6",
        })
        assert isinstance(provider, BartZeroShotProvider)
        assert provider._max_words == 200
        assert provider._confidence_threshold == pytest.approx(0.6)

    def test_factory_is_case_insensitive_for_bart(self) -> None:
        """'BART', 'Bart', and 'bart' all create BartZeroShotProvider."""
        for name in ("BART", "Bart", "bart"):
            p = create_provider({"provider": name})
            assert isinstance(p, BartZeroShotProvider), (
                f"Expected BartZeroShotProvider for provider='{name}'"
            )
