"""
Pulse Orchestrator — LLM Client

Provider-agnostic wrapper for LLM API calls.
Supports Anthropic (Claude) and OpenAI (GPT).

Key design decisions:
  - Forces structured JSON output from every call
  - Handles retries on transient errors (rate limits, timeouts)
  - Logs token usage for cost tracking
  - Provider is chosen at config time, not call time

Usage:
    from app.integrations.llm_client import llm_client
    result = await llm_client.call("You are a security expert...", "Review this diff...")
"""

import json
import time
from typing import Optional

from app.config import settings
from app.models.agent_models import TokenUsage
from app.utils.logger import setup_logger

logger = setup_logger("pulse.llm")

# Maximum retries on transient errors
MAX_RETRIES = 3


class LLMResponse:
    """Parsed response from an LLM call."""

    def __init__(
        self,
        content: str,
        parsed_json: Optional[dict | list],
        token_usage: TokenUsage,
        model: str,
        duration_seconds: float,
    ):
        self.content = content
        self.parsed_json = parsed_json
        self.token_usage = token_usage
        self.model = model
        self.duration_seconds = duration_seconds


class LLMClient:
    """
    Provider-agnostic LLM client.

    Reads LLM_PROVIDER and LLM_API_KEY from config.
    Supports 'anthropic' and 'openai'.
    """

    def __init__(self):
        self._anthropic_client = None
        self._openai_client = None

    def _get_anthropic_client(self):
        """Lazy-init Anthropic client."""
        if self._anthropic_client is None:
            try:
                import anthropic
                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=settings.llm_api_key
                )
            except ImportError:
                raise RuntimeError(
                    "Anthropic SDK not installed. Run: pip install anthropic"
                )
        return self._anthropic_client

    def _get_openai_client(self):
        """Lazy-init OpenAI client."""
        if self._openai_client is None:
            try:
                import openai
                self._openai_client = openai.AsyncOpenAI(
                    api_key=settings.llm_api_key
                )
            except ImportError:
                raise RuntimeError(
                    "OpenAI SDK not installed. Run: pip install openai"
                )
        return self._openai_client

    async def call(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Send a prompt to the configured LLM and get a response.

        Args:
            system_prompt: The system/role prompt (e.g., "You are a security expert...")
            user_message: The user message (e.g., the diff to review)
            model: Override the default model (optional)
            temperature: 0.0 for deterministic, higher for creative
            max_tokens: Maximum output tokens

        Returns:
            LLMResponse with content, parsed JSON, token usage, and timing
        """
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY is not configured. "
                "Run `pulse init` or set it in your .env file."
            )

        provider = settings.llm_provider.lower()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if provider == "anthropic":
                    return await self._call_anthropic(
                        system_prompt, user_message, model, temperature, max_tokens
                    )
                elif provider == "openai":
                    return await self._call_openai(
                        system_prompt, user_message, model, temperature, max_tokens
                    )
                else:
                    raise ValueError(
                        f"Unsupported LLM provider: '{provider}'. "
                        f"Use 'anthropic' or 'openai'."
                    )
            except Exception as e:
                error_str = str(e).lower()
                is_transient = any(
                    keyword in error_str
                    for keyword in ["rate_limit", "timeout", "overloaded", "529", "503"]
                )

                if is_transient and attempt < MAX_RETRIES:
                    wait_time = 2 ** attempt  # exponential backoff: 2s, 4s, 8s
                    logger.warning(
                        f"LLM call failed (attempt {attempt}/{MAX_RETRIES}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    import asyncio
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"LLM call failed after {attempt} attempt(s): {e}")
                    raise

    async def _call_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call Anthropic's Claude API."""
        client = self._get_anthropic_client()
        model = model or "claude-sonnet-4-20250514"

        start = time.time()
        logger.info(f"Calling Anthropic ({model})...")

        # Instruct JSON output in the system prompt
        json_system = (
            system_prompt + "\n\n"
            "IMPORTANT: You MUST respond with ONLY valid JSON. "
            "No markdown, no explanation outside the JSON. "
            "Your entire response must be parseable by json.loads()."
        )

        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=json_system,
            messages=[
                {"role": "user", "content": user_message}
            ],
        )

        duration = time.time() - start
        content = response.content[0].text

        # Parse JSON from response
        parsed = self._try_parse_json(content)

        token_usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
        )

        logger.info(
            f"Anthropic response: {token_usage.input_tokens} in / "
            f"{token_usage.output_tokens} out / {duration:.1f}s"
        )

        return LLMResponse(
            content=content,
            parsed_json=parsed,
            token_usage=token_usage,
            model=model,
            duration_seconds=duration,
        )

    async def _call_openai(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call OpenAI's GPT API."""
        client = self._get_openai_client()
        model = model or "gpt-4o"

        start = time.time()
        logger.info(f"Calling OpenAI ({model})...")

        response = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        duration = time.time() - start
        content = response.choices[0].message.content or ""

        parsed = self._try_parse_json(content)

        token_usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=model,
        )

        logger.info(
            f"OpenAI response: {token_usage.input_tokens} in / "
            f"{token_usage.output_tokens} out / {duration:.1f}s"
        )

        return LLMResponse(
            content=content,
            parsed_json=parsed,
            token_usage=token_usage,
            model=model,
            duration_seconds=duration,
        )

    def _try_parse_json(self, content: str) -> Optional[dict | list]:
        """
        Attempt to parse JSON from the LLM response.

        Handles common issues:
          - Response wrapped in ```json ... ``` markdown blocks
          - Leading/trailing whitespace
        """
        text = content.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON. Raw: {text[:200]}...")
            return None


# ─── Singleton ───
llm_client = LLMClient()
