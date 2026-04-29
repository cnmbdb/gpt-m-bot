#!/usr/bin/env python3
import os
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

# 加载 .env 文件
_env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import config
from handlers import commands

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application):
    """Set up bot command menu and menu button."""
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start", "开始使用 / 重新打开菜单"),
        BotCommand("recharge", "充值余额"),
        BotCommand("me", "个人中心 / 查看余额"),
        BotCommand("pdd", "分享赚钱 / 推荐有礼"),
        BotCommand("sc", "生成图片"),
        BotCommand("gt", "改图"),
    ])


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_start(update, context)


async def recharge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_recharge(update, context)


async def me_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_me(update, context)


async def pdd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_pdd(update, context)


async def sc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_image_gen_sc_direct(update, context)


async def gt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_image_edit_gt_direct(update, context)


async def zs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands.cmd_zs(update, context)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data if update.callback_query else ""
    if data.startswith("confirm_"):
        await commands.handle_confirm_callback(update, context)
    elif data.startswith("gen_"):
        await commands.handle_confirm_callback(update, context)
    elif data.startswith("action_"):
        await commands.handle_confirm_callback(update, context)
    elif data.startswith("lang_"):
        await commands.handle_lang_callback(update, context)


def main():
    if not config.BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set! Please set it in .env file.")
        return

    app = Application.builder().token(config.BOT_TOKEN).build()
    app.post_init = post_init

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("recharge", recharge_cmd))
    app.add_handler(CommandHandler("me", me_cmd))
    app.add_handler(CommandHandler("pdd", pdd_cmd))
    app.add_handler(CommandHandler("sc", sc_cmd))
    app.add_handler(CommandHandler("gt", gt_cmd))
    app.add_handler(CommandHandler("zs", zs_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        filters.PHOTO,
        commands.handle_photo_message
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        commands.handle_message
    ))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
