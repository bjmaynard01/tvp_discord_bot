# TVP Discord Bot — CLAUDE.md

A Discord bot that proxies conversations to an Open WebUI instance, maintaining per-channel conversation history.

## Project Structure

```
tvp_bot/
├── bot/
│   ├── bot.py           # Main bot logic — events, slash commands, history management
│   ├── config.py        # Environment variable loader (all settings live here)
│   └── requirements.txt # Python dependencies
├── deploy/
│   ├── .env.example     # Template for environment variables
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

## Bot Commands

- `@mention <question>` — Ask a question via mention
- `@mention !web <question>` — Ask with live web search enabled (`!web` prefix, right after the mention)
- `/tvpask <question>` — Slash command equivalent
- `/tvpwebsearch <question>` — Slash command that always enables web search
- `/tvpclear` — Clear this channel's conversation history (ephemeral)
- `/tvphistory` — Show message count in history (ephemeral)
- `/tvpmodel` — Show current model ID (ephemeral)

> Web search note: `!web` is used instead of `/web` because Discord intercepts `/` at the start of a message as a slash command.

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
- [deploy/.env.example](deploy/.env.example) — Keep in sync when adding new config variables
