"""
llm/groq_client.py — Groq (Qwen 3 32B) API wrapper.

Drop-in replacement for the previous Claude client. Uses Groq's free,
OpenAI-compatible chat completions API to serve `qwen/qwen3-32b`.
"""

import os
import re

import groq
from loguru import logger

from config import (
    GROQ_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE,
    LLM_TIMEOUT, LLM_MAX_RETRIES, SYSTEM_PROMPT,
)

# Qwen3 can emit chain-of-thought wrapped in <think>...</think>. We disable it
# via reasoning_effort and strip any residual tags defensively.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class GroqClient:
    def __init__(self):
        api_key = self._resolve_api_key()
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set.\n"
                "  Add it to backend/.env  ->  GROQ_API_KEY=gsk_...\n"
                "  Windows: set GROQ_API_KEY=gsk_...\n"
                "  Linux:   export GROQ_API_KEY=gsk_...\n"
                "  Get a free key at https://console.groq.com/keys"
            )
        # Note: the Groq SDK appends the "/openai/v1" path itself, so we must
        # NOT set base_url to include it (that caused a doubled-path 404).
        self.client = groq.Groq(
            api_key=api_key,
            timeout=LLM_TIMEOUT,
            max_retries=LLM_MAX_RETRIES,
        )
        self.model = GROQ_MODEL
        self.key_fingerprint = f"{api_key[:8]}...{api_key[-4:]}"
        logger.info(f"Groq client configured — {self.model} ({self.key_fingerprint})")

    def _resolve_api_key(self) -> str:
        key = (
            os.getenv("GROQ_API_KEY")
            or os.getenv("GROQ_KEY")
            or ""
        )
        key = key.strip()
        if (key.startswith('"') and key.endswith('"')) or (
            key.startswith("'") and key.endswith("'")
        ):
            key = key[1:-1].strip()
        return key

    def generate(self, prompt: str, stream: bool = False) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                # Disable Qwen3 "thinking" so answers are direct and fast.
                extra_body={"reasoning_effort": "none"},
            )
            text = (resp.choices[0].message.content or "").strip()
            text = _THINK_RE.sub("", text).strip()
            usage = getattr(resp, "usage", None)
            if usage:
                logger.info(
                    f"Tokens — in:{usage.prompt_tokens} out:{usage.completion_tokens}"
                )
            return text
        except groq.RateLimitError:
            return "Rate limit reached. Please wait a moment and retry."
        except groq.AuthenticationError:
            logger.error(
                f"Groq authentication failed: invalid API key ({self.key_fingerprint}). "
                "Regenerate it at https://console.groq.com/keys and update GROQ_API_KEY."
            )
            return "Authentication error: invalid GROQ_API_KEY (rejected by Groq)."
        except groq.APITimeoutError:
            logger.error(
                f"Groq request timed out after {LLM_TIMEOUT}s and "
                f"{LLM_MAX_RETRIES} retries. Check the network connection to "
                "api.groq.com, or raise LLM_TIMEOUT."
            )
            return "The model request timed out. Check the network connection and retry."
        except groq.APIConnectionError as e:
            logger.error(f"Groq connection error: {e}")
            return "Could not reach the model service. Check your internet/proxy connection."
        except groq.APIStatusError as e:
            logger.error(f"API error {e.status_code}: {e.message}")
            return f"API error {e.status_code}. Please retry."
        except Exception as e:  # noqa: BLE001
            logger.error(f"Generate failed: {e}")
            return f"Generation error: {e}"
