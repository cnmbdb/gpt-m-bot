import re
import json
import asyncio
import subprocess
import threading
import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

import config
import services.billing as billing_svc
import services.language as lang_svc
import services.image as image_svc

billing = billing_svc.BillingService()
lang_service = lang_svc.LanguageService()
image_service = image_svc.ImageService()

# In-memory state for multi-step flows
user_states: dict[int, dict] = {}
# Active polling jobs: {(user_id, chat_id): {"order_id": str, "message_id": int, "stop_event": threading.Event}}
active_polls: dict[tuple, dict] = {}
# Album collection: {album_key: {"photos": [], "caption": "", "count": int, "timer": asyncio.Task}}
# album_key = f"{user_id}:{media_group_id}" to isolate users
pending_albums: dict[str, dict] = {}
ALBUM_COLLECT_DELAY = 0.5  # seconds to wait for album photos

_chat_locks: dict[int, asyncio.Lock] = {}

def get_chat_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _chat_locks:
        _chat_locks[chat_id] = asyncio.Lock()
    return _chat_locks[chat_id]


def mark_processing(chat_id: int) -> bool:
    """Atomically mark chat_id as 'processing'. Returns True if acquired, False if already processing."""
    current = user_states.get(chat_id, {})
    if current.get("step") == "processing":
        return False
    user_states[chat_id] = {**current, "step": "processing"}
    return True


def mark_idle(chat_id: int) -> None:
    """Reset chat state to 'idle' (preserves other fields)."""
    user_states[chat_id] = {**user_states.get(chat_id, {}), "step": "idle"}

POLL_INTERVAL = 5
ORDER_TIMEOUT = 15 * 60


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def cmd_zs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员积分操作命令（隐藏）- 支持回复消息或直接指定用户"""
    user_id = update.effective_user.id

    if not is_admin(user_id):
        return

    chat_id = update.effective_chat.id
    args = context.args or []

    target_id = None
    amount = 0

    if update.message.reply_to_message:
        replied_user_id = str(update.message.reply_to_message.from_user.id)
        if args:
            amount_str = args[0]
            if amount_str.startswith("+"):
                amount = int(amount_str[1:])
            elif amount_str.startswith("-"):
                amount = -int(amount_str[1:])
            else:
                try:
                    amount = int(amount_str)
                except ValueError:
                    await send_message(chat_id, "❌ 格式错误，使用 `/zs +100` 或 `/zs -50`")
                    return
            target_id = replied_user_id
        else:
            await send_message(chat_id, "📋 回复用户消息后，使用 `/zs +100` 或 `/zs -50` 操作积分\n\n例：回复某用户消息后发送 `/zs +50` → 给该用户加50积分")
            return
    else:
        if not args or len(args) < 2:
            await send_message(chat_id, "📋 /zs 格式说明：\n\n"
                "**方式一**：回复用户消息后使用\n"
                "`/zs +100` — 给被回复用户加100积分\n"
                "`/zs -50` — 扣除被回复用户50积分\n\n"
                "**方式二**：直接指定用户\n"
                "`/zs <user_id> +100` — 给用户加100积分\n"
                "`/zs <user_id> -50` — 扣除用户50积分\n\n"
                "支持一次操作多个：\n"
                "`/zs <user_id1> +100 <user_id2> -50`")
            return

        target_id = str(args[0])
        amount_str = args[1]
        if amount_str.startswith("+"):
            amount = int(amount_str[1:])
        elif amount_str.startswith("-"):
            amount = -int(amount_str[1:])
        else:
            try:
                amount = int(amount_str)
            except ValueError:
                await send_message(chat_id, "❌ 格式错误，请使用 `/zs 用户ID +100` 或 `/zs 用户ID -50`")
                return

    if not target_id:
        await send_message(chat_id, "❌ 未指定用户，请回复用户消息后使用 `/zs +100`")
        return

    try:
        billing.add_balance(target_id, amount)
        balance_data = billing.get_balance(target_id)
        current = balance_data.get("balance", 0)
        sign = "+" if amount > 0 else ""
        action = "增加" if amount > 0 else "扣除"
        await send_message(chat_id, f"✅ 已{action} **{sign}{amount}** 积分给用户 **{target_id}**\n当前余额: **{current}** 积分")
    except Exception as e:
        await send_message(chat_id, f"❌ 操作失败: {e}")


async def send_message(chat_id: int, text: str, reply_markup=None, parse_mode="Markdown"):
    from telegram import Bot
    bot = Bot(token=config.BOT_TOKEN)
    await bot.send_message(
        chat_id=chat_id, text=text,
        reply_markup=reply_markup, parse_mode=parse_mode,
    )


async def edit_message(chat_id: int, message_id: int, text: str, reply_markup=None, parse_mode="Markdown"):
    from telegram import Bot
    bot = Bot(token=config.BOT_TOKEN)
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, reply_markup=reply_markup, parse_mode=parse_mode,
        )
    except Exception:
        pass


def lang_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇨🇳 简体中文", callback_data="lang_zh"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
    ]])


def recharge_keyboard(order_id: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 已转账，确认到账", callback_data=f"confirm_{order_id}"),
    ]])


def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🎨 AI 生图"), KeyboardButton("💰 充值余额")],
        [KeyboardButton("👤 个人中心"), KeyboardButton("💰 分享赚钱")],
        [KeyboardButton("❓ 帮助")],
    ], resize_keyboard=True)


def model_select_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 AI (50积分/张)", callback_data="gen_gpt-m2")],
    ])


def action_select_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 生成图片", callback_data="do_action_gen")],
        [InlineKeyboardButton("✏️ 修改图片", callback_data="do_action_edit")],
    ])


def continue_edit_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ 继续修改图片", callback_data="continue_edit")],
    ])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    if is_admin(update.effective_user.id):
        await send_message(chat_id, config.WELCOME_ZH, main_menu_keyboard())
        return

    # 处理推荐链接: /start pdd_{referrer_id}
    referrer_id = None
    if context.args and context.args[0].startswith("pdd_"):
        referrer_id = context.args[0][4:]

    # 绑定推荐关系
    if referrer_id and referrer_id != user_id:
        try:
            billing.bind_referrer(user_id, referrer_id)
            pref_lang = lang_service.get(user_id) or "zh"
            bind_msg = {
                "zh": "🎉 推荐绑定成功！被推荐人充值后你可获得返现奖励。",
                "en": "🎉 Referral link applied! You'll get cashback when your referee recharges.",
                "ru": "🎉 Реферальная ссылка применена! Вы получите кэшбэк при пополнении реферала.",
            }.get(pref_lang, "🎉 Referral link applied!")
            await send_message(chat_id, bind_msg)
        except Exception:
            pass

    # 先判断是否需要选语言
    if lang_service.is_new_or_inactive(user_id):
        await send_message(chat_id, config.LANG_SELECT_MSG, lang_keyboard())
    else:
        pref = lang_service.get(user_id) or "zh"
        await send_message(chat_id, config.WELCOMES.get(pref, config.WELCOME_ZH), main_menu_keyboard())

    # 最后再更新活跃时间
    lang_service.touch(user_id)


async def handle_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    callback_data = None
    if update.callback_query:
        callback_data = update.callback_query.data
        await update.callback_query.answer()
    elif update.message:
        callback_data = update.message.text.strip()

    if callback_data not in ("lang_zh", "lang_en", "lang_ru"):
        return

    lang = callback_data.split("_")[1]
    lang_service.set(user_id, lang)
    await send_message(chat_id, config.WELCOMES.get(lang, config.WELCOME_ZH), main_menu_keyboard())


async def cmd_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    try:
        bal_data = billing.get_balance(user_id)
        balance = bal_data.get("balance", 0)
    except Exception:
        balance = 0

    try:
        billing.claim_bonus(user_id)
        bonus_msg = "✨ 新用户福利已发放（+100积分），可以先试试生图！"
    except Exception:
        bonus_msg = ""

    text = (
        f"💰 **当前余额:** {balance}\n\n"
        f"{bonus_msg}\n"
        f"生图费用:50 积分/张 (1 USDT = 100 积分)\n\n"
        f"充值地址 (TRON TRC20):\n"
        f"`{config.TRC20_ADDRESS}`\n\n"
        f"请输入充值金额（USDT）:"
    )

    user_states[chat_id] = {
        "step": "awaiting_recharge_amount",
        "user_id": user_id,
    }

    await send_message(chat_id, text, main_menu_keyboard(), parse_mode="Markdown")


async def handle_recharge_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    state = user_states.get(chat_id)
    if not state or state.get("step") != "awaiting_recharge_amount":
        return False

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await send_message(chat_id, "请输入有效金额（如 10）", main_menu_keyboard())
        return True

    uid = state["user_id"]
    del user_states[chat_id]

    try:
        order = billing.recharge(uid, amount, "USDT")
        expiry = order.get("expiresAt", "N/A")
        msg = (
            f"✅ **订单已创建!**\n\n"
            f"订单号: `{order['orderId']}`\n"
            f"金额: **{order['amount']} USDT**\n"
            f"到账积分: **{order['credits']} 积分**\n\n"
            f"充值地址 (TRC20):\n`{order['address']}`\n\n"
            f"⏰ 请在 **{expiry}** 前转账到上方地址，\n"
            f"系统将自动检测到账并发放积分。\n\n"
            f"⚠️ 请务必向上方地址转入 **精确金额 {order['amount']} USDT**，\n"
            f"否则无法自动到账。"
        )
        sent = await send_message(chat_id, msg, main_menu_keyboard(), "Markdown")
    except Exception as e:
        await send_message(chat_id, f"创建订单失败: {e}")

    return True


# Album collection: {media_group_id: {"photos": [], "caption": "", "user_id": int, "message_id": int, "processed": bool}}
pending_albums: dict[str, dict] = {}


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle single photos and album photo grouping."""
    global pending_albums

    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    message = update.message
    photos = message.photo or []
    caption = message.caption or ""
    media_group_id = message.media_group_id

    if not photos:
        return

    # If this is part of an album (has media_group_id)
    if media_group_id:
        album_key = f"{user_id}:{media_group_id}"
        album = pending_albums.get(album_key)

        if album is None:
            # First photo in album - start collecting
            pending_albums[album_key] = {
                "photos": list(photos),
                "caption": caption,
                "user_id": update.effective_user.id,
                "message_id": message.message_id,
                "chat_id": chat_id,
                "context": context,
                "processed": False,
            }
            # Schedule processing after a short delay
            loop = asyncio.get_event_loop()
            loop.create_task(_process_album_after_delay(album_key))
            return

        if not album["processed"]:
            # Add to existing album
            album["photos"].extend(photos)
            if caption:
                album["caption"] = caption
        return

    # Single photo (no media_group_id) - process immediately
    photo_bytes_list = []
    for photo in photos:
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        photo_bytes_list.append(bytes(photo_bytes))
    await _process_single_or_album(chat_id, user_id, photo_bytes_list, caption, context)


async def _process_album_after_delay(album_key: str):
    """Wait for all album photos to arrive, then process."""
    await asyncio.sleep(1.5)  # Wait for all photos to arrive

    album = pending_albums.get(album_key)
    if not album or album["processed"]:
        return

    album["processed"] = True
    photos = album["photos"]
    caption = album["caption"]
    user_id = str(album["user_id"])
    chat_id = album["chat_id"]
    context = album["context"]

    # Download all photos
    photo_bytes_list = []
    for photo in photos:
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        photo_bytes_list.append(bytes(photo_bytes))

    # Clean up
    del pending_albums[album_key]

    await _process_single_or_album(chat_id, user_id, photo_bytes_list, caption, context)


async def _process_single_or_album(chat_id: int, user_id: str, photo_bytes_list: list, caption: str, context: ContextTypes.DEFAULT_TYPE):
    """Process photo(s) with caption as edit or generation request."""
    # Handle multiple photos as generation from reference images
    is_album = len(photo_bytes_list) > 1

    current_state = user_states.get(chat_id, {})
    if current_state.get("step") == "processing":
        return

    if chat_id not in user_states:
        if not caption.strip():
            if is_album:
                await send_message(chat_id, "发送多张图片时，请在文字中描述想要生成的图片（如：「把这张图的风格应用到那张图」）")
            else:
                await send_message(chat_id, "发送图片时，请附上修改指令。\n\n格式：图片 + 修改描述（如：`把背景换成蓝色`）")
            return

        limits = _check_limits(user_id)
        if not limits.get("allowed"):
            reason = limits.get("reason", "")
            if reason == "rate_limit":
                await send_message(chat_id, "⏳ 今日生成次数已达上限（5次），请明天再试。")
            elif reason == "daily_limit":
                await send_message(chat_id, f"⚠️ 余额不足（{limits.get('balance', 0)} 积分），请先充值后再试。")
            else:
                await send_message(chat_id, "⚠️ 当前无法使用，请联系管理员。")
            return

        if is_album:
            # Multiple photos: use as reference for generation
            await cmd_image_edit_gt(None, context, photo_bytes_list, caption.strip(), config.DEFAULT_IMAGE_MODEL, explicit_user_id=user_id, explicit_chat_id=chat_id)
        else:
            # Single photo: use as edit
            await cmd_image_edit_gt(None, context, photo_bytes_list, caption.strip(), config.DEFAULT_IMAGE_MODEL, explicit_user_id=user_id, explicit_chat_id=chat_id)
        return

    state = user_states[chat_id]
    step = state.get("step")
    instruction = caption.strip()

    if step == "awaiting_gt_edit":
        if not instruction:
            await send_message(chat_id, "请在图片说明中描述修改内容，例如：「把数字 556 改为 789」")
            return
        del user_states[chat_id]
        await cmd_image_edit_gt(None, context, photo_bytes_list, instruction, state.get("model", config.DEFAULT_IMAGE_MODEL), explicit_user_id=user_id, explicit_chat_id=chat_id)
        return

    if step == "awaiting_sc_prompt":
        if not instruction:
            await send_message(chat_id, "请在图片说明中描述想要生成的图片")
            return
        del user_states[chat_id]
        await cmd_image_gen_sc_with_ref(None, context, instruction, photo_bytes_list, state.get("model", config.DEFAULT_IMAGE_MODEL), explicit_user_id=user_id, explicit_chat_id=chat_id)
        return

    await send_message(chat_id, "当前状态不需要图片，请输入描述。")
    return


async def handle_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        return

    data = update.callback_query.data

    if data.startswith("confirm_"):
        order_id = data.replace("confirm_", "")
        user_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id

        await update.callback_query.answer("正在确认...", show_alert=True)

        try:
            order = billing.get_order(order_id)
        except Exception as e:
            await send_message(chat_id, f"查询订单失败: {e}")
            return

        if order.get("userId") != user_id:
            await send_message(chat_id, "这不是你的订单!")
            return

        if order.get("status") == "completed":
            await send_message(chat_id, f"✅ 此订单已到账！当前余额: {order.get('credits')} 积分")
            return

        if order.get("status") == "expired":
            await send_message(chat_id, f"⏰ 此订单已超时，请重新发起充值")
            return

        msg = await send_message(chat_id, f"⏰ 正在确认订单 `{order_id}`，请稍候...")
        await poll_order_until_done(chat_id, order_id, msg.message_id)
        return

    if data == "continue_edit":
        chat_id = update.effective_chat.id
        state = user_states.get(chat_id, {})
        if not state:
            await send_message(chat_id, "⚠️ 会话已过期，请重新生成图片。")
            return
        await update.callback_query.answer("请发送修改指令...")
        await send_message(
            chat_id,
            "✏️ 请输入修改指令，我会基于当前图片进行修改：\n\n"
            "格式参考：\n"
            "`把背景换成蓝色`\n"
            "`添加一些星星装饰`\n"
            "`把文字改大一点`\n\n"
            "⚠️ 继续修改将消耗 40 积分",
        )
        user_states[chat_id] = {
            "step": "awaiting_continue_edit",
            "user_id": state.get("user_id"),
            "model": state.get("model", config.DEFAULT_IMAGE_MODEL),
            "last_image_data": state.get("last_image_data"),
        }
        return

    if data.startswith("gen_") or data.startswith("action_"):
        model = None
        if data.startswith("gen_"):
            model = data[4:]
        elif data.startswith("action_"):
            state = user_states.get(update.effective_chat.id, {})
            model = state.get("model", config.DEFAULT_IMAGE_MODEL)

        user_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id
        model_info = config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])
        cost = model_info["cost"]
        name = model_info["name"]
        user_states[chat_id] = {"step": "awaiting_action", "user_id": user_id, "model": model}
        await update.callback_query.message.edit_text(
            f"✅ 已选择 {name}（{cost}积分/张）\n\n请选择操作：",
            reply_markup=action_select_keyboard(),
        )
        return

    if data.startswith("do_action_"):
        action = data[10:]
        chat_id = update.effective_chat.id
        state = user_states.get(chat_id, {})
        model = state.get("model", config.DEFAULT_IMAGE_MODEL)
        if action == "gen":
            user_states[chat_id] = {"step": "awaiting_sc_prompt", "user_id": state.get("user_id"), "model": model}
            await update.callback_query.message.edit_text(
                "🎨 请输入生成图片的描述：\n\n"
                "格式参考：\n"
                "`文案：张派派设计 飞机第一美工 @PSPS\n"
                "尺寸：1080*1920\n"
                "风格：蓝色，轻量化`",
                reply_markup=None,
            )
        elif action == "edit":
            user_states[chat_id] = {"step": "awaiting_gt_edit", "user_id": state.get("user_id"), "model": model}
            await update.callback_query.message.edit_text(
                "✏️ 请发送要修改的图片，并在消息中说明修改内容：\n\n"
                "格式参考：\n"
                "`把背景换成蓝色`\n"
                "`添加一些星星装饰`\n"
                "`把文字改大一点`",
                reply_markup=None,
            )
        return


def poll_order_sync(order_id: str, timeout: float = ORDER_TIMEOUT) -> dict:
    """Blocking poll until order is completed or expired or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            order = billing.get_order(order_id)
            if order.get("status") in ("completed", "expired"):
                return order
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return billing.get_order(order_id)


async def poll_order_until_done(chat_id: int, order_id: str, message_id: int):
    """Poll order and update the message in place."""
    last_status = None
    deadline = time.time() + ORDER_TIMEOUT

    while time.time() < deadline:
        try:
            order = billing.get_order(order_id)
            status = order.get("status", "unknown")
            if status != last_status:
                last_status = status
                if status == "completed":
                    text = (
                        f"💰 **充值成功！**\n\n"
                        f"订单号: `{order_id}`\n"
                        f"到账: **{order.get('credits', 0)} 积分**\n"
                        f"交易Hash: `{order.get('txHash', 'N/A')}`\n\n"
                        f"快去发送「用 GPT Image 1 帮我画一个图」试试吧!"
                    )
                    await edit_message(chat_id, message_id, text, parse_mode="Markdown")
                    return
                elif status == "expired":
                    text = f"⏰ 订单 `{order_id}` 已超时，请重新发起充值（/recharge）"
                    await edit_message(chat_id, message_id, text, parse_mode="Markdown")
                    return
        except Exception:
            pass
        await asyncio.sleep(POLL_INTERVAL)

    try:
        order = billing.get_order(order_id)
        if order.get("status") == "pending":
            text = (
                f"⏰ 订单 `{order_id}` 仍在等待转账...\n\n请向充值地址转入精确金额，系统将自动检测到账。\n\n金额: **{order.get('amount')} USDT**\n到账积分: **{order.get('credits')} 积分**"
            )
            await edit_message(chat_id, message_id, text, main_menu_keyboard(), "Markdown")
    except Exception:
        pass


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    try:
        bal_data = billing.get_balance(user_id)
        balance = bal_data.get("balance", 0)
    except Exception:
        balance = 0

    try:
        tx_list = billing.get_transactions(user_id)
    except Exception:
        tx_list = []

    from datetime import datetime

    TYPE_NAMES = {
        "recharge": "充值",
        "recharge_complete": "充值到账",
        "deduct": "消费",
        "refund": "退款",
        "bonus": "新用户奖励(100积分)",
    }

    text = (
        f"👤 **个人中心**\n\n"
        f"当前余额: **{balance} 积分**\n"
        f"生图费用: AI = {config.IMAGE_COST}积分/张\n"
        f"\n💰 **交易记录:**\n"
    )

    if tx_list[:10]:
        for t in tx_list[:10]:
            t_name = TYPE_NAMES.get(t.get("type"), t.get("type", ""))
            t_amt = t.get("amount", 0)
            t_reason = t.get("reason", "")
            t_time = datetime.fromtimestamp(t.get("createdAt", 0) / 1000).strftime("%m-%d %H:%M")
            sign = "+" if t.get("type") in ("recharge", "recharge_complete", "refund", "bonus") else "-"
            text += f"  {sign}{t_amt} {t_name} ({t_time})\n"
    else:
        text += "  暂无交易记录\n"

    text += f"\n充值地址 (TRC20):\n`{config.TRC20_ADDRESS}`\n\n发送 /recharge 快速充值"

    await send_message(chat_id, text, main_menu_keyboard(), "Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (
        f"🔧 **使用帮助**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎨 **AI 生图**\n"
        f"点击底部「🎨 AI 生图」按钮\n"
        f"→ 选择「🎨 生成图片」输入描述生成\n"
        f"→ 或选择「✏️ 修改图片」发送图片+描述修改\n\n"
        f"💰 **充值方式**\n"
        f"USDT TRC20 充值\n"
        f"地址: `{config.TRC20_ADDRESS}`\n"
        f"比例: 1 USDT = {config.RECHARGE_RATE} 积分\n\n"
        f"💳 **收费标准**\n"
        f"• 首次生成图片: {config.IMAGE_COST} 积分/张\n"
        f"• 首次修改图片: {config.IMAGE_COST} 积分/张\n"
        f"• 继续修改: {config.IMAGE_COST_CONTINUE_EDIT} 积分/次\n"
        f"• 新用户赠送: {config.NEW_USER_BONUS} 积分\n\n"
        f"👤 **个人中心**\n"
        f"查看余额和交易记录\n\n"
        f"💡 **快捷命令**\n"
        f"`/sc` — 生成图片\n"
        f"`/gt` — 修改图片\n"
        f"`/recharge` — 充值\n"
        f"`/me` — 余额查询\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📞 **联系管理员**\n"
        f"如有问题或建议，请联系管理员\n\n"
        f"💡 **使用技巧**\n"
        f"• 生成图片后，点击「✏️ 继续修改图片」按钮可进行多轮修改\n"
        f"• 每次修改仅需 {config.IMAGE_COST_CONTINUE_EDIT} 积分，比重新生成更划算\n"
        f"• 图片生成后可无限次继续修改\n"
    )
    await send_message(chat_id, text, main_menu_keyboard(), "Markdown")


async def cmd_pdd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    # 获取推荐信息
    try:
        info = billing.get_referral_info(user_id)
    except Exception:
        info = {"referralCount": 0, "totalEarnings": 0, "pendingCredits": 0}

    count = info.get("referralCount", 0)
    earned = info.get("totalEarnings", 0)
    pending = info.get("pendingCredits", 0)

    # 生成分享链接
    bot_username = (await context.bot.get_me()).username
    share_link = f"https://t.me/{bot_username}/start?start=pdd_{user_id}"

    text = (
        "🎉 **分享赚钱**\n\n"
        f"我的推荐码: `{user_id}`\n\n"
        f"📊 **推荐数据:**\n"
        f"  已成功推荐: **{count}** 人\n"
        f"  已到账返现: **{earned}** 积分\n"
        f"  待返现: **{pending}** 积分\n\n"
        "💡 **如何赚钱:**\n"
        "  1. 分享你的推荐链接\n"
        "  2. 被推荐人通过链接注册并充值 ≥10 USDT\n"
        "  3. 你立即获得 **300 积分** 返现\n\n"
        f"🔗 **推荐链接:**\n"
        f"`{share_link}`\n\n"
        "点击上方链接可直接分享给好友！"
    )
    await send_message(chat_id, text, main_menu_keyboard(), "Markdown")


def _check_limits(user_id: str) -> dict:
    import requests as http_requests
    try:
        resp = http_requests.get(f"{config.BILLING_URL}/limits/{user_id}", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"allowed": True}
    except Exception:
        return {"allowed": True}


async def cmd_image_gen_sc(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, model: str = None):
    if model is None:
        model = config.DEFAULT_IMAGE_MODEL
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    model_info = config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])
    cost = model_info["cost"]
    model_name = model_info["name"]

    await send_message(chat_id, f"🎨 正在用 {model_name} 生成图片，请稍候...")

    limits = _check_limits(user_id)
    if not limits.get("allowed"):
        reason = limits.get("reason", "")
        if reason == "rate_limit":
            await send_message(chat_id, "⏳ 今日生成次数已达上限（5次），请明天再试。")
        elif reason == "daily_limit":
            await send_message(chat_id, f"⚠️ 余额不足（{limits.get('balance', 0)} 积分），请先充值。")
        else:
            await send_message(chat_id, "⚠️ 当前无法生成图片，请联系管理员。")
        return

    try:
        billing.deduct(user_id, cost, "image_generation_sc")
    except Exception as e:
        await send_message(chat_id, f"⚠️ 扣费失败: {e}\n请检查余额后重试。")
        return

    try:
        img_data = image_service.generate_direct(prompt, model=model)
        from io import BytesIO
        bio = BytesIO(img_data)
        bio.name = "generated_image.png"
        bio.seek(0)

        user_states[chat_id] = {
            "step": "idle",
            "user_id": user_id,
            "model": model,
            "last_image_data": img_data,
        }

        await context.bot.send_photo(
            chat_id=chat_id, photo=bio,
            caption=f"✅ {model_name} 图片已生成！消耗 {cost} 积分\n\n💡 如需继续修改，点击下方按钮并发送修改指令（消耗 40 积分）",
            reply_markup=continue_edit_keyboard(),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            billing.refund(user_id, cost, "generation_failed")
        except Exception:
            pass
        await send_message(chat_id, f"❌ [DEBUG] 生成失败: {e}\n积分已退回，请稍后重试。")


async def cmd_image_gen_sc_with_ref(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, ref_images: list, model: str = None, explicit_user_id: str = None, explicit_chat_id: int = None):
    if model is None:
        model = config.DEFAULT_IMAGE_MODEL
    user_id = str(update.effective_user.id if update else explicit_user_id)
    chat_id = update.effective_chat.id if update else explicit_chat_id
    model_info = config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])
    cost = model_info["cost"]
    model_name = model_info["name"]

    if not mark_processing(chat_id):
        await send_message(chat_id, "⏳ 正在处理中，请稍候再试...")
        return

    await send_message(chat_id, f"🎨 正在用 {model_name} 参考图片生成，请稍候...")

    limits = _check_limits(user_id)
    if not limits.get("allowed"):
        reason = limits.get("reason", "")
        if reason == "rate_limit":
            await send_message(chat_id, "⏳ 今日生成次数已达上限（5次），请明天再试。")
        elif reason == "daily_limit":
            await send_message(chat_id, f"⚠️ 余额不足（{limits.get('balance', 0)} 积分），请先充值。")
        else:
            await send_message(chat_id, "⚠️ 当前无法生成图片，请联系管理员。")
        return

    try:
        billing.deduct(user_id, cost, "image_generation_sc_ref")
    except Exception as e:
        await send_message(chat_id, f"⚠️ 扣费失败: {e}\n请检查余额后重试。")
        return

    try:
        img_data, img_url = image_service.generate_with_image(prompt, ref_images, model=model)

        user_states[chat_id] = {
            "step": "idle",
            "user_id": user_id,
            "model": model,
            "last_image_data": img_data,
            "last_image_url": img_url,
        }

        from urllib.parse import urlparse
        gpt_api_host = urlparse(config.GPT_API_BASE_URL).netloc
        if img_url and (gpt_api_host in img_url or "localhost" in img_url):
            try:
                parsed = urlparse(img_url)
                local_path = os.path.join(config.GPT_API_IMAGES_DIR, parsed.path.lstrip("/images/").lstrip("/"))
                if os.path.exists(local_path):
                    await context.bot.send_photo(
                        chat_id=chat_id, photo=open(local_path, 'rb'),
                        caption=f"✅ {model_name} 参考图片已生成！消耗 {cost} 积分\n\n💡 如需继续修改，点击下方按钮并发送修改指令（消耗 40 积分）",
                        reply_markup=continue_edit_keyboard(),
                    )
                    return
            except Exception:
                pass

        if img_data:
            from io import BytesIO
            bio = BytesIO(img_data)
            bio.name = "generated_image.png"
            await context.bot.send_photo(
                chat_id=chat_id, photo=bio,
                caption=f"✅ {model_name} 参考图片已生成！消耗 {cost} 积分\n\n💡 如需继续修改，点击下方按钮并发送修改指令（消耗 40 积分）",
                reply_markup=continue_edit_keyboard(),
            )
        else:
            raise RuntimeError("无法获取图片数据")
        mark_idle(chat_id)
    except Exception as e:
        mark_idle(chat_id)
        err_str = str(e)
        if err_str == "Timed out":
            await send_message(chat_id, "⚠️ Telegram 上传超时，但图片可能已生成。\n请稍后查看或重试（不会重复扣费）。")
        else:
            try:
                billing.refund(user_id, cost, "generation_failed")
            except Exception:
                pass
            await send_message(chat_id, f"❌ 图片生成失败: {e}\n积分已退回，请稍后重试。")


async def cmd_image_continue_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, instruction: str, image_data: bytes, model: str = None):
    """继续编辑上次生成的图片"""
    if model is None:
        model = config.DEFAULT_IMAGE_MODEL
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    model_info = config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])
    model_name = model_info["name"]
    cost = config.IMAGE_COST_CONTINUE_EDIT

    if not mark_processing(chat_id):
        await send_message(chat_id, "⏳ 正在处理中，请稍候再试...")
        return

    await send_message(chat_id, f"✏️ 正在用 {model_name} 继续修改图片，消耗 {cost} 积分...")

    try:
        billing.deduct(user_id, cost, "image_continue_edit")
    except Exception as e:
        await send_message(chat_id, f"⚠️ 扣费失败: {e}\n请检查余额后重试。")
        return

    try:
        img_data = image_service.edit_image(image_data, instruction, model=model)
        from io import BytesIO
        bio = BytesIO(img_data)
        bio.name = "continue_edited.png"
        bio.seek(0)

        user_states[chat_id] = {
            "step": "idle",
            "user_id": user_id,
            "model": model,
            "last_image_data": img_data,
        }

        await context.bot.send_photo(
            chat_id=chat_id, photo=bio,
            caption=f"✅ {model_name} 继续修改完成！消耗 {cost} 积分\n\n💡 如需继续修改，点击下方按钮并发送修改指令（消耗 40 积分）",
            reply_markup=continue_edit_keyboard(),
        )
        mark_idle(chat_id)
    except Exception as e:
        mark_idle(chat_id)
        err_str = str(e)
        if err_str == "Timed out":
            await send_message(chat_id, "⚠️ Telegram 上传超时，但图片可能已生成。\n请稍后查看或重试（不会重复扣费）。")
        else:
            try:
                billing.refund(user_id, cost, "continue_edit_failed")
            except Exception:
                pass
            await send_message(chat_id, f"❌ 修改失败: {e}\n积分已退回，请稍后重试。")


async def cmd_image_edit_gt(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_files: list, instruction: str, model: str = None, explicit_user_id: str = None, explicit_chat_id: int = None):
    if model is None:
        model = config.DEFAULT_IMAGE_MODEL
    user_id = str(update.effective_user.id if update else explicit_user_id)
    chat_id = update.effective_chat.id if update else explicit_chat_id
    model_info = config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])
    cost = model_info["cost"]
    model_name = model_info["name"]

    if not mark_processing(chat_id):
        await send_message(chat_id, "⏳ 正在处理中，请稍候再试...")
        return

    await send_message(chat_id, f"✏️ 正在用 {model_name} 修改图片，请稍候...")

    limits = _check_limits(user_id)
    if not limits.get("allowed"):
        reason = limits.get("reason", "")
        if reason == "rate_limit":
            await send_message(chat_id, "⏳ 今日次数已达上限，请明天再试。")
        elif reason == "daily_limit":
            await send_message(chat_id, f"⚠️ 余额不足（{limits.get('balance', 0)} 积分），请先充值。")
        else:
            await send_message(chat_id, "⚠️ 当前无法改图，请联系管理员。")
        return

    try:
        billing.deduct(user_id, cost, "image_edit_gt")
    except Exception as e:
        await send_message(chat_id, f"⚠️ 扣费失败: {e}\n请检查余额后重试。")
        return

    try:
        img_data = image_service.edit_image(photo_files, instruction, model=model)
        from io import BytesIO
        bio = BytesIO(img_data)
        bio.name = "edited_image.png"
        bio.seek(0)

        user_states[chat_id] = {
            "step": "idle",
            "user_id": user_id,
            "model": model,
            "last_image_data": img_data,
        }

        await context.bot.send_photo(
            chat_id=chat_id, photo=bio,
            caption=f"✅ {model_name} 改图完成！消耗 {cost} 积分\n\n💡 如需继续修改，点击下方按钮并发送修改指令（消耗 40 积分）",
            reply_markup=continue_edit_keyboard(),
        )
        mark_idle(chat_id)
    except Exception as e:
        mark_idle(chat_id)
        err_str = str(e)
        if err_str == "Timed out":
            await send_message(chat_id, "⚠️ Telegram 上传超时，但图片可能已生成。\n请稍后查看或重试（不会重复扣费）。")
        else:
            try:
                billing.refund(user_id, cost, "edit_failed")
            except Exception:
                pass
            await send_message(chat_id, f"❌ 改图失败: {e}\n积分已退回，请稍后重试。")


async def cmd_image_gen_sc_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /sc command - default gpt-image-1"""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    user_states[chat_id] = {"step": "awaiting_sc_prompt", "user_id": user_id, "model": config.DEFAULT_IMAGE_MODEL}
    await send_message(
        chat_id,
        "✨ 请输入生成图片的描述：\n\n"
        "格式参考：\n"
        "`文案：张派派设计 飞机第一美工 @PSPS\n"
        "尺寸：1080*1920\n"
        "风格：蓝色，轻量化`",
    )


async def cmd_image_edit_gt_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /gt command - default gpt-image-1"""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    user_states[chat_id] = {"step": "awaiting_gt_edit", "user_id": user_id, "model": config.DEFAULT_IMAGE_MODEL}
    await send_message(
        chat_id,
        "✏️ 请发送要修改的图片，并在消息中说明修改内容：\n\n"
        "格式参考：\n"
        "`把图上的数字 556 改为 789`\n"
        "`把文字 hello 改成 hi`",
    )


async def cmd_image_gen(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, model: str = None):
    if model is None:
        model = config.DEFAULT_IMAGE_MODEL
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    model_info = config.IMAGE_MODELS.get(model, config.IMAGE_MODELS[config.DEFAULT_IMAGE_MODEL])
    cost = model_info["cost"]
    model_name = model_info["name"]

    status_msg = await send_message(chat_id, f"🎨 正在用 {model_name} 生成图片，请稍候...")

    limits = _check_limits(user_id)
    if not limits.get("allowed"):
        reason = limits.get("reason", "")
        if reason == "rate_limit":
            await send_message(chat_id, "⏳ 今日生成次数已达上限（5次），请明天再试。")
        elif reason == "daily_limit":
            await send_message(
                chat_id,
                f"⚠️ 余额不足（{limits.get('balance', 0)} 积分），无法生成图片。请先充值。",
            )
        else:
            await send_message(chat_id, "⚠️ 当前无法生成图片，请联系管理员。")
        return

    try:
        billing.deduct(user_id, cost, "image_generation")
    except Exception as e:
        await send_message(chat_id, f"⚠️ 扣费失败: {e}\n请检查余额后重试。")
        return

    try:
        img_data = image_service.generate_direct(prompt, model=model)
        from io import BytesIO
        bio = BytesIO(img_data)
        bio.name = "generated_image.png"
        bio.seek(0)

        user_states[chat_id] = {
            "step": "idle",
            "user_id": user_id,
            "model": model,
            "last_image_data": img_data,
        }

        await context.bot.send_photo(
            chat_id=chat_id, photo=bio,
            caption=f"✅ {model_name} 图片已生成！消耗 {cost} 积分\n\n💡 如需继续修改，点击下方按钮并发送修改指令（消耗 40 积分）",
            reply_markup=continue_edit_keyboard(),
        )
    except Exception as e:
        try:
            billing.refund(user_id, cost, "generation_failed")
        except Exception:
            pass
        await send_message(chat_id, f"❌ 图片生成失败: {e}\n积分已退回，请稍后重试。")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)

    # 更新活跃时间
    lang_service.touch(user_id)

    # 底部菜单按钮处理
    if text == "🎨 AI 生图" or "AI 生图" in text:
        await send_message(chat_id, "🎨 请选择操作：", action_select_keyboard())
        return

    if text == "💰 充值余额":
        await cmd_recharge(update, context)
        return

    if text == "👤 个人中心" or "个人中心" in text:
        await cmd_me(update, context)
        return

    if text == "💰 分享赚钱" or "分享赚钱" in text:
        await cmd_pdd(update, context)
        return

    if text == "❓ 帮助" or text in ("帮助", "/help", "help"):
        await cmd_help(update, context)
        return

    if text == "💰 分享赚钱" or "分享赚钱" in text:
        await cmd_pdd(update, context)
        return

    if text in ("lang_zh", "lang_en", "lang_ru"):
        await handle_lang_callback(update, context)
        return

    # 处理充值金额输入
    if chat_id in user_states:
        handled = await handle_recharge_amount(update, context)
        if handled:
            return

        state = user_states[chat_id]
        step = state.get("step")

        if step == "awaiting_sc_prompt":
            del user_states[chat_id]
            await cmd_image_gen_sc(update, context, text, state.get("model", config.DEFAULT_IMAGE_MODEL))
            return

        if step == "awaiting_continue_edit":
            last_image = state.get("last_image_data")
            if last_image:
                del user_states[chat_id]
                await cmd_image_continue_edit(update, context, text, last_image, state.get("model", config.DEFAULT_IMAGE_MODEL))
            else:
                await send_message(chat_id, "⚠️ 未找到上次生成的图片，请重新生成。")
                del user_states[chat_id]
            return

        if step == "awaiting_gt_edit":
            # gt 改图不靠文字，靠照片消息，见 handle_photo_message
            return

    image_pat2 = re.compile(r"用\s*Image\s*2\s*(帮我画|生成|画|绘制|创作|创造)\s*(.+)")
    image_pat1 = re.compile(r"用\s*Image\s*1\s*(帮我画|生成|画|绘制|创作|创造)\s*(.+)")
    match2 = image_pat2.match(text)
    match1 = image_pat1.match(text)
    if match2:
        prompt = match2.group(2).strip()
        if prompt:
            await cmd_image_gen(update, context, prompt, config.DEFAULT_IMAGE_MODEL)
            return
    if match1:
        prompt = match1.group(2).strip()
        if prompt:
            await cmd_image_gen(update, context, prompt, config.DEFAULT_IMAGE_MODEL)
            return

    if is_admin(update.effective_user.id):
        return

    limits = _check_limits(user_id)
    if not limits.get("allowed"):
        return

    pref = lang_service.get(user_id) or "zh"
    await send_message(chat_id, config.WELCOMES[pref])
