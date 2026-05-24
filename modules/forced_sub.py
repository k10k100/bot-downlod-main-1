"""
وحدة الاشتراك الإجباري مع متابعة الأهداف
"""
import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from modules import database as db

logger = logging.getLogger(__name__)


async def check_user_subscribed(bot, user_id: int) -> tuple[bool, list[dict]]:
    """
    يتحقق هل المستخدم مشترك في جميع القنوات الإجبارية المفعلة
    يرجع (True, []) إذا مشترك، أو (False, [قنوات غير مشترك بها])
    """
    if db.get_setting("forced_sub_enabled", "1") != "1":
        return True, []

    channels = db.get_enabled_channels()
    if not channels:
        return True, []

    not_subbed = []
    for ch in channels:
        channel_username = ch["channel"]
        try:
            member = await bot.get_chat_member(f"@{channel_username}", user_id)
            if member.status in ("left", "kicked"):
                not_subbed.append(ch)
        except Exception as e:
            logger.warning(f"فشل فحص اشتراك @{channel_username}: {e}")
            not_subbed.append(ch)

    return len(not_subbed) == 0, not_subbed


async def send_subscription_prompt(message, not_subbed: list[dict]) -> None:
    """إرسال رسالة طلب الاشتراك مع أزرار القنوات"""
    sub_msg = db.get_setting("subscription_msg",
        "🔔 يجب الاشتراك في القنوات التالية أولاً:\n{channels}\nثم اضغط ✅ تحقق من الاشتراك")

    channels_text = "\n".join(f"• @{ch['channel']}" for ch in not_subbed)
    text = sub_msg.replace("{channels}", channels_text)

    buttons = []
    for ch in not_subbed:
        buttons.append([InlineKeyboardButton(
            f"📢 @{ch['channel']}",
            url=f"https://t.me/{ch['channel']}"
        )])
    buttons.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def monitor_channel_targets(bot) -> None:
    """
    مهمة خلفية تراقب عدد المشتركين في القنوات وتحقق الأهداف تلقائيًا
    تعمل كل 10 دقائق
    """
    while True:
        try:
            channels = db.get_all_channels()
            for ch in channels:
                if not ch["enabled"] or ch["completed"]:
                    continue
                if not ch["target"]:
                    continue
                try:
                    chat = await bot.get_chat(f"@{ch['channel']}")
                    count = chat.get_member_count() if hasattr(chat, 'get_member_count') else 0
                    # في بعض إصدارات python-telegram-bot
                    try:
                        count = await bot.get_chat_member_count(f"@{ch['channel']}")
                    except Exception:
                        pass

                    db.update_channel_count(ch["id"], count)
                    logger.info(f"@{ch['channel']}: {count}/{ch['target']}")

                    if ch["target"] > 0 and count >= ch["target"]:
                        db.mark_channel_completed(ch["id"])
                        logger.info(f"✅ القناة @{ch['channel']} وصلت هدفها!")
                except Exception as e:
                    logger.warning(f"خطأ مراقبة @{ch['channel']}: {e}")
        except Exception as e:
            logger.error(f"خطأ في monitor_channel_targets: {e}")

        await asyncio.sleep(600)  # كل 10 دقائق
