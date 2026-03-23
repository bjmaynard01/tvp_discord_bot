import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import logging
from collections import defaultdict, deque
from config import (
    DISCORD_TOKEN,
    OPENWEBUI_API_URL,
    OPENWEBUI_API_KEY,
    MODEL_ID,
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_TOKENS_ESTIMATE,
    SYSTEM_PROMPT,
    MAX_TOKENS,
    DISCORD_WEBHOOK_URL,
)

# Per-channel locks to prevent concurrent requests
channel_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
# Track if a channel is currently processing
channel_busy: dict[int, bool] = defaultdict(bool)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tvp-bot")

# ── Intents ───────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # Required to read message text

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # Slash command tree

# ── Per-channel conversation history ─────────────────────────────────────────
# Key: channel_id (int) → deque of {"role": "user"|"assistant", "content": str}
conversation_history: dict[int, deque] = defaultdict(
    lambda: deque(maxlen=MAX_HISTORY_MESSAGES)
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def trim_history_by_tokens(history: deque) -> list[dict]:
    """
    Return a list of messages trimmed so that the rough token estimate
    stays under MAX_HISTORY_TOKENS_ESTIMATE.  Oldest messages are dropped first.
    Very rough: 1 token ≈ 4 chars.
    """
    messages = list(history)
    while messages:
        total_chars = sum(len(m["content"]) for m in messages)
        if total_chars // 4 <= MAX_HISTORY_TOKENS_ESTIMATE:
            break
        messages.pop(0)  # drop oldest
    return messages

async def notify_admin_webook(error_code: int, error_body: str, channel_id: int):
    if not DISCORD_WEBHOOK_URL:
        log.warning("No webhook URL configured, cannot send admin notification.")
        return

    payload = {
        "content": f"⚠️ **TVP Bot Error**\nChannel: `{channel_id}`\nStatus: `{error_code}`\n```{error_body}```"
    }
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as exc:
        log.error("Failed to send admin webhook: %s", exc)


async def query_openwebui(channel_id: int, user_message: str) -> str:
    """Send the user message to Open WebUI and return the assistant reply."""
    history = conversation_history[channel_id]

    # Append the new user turn
    history.append({"role": "user", "content": user_message})

    # Build the payload
    trimmed = trim_history_by_tokens(history)
    messages_payload = []
    if SYSTEM_PROMPT:
        messages_payload.append({"role": "system", "content": SYSTEM_PROMPT})
    messages_payload.extend(trimmed)

    payload = {
        "model": MODEL_ID,
        "messages": messages_payload,
        "max_tokens": MAX_TOKENS,
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
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 429:
                    body = await resp.text()
                    log.error("OpenWebUI rate limit hit: %s", body)
                    await notify_admin_webook(429, body)
                    return f"⚠️ API error {resp.status} (rate limit) - check bot logs."
                if resp.status != 200:
                    body = await resp.text()
                    log.error("OpenWebUI error %s: %s", resp.status, body)
                    await notify_admin_webook(resp.status, body)
                    return f"⚠️ API error {resp.status} — check bot logs."

                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]

    except asyncio.TimeoutError:
        log.error("Request to OpenWebUI timed out")
        return "⚠️ The model took too long to respond. Try again."
    except Exception as exc:
        log.exception("Unexpected error querying OpenWebUI: %s", exc)
        return "⚠️ Something went wrong. Check bot logs."

    # Store the assistant reply in history
    history.append({"role": "assistant", "content": reply})
    return reply


def chunk_message(text: str, limit: int = 1900) -> list[str]:
    """Split a long response into Discord-safe chunks (≤2000 chars)."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        # Try to split at a newline within the limit
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks

async def handle_query(channel_id: int, user_message: str) -> str:
    lock = channel_locks[channel_id]
    
    if channel_busy[channel_id]:
        return "⏳ I'm still working on the previous question — give me a moment and try again."
    
    async with lock:
        channel_busy[channel_id] = True
        try:
            return await query_openwebui(channel_id, user_message)
        finally:
            channel_busy[channel_id] = False

# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await tree.sync()
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Slash commands synced.")


@bot.event
async def on_message(message: discord.Message):
    """Respond when the bot is @mentioned."""
    # Ignore self and other bots
    if message.author.bot:
        return

    # Only act when the bot is mentioned
    if bot.user not in message.mentions:
        await bot.process_commands(message)
        return

    # Strip the mention from the message
    user_text = message.content
    for mention in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
        user_text = user_text.replace(mention, "").strip()

    if not user_text:
        await message.reply("Hey! Ask me anything. 😊", mention_author=False)
        return

    async with message.channel.typing():
        reply = await handle_query(message.channel.id, user_text)

    chunks = chunk_message(reply)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)

    await bot.process_commands(message)


# ── Slash Commands ────────────────────────────────────────────────────────────

@tree.command(name="tvpask", description="Ask the TVP AI assistant a question.")
@app_commands.describe(question="Your question or message for the assistant.")
async def slash_ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)

    reply = await handle_query(interaction.channel_id, question)
    chunks = chunk_message(reply)

    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@tree.command(name="tvpclear", description="Clear TVP bot conversation history for this channel.")
async def slash_clear(interaction: discord.Interaction):
    conversation_history[interaction.channel_id].clear()
    await interaction.response.send_message(
        "🗑️ TVP bot conversation history cleared for this channel.", ephemeral=True
    )


@tree.command(name="tvphistory", description="Show how many messages are in the TVP bot conversation history.")
async def slash_history(interaction: discord.Interaction):
    count = len(conversation_history[interaction.channel_id])
    await interaction.response.send_message(
        f"📝 This channel has **{count}** message(s) in the TVP bot conversation history "
        f"(max: {MAX_HISTORY_MESSAGES}).",
        ephemeral=True,
    )


@tree.command(name="tvpmodel", description="Show which model the TVP bot is currently using.")
async def slash_model(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🤖 Currently using model: `{MODEL_ID}` via `{OPENWEBUI_API_URL}`",
        ephemeral=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
