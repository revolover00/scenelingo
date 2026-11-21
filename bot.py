"""Telegram bot: handles /start, /stop, /help, /today.

Run with:  python bot.py
(Uses long polling — no server needed. For 24/7 free hosting,
use a free-tier host or run it alongside the daily job.)
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import db
from async_file import open_binary_async
from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

WELCOME = (
    "أهلاً بيك في بوت كلمات الأفلام 🎬\n\n"
    "كل يوم هبعتلك كلمة جديدة + لقطة من فيلم اتقالت فيها.\n"
    "هتتعلم إنجليزي وانت بتتفرج 😎\n\n"
    "/today — كلمة النهاردة دلوقتي\n"
    "/stop — إلغاء الاشتراك"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    db.add_subscriber(user.id, user.username, user.first_name)
    await update.message.reply_text(WELCOME)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    db.remove_subscriber(user.id)
    await update.message.reply_text("تم إلغاء الاشتراك. نراك قريباً 👋")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send today's word on demand (same pipeline as daily_job)."""
    from daily_job import build_today_message

    await update.message.reply_text("⏳ بجهز كلمة النهاردة...")
    try:
        clip_path, caption = await asyncio.to_thread(build_today_message)
        async with open_binary_async(clip_path) as video:
            await update.message.reply_video(video=video, caption=caption)
    except Exception as exc:
        log.exception("today command failed")
        await update.message.reply_text(f"حصلت مشكلة، حاول تاني بعد شوية. ({exc})")


def main() -> None:
    config.validate("bot_token", "database_url")
    db.init_db()
    app = Application.builder().token(config.bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("today", today))
    log.info("Bot is running (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
