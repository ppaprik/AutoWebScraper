#======================================================================================================
# Tests for the HTTP classification provider.
# Uses unittest.mock to patch aiohttp.ClientSession.post.
#======================================================================================================

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services.classification import (
    ClassificationResult,
    HttpApiProvider,
    create_provider,
)


#----------------------------------------------------------------------------------------------------
# HELPER: Mock aiohttp response
def _mock_aiohttp_post(response_json, status=200):
    """
    Build a patch for aiohttp.ClientSession that returns the given JSON.
    Returns a context manager decorator ready to wrap a test function.
    """
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=response_json)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    return patch("aiohttp.ClientSession", return_value=mock_session)


#----------------------------------------------------------------------------------------------------
# CONFIGURATION
class TestHttpApiProviderConfig:

    def test_provider_name(self):
        """Provider exposes the correct name."""
        provider = HttpApiProvider(config={})
        assert provider.name == "http_api"

    def test_default_endpoint(self):
        """Default endpoint points to Ollama on host."""
        provider = HttpApiProvider(config={})
        assert "11434" in provider._endpoint

    def test_custom_endpoint(self):
        """Custom endpoint is respected."""
        provider = HttpApiProvider(
            config={"http_endpoint": "http://my-server:8080/classify"}
        )
        assert provider._endpoint == "http://my-server:8080/classify"

    def test_default_format_is_ollama(self):
        """Default API format is Ollama."""
        provider = HttpApiProvider(config={})
        assert provider._api_format == "ollama"

    def test_openai_format(self):
        """OpenAI format is recognized."""
        provider = HttpApiProvider(config={"http_api_format": "openai_chat"})
        assert provider._api_format == "openai_chat"

    def test_unknown_format_defaults_to_ollama(self):
        """Unknown format silently falls back to Ollama."""
        provider = HttpApiProvider(config={"http_api_format": "nonsense"})
        assert provider._api_format == "ollama"


#----------------------------------------------------------------------------------------------------
# PROMPT AND REQUEST BUILDING
class TestPromptBuilding:

    def test_build_prompt_includes_labels(self):
        """Built prompt includes all candidate labels."""
        provider = HttpApiProvider(config={})
        prompt = provider._build_prompt("Sample text", ["Food", "History", "Tech"])
        assert "Food" in prompt
        assert "History" in prompt
        assert "Tech" in prompt
        assert "Sample text" in prompt

    def test_build_prompt_truncates_long_text(self):
        """Very long text is truncated to fit token limits."""
        provider = HttpApiProvider(config={})
        long_text = "x" * 5000
        prompt = provider._build_prompt(long_text, ["Food"])
        assert len(prompt) < 5000

    def test_ollama_request_body_format(self):
        """Ollama request uses prompt + model fields."""
        provider = HttpApiProvider(config={"http_api_format": "ollama"})
        body = provider._build_request_body("test prompt")
        assert body["model"] == "llama3"
        assert body["prompt"] == "test prompt"
        assert body["stream"] is False

    def test_openai_request_body_format(self):
        """OpenAI request uses messages array."""
        provider = HttpApiProvider(config={"http_api_format": "openai_chat"})
        body = provider._build_request_body("test prompt")
        assert "messages" in body
        assert body["messages"][0]["content"] == "test prompt"

    def test_auth_header_added_when_configured(self):
        """Authorization header is added when configured."""
        provider = HttpApiProvider(config={"http_auth_header": "Bearer sk-123"})
        headers = provider._build_headers()
        assert headers["Authorization"] == "Bearer sk-123"

    def test_no_auth_header_by_default(self):
        """No Authorization header when not configured."""
        provider = HttpApiProvider(config={})
        headers = provider._build_headers()
        assert "Authorization" not in headers


#----------------------------------------------------------------------------------------------------
# RESPONSE PARSING
class TestResponseParsing:

    def test_parse_clean_json_response(self):
        """Clean JSON response parses correctly."""
        provider = HttpApiProvider(config={})
        response = '{"labels": ["Food", "History"], "scores": [0.9, 0.7]}'
        result = provider._parse_response(response, ["Food", "History", "Tech"])

        assert result.has_result is True
        assert "Food" in result.labels
        assert "History" in result.labels
        assert result.primary_label == "Food"  # Higher score
        assert result.primary_score == 0.9

    def test_parse_json_in_markdown_fence(self):
        """JSON wrapped in markdown code fence is extracted."""
        provider = HttpApiProvider(config={})
        response = '```json\n{"labels": ["Food"], "scores": [0.8]}\n```'
        result = provider._parse_response(response, ["Food", "Tech"])
        assert result.primary_label == "Food"

    def test_parse_json_with_surrounding_text(self):
        """JSON embedded in conversational text is extracted."""
        provider = HttpApiProvider(config={})
        response = (
            'Sure, here is the classification:\n'
            '{"labels": ["Tech"], "scores": [0.95]}\n'
            'Let me know if you need more.'
        )
        result = provider._parse_response(response, ["Food", "Tech"])
        assert result.primary_label == "Tech"

    def test_parse_hallucinated_labels_filtered_out(self):
        """Labels not in the candidate list are filtered out."""
        provider = HttpApiProvider(config={})
        response = '{"labels": ["Fake", "Food"], "scores": [0.9, 0.6]}'
        result = provider._parse_response(response, ["Food", "Tech"])
        assert "Fake" not in result.labels
        assert "Food" in result.labels

    def test_parse_case_insensitive_matching(self):
        """Label matching is case-insensitive but returns canonical casing."""
        provider = HttpApiProvider(config={})
        response = '{"labels": ["food", "TECH"], "scores": [0.8, 0.7]}'
        result = provider._parse_response(response, ["Food", "Tech"])
        assert "Food" in result.labels  # Original casing preserved
        assert "Tech" in result.labels

    def test_parse_empty_labels(self):
        """Empty label array returns empty result."""
        provider = HttpApiProvider(config={})
        response = '{"labels": [], "scores": []}'
        result = provider._parse_response(response, ["Food", "Tech"])
        assert result.has_result is False

    def test_parse_malformed_json(self):
        """Malformed JSON returns empty result with error metadata."""
        provider = HttpApiProvider(config={})
        response = "This is not JSON at all, just plain text."
        result = provider._parse_response(response, ["Food"])
        assert result.has_result is False
        assert result.raw_response is not None

    def test_parse_scores_clamped(self):
        """Out-of-range scores are clamped to [0, 1]."""
        provider = HttpApiProvider(config={})
        response = '{"labels": ["Food"], "scores": [1.5]}'
        result = provider._parse_response(response, ["Food"])
        assert result.primary_score == 1.0

        response = '{"labels": ["Food"], "scores": [-0.3]}'
        result = provider._parse_response(response, ["Food"])
        assert result.primary_score == 0.0

    def test_parse_invalid_score_defaults_to_one(self):
        """Non-numeric scores default to 1.0."""
        provider = HttpApiProvider(config={})
        response = '{"labels": ["Food"], "scores": ["high"]}'
        result = provider._parse_response(response, ["Food"])
        assert result.primary_score == 1.0

    def test_parse_results_sorted_by_confidence(self):
        """Results are always sorted by score descending."""
        provider = HttpApiProvider(config={})
        response = '{"labels": ["Food", "Tech", "History"], "scores": [0.3, 0.9, 0.6]}'
        result = provider._parse_response(response, ["Food", "Tech", "History"])
        assert result.labels == ["Tech", "History", "Food"]
        assert result.scores == [0.9, 0.6, 0.3]
        assert result.primary_label == "Tech"


#----------------------------------------------------------------------------------------------------
# END-TO-END CLASSIFY (WITH MOCKED HTTP)
class TestClassifyEndToEnd:

    @pytest.mark.asyncio
    async def test_classify_empty_text_returns_empty(self):
        """Empty text short-circuits without making an HTTP call."""
        provider = HttpApiProvider(config={})
        result = await provider.classify("", ["Food"])
        assert result.has_result is False

    @pytest.mark.asyncio
    async def test_classify_no_candidates_returns_empty(self):
        """Empty candidate list short-circuits."""
        provider = HttpApiProvider(config={})
        result = await provider.classify("Some text", [])
        assert result.has_result is False

    @pytest.mark.asyncio
    async def test_classify_successful_ollama_response(self):
        """A successful Ollama response is parsed correctly."""
        fake_response = {
            "response": '{"labels": ["Food"], "scores": [0.85]}'
        }

        with _mock_aiohttp_post(fake_response):
            provider = HttpApiProvider(config={})
            result = await provider.classify(
                "A recipe for making pasta from scratch.",
                ["Food", "Tech", "History"],
            )

        assert result.has_result is True
        assert result.primary_label == "Food"
        assert result.primary_score == 0.85

    @pytest.mark.asyncio
    async def test_classify_openai_format_response(self):
        """OpenAI-format responses are parsed via the right extractor."""
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"labels": ["Tech"], "scores": [0.9]}'
                    }
                }
            ]
        }

        with _mock_aiohttp_post(fake_response):
            provider = HttpApiProvider(
                config={"http_api_format": "openai_chat"}
            )
            result = await provider.classify(
                "A new programming framework was released today.",
                ["Food", "Tech"],
            )

        assert result.primary_label == "Tech"

    @pytest.mark.asyncio
    async def test_classify_http_error_returns_empty(self):
        """HTTP errors return an empty result, not an exception."""
        with _mock_aiohttp_post({}, status=500):
            provider = HttpApiProvider(config={})
            result = await provider.classify("Text", ["Food"])

        assert result.has_result is False


#----------------------------------------------------------------------------------------------------
# FACTORY INTEGRATION
class TestFactoryIntegration:

    def test_factory_creates_http_api_provider(self):
        """Factory creates HttpApiProvider for provider='http_api'."""
        provider = create_provider({"provider": "http_api"})
        assert isinstance(provider, HttpApiProvider)

    def test_factory_passes_config_to_provider(self):
        """Factory passes config keys through to the provider."""
        provider = create_provider({
            "provider": "http_api",
            "http_endpoint": "http://custom:9999/api",
            "http_model": "mistral",
        })
        assert isinstance(provider, HttpApiProvider)
        assert provider._endpoint == "http://custom:9999/api"
        assert provider._model == "mistral"
