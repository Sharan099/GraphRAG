"""
llm/claude_client.py — Claude API wrapper (drop-in interface)
"""

import os
import anthropic
from loguru import logger
from config import CLAUDE_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, SYSTEM_PROMPT


class ClaudeClient:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set.\n"
                "  Windows: set ANTHROPIC_API_KEY=sk-ant-...\n"
                "  Linux:   export ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model  = CLAUDE_MODEL
        self._verify()

    def _verify(self):
        try:
            self.client.models.list()
            logger.info(f"Claude API ready — {self.model}")
        except anthropic.AuthenticationError:
            raise EnvironmentError("ANTHROPIC_API_KEY invalid. Check console.anthropic.com")
        except Exception as e:
            logger.warning(f"API check skipped: {e}")

    def generate(self, prompt: str, stream: bool = False) -> str:
        try:
            resp = self.client.messages.create(
                model      = self.model,
                max_tokens = LLM_MAX_TOKENS,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            u    = resp.usage
            logger.info(f"Tokens — in:{u.input_tokens} out:{u.output_tokens}")
            return text
        except anthropic.RateLimitError:
            return "Rate limit reached. Please wait a moment and retry."
        except anthropic.APIStatusError as e:
            logger.error(f"API error {e.status_code}: {e.message}")
            return f"API error {e.status_code}. Please retry."
        except Exception as e:
            logger.error(f"Generate failed: {e}")
            return f"Generation error: {e}"
