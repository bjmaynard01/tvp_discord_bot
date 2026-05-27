"""
affirmations.py — Standalone module for the affirmations/quotes/facts system.

Loads a curated library from affirmations.json and picks randomly from it.
Falls back to AI generation via Open WebUI when the library has no match.
This module never touches conversation_history — all API calls are fire-and-forget.
"""

import random
import json
import logging
import aiohttp
from pathlib import Path
from config import OPENWEBUI_API_URL, OPENWEBUI_API_KEY, MODEL_ID

log = logging.getLogger("tvp-bot")

# Resolves to bot/content/affirmations.json regardless of where the bot is run from
LIBRARY_PATH = Path(__file__).parent / "content" / "affirmations.json"

CATEGORY_LABELS = {
    "affirmation":    "Daily Affirmation",
    "science_fact":   "Science Fact",
    "history":        "Trans History",
    "quote":          "Quote",
    "community_stat": "By the Numbers",
    "reframe":        "Myth vs. Reality",
}

# Per-category prompts used when the library has no match and we fall back to AI
CATEGORY_PROMPTS = {
    "affirmation": (
        "Write one warm, affirming message for a transgender person. "
        "2-4 sentences. No clichés."
    ),
    "science_fact": (
        "Share one interesting scientific fact about gender identity, trans neuroscience, "
        "genetics, or trans healthcare. 2-3 sentences. Include what field of science it comes from."
    ),
    "history": (
        "Share one brief historical fact or milestone related to transgender history "
        "or a trans pioneer. 2-3 sentences."
    ),
    "quote": (
        "Provide one real, attributed quote from a transgender person, trans activist, or trans ally "
        "about gender identity, transition, or transgender rights. "
        "Format: quote text, then attribution on a new line starting with —"
    ),
    "community_stat": (
        "Share one meaningful statistic from transgender health research or community surveys "
        "(such as the US Transgender Survey or WPATH data). 1-2 sentences. "
        "Include the source name and approximate year."
    ),
    "reframe": (
        "Briefly address one common myth or misconception about transgender people or trans healthcare "
        "and provide the accurate information. Format: start with 'Myth:' then 'Reality:'"
    ),
}

_GENERATION_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant for a transgender community Discord server. "
    "Respond with ONLY the requested content — no preamble, no explanation, "
    "no formatting beyond what is asked."
)


def load_library(path: Path = LIBRARY_PATH) -> list[dict]:
    """Load the curated library JSON. Returns [] and logs a warning if file is missing."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning("Affirmations library not found at %s — AI fallback will be used.", path)
        return []
    except Exception as exc:
        log.warning("Failed to load affirmations library: %s", exc)
        return []


def pick_from_library(library: list[dict], category: str | None = None) -> dict | None:
    """
    Pick a random entry. If category is given, filter to that category first.
    Returns None if no matching entries exist (triggers AI fallback in get_affirmation).
    """
    pool = [item for item in library if item.get("category") == category] if category else library
    return random.choice(pool) if pool else None


async def generate_affirmation(category: str | None) -> str:
    """
    Generate content via Open WebUI. Direct aiohttp POST — does NOT use handle_query()
    and does NOT touch conversation_history.
    """
    # Fall back to generic affirmation prompt if the category isn't in our list
    effective_category = category if category in CATEGORY_PROMPTS else "affirmation"
    user_prompt = CATEGORY_PROMPTS[effective_category]

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": _GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OPENWEBUI_API_URL}/api/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.error("Affirmation generation failed %s: %s", resp.status, body)
                    return "Something went wrong generating an affirmation. Please try again."
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.exception("Unexpected error generating affirmation: %s", exc)
        return "Something went wrong generating an affirmation. Please try again."


async def get_affirmation(category: str | None = None) -> tuple[str, str, bool]:
    """
    Main entry point for the affirmations system.
    Returns (content, source_or_empty_string, was_ai_generated).
    Tries the curated library first; falls back to AI generation on a miss.
    """
    library = load_library()
    entry = pick_from_library(library, category)

    if entry:
        return entry["content"], entry.get("source") or "", False

    # Library miss — generate via AI
    content = await generate_affirmation(category)
    return content, "", True
