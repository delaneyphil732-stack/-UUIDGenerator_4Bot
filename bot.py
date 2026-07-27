"""
UUID Generator Telegram Bot
============================
Replicates the functionality of the popular "@UUIDGenerator_4Bot"-style bots:
  - Slash commands to generate UUID v1 / v3 / v4 / v5
  - Bulk generation
  - Inline mode: type "@YourBotUsername" in ANY chat to get an instant UUID,
    or "@YourBotUsername 5" for 5 UUIDs, or "@YourBotUsername 3 <ns> <name>"
    for a namespaced v3/v5 UUID.

Env vars required:
  BOT_TOKEN - Telegram bot token from @BotFather
"""

import logging
import os
import uuid
from typing import List

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_BULK = 50  # safety cap so nobody spams huge lists

# ---------------------------------------------------------------------------
# Core UUID helpers
# ---------------------------------------------------------------------------

NAMESPACE_ALIASES = {
    "dns": uuid.NAMESPACE_DNS,
    "url": uuid.NAMESPACE_URL,
    "oid": uuid.NAMESPACE_OID,
    "x500": uuid.NAMESPACE_X500,
}


def resolve_namespace(token: str) -> uuid.UUID:
    """Accepts a known alias (dns/url/oid/x500) or a raw UUID string."""
    token_lower = token.lower()
    if token_lower in NAMESPACE_ALIASES:
        return NAMESPACE_ALIASES[token_lower]
    return uuid.UUID(token)


def gen_uuid1() -> str:
    return str(uuid.uuid1())


def gen_uuid4() -> str:
    return str(uuid.uuid4())


def gen_uuid3(namespace: uuid.UUID, name: str) -> str:
    return str(uuid.uuid3(namespace, name))


def gen_uuid5(namespace: uuid.UUID, name: str) -> str:
    return str(uuid.uuid5(namespace, name))


def gen_bulk_v4(count: int) -> List[str]:
    count = max(1, min(count, MAX_BULK))
    return [gen_uuid4() for _ in range(count)]


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = (await context.bot.get_me()).username
    text = (
        "👋 *UUID Generator Bot*\n\n"
        "I generate UUIDs (v1, v3, v4, v5) right here or *inline* in any chat.\n\n"
        f"Try inline mode: type `@{bot_username}` in any chat box.\n\n"
        "Use /help to see all commands."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = (await context.bot.get_me()).username
    text = (
        "*Commands*\n"
        "/uuid or /uuid4 — generate a random UUID v4\n"
        "/uuid1 — generate a time\\-based UUID v1\n"
        "/uuid3 <namespace> <name> — deterministic MD5 UUID v3\n"
        "/uuid5 <namespace> <name> — deterministic SHA\\-1 UUID v5\n"
        "/bulk <count> — generate up to 50 UUID v4s at once\n\n"
        "*Namespace* can be `dns`, `url`, `oid`, `x500`, or any raw UUID\\.\n\n"
        "*Inline mode* — type this in any chat:\n"
        f"`@{bot_username}` → one UUID v4\n"
        f"`@{bot_username} 8` → 8 UUID v4s\n"
        f"`@{bot_username} 1` → a UUID v1\n"
        f"`@{bot_username} 5 dns example.com` → a UUID v5\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def uuid4_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"`{gen_uuid4()}`", parse_mode=ParseMode.MARKDOWN)


async def uuid1_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"`{gen_uuid1()}`", parse_mode=ParseMode.MARKDOWN)


async def uuid3_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /uuid3 <namespace> <name>\nExample: /uuid3 dns example.com"
        )
        return
    try:
        ns = resolve_namespace(args[0])
        name = " ".join(args[1:])
        await update.message.reply_text(
            f"`{gen_uuid3(ns, name)}`", parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await update.message.reply_text(
            "Invalid namespace. Use dns, url, oid, x500, or a raw UUID."
        )


async def uuid5_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /uuid5 <namespace> <name>\nExample: /uuid5 dns example.com"
        )
        return
    try:
        ns = resolve_namespace(args[0])
        name = " ".join(args[1:])
        await update.message.reply_text(
            f"`{gen_uuid5(ns, name)}`", parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await update.message.reply_text(
            "Invalid namespace. Use dns, url, oid, x500, or a raw UUID."
        )


async def bulk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    count = 10
    if args:
        try:
            count = int(args[0])
        except ValueError:
            await update.message.reply_text("Usage: /bulk <count 1-50>")
            return
    ids = gen_bulk_v4(count)
    text = "`" + "`\n`".join(ids) + "`"
    if count > MAX_BULK:
        text += f"\n\n_(capped at {MAX_BULK})_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Inline mode handler
# ---------------------------------------------------------------------------

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query.strip()
    results = []

    parts = query.split()

    try:
        if not parts:
            value = gen_uuid4()
            results.append(_article("UUID v4 (random)", value))

        elif parts[0] == "1":
            value = gen_uuid1()
            results.append(_article("UUID v1 (time-based)", value))

        elif parts[0] in ("3", "5") and len(parts) >= 3:
            ns = resolve_namespace(parts[1])
            name = " ".join(parts[2:])
            value = gen_uuid3(ns, name) if parts[0] == "3" else gen_uuid5(ns, name)
            label = f"UUID v{parts[0]} (namespace={parts[1]}, name={name})"
            results.append(_article(label, value))

        elif parts[0].isdigit():
            n = max(1, min(int(parts[0]), MAX_BULK))
            ids = gen_bulk_v4(n)
            joined = "\n".join(ids)
            results.append(_article(f"{n} UUID v4s", joined, is_bulk=True))

        else:
            value = gen_uuid4()
            results.append(_article("UUID v4 (random)", value))

    except ValueError:
        value = "Invalid input — try: 3 dns example.com"
        results.append(_article("Error", value))

    await update.inline_query.answer(results, cache_time=1, is_personal=True)


def _article(title: str, value: str, is_bulk: bool = False) -> InlineQueryResultArticle:
    display = value if not is_bulk else value.replace("\n", ", ")
    return InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=title,
        description=display[:100],
        input_message_content=InputTextMessageContent(
            f"`{value}`" if not is_bulk else "`" + value.replace("\n", "`\n`") + "`",
            parse_mode=ParseMode.MARKDOWN,
        ),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("uuid", uuid4_cmd))
    application.add_handler(CommandHandler("uuid4", uuid4_cmd))
    application.add_handler(CommandHandler("uuid1", uuid1_cmd))
    application.add_handler(CommandHandler("uuid3", uuid3_cmd))
    application.add_handler(CommandHandler("uuid5", uuid5_cmd))
    application.add_handler(CommandHandler("bulk", bulk_cmd))
    application.add_handler(InlineQueryHandler(inline_query))

    logger.info("Starting bot with long polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
