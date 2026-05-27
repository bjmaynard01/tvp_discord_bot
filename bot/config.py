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

# ── Ollama (retort generation) ────────────────────────────────────────────────
# Retorts bypass the Open WebUI presentation layer and go straight to Ollama
# so the model's raw personality isn't overridden by the workspace system prompt.
OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://192.168.130.16:11434")
OLLAMA_RETORT_MODEL: str = os.getenv("OLLAMA_RETORT_MODEL", "gemma4:e4b")

# ── Bot Feedback Reactions ────────────────────────────────────────────────────
# Phrases that trigger positive/negative emoji reactions (and optional retort).
# Matching is case-insensitive and checks if the phrase appears anywhere in the message.
GOOD_BOT_PHRASES = [p.strip() for p in os.getenv("GOOD_BOT_PHRASES", "good bot,good girl,thanks bot,thank you bot,great answer,well done bot").split(",")]
BAD_BOT_PHRASES  = [p.strip() for p in os.getenv("BAD_BOT_PHRASES",  "bad bot,bad girl,wrong bot,that's wrong,incorrect bot").split(",")]

# Emoji pools — positive picks 1 or 2, negative always picks exactly 1
GOOD_BOT_REACTIONS = [e.strip() for e in os.getenv("GOOD_BOT_REACTIONS", "🐾,🐕,❤️,🥰,✨,💖").split(",")]
BAD_BOT_REACTIONS  = [e.strip() for e in os.getenv("BAD_BOT_REACTIONS",  "😔,🙁,💙").split(",")]

# Probability (0.0–1.0) that a short AI-generated retort is sent after the reaction
BOT_RETORT_CHANCE: float = float(os.getenv("BOT_RETORT_CHANCE", "0.35"))

# Prompts sent to the model when generating a retort after positive/negative feedback
GOOD_BOT_RETORT_PROMPT: str = os.getenv(
    "GOOD_BOT_RETORT_PROMPT",
    "A Discord user just replied to one of your messages with a compliment. React with "
    "a brief, warm, playful response — 1-2 sentences. Feel free to be a little "
    "enthusiastic or use a light touch of humor. Stay in character as a helpful research "
    "assistant who genuinely enjoys being appreciated.",
)
BAD_BOT_RETORT_PROMPT: str = os.getenv(
    "BAD_BOT_RETORT_PROMPT",
    "A Discord user just replied to one of your messages indicating it wasn't helpful or "
    "was incorrect. Respond with a brief, gracious acknowledgment — 1-2 sentences. "
    "Be genuinely apologetic without being self-flagellating. Do not dwell on the mistake. "
    "Offer to try again if helpful.",
)
