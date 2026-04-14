# TVP Discord Bot

A Discord bot that connects your server to the [Open WebUI](https://gpt.maynardfolks.com) workspace model (`tvp-chatbot`), with per-channel conversation history and both `@mention` and `/slash` command support.

---

## Features

| Feature | Detail |
|---|---|
| `@BotName your question` | Mention the bot anywhere it has access |
| `@BotName !web your question` | Mention with `!web` prefix to enable live web search |
| `/tvpask <question>` | Slash command — works with Discord's autocomplete |
| `/tvpwebsearch <question>` | Slash command that always uses live web search |
| `/tvpclear` | Wipe conversation history for the current channel |
| `/tvphistory` | See how many messages are in the current history |
| `/tvpmodel` | Check which model is active |
| Typing indicator | Bot shows "typing…" while the model generates |
| Per-channel history | Each channel has its own independent conversation thread |
| Token-aware trimming | Oldest messages are dropped when history grows too large |

### Web Search

There are two ways to have the bot search the web before answering:

- **Slash command:** `/tvpwebsearch your question` — always uses web search
- **Mention prefix:** `@BotName !web your question` — add `!web` right after the mention

> **Why `!web` and not `/web`?** Discord intercepts `/` at the start of a message and treats it as a slash command, so `!web` is used as the prefix instead.

---

## Setup

### 1. Clone / copy the files

```bash
git clone <your-repo>
cd discord-bot
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
DISCORD_TOKEN=        # From Discord Developer Portal
OPENWEBUI_API_KEY=    # Generated in Open WebUI → Settings → Account → API Keys
```

Everything else has sensible defaults for development.

### 4. Create the Discord bot

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. **New Application** → give it a name
3. Go to **Bot** → **Add Bot**
4. Under **Privileged Gateway Intents**, enable:
   - ✅ **Message Content Intent** (required for @ mentions to work)
5. Copy the token → paste into `DISCORD_TOKEN` in `.env`
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`
7. Use the generated URL to invite the bot to your server

### 5. Run the bot

```bash
python bot.py
```

You should see:
```
Logged in as YourBot#1234 (ID: ...)
Slash commands synced.
```

---

## Conversation History Tuning

The bot keeps a per-channel message history that is sent as context with each request. Two knobs control this in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `MAX_HISTORY_MESSAGES` | `20` | Hard cap on stored messages (user + assistant combined) |
| `MAX_HISTORY_TOKENS_ESTIMATE` | `4000` | Rough token ceiling — oldest messages trimmed first |

**Recommendations:**

- **Dev (llama3.1:8b local):** defaults are fine. Reduce to `MAX_HISTORY_MESSAGES=10` if the model is slow.
- **Prod (llama3.3-70b via Groq):** Groq has rate limits on tokens-per-minute. If you hit `429` errors, lower `MAX_HISTORY_TOKENS_ESTIMATE` to `2000`–`3000` first, then reduce `MAX_HISTORY_MESSAGES`.
- Use `/clear` in Discord to manually reset a channel's history at any time.

---

## Switching to Groq / Production

Only one change needed in `.env`:

```
MODEL_ID=tvp-chatbot   # stays the same — this is your workspace model
```

The workspace model handles the backend swap (llama3.1:8b → llama3.3-70b-versatile) internally. The bot talks to the same Open WebUI endpoint regardless.

If you want to tighten history for Groq rate limits:
```
MAX_HISTORY_MESSAGES=10
MAX_HISTORY_TOKENS_ESTIMATE=2000
```

---

## File Structure

```
discord-bot/
├── bot.py            # Main bot logic
├── config.py         # All settings loaded from .env
├── requirements.txt
├── .env.example      # Template — copy to .env
├── .env              # Your secrets (gitignored)
└── .gitignore
```

---

## Running as a Service (optional)

To keep the bot running as a background service on Linux:

```ini
# /etc/systemd/system/tvp-discord-bot.service
[Unit]
Description=TVP Discord Bot
After=network.target

[Service]
WorkingDirectory=/path/to/discord-bot
ExecStart=/path/to/discord-bot/.venv/bin/python bot.py
Restart=always
RestartSec=10
EnvironmentFile=/path/to/discord-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tvp-discord-bot
sudo systemctl start tvp-discord-bot
```
