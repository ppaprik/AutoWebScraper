#======================================================================================================
# Classification provider backed by an HTTP API.
#======================================================================================================

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import aiohttp

from backend.logging_config import get_logger
from backend.src.services.classification.base import (
    ClassificationProvider,
    ClassificationResult,
)

logger = get_logger("http_api_provider")


# Default prompt template asks the model to return JSON only.
# {text} and {labels} are substituted at classification time.
_DEFAULT_PROMPT_TEMPLATE = (
    "You are a content classifier. Classify the following text into one or "
    "more of these categories: {labels}.\n\n"
    "Respond ONLY with a JSON object in this exact format, no other text:\n"
    '{{"labels": ["Category1", "Category2"], "scores": [0.9, 0.7]}}\n\n'
    "Only include categories you are confident about (score >= 0.4). "
    "If none fit, return empty arrays: {{\"labels\": [], \"scores\": []}}.\n\n"
    "Text to classify:\n{text}"
)


class HttpApiProvider(ClassificationProvider):
    """
    Classification provider backed by an HTTP API.
    """

    provider_name: str = "http_api"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)

        self._endpoint: str = config.get(
            "http_endpoint", "http://host.docker.internal:11434/api/generate"
        )
        self._model: str = config.get("http_model", "llama3")
        self._timeout: int = int(config.get("http_timeout", 30))
        self._api_format: str = config.get("http_api_format", "ollama").lower()
        self._prompt_template: str = config.get(
            "http_prompt_template", _DEFAULT_PROMPT_TEMPLATE
        )
        self._auth_header: Optional[str] = config.get("http_auth_header")

        if self._api_format not in ("ollama", "openai_chat"):
            logger.warning(
                "unknown_api_format_defaulting_to_ollama",
                format=self._api_format,
            )
            self._api_format = "ollama"


    #---------------------------------------------------------------------------
    # PUBLIC API
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

        prompt = self._build_prompt(text, candidate_labels)
        request_body = self._build_request_body(prompt)
        headers = self._build_headers()

        try:
            response_text = await self._post_request(request_body, headers)
        except Exception as exc:
            logger.warning("http_classification_request_failed", error=str(exc))
            return ClassificationResult(
                raw_response={"error": str(exc), "provider": "http_api"},
            )

        if not response_text:
            return ClassificationResult(
                raw_response={"error": "empty response", "provider": "http_api"},
            )

        return self._parse_response(response_text, candidate_labels)


    #---------------------------------------------------------------------------
    # REQUEST BUILDING
    def _build_prompt(self, text: str, candidate_labels: List[str]) -> str:
        """Fill the prompt template with the text and label list."""
        labels_str = ", ".join(candidate_labels)

        # Truncate very long text to avoid hitting token limits.
        # Most prompts work best with ~2000-3000 characters of context.
        if len(text) > 3000:
            text = text[:3000] + "..."

        return self._prompt_template.format(text=text, labels=labels_str)

    def _build_request_body(self, prompt: str) -> Dict[str, Any]:
        """Build the JSON request body based on the API format."""
        if self._api_format == "openai_chat":
            return {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "stream": False,
            }

        # Default: Ollama /api/generate format
        return {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers, including optional auth."""
        headers = {"Content-Type": "application/json"}
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        return headers


    #---------------------------------------------------------------------------
    # HTTP TRANSPORT
    async def _post_request(
        self,
        body: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Optional[str]:
        """
        Perform the actual HTTP POST and extract the model's text output.
        Returns the extracted text string or None on failure.
        """
        timeout = aiohttp.ClientTimeout(total=self._timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                self._endpoint,
                json=body,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    logger.warning(
                        "http_classification_http_error",
                        status=response.status,
                        endpoint=self._endpoint,
                    )
                    return None

                data = await response.json()
                return self._extract_text_from_response(data)

    def _extract_text_from_response(self, data: Dict[str, Any]) -> Optional[str]:
        """Pull the generated text out of the API response body."""
        if self._api_format == "openai_chat":
            # OpenAI: data["choices"][0]["message"]["content"]
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                logger.warning("openai_response_format_unexpected", data=str(data)[:200])
                return None

        # Ollama: data["response"]
        return data.get("response")


    #---------------------------------------------------------------------------
    # RESPONSE PARSING
    def _parse_response(
        self,
        response_text: str,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        """
        Parse the model's classification response and return a ClassificationResult.
        """
        json_obj = self._extract_json_object(response_text)

        if json_obj is None:
            logger.warning(
                "classification_response_no_json",
                response_preview=response_text[:200],
            )
            return ClassificationResult(
                raw_response={"error": "no_json", "text": response_text[:500]},
            )

        raw_labels = json_obj.get("labels", [])
        raw_scores = json_obj.get("scores", [])

        if not isinstance(raw_labels, list) or not isinstance(raw_scores, list):
            return ClassificationResult(
                raw_response={"error": "invalid_schema", "parsed": json_obj},
            )

        # Filter to only labels that exist in the candidate set
        # (models sometimes hallucinate labels outside the list)
        candidate_set = {label.lower() for label in candidate_labels}
        labels: List[str] = []
        scores: List[float] = []

        for idx, raw_label in enumerate(raw_labels):
            if not isinstance(raw_label, str):
                continue

            # Try to match the model's label to one in our candidate list
            matched = self._match_label(raw_label, candidate_labels, candidate_set)
            if matched is None:
                continue

            # Pair with a score if present and valid
            score = 1.0
            if idx < len(raw_scores):
                try:
                    score = float(raw_scores[idx])
                    # Clamp to [0.0, 1.0]
                    score = max(0.0, min(1.0, score))
                except (TypeError, ValueError):
                    score = 1.0

            labels.append(matched)
            scores.append(score)

        if not labels:
            return ClassificationResult(
                raw_response={"parsed": json_obj, "filtered_out": raw_labels},
            )

        # Sort labels by score descending so primary_label is highest confidence
        paired = sorted(zip(labels, scores), key=lambda pair: pair[1], reverse=True)
        labels = [item[0] for item in paired]
        scores = [item[1] for item in paired]

        return ClassificationResult(
            labels=labels,
            scores=scores,
            primary_label=labels[0],
            primary_score=scores[0],
            raw_response={"parsed": json_obj},
        )

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        """
        Extract a JSON object from the given text.
        """
        if not text:
            return None

        # Strip common markdown code fences
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or just ```)
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            # Remove closing fence
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # Try parsing the whole cleaned string first
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: find the first { ... } block with regex
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return None

        return None

    @staticmethod
    def _match_label(
        raw_label: str,
        candidate_labels: List[str],
        candidate_set_lower: set,
    ) -> Optional[str]:
        """
        Match a label returned by the model to one in the candidate list.
        Matching is case-insensitive and tolerates whitespace differences.
        Returns the canonical (original-case) label or None if no match.
        """
        raw_lower = raw_label.strip().lower()

        if raw_lower in candidate_set_lower:
            # Find the original-case version
            for candidate in candidate_labels:
                if candidate.lower() == raw_lower:
                    return candidate

        return None
