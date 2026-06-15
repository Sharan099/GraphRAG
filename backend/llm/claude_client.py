"""
llm/claude_client.py — Claude API wrapper (drop-in interface)
"""

import os
import anthropic
from loguru import logger
from config import CLAUDE_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, SYSTEM_PROMPT


class ClaudeClient:
    def __init__(self):
        api_key = self._resolve_api_key()
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set.\n"
                "  Windows: set ANTHROPIC_API_KEY=sk-ant-...\n"
                "  Linux:   export ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model  = CLAUDE_MODEL
        self.key_fingerprint = f"{api_key[:12]}...{api_key[-6:]}"
        self._verify()

    def _resolve_api_key(self) -> str:
        """
        Read API key from common environment variables and sanitize common
        shell mistakes (quotes and trailing whitespace).
        """
        key = (
            os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_KEY")
            or os.getenv("CLAUDE_API_KEY")
            or ""
        )
        key = key.strip()
        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1].strip()
        return key

    def _verify(self):
        # Avoid a hard network preflight here. Some environments can block/list
        # model metadata endpoints while inference still works. We validate key
        # during the first real generation request instead.
        logger.info(f"Claude client configured — {self.model} ({self.key_fingerprint})")

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
        except anthropic.AuthenticationError:
            logger.error(
                f"Anthropic authentication failed: invalid API key ({self.key_fingerprint}). "
                "Please rotate/regenerate the key in Anthropic Console and update ANTHROPIC_API_KEY."
            )
            return "Authentication error: invalid ANTHROPIC_API_KEY (rejected by Anthropic)."
        except anthropic.APIStatusError as e:
            logger.error(f"API error {e.status_code}: {e.message}")
            return f"API error {e.status_code}. Please retry."
        except Exception as e:
            logger.error(f"Generate failed: {e}")
            return f"Generation error: {e}"
