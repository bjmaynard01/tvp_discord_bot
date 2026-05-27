import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import logging
import random
from collections import defaultdict, deque
from typing import Optional
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
    GOOD_BOT_PHRASES,
    BAD_BOT_PHRASES,
    GOOD_BOT_REACTIONS,
    BAD_BOT_REACTIONS,
    BOT_RETORT_CHANCE,
    GOOD_BOT_RETORT_PROMPT,
    BAD_BOT_RETORT_PROMPT,
    OLLAMA_API_URL,
    OLLAMA_RETORT_MODEL,
)
from affirmations import get_affirmation, CATEGORY_LABELS

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

async def notify_admin_webook(error_code: int, error_body: str):#, channel_id: int):
    if not DISCORD_WEBHOOK_URL:
        log.warning("No webhook URL configured, cannot send admin notification.")
        return

    payload = {
        #"content": f"⚠️ **TVP Bot Error**\nChannel: `{channel_id}`\nStatus: `{error_code}`\n```{error_body}```"
        "content": f"⚠️ **TVP Bot Error**\nStatus: `{error_code}`\n```{error_body}```"
    }
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as exc:
        log.error("Failed to send admin webhook: %s", exc)


async def query_openwebui(channel_id: int, user_message: str, web_search: bool = False) -> str:
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
    if web_search:
        payload["features"] = {"web_search": True}

    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            log.info("Querying model=%r url=%s", MODEL_ID, f"{OPENWEBUI_API_URL}/api/chat/completions")
            async with session.post(
                f"{OPENWEBUI_API_URL}/api/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=300),
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

                # Collect unique source names from knowledge base / web search citations.
                # The same document appears multiple times (once per chunk), so deduplicate.
                cited_sources = []
                for source_group in data.get("sources", []):
                    for meta in source_group.get("metadata", []):
                        name = meta.get("name") or meta.get("source")
                        if name and name not in cited_sources:
                            cited_sources.append(name)

                if cited_sources:
                    source_list = "\n".join(f"• {name}" for name in cited_sources)
                    reply += f"\n\n📚 **Sources:**\n{source_list}"

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

async def generate_retort(is_positive: bool) -> str:
    """
    Generate a short personality retort via Ollama (raw model, no presentation layer).
    Goes directly to Ollama so the workspace system prompt in Open WebUI doesn't
    override the bot's silly personality. Does NOT use handle_query() and does NOT
    touch conversation_history.
    """
    system_prompt = (
        "You are Simple Dog from Hyperbole and a Half. "
        "Respond with ONLY your reply — no preamble, no quotation marks, no explanation. "
        "Keep it to 1-2 sentences."
    )
    user_prompt = GOOD_BOT_RETORT_PROMPT if is_positive else BAD_BOT_RETORT_PROMPT

    # Ollama native /api/chat format — no auth header needed.
    # think=False disables chain-of-thought on thinking models (e.g. gemma4:e4b),
    # which otherwise put their output in a "thinking" field and leave content empty.
    # num_predict caps output tokens (Ollama's equivalent of max_tokens).
    payload = {
        "model": OLLAMA_RETORT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 120,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_API_URL}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                log.info("Ollama responded with status %s", resp.status)
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Retort generation failed — status %s, body: %s", resp.status, body[:200])
                    return ""
                data = await resp.json()
                log.info("Ollama raw response: %r", str(data)[:300])
                content = data["message"]["content"].strip()
                if not content:
                    log.warning("Ollama returned 200 but content was empty")
                return content
    except Exception as exc:
        log.warning("Retort generation error: %s", exc)
        return ""


async def handle_bot_feedback(message: discord.Message):
    """
    Check if a message is positive/negative feedback directed at the bot.
    If so, react with emoji and optionally send a short AI-generated retort.
    All errors are caught here — this must never disrupt normal message handling.
    """
    try:
        content_lower = message.content.lower()

        # Check trigger conditions: must be a reply to a bot message OR an @mention of the bot
        is_reply_to_bot = (
            message.reference is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author.id == bot.user.id
        )
        is_mention = bot.user in message.mentions

        if not (is_reply_to_bot or is_mention):
            return

        # Determine feedback type — good phrases take priority on a tie
        is_positive = any(phrase in content_lower for phrase in GOOD_BOT_PHRASES)
        is_negative = any(phrase in content_lower for phrase in BAD_BOT_PHRASES)

        if not (is_positive or is_negative):
            return

        trigger_type = "reply+mention" if (is_reply_to_bot and is_mention) else ("reply" if is_reply_to_bot else "mention")
        feedback_type = "positive" if is_positive else "negative"
        log.info("Feedback triggered (%s, %s) in channel %s", trigger_type, feedback_type, message.channel.id)

        # Apply emoji reactions
        if is_positive:
            # Pick 1 or 2 emoji from the positive pool
            emojis = random.sample(GOOD_BOT_REACTIONS, k=min(random.randint(1, 2), len(GOOD_BOT_REACTIONS)))
        else:
            emojis = [random.choice(BAD_BOT_REACTIONS)]

        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
                log.info("Reaction added: %s to message %s", emoji, message.id)
            except Exception as exc:
                log.warning("Failed to add reaction %s: %s", emoji, exc)

        # Roll for retort
        roll = random.random()
        log.info("Retort roll: %.2f (threshold: %.2f) — %s", roll, BOT_RETORT_CHANCE, "firing" if roll < BOT_RETORT_CHANCE else "skipped")
        if roll < BOT_RETORT_CHANCE:
            retort = await generate_retort(is_positive)
            if retort:
                try:
                    await message.reply(retort, mention_author=False)
                    log.info("Retort sent to message %s", message.id)
                except Exception as exc:
                    log.warning("Failed to send retort: %s", exc)

    except Exception as exc:
        log.warning("Error in handle_bot_feedback: %s", exc)


async def handle_query(channel_id: int, user_message: str, web_search: bool = False) -> str:
    lock = channel_locks[channel_id]

    if channel_busy[channel_id]:
        return "⏳ I'm still working on the previous question — give me a moment and try again."

    async with lock:
        channel_busy[channel_id] = True
        try:
            return await query_openwebui(channel_id, user_message, web_search=web_search)
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

    # Check for feedback reactions in the background — never blocks normal processing
    asyncio.create_task(handle_bot_feedback(message))

    # Only act on queries when the bot is mentioned
    if bot.user not in message.mentions:
        await bot.process_commands(message)
        return

    # Strip the mention from the message
    user_text = message.content
    for mention in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
        user_text = user_text.replace(mention, "").strip()
        # Don't treat feedback phrases as queries — handle_bot_feedback handles those
    stripped_lower = user_text.lower()
    if any(phrase in stripped_lower for phrase in GOOD_BOT_PHRASES + BAD_BOT_PHRASES):
        return

    if not user_text:
        await message.reply("Hey! Ask me anything. 😊", mention_author=False)
        return

    # Check for !web prefix (avoids Discord's slash command UI intercepting '/')
    web_search = False
    if user_text.lower().startswith("!web ") or user_text.lower() == "!web":
        web_search = True
        user_text = user_text[len("!web"):].strip()
        if not user_text:
            await message.reply("Please include a query after `!web`.", mention_author=False)
            return

    async with message.channel.typing():
        reply = await handle_query(message.channel.id, user_text, web_search=web_search)

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


@tree.command(name="tvpwebsearch", description="Ask the TVP AI assistant a question using live web search.")
@app_commands.describe(question="Your question — the bot will search the web before answering.")
async def slash_websearch(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)

    reply = await handle_query(interaction.channel_id, question, web_search=True)
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
        f"🤖 Currently using model: `{MODEL_ID}`",
        ephemeral=True,
    )


@tree.command(name="tvpaffirmation", description="Post a random affirmation, quote, or fact.")
@app_commands.describe(category="Optional category filter. Use /tvpcategories to see options.")
async def slash_affirmation(interaction: discord.Interaction, category: Optional[str] = None):
    await interaction.response.defer()

    # Normalize category input — lowercase, treat empty string as no filter
    category_key = category.lower().strip() if category else None

    # Validate the category if one was given
    if category_key and category_key not in CATEGORY_LABELS:
        await interaction.followup.send(
            f"❌ Unknown category `{category}`. Use `/tvpcategories` to see valid options.",
            ephemeral=True,
        )
        return

    content, source, was_ai_generated = await get_affirmation(category_key)

    label = CATEGORY_LABELS.get(category_key or "", "Daily Affirmation")
    lines = [f"✨ **{label}**\n", content]
    if source:
        lines.append(f"\n*— {source}*")
    lines.append("\n───────────────────────────────")
    if was_ai_generated:
        lines.append("🤖 *AI-generated*")

    await interaction.followup.send("\n".join(lines))


@tree.command(name="tvpcategories", description="List available affirmation categories.")
async def slash_categories(interaction: discord.Interaction):
    category_list = "\n".join(f"• `{key}` — {label}" for key, label in CATEGORY_LABELS.items())
    await interaction.response.send_message(
        f"**Available categories for `/tvpaffirmation`:**\n{category_list}",
        ephemeral=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
