"""
بوت تيليجرام المطور - النسخة الكاملة
======================================
يحافظ على جميع وظائف التحميل الأصلية
ويضيف لوحة إدارة كاملة بالأزرار

المتطلبات:
    pip install python-telegram-bot==20.5 yt-dlp python-dotenv imageio-ffmpeg psutil

المتغيرات البيئية:
    BOT_TOKEN  - توكن البوت من BotFather
    ADMIN_ID   - معرف الأدمن الرئيسي
"""

import asyncio
import logging
from flask import Flask
from threading import Thread
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram import BotCommand, BotCommandScopeChat

from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ── وحدات المشروع
from modules import database as db
from modules.admin_panel import (
    admin_main_keyboard,
    handle_admin_callback,
    handle_admin_text,
    broadcast_control,
)
from modules.forced_sub import (
    check_user_subscribed,
    send_subscription_prompt,
    monitor_channel_targets,
)
from modules.queue_manager import enqueue_download, start_workers
from bot_helpers import detect_platform, is_url, format_developer_link

# ── تحميل المتغيرات البيئية
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))

# ── الإعداد
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# بناء قائمة المستخدم الديناميكية
# ══════════════════════════════════════════════════════════════════

def build_user_menu(user_id: int) -> InlineKeyboardMarkup:
    """بناء قائمة المستخدم مع ميزة الإخفاء وإعادة زر الإدارة الأصلي للبوت"""
    static_buttons = []
    
    if db.get_setting("show_btn_download", "1") == "1":
        static_buttons.append([InlineKeyboardButton("📥 تحميل رابط", callback_data="download")])

    # الأزرار الديناميكية الأصلية من قاعدة بياناتك
    dynamic = db.get_visible_buttons()
    for btn in dynamic:
        if btn["action_type"] == "url":
            static_buttons.append([InlineKeyboardButton(btn["label"], url=btn["action"])])
        else:
            static_buttons.append([InlineKeyboardButton(btn["label"], callback_data=f"dyn:{btn['action']}")])

    # فحص ظهور الأزرار الثابتة
    row = []
    if db.get_setting("show_btn_vip", "1") == "1":
        row.append(InlineKeyboardButton("💎 VIP", callback_data="vip"))
        
    if db.get_setting("show_btn_shop", "1") == "1":
        row.append(InlineKeyboardButton("🏪 المتجر", callback_data="shop"))
        
    if db.get_setting("show_btn_info", "1") == "1":
        row.append(InlineKeyboardButton("ℹ️ معلومات", callback_data="info"))
        
    if row:
        static_buttons.append(row)

    #if db.get_setting("show_btn_developer", "1") == "1":
        dev_link = db.get_setting("developer_link", "")
        if dev_link:
            url = format_developer_link(dev_link)
            static_buttons.append([InlineKeyboardButton("📞 تواصل المطور", url=url)])

    # 🛑 إرجاع الزر الأصلي لبوتك لتفتح لوحتك الأساسية فوراً
    if db.is_admin(user_id):
        static_buttons.append([InlineKeyboardButton("⚙️ لوحة الإدارة", callback_data="adm:main")])

    return InlineKeyboardMarkup(static_buttons)

# ══════════════════════════════════════════════════════════════════
# أوامر البوت
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# دوال الأوامر المحدثة
# ══════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /start - يسجل المستخدم ويرسل رسالة الترحيب"""
    user = update.effective_user
    db.record_user(user)

    # فحص الحظر
    if db.is_banned(user.id):
        ban_msg = db.get_setting("ban_message", "🚫 أنت محظور من استخدام البوت.")
        await update.message.reply_text(ban_msg)
        return

    welcome = db.get_setting("welcome_message",
        "أهلاً {name}!\n\nهذا بوت تحميل متعدد المنصات.\nأرسل رابط الفيديو أو اختر من القائمة.")
    text = welcome.replace("{name}", user.mention_html())

    ads = db.get_setting("ads_text", "")
    if ads:
        text += f"\n\n{ads}"
    
    # إضافة تلميح لأمر التواصل مع المطور
    #text += "\n\n📞 للتواصل مع المطور استخدم الأمر: /developer"

    await update.message.reply_html(text, reply_markup=build_user_menu(user.id))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /help - المساعدة"""
    await update.message.reply_text(
        "أرسل رابط فيديو من YouTube, TikTok, Instagram, Twitter, Facebook...\n"
        "استخدم الأزرار للوصول السريع إلى الميزات.\n\n"
        "🔗 للتواصل مع المطور استخدم الأمر: /developer"
    )


async def cmd_developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /developer - إرسال رابط تواصل المطور"""
    # جلب الرابط من قاعدة البيانات، مع وضع رابط افتراضي إذا كان الحقل فارغاً
    dev_link = db.get_setting("developer_link", "https://t.me/your_username")
    
    await update.message.reply_text(
        f"📞 يمكنك التواصل مع المطور من خلال الرابط التالي:\n{dev_link}",
        disable_web_page_preview=True
    )


# ══════════════════════════════════════════════════════════════════
# معالج Callback الرئيسي
# ══════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    data = query.data

    # ── 1. لوحة إدارة ظهور الأزرار (تفتح عبر أمر أو من الكود)
    # ── 1. فتح لوحة إدارة الأزرار (إخفاء/إظهار)
    # ── 1. لوحة التحكم بظهور الأزرار (توضع في البداية لكي تفتح بشكل مستقل ونظيف)
    if data == "adm_manage_keys":
        if not db.is_admin(user.id): return
        await query.answer()
        
        status_vip = "🟢 ظاهر" if db.get_setting("show_btn_vip", "1") == "1" else "🔴 مخفي"
        status_shop = "🟢 ظاهر" if db.get_setting("show_btn_shop", "1") == "1" else "🔴 مخفي"
        status_info = "🟢 ظاهر" if db.get_setting("show_btn_info", "1") == "1" else "🔴 مخفي"
        
        visibility_keyboard = [
            [InlineKeyboardButton(f"زر الـ VIP ({status_vip})", callback_data="toggle_key:vip")],
            [InlineKeyboardButton(f"زر المتجر ({status_shop})", callback_data="toggle_key:shop")],
            [InlineKeyboardButton(f"زر معلومات ({status_info})", callback_data="toggle_key:info")],
            # العودة هنا سترسل callback يبدأ بـ adm:main ليعيدك للوحة الأصلية
            [InlineKeyboardButton("🔙 العودة للوحة الإدارة", callback_data="adm:main")]
        ]
        await query.edit_message_text(
            "🎛️ **لوحة التحكم بظهور أزرار واجهة المستخدم:**\n\nاضغط على أي زر لعكس حالته فوراً (إخفاء أو إظهار عن المستخدمين):",
            reply_markup=InlineKeyboardMarkup(visibility_keyboard),
            parse_mode="Markdown"
        )
        return

    # ── 2. معالجة تبديل حالة الأزرار (Toggle) عند الضغط عليها
    if data.startswith("toggle_key:"):
        if not db.is_admin(user.id): return
        btn_target = data.split(":")[-1]
        setting_name = f"show_btn_{btn_target}"
        
        current_state = db.get_setting(setting_name, "1")
        new_state = "0" if current_state == "1" else "1"
        db.set_setting(setting_name, new_state)
        await query.answer("🔄 تم تحديث حالة الزر!")
        
        status_vip = "🟢 ظاهر" if db.get_setting("show_btn_vip", "1") == "1" else "🔴 مخفي"
        status_shop = "🟢 ظاهر" if db.get_setting("show_btn_shop", "1") == "1" else "🔴 مخفي"
        status_info = "🟢 ظاهر" if db.get_setting("show_btn_info", "1") == "1" else "🔴 مخفي"
        
        visibility_keyboard = [
            [InlineKeyboardButton(f"زر الـ VIP ({status_vip})", callback_data="toggle_key:vip")],
            [InlineKeyboardButton(f"زر المتجر ({status_shop})", callback_data="toggle_key:shop")],
            [InlineKeyboardButton(f"زر معلومات ({status_info})", callback_data="toggle_key:info")],
            [InlineKeyboardButton("🔙 العودة للوحة الإدارة", callback_data="adm:main")]
        ]
        await query.edit_message_text(
            "🎛️ **لوحة التحكم بظهور أزرار واجهة المستخدم:**\n\nاضغط على أي زر لعكس حالته فوراً (إخفاء أو إظهار عن المستخدمين):",
            reply_markup=InlineKeyboardMarkup(visibility_keyboard),
            parse_mode="Markdown"
        )
        return
# ── 3. معالجة لوحة الإدارة (adm:*)
    if data.startswith("adm:"):
        if not db.is_admin(user.id): return
        
        # إذا كان إغلاق، نحذف الرسالة فقط ولا نعيد قائمة المستخدمين (تجنباً للتداخل)
        if data == "adm:close":
            await query.message.delete()
            return

        # نترك الملف الخارجي يبني اللوحة الأصلية
        await handle_admin_callback(update, context)
        
        # حقن الزر الجديد (لوحة التحكم بالأزرار) بشكل نظيف
        try:
            current_markup = query.message.reply_markup
            if current_markup and current_markup.inline_keyboard:
                keyboard = list(current_markup.inline_keyboard)
                
                # فحص لمنع التكرار
                if not any(any(b.callback_data == "adm_manage_keys" for b in row) for row in keyboard):
                    new_btn = InlineKeyboardButton("🎛️ لوحة التحكم بالأزرار", callback_data="adm_manage_keys")
                    # نضيفه كصف جديد قبل زر الإغلاق إذا وجد
                    keyboard.insert(-1, [new_btn]) 
                    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass
        return

        # الآن نجعل الملف الخارجي يرسل لوحتك الأساسية ذات التسعة أزرار
        await handle_admin_callback(update, context)
        
        # نقوم بحقن الزر الجديد "داخل" اللوحة الأساسية فقط عندما تكون data == "adm:main"
        if data == "adm:main":
            try:
                current_markup = query.message.reply_markup
                if current_markup and current_markup.inline_keyboard:
                    keyboard = list(current_markup.inline_keyboard)
                    
                    # فحص لمنع تكرار حقن الزر
                    has_btn = any(any(b.callback_data == "adm_manage_keys" for b in row) for row in keyboard)
                    if not has_btn:
                        new_btn = InlineKeyboardButton("🎛️ لوحة التحكم بالأزرار", callback_data="adm_manage_keys")
                        
                        # حقن الزر فوق زر ❌ إغلاق مباشرة (الصف قبل الأخير)
                        if len(keyboard) > 0:
                            keyboard.insert(-1, [new_btn])
                        else:
                            keyboard.append([new_btn])
                        
                        # تحديث الأزرار لتظهر مدمجة تماماً في نفس اللوحة
                        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                pass
        return

    # ── 2. معالجة تبديل حالة الأزرار (Toggle)
    if data.startswith("toggle_key:"):
        if not db.is_admin(user.id): return
        btn_target = data.split(":")[-1]
        setting_name = f"show_btn_{btn_target}"
        
        current_state = db.get_setting(setting_name, "1")
        new_state = "0" if current_state == "1" else "1"
        db.set_setting(setting_name, new_state)
        await query.answer("🔄 تم تحديث حالة الزر!")
        
        status_vip = "🟢 ظاهر" if db.get_setting("show_btn_vip", "1") == "1" else "🔴 مخفي"
        status_shop = "🟢 ظاهر" if db.get_setting("show_btn_shop", "1") == "1" else "🔴 مخفي"
        status_info = "🟢 ظاهر" if db.get_setting("show_btn_info", "1") == "1" else "🔴 مخفي"
        
        visibility_keyboard = [
            [InlineKeyboardButton(f"زر الـ VIP ({status_vip})", callback_data="toggle_key:vip")],
            [InlineKeyboardButton(f"زر المتجر ({status_shop})", callback_data="toggle_key:shop")],
            [InlineKeyboardButton(f"زر معلومات ({status_info})", callback_data="toggle_key:info")],
            [InlineKeyboardButton("🔙 العودة للوحة الإدارة", callback_data="adm:main")]
        ]
        await query.edit_message_text(
            "🎛️ **لوحة التحكم بظهور أزرار واجهة المستخدم:**\n\nاضغط على أي زر لعكس حالته فوراً (إخفاء أو إظهار عن المستخدمين):",
            reply_markup=InlineKeyboardMarkup(visibility_keyboard),
            parse_mode="Markdown"
        )
        return

    # ── 3. حقن زر التحكم بالأزرار ذكياً داخل لوحة الإدارة الأصلية وحل مشكلة الإغلاق
    if data.startswith("adm:"):
        if not db.is_admin(user.id): return
        
        # إذا ضغط على زر إغلاق الأصلي، نعيد إظهار واجهة المستخدم فوراً بدلاً من مسح الشاشة
        if data in ["adm:close", "adm:exit", "adm:back"]:
            await query.answer()
            await query.edit_message_text(
                "🎯 تم الخروج من لوحة الإدارة. أهلاً بك في واجهة المستخدم:",
                reply_markup=build_user_menu(user.id),
                parse_mode="HTML"
            )
            return

        # نترك الملف الخارجي يبني اللوحة الأصلية أولاً
        await handle_admin_callback(update, context)
        
        # نقوم بالتقاط الكيبورد الناتج ونحقن الزر الجديد فيه
        try:
            current_markup = query.message.reply_markup
            if current_markup and current_markup.inline_keyboard:
                keyboard = list(current_markup.inline_keyboard)
                
                # فحص لمنع تكرار الزر عند التحديث
                has_btn = any(any(b.callback_data == "adm_manage_keys" for b in row) for row in keyboard)
                if not has_btn:
                    # نضع الزر الجديد في الصف قبل الأخير (فوق زر إغلاق الأحمر مباشرة)
                    new_btn = InlineKeyboardButton("🎛️ لوحة التحكم بالأزرار", callback_data="adm_manage_keys")
                    if len(keyboard) > 0:
                        keyboard.insert(-1, [new_btn])  # حقن فوق زر إغلاق
                    else:
                        keyboard.append([new_btn])
                    
                    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass
        return

    # ── التحقق من الاشتراك
    if data == "check_sub":
        await query.answer()
        subbed, not_subbed = await check_user_subscribed(context.bot, user.id)
        if subbed:
            await query.edit_message_text(
                "✅ شكرًا! تم التحقق من اشتراكك. أرسل الرابط الآن.",
                reply_markup=build_user_menu(user.id)
            )
        else:
            await query.answer("❌ لم تشترك بعد في جميع القنوات!", show_alert=True)
        return

    # ── إيقاف/استئناف/إلغاء الإذاعة
    if data.startswith("adm:bc:pause:") or data.startswith("adm:bc:resume:") or data.startswith("adm:bc:cancel:"):
        log_id = int(data.split(":")[-1])
        action = data.split(":")[2]
        if action == "pause": broadcast_control.setdefault(log_id, {})["paused"] = True
        elif action == "resume": broadcast_control.setdefault(log_id, {})["paused"] = False
        elif action == "cancel": broadcast_control.setdefault(log_id, {})["cancelled"] = True
        await query.answer("✅ تم الإجراء")
        return

    await query.answer()

    async def edit(text: str, kb=None) -> None:
        try:
            await query.edit_message_text(text, reply_markup=kb or build_user_menu(user.id), parse_mode="HTML")
        except BadRequest: pass

    # ── قائمة أزرار واجهة المستخدم الثابتة
    if data == "download":
        await edit("📥 أرسل الرابط الآن وسأبدأ بالتحميل فورًا.")

    elif data == "vip":
        is_vip = db.is_vip(user.id)
        msg = db.get_setting("vip_message", "💎 أنت عضو VIP!") if is_vip else "💎 VIP يمنحك تحميل أسرع ودعم جودة أعلى.\nللحصول على VIP، تواصل مع المسؤول."
        await edit(msg)

    elif data == "shop":
        text = db.get_setting("shop_message", "🏪 <b>المتجر الرقمي:</b>\n\nلم يتم إضافة منتجات بعد.")
        await edit(text)

    elif data == "info":
        text = db.get_setting("info_message", "")
        if not text:
            platforms = db.get_platforms()
            enabled_list = [p for p, v in platforms.items() if v]
            text = f"🤖 <b>بوت تحميل متعدد المنصات</b>\n\n✅ المنصات المفعلة: {', '.join(enabled_list)}"
        await edit(text)

    elif data.startswith("dyn:"):
        cb = data[4:]
        await edit(f"🔄 تم الضغط على: {cb}\n(الزر ديناميكي من لوحة الإدارة)")
# ══════════════════════════════════════════════════════════════════
# معالج الرسائل النصية (التحميل الرئيسي)
# ══════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text.strip()

    # تسجيل المستخدم وزيادة عداد الرسائل
    db.record_user(user)
    db.increment_messages(user.id)

    # فحص الحظر
    if db.is_banned(user.id):
        ban_msg = db.get_setting("ban_message", "🚫 أنت محظور.")
        await update.message.reply_text(ban_msg)
        return

    # ✨ ميزة الأدمن: تعديل رسالة المعلومات بدون كود
    if text.startswith("تحديث_المعلومات "):
        if db.is_admin(user.id):
            new_info = text.replace("تحديث_المعلومات ", "").strip()
            if new_info:
                db.set_setting("info_message", new_info)
                await update.message.reply_text("✅ تم تحديث نص زر (ℹ️ معلومات) بنجاح في قاعدة البيانات!")
            else:
                await update.message.reply_text("❌ يرجى كتابة نص بعد الكلمة.")
            return

    # فحص نص الأدمن (حوارات متعددة الخطوات)
    if await handle_admin_text(update, context):
        return

    # فحص إذا كان الرسالة رابطًا
    if not is_url(text):
        await update.message.reply_text(
            "🚫 الرابط غير صحيح، أرسل رابط فيديو صالحًا.",
            reply_markup=build_user_menu(user.id)
        )
        return

    # فحص الاشتراك الإجباري
    subbed, not_subbed = await check_user_subscribed(context.bot, user.id)
    if not subbed:
        await send_subscription_prompt(update.message, not_subbed)
        return

    # فحص تفعيل المنصة
    platform = detect_platform(text)
    if not db.is_platform_enabled(platform):
        await update.message.reply_text(
            f"🚫 منصة ({platform}) معطلة حالياً.\nتواصل مع المسؤول لتفعيلها.",
            reply_markup=build_user_menu(user.id)
        )
        return

    # فحص الضغط الشديد (Queue)
    from modules.queue_manager import _queue
    queue_size = _queue.qsize()
    if queue_size > 50:
        await update.message.reply_text(
            "⚠️ الخادم مزدحم حالياً، انتظر قليلاً وأعد المحاولة."
        )
        return

    # رسالة الانتظار
    wait_msg = await update.message.reply_text("⏳ جاري تجهيز التحميل...")

    # ── التحميل عبر Queue
    try:
        result = await enqueue_download(user.id, text, wait_msg, context)
    except Exception as e:
        logger.error(f"خطأ في التحميل: {e}")
        result = None

    if not result:
        try:
            await wait_msg.edit_text("❌ فشل التحميل. حاول مرة أخرى أو جرب رابطًا آخر.")
        except Exception:
            pass
        return

    # ── إذا كانت النتيجة من الكاش (dict فيه file_id)
    if isinstance(result, dict) and result.get("file_id"):
        ads = db.get_setting("ads_text", "")
        caption = f"✅ تم التحميل (كاش سريع)!\n{ads}" if ads else "✅ تم التحميل (كاش سريع)!"
        try:
            await update.message.reply_video(video=result["file_id"], caption=caption)
            await wait_msg.delete()
        except Exception:
            await wait_msg.edit_text("❌ خطأ في إرسال الملف من الكاش.")
        return

    # ── إرسال الملف المحمل
    result_path: Path = result
    ads = db.get_setting("ads_text", "")
    caption = f"✅ تم التحميل!\n{ads}\nمستعد لمزيد من الروابط." if ads else "✅ تم التحميل!"

    file_id_saved = None
    try:
        with open(result_path, "rb") as vf:
            sent = await update.message.reply_video(video=vf, caption=caption)
            # حفظ file_id في الكاش
            if sent and sent.video:
                file_id_saved = sent.video.file_id
        await wait_msg.delete()
    except Exception as exc:
        logger.warning(f"فشل إرسال كفيديو: {exc}")
        try:
            with open(result_path, "rb") as f:
                sent = await update.message.reply_document(document=f, caption=caption)
                if sent and sent.document:
                    file_id_saved = sent.document.file_id
            await wait_msg.delete()
        except Exception as inner:
            logger.error(f"فشل إرسال كملف: {inner}")
            try:
                await wait_msg.edit_text("❌ تعذر إرسال الملف، ربما الحجم كبير جدًا.")
            except Exception:
                pass
    finally:
        # حفظ في الكاش
        if file_id_saved and db.get_setting("cache_enabled", "1") == "1":
            # احذف سطر الـ import من هنا لأنه موجود فوق أصلاً
            import hashlib
            ck = hashlib.md5(text.encode()).hexdigest()
            
            # التعديل المهم هنا: غير اسم المتغير من platform إلى p_type
            p_type = detect_platform(text) 
            db.set_cache(ck, file_id_saved, text, p_type)

        # حذف الملف التلقائي
        if db.get_setting("auto_delete_files", "1") == "1":
            try:
                if result_path.exists():
                    result_path.unlink(missing_ok=True)
            except Exception:
                pass

# ══════════════════════════════════════════════════════════════════
# أوامر الإدارة (للتوافق مع الأوامر القديمة)
# ══════════════════════════════════════════════════════════════════

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 للأدمن فقط.")
        return
    await update.message.reply_text(
        f"📊 المستخدمون: {db.get_user_count()}\n"
        f"📥 التحميلات: {db.get_download_count()}\n"
        f"💎 VIP: {db.get_vip_count()}\n"
        f"👮 الأدمن: {db.get_admin_count()}"
    )


async def cmd_addvip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not db.is_admin(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        db.add_vip(int(context.args[0]), update.effective_user.id)
        await update.message.reply_text(f"✅ تمت إضافة {context.args[0]} إلى VIP.")


async def cmd_removevip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not db.is_admin(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        db.remove_vip(int(context.args[0]))
        await update.message.reply_text(f"✅ تمت إزالة {context.args[0]} من VIP.")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not db.is_admin(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        db.ban_user(int(context.args[0]))
        await update.message.reply_text(f"✅ تم حظر {context.args[0]}.")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not db.is_admin(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        db.unban_user(int(context.args[0]))
        await update.message.reply_text(f"✅ تم رفع الحظر عن {context.args[0]}.")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """للتوافق مع الأمر القديم /broadcast"""
    if not db.is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("استخدم: /broadcast النص")
        return
    text = " ".join(context.args)
    user_ids = db.get_all_user_ids()
    count = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, f"📢 إعلان:\n{text}")
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"✅ تم الإرسال إلى {count} مستخدم.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("خطأ غير معالج: %s", context.error)


# ══════════════════════════════════════════════════════════════════
# نقطة الإطلاق
# ══════════════════════════════════════════════════════════════════

async def post_init(application) -> None:
    """بعد الإطلاق: تشغيل workers ومراقبة القنوات وتحديث أوامر الأدمن"""
    workers = int(db.get_setting("broadcast_workers", "3"))
    await start_workers(workers)
    
    # مراقبة أهداف القنوات في الخلفية
    asyncio.create_task(monitor_channel_targets(application.bot))
    
    # تعريف أوامر الأدمن
    admin_commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("stats", "إحصائيات البوت"),
        BotCommand("broadcast", "إذاعة رسالة"),
        BotCommand("addvip", "إضافة عضو VIP"),
        BotCommand("removevip", "إزالة عضو VIP"),
        BotCommand("ban", "حظر مستخدم"),
        BotCommand("unban", "رفع الحظر"),
    ]
    
    # تعيين الأوامر للأدمن فقط (لن تظهر للمستخدمين)
    try:
        await application.bot.set_my_commands(
            admin_commands, 
            scope=BotCommandScopeChat(chat_id=ADMIN_ID)
        )
        # تعيين الأوامر العامة للمستخدمين (القائمة المختصرة)
        general_commands = [
            BotCommand("start", "بدء البوت"),
            BotCommand("help", "المساعدة"),
            BotCommand("developer", "تواصل مع المطور"),
        ]
        await application.bot.set_my_commands(general_commands)
    except Exception as e:
        logger.error(f"خطأ في تعيين أوامر البوت: {e}")

    logger.info("✅ البوت جاهز وجميع الخدمات تعمل")
# أضف هذه الدالة قبل دالة main
def run_web():
    app = Flask(__name__)
    @app.route('/')
    def home():
        return "Bot is Online"
    # Railway يستخدم متغير البيئة PORT، وإذا لم يوجد نستخدم 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود في المتغيرات البيئية!")

    # تهيئة قاعدة البيانات
    db.init_db()

    # إضافة الأدمن الرئيسي
    if ADMIN_ID > 0:
        db.add_admin(ADMIN_ID)

    # بناء التطبيق
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── تسجيل المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("developer", cmd_developer))
    application.add_handler(CommandHandler("update", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("broadcast", cmd_broadcast))
    application.add_handler(CommandHandler("addvip", cmd_addvip))
    application.add_handler(CommandHandler("removevip", cmd_removevip))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("unban", cmd_unban))

    # معالج الأزرار (كل callbacks)
    application.add_handler(CallbackQueryHandler(handle_callback))

    # معالج الرسائل النصية (التحميل الرئيسي)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    application.add_error_handler(error_handler)

    # تشغيل خادم الويب (Flask) في الخلفية لمنع الإغلاق
    Thread(target=run_web).start()

    logger.info("🚀 البوت يعمل الآن...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()