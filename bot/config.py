"""
config.py — Central configuration for the TVP Discord bot.

Copy .env.example to .env and fill in your values.
All settings here can be overridden via environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Discord ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

# ── Open WebUI ────────────────────────────────────────────────────────────────
OPENWEBUI_API_URL: str = os.getenv(
    "OPENWEBUI_API_URL", "https://gpt.maynardfolks.com"
)
OPENWEBUI_API_KEY: str = os.getenv("OPENWEBUI_API_KEY", "")

# The workspace model ID as it appears in Open WebUI
MODEL_ID: str = os.getenv("MODEL_ID", "tvp-chatbot")

# ── Conversation History Tuning ───────────────────────────────────────────────
# Maximum number of turns (user + assistant messages) kept per channel.
# Increase for longer memory, decrease to reduce token usage / avoid rate limits.
MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

# Rough token ceiling for history trimming (1 token ≈ 4 chars).
# Messages older than this threshold are dropped from the context window.
# 4000 leaves headroom under typical 8k context limits.
MAX_HISTORY_TOKENS_ESTIMATE: int = int(
    os.getenv("MAX_HISTORY_TOKENS_ESTIMATE", "4000")
)

# ── Response Length ───────────────────────────────────────────────────────────
# Maximum tokens in the model's response. None = no cap (model decides).
# 500-800 is a good Discord-friendly range. Raise for more detailed responses.
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "750"))

# ── System Prompt ─────────────────────────────────────────────────────────────
# Optional system message prepended to every request.
# Leave blank to rely entirely on the workspace model's own system prompt.
SYSTEM_PROMPT: str = os.getenv("SYSTEM_PROMPT", "")
