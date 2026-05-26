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