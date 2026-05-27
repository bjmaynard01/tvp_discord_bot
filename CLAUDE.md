# TVP Discord Bot — CLAUDE.md

A Discord bot that proxies conversations to an Open WebUI instance, maintaining per-channel conversation history. Also includes a curated affirmations/quotes/facts system with AI generation fallback.

## Project Structure

```
tvp_bot/
├── bot/
│   ├── bot.py              # Main bot logic — events, slash commands, history management
│   ├── config.py           # Environment variable loader (all settings live here)
│   ├── affirmations.py     # Affirmations module — library loader, picker, AI generation
│   ├── affirmations.json   # Curated affirmation/quote/fact library
│   └── requirements.txt    # Python dependencies
├── deploy/
│   ├── .env.example        # Template for environment variables
│   └── docker-compose.yml
├── Dockerfile
└── .github/workflows/deploy.yml  # CI/CD — builds and pushes Docker image on push to main
```

## Running the Bot

```bash
# Install dependencies
pip install -r bot/requirements.txt

# Run (requires bot/.env to be configured)
python bot/bot.py
```

## Environment Variables

All config is in `bot/.env` (gitignored). Copy `deploy/.env.example` to get started.
No new variables are required for the affirmations feature — it reuses existing Open WebUI config.

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | — | Bot auth token (required) |
| `DISCORD_WEBHOOK_URL` | — | Admin error notification webhook (optional) |
| `OPENWEBUI_API_URL` | `https://gpt.maynardfolks.com` | Open WebUI endpoint |
| `OPENWEBUI_API_KEY` | — | API key for Open WebUI |
| `MODEL_ID` | `tvp-chatbot` | Workspace model ID in Open WebUI |
| `MAX_HISTORY_MESSAGES` | `20` | Max messages stored per channel |
| `MAX_HISTORY_TOKENS_ESTIMATE` | `4000` | Rough token ceiling for history trimming |
| `MAX_TOKENS` | `750` | Max tokens in model response |
| `SYSTEM_PROMPT` | `""` | Optional override system prompt |

## Architecture

- **Per-channel history:** `defaultdict(deque)` keyed by channel ID; oldest messages dropped when limits are hit
- **Concurrency control:** Per-channel `asyncio.Lock` + `channel_busy` flag prevents concurrent queries on the same channel
- **Token trimming:** Rough estimate of 1 token ≈ 4 chars; oldest messages dropped until under `MAX_HISTORY_TOKENS_ESTIMATE`
- **Response chunking:** Discord messages capped at 1900 chars; longer responses split at newlines
- **API:** Calls Open WebUI's `/api/chat/completions` endpoint (OpenAI-compatible)
- **Error handling:** 429 rate limits and timeouts handled gracefully; admin webhook notified on errors
- **Affirmations:** Standalone module (`affirmations.py`) — AI generation calls bypass `handle_query()` entirely and never touch `conversation_history`

## Bot Commands

- `@mention <question>` — Ask a question via mention
- `@mention !web <question>` — Ask with live web search enabled (`!web` prefix, right after the mention)
- `/tvpask <question>` — Slash command equivalent
- `/tvpwebsearch <question>` — Slash command that always enables web search
- `/tvpclear` — Clear this channel's conversation history (ephemeral)
- `/tvphistory` — Show message count in history (ephemeral)
- `/tvpmodel` — Show current model ID (ephemeral)
- `/tvpaffirmation [category]` — Post a random affirmation, quote, or fact; optional category filter
- `/tvpcategories` — List available affirmation categories (ephemeral)

> Web search note: `!web` is used instead of `/web` because Discord intercepts `/` at the start of a message as a slash command.

## Affirmations System

### Overview

Delivers affirmations, quotes, and facts to Discord. Manual/on-demand for now — no scheduled automation yet. Future phase: email approval pipeline (human reviews candidate before it posts).

### Categories

| Category | Label | Description |
|---|---|---|
| `affirmation` | Daily Affirmation | Warm, validating messages ("you are valid, you belong here" tone) |
| `science_fact` | Science Fact | Neuroscience, genetics, biology related to gender/trans health |
| `history` | Trans History | Trans history, pioneers, milestones |
| `quote` | Quote | Attributed quotes from trans figures or allies |
| `community_stat` | By the Numbers | Data points from USTS, SOC8, survey sources |
| `reframe` | Myth vs. Reality | Short myth/reality debunk format |

Category input is case-insensitive. Invalid category returns an ephemeral error pointing to `/tvpcategories`.

### Library Format (`affirmations.json`)

Flat JSON array of objects:
```json
[
  {
    "category": "science_fact",
    "content": "The text of the affirmation, quote, or fact.",
    "source": "Optional attribution string or null"
  }
]
```

### `affirmations.py` Module

| Function | Description |
|---|---|
| `load_library(path)` | Loads `affirmations.json`; returns `[]` and logs warning on missing file |
| `pick_from_library(library, category)` | Random pick; filters by category if provided; returns `None` on miss (triggers AI fallback) |
| `generate_affirmation(category)` | Direct `aiohttp` POST to Open WebUI — bypasses `handle_query()`, does NOT touch conversation history |
| `get_affirmation(category)` | Main entry point; returns `(content, source_or_empty, was_ai_generated)` |

### AI Generation Prompts

System prompt for all generation calls:
> `"You are a knowledgeable assistant for a transgender community Discord server. Respond with ONLY the requested content — no preamble, no explanation, no formatting beyond what is asked."`

Per-category user prompts:

| Category | Prompt |
|---|---|
| `affirmation` | `"Write one warm, affirming message for a transgender person. 2-4 sentences. No clichés."` |
| `science_fact` | `"Share one interesting scientific fact about gender identity, trans neuroscience, genetics, or trans healthcare. 2-3 sentences. Include what field of science it comes from."` |
| `history` | `"Share one brief historical fact or milestone related to transgender history or a trans pioneer. 2-3 sentences."` |
| `quote` | `"Provide one real, attributed quote from a transgender person, trans activist, or trans ally about gender identity, transition, or transgender rights. Format: quote text, then attribution on a new line starting with —"` |
| `community_stat` | `"Share one meaningful statistic from transgender health research or community surveys (such as the US Transgender Survey or WPATH data). 1-2 sentences. Include the source name and approximate year."` |
| `reframe` | `"Briefly address one common myth or misconception about transgender people or trans healthcare and provide the accurate information. Format: start with 'Myth:' then 'Reality:'"` |

### Output Format

```
✨ **[Category Label]**

[content]

*— [source]*        ← only if source exists
───────────────────────────────
🤖 *AI-generated*   ← only if was_ai_generated is True
```

### Changes to `bot.py`

- Add `from affirmations import get_affirmation` import
- Add `/tvpaffirmation` slash command (public, not ephemeral)
- Add `/tvpcategories` slash command (ephemeral)
- Do NOT modify any existing commands or their behavior

### Testing Checklist

1. `/tvpcategories` — lists all 6 categories
2. `/tvpaffirmation` — random, no category
3. `/tvpaffirmation category:science_fact` — specific category hit
4. `/tvpaffirmation category:invalid` — ephemeral error response
5. Existing commands (`/tvpask`, `/tvpclear`, etc.) unchanged
6. Affirmation AI calls do NOT increment `/tvphistory` count

## Bot Feedback Reactions

### Overview

When a user compliments or criticizes the bot (via direct reply or @mention), the bot
reacts with emoji and optionally sends a short AI-generated retort. Positive and
negative feedback are handled differently. All behavior is configurable via env vars.

### Trigger Conditions

A feedback event fires ONLY when BOTH of these are true:
- The message is a **direct reply to a bot message** OR contains an **@mention of the bot**
- The message content contains a phrase from `GOOD_BOT_PHRASES` or `BAD_BOT_PHRASES`

"good bot" said randomly in a channel with no reply/mention context does nothing.
Trigger phrase matching is case-insensitive and checks if the phrase appears anywhere
in the message content (not exact match).

Good phrases are checked first. If a message matches both (unlikely but possible),
good wins.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GOOD_BOT_PHRASES` | `"good bot,good girl,thanks bot,thank you bot,great answer,well done bot"` | Comma-separated trigger phrases for positive feedback |
| `BAD_BOT_PHRASES` | `"bad bot,bad girl,wrong bot,that's wrong,incorrect bot"` | Comma-separated trigger phrases for negative feedback |
| `GOOD_BOT_REACTIONS` | `"🐾,🐕,❤️,🥰,✨,💖"` | Comma-separated emoji pool for positive reactions |
| `BAD_BOT_REACTIONS` | `"😔,🙁,💙"` | Comma-separated emoji pool for negative reactions |
| `BOT_RETORT_CHANCE` | `0.35` | Float 0.0–1.0; probability that a retort message fires after reaction |

### Reaction Behavior

- **Positive:** randomly pick 1 or 2 emoji from `GOOD_BOT_REACTIONS`, add each as a
  reaction to the triggering message via `message.add_reaction()`
- **Negative:** randomly pick exactly 1 emoji from `BAD_BOT_REACTIONS`, add as reaction

### Retort Behavior

After reactions are applied, roll `random.random()` against `BOT_RETORT_CHANCE`.
If the roll passes, generate and send a retort:

- Retort is generated via a **direct aiohttp POST to Open WebUI** — same pattern as
  affirmations AI generation. MUST NOT use `handle_query()`. MUST NOT touch
  `conversation_history`. This is a fire-and-forget personality response, not a
  conversation turn.
- Send the retort as a reply to the triggering message (not a standalone channel message)
- Retort should be short — 1-2 sentences max. Enforce via prompt and `max_tokens=120`

### Retort Prompts

**System prompt (both):**
```
You are a warm, knowledgeable assistant for a transgender community Discord server.
You have a gentle, earnest personality. Respond with ONLY the retort — no preamble,
no quotation marks, no explanation.
```

**Positive user prompt:**
```
A Discord user just replied to one of your messages with a compliment. React with
a brief, warm, playful response — 1-2 sentences. Feel free to be a little
enthusiastic or use a light touch of humor. Stay in character as a helpful research
assistant who genuinely enjoys being appreciated.
```

**Negative user prompt:**
```
A Discord user just replied to one of your messages indicating it wasn't helpful or
was incorrect. Respond with a brief, gracious acknowledgment — 1-2 sentences.
Be genuinely apologetic without being self-flagellating. Do not dwell on the mistake.
Offer to try again if helpful.
```

### Changes to `config.py`

Add these variables with the defaults shown above:

```python
GOOD_BOT_PHRASES = [p.strip() for p in os.getenv("GOOD_BOT_PHRASES", "good bot,good girl,thanks bot,thank you bot,great answer,well done bot").split(",")]
BAD_BOT_PHRASES  = [p.strip() for p in os.getenv("BAD_BOT_PHRASES",  "bad bot,bad girl,wrong bot,that's wrong,incorrect bot").split(",")]
GOOD_BOT_REACTIONS = [e.strip() for e in os.getenv("GOOD_BOT_REACTIONS", "🐾,🐕,❤️,🥰,✨,💖").split(",")]
BAD_BOT_REACTIONS  = [e.strip() for e in os.getenv("BAD_BOT_REACTIONS",  "😔,🙁,💙").split(",")]
BOT_RETORT_CHANCE  = float(os.getenv("BOT_RETORT_CHANCE", "0.35"))
```

### Changes to `bot.py`

Add imports:
```python
import random
from config import (
    ...existing imports...,
    GOOD_BOT_PHRASES,
    BAD_BOT_PHRASES,
    GOOD_BOT_REACTIONS,
    BAD_BOT_REACTIONS,
    BOT_RETORT_CHANCE,
)
```

Add a new async helper function `handle_bot_feedback(message)`:
- Determines if message is a valid trigger (reply to bot OR @mention of bot)
- Checks content against good/bad phrase lists (case-insensitive, good wins on tie)
- Applies reactions
- Rolls for retort, generates and sends if it fires
- Errors in this function should be caught and logged — NEVER bubble up to disrupt
  normal message handling

Call `handle_bot_feedback(message)` at the top of `on_message`, before any other
processing, but after the bot self-message guard. It should run regardless of whether
the message would otherwise trigger a normal query.

### Important Constraints

- `handle_bot_feedback` MUST be non-blocking — use `asyncio.create_task()` if needed
  to avoid delaying normal message processing
- Reaction failures (e.g. missing permissions) must be caught silently — log warning,
  do not raise
- Retort generation MUST bypass `handle_query()` and `conversation_history`
- Do NOT add retort content to channel history
- Do NOT trigger feedback handling on messages from other bots
- `deploy/.env.example` must be updated with all 5 new variables and their defaults

### Testing Checklist

1. Reply to a bot message with "good bot" → 1 or 2 positive emoji reactions appear
2. Reply to a bot message with "BAD BOT" (caps) → exactly 1 negative emoji reaction
3. @mention bot with "thanks bot" → reactions fire
4. "good bot" with no reply/mention context → nothing happens
5. Run ~10 good bot triggers → retort fires roughly 3-4 times (validates ~35% rate)
6. Retort appears as a reply to the triggering message, not standalone
7. `/tvphistory` count does NOT increase after a retort fires
8. Normal bot queries still work after feedback handling runs
9. Bot does not react to other bots saying "good bot"

## Deployment

CI/CD via GitHub Actions builds a Docker image on push to `main` and pushes to GitHub Container Registry. Production runs via `docker-compose` with Watchtower for automatic updates.

```bash
# Manual Docker run
docker build -t tvp-bot .
docker run -v /path/to/.env:/app/.env tvp-bot

# Or with compose
cd deploy && docker-compose up -d
```

## Key Files to Know

- [bot/bot.py](bot/bot.py) — All bot logic; start here for any changes
- [bot/config.py](bot/config.py) — Add new env vars here; everything else imports from this module
- [bot/affirmations.py](bot/affirmations.py) — Affirmations module; standalone, no circular imports
- [bot/affirmations.json](bot/affirmations.json) — Curated library; safe to edit directly
- [deploy/.env.example](deploy/.env.example) — Keep in sync when adding new config variables