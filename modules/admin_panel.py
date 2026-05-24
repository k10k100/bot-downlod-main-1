"""
وحدة لوحة الإدارة - Admin Panel
لوحة إدارة كاملة بالأزرار داخل البوت
"""
import asyncio
import json
import logging
import psutil
import time
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from modules import database as db

logger = logging.getLogger(__name__)

# حالة الحوار لكل أدمن (conversation state)
admin_states: dict[int, dict] = {}


# ═══════════════════════════════════════════════════════════════
# بناء لوحات الأزرار
# ═══════════════════════════════════════════════════════════════

def admin_main_keyboard() -> InlineKeyboardMarkup:
    """اللوحة الرئيسية للأدمن"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 الإحصائيات",       callback_data="adm:stats"),
            InlineKeyboardButton("📢 القنوات الإجبارية", callback_data="adm:channels"),
        ],
        [
            InlineKeyboardButton("🎛 واجهة المستخدم",   callback_data="adm:ui"),
            InlineKeyboardButton("✉️ الرسائل",           callback_data="adm:messages"),
        ],
        [
            InlineKeyboardButton("👮 الأدمن",            callback_data="adm:admins"),
            InlineKeyboardButton("📣 الإذاعة",           callback_data="adm:broadcast"),
        ],
        [
            InlineKeyboardButton("🌐 المنصات",           callback_data="adm:platforms"),
            InlineKeyboardButton("🏪 المتجر",            callback_data="adm:shop"),
        ],
        [
            InlineKeyboardButton("⚡ الأداء والسرعة",   callback_data="adm:performance"),
            InlineKeyboardButton("🔧 إعدادات التحميل",  callback_data="adm:dl_settings"),
        ],
        # أضف هذا السطر هنا
        [InlineKeyboardButton("🎛️ لوحة التحكم بالأزرار", callback_data="adm_manage_keys")],
        
        [InlineKeyboardButton("❌ إغلاق", callback_data="adm:close")],
    ])


def back_button(target: str = "adm:main") -> list:
    return [[InlineKeyboardButton("⬅️ رجوع", callback_data=target)]]


# ═══════════════════════════════════════════════════════════════
# لوحة الإحصائيات
# ═══════════════════════════════════════════════════════════════

async def show_stats(query, context) -> None:
    users       = db.get_user_count()
    today       = db.get_today_users()
    active      = db.get_active_users()
    downloads   = db.get_download_count()
    top_plat    = db.get_top_platform()
    vip_cnt     = db.get_vip_count()
    admins_cnt  = db.get_admin_count()
    channels_cnt= db.get_channel_count()
    messages    = db.get_total_messages()

    text = (
        "📊 *إحصائيات البوت*\n\n"
        f"👥 إجمالي المستخدمين: `{users}`\n"
        f"🆕 مستخدمو اليوم: `{today}`\n"
        f"🟢 المستخدمون النشطون: `{active}`\n"
        f"📥 عدد التحميلات: `{downloads}`\n"
        f"🏆 أكثر منصة: `{top_plat}`\n"
        f"💎 أعضاء VIP: `{vip_cnt}`\n"
        f"👮 الأدمن: `{admins_cnt}`\n"
        f"📡 القنوات المضافة: `{channels_cnt}`\n"
        f"💬 الرسائل المرسلة: `{messages}`\n"
    )

    kb = InlineKeyboardMarkup(back_button())
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# لوحة القنوات الإجبارية
# ═══════════════════════════════════════════════════════════════

async def show_channels(query, context) -> None:
    channels = db.get_all_channels()
    forced_on = db.get_setting("forced_sub_enabled", "1") == "1"

    status_icon = "✅" if forced_on else "❌"
    toggle_label = "تعطيل الإجبار" if forced_on else "تفعيل الإجبار"
    toggle_cb = "adm:ch:disable_all" if forced_on else "adm:ch:enable_all"

    text = f"📢 *القنوات الإجبارية*\nالحالة العامة: {status_icon}\n\n"

    buttons = [
        [InlineKeyboardButton(f"➕ إضافة قناة",   callback_data="adm:ch:add")],
        [InlineKeyboardButton(f"{toggle_label}",    callback_data=toggle_cb)],
    ]

    for ch in channels:
        ch_name = f"@{ch['channel']}"
        target = ch['target']
        current = ch['current_count']
        done = "✅" if ch['completed'] else ("🟢" if ch['enabled'] else "🔴")

        # شريط التقدم
        if target > 0:
            pct = min(int(current / target * 10), 10)
            bar = "█" * pct + "░" * (10 - pct)
            progress = f"\n`{bar}` {current}/{target}"
        else:
            progress = ""

        text += f"{done} {ch_name}{progress}\n"

        ch_buttons = [
            InlineKeyboardButton("✏️ الهدف",  callback_data=f"adm:ch:target:{ch['id']}"),
            InlineKeyboardButton("🔄 تشغيل",  callback_data=f"adm:ch:enable:{ch['id']}"),
            InlineKeyboardButton("⏸ إيقاف",   callback_data=f"adm:ch:disable:{ch['id']}"),
            InlineKeyboardButton("🗑 حذف",    callback_data=f"adm:ch:del:{ch['id']}"),
        ]
        buttons.append(ch_buttons)

    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة إدارة واجهة المستخدم (الأزرار)
# ═══════════════════════════════════════════════════════════════

async def show_ui_manager(query, context) -> None:
    btns = db.get_all_buttons()
    text = "🎛 *إدارة واجهة المستخدم*\n\nقائمة الأزرار الحالية:\n\n"

    buttons = [
        [InlineKeyboardButton("➕ إضافة زر", callback_data="adm:ui:add")],
    ]

    for b in btns:
        vis = "👁" if b['visible'] else "🙈"
        pin = "📌" if b['pinned'] else ""
        label = f"{pin}{vis} {b['label']}"
        row = [
            InlineKeyboardButton(label, callback_data=f"adm:ui:view:{b['id']}"),
        ]
        buttons.append(row)
        ctrl = [
            InlineKeyboardButton("✏️",  callback_data=f"adm:ui:edit:{b['id']}"),
            InlineKeyboardButton("🗑",  callback_data=f"adm:ui:del:{b['id']}"),
            InlineKeyboardButton("👁",  callback_data=f"adm:ui:tog:{b['id']}"),
            InlineKeyboardButton("📌",  callback_data=f"adm:ui:pin:{b['id']}"),
            InlineKeyboardButton("⬆️",  callback_data=f"adm:ui:up:{b['id']}"),
            InlineKeyboardButton("⬇️",  callback_data=f"adm:ui:down:{b['id']}"),
        ]
        buttons.append(ctrl)

    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة الرسائل
# ═══════════════════════════════════════════════════════════════

async def show_messages(query, context) -> None:
    text = "✉️ *إدارة الرسائل*\nاختر الرسالة للتعديل:"
    buttons = [
        [InlineKeyboardButton("👋 رسالة الترحيب",        callback_data="adm:msg:welcome")],
        [InlineKeyboardButton("🔔 رسالة الاشتراك",       callback_data="adm:msg:subscription")],
        [InlineKeyboardButton("🚫 رسالة الحظر",          callback_data="adm:msg:ban")],
        [InlineKeyboardButton("💎 رسالة VIP",            callback_data="adm:msg:vip")],
        [InlineKeyboardButton("⏰ رسالة انتهاء VIP",    callback_data="adm:msg:vip_expired")],
        [InlineKeyboardButton("📢 نص الإعلانات",         callback_data="adm:msg:ads")],
        [InlineKeyboardButton("🔗 رابط المطور",          callback_data="adm:msg:dev_link")],
    ]
    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة الأدمن
# ═══════════════════════════════════════════════════════════════

async def show_admins(query, context) -> None:
    admins = db.get_all_admins()
    text = "👮 *إدارة الأدمن*\n\n"
    for adm in admins:
        role = "كامل" if adm["role"] == "full" else "محدود"
        text += f"• `{adm['user_id']}` — {role}\n"

    buttons = [
        [InlineKeyboardButton("➕ إضافة أدمن",   callback_data="adm:adm:add_full"),
         InlineKeyboardButton("➕ أدمن محدود",   callback_data="adm:adm:add_limited")],
        [InlineKeyboardButton("🗑 حذف أدمن",     callback_data="adm:adm:remove")],
    ]
    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة الإذاعة
# ═══════════════════════════════════════════════════════════════

async def show_broadcast(query, context) -> None:
    text = "📣 *نظام الإذاعة الاحترافي*\nاختر الفئة المستهدفة:"
    buttons = [
        [InlineKeyboardButton("👥 الجميع",         callback_data="adm:bc:all"),
         InlineKeyboardButton("💎 VIP فقط",        callback_data="adm:bc:vip")],
        [InlineKeyboardButton("🟢 النشطون",        callback_data="adm:bc:active"),
         InlineKeyboardButton("🆕 مستخدمو اليوم", callback_data="adm:bc:today")],
        [InlineKeyboardButton("📋 سجل الإذاعة",   callback_data="adm:bc:logs")],
    ]
    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة المنصات
# ═══════════════════════════════════════════════════════════════

async def show_platforms(query, context) -> None:
    platforms_list = [
        ("youtube", "YouTube"), ("tiktok", "TikTok"), ("instagram", "Instagram"),
        ("facebook", "Facebook"), ("twitter", "X / Twitter"), ("snapchat", "Snapchat"),
        ("pinterest", "Pinterest"), ("other", "منصات أخرى"),
    ]
    text = "🌐 *إدارة المنصات*\nاضغط للتبديل:\n\n"
    buttons = []
    for key, name in platforms_list:
        enabled = db.is_platform_enabled(key)
        icon = "✅" if enabled else "❌"
        text += f"{icon} {name}\n"
        buttons.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"adm:plat:tog:{key}")])

    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة المتجر
# ═══════════════════════════════════════════════════════════════

async def show_shop(query, context) -> None:
    products = db.get_all_products()
    text = "🏪 *المتجر*\n\n"
    buttons = [
        [InlineKeyboardButton("➕ إضافة منتج", callback_data="adm:shop:add")],
    ]
    for p in products:
        text += f"• {p['name']} — {p['price']} {p['currency']}\n"
        buttons.append([
            InlineKeyboardButton(f"✏️ {p['name']}", callback_data=f"adm:shop:edit:{p['id']}"),
            InlineKeyboardButton("🗑 حذف",          callback_data=f"adm:shop:del:{p['id']}"),
        ])
    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة الأداء
# ═══════════════════════════════════════════════════════════════

async def show_performance(query, context) -> None:
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        ram_used = ram.used // (1024 * 1024)
        ram_total = ram.total // (1024 * 1024)
    except Exception:
        cpu, ram_used, ram_total = 0, 0, 0

    cache_on = db.get_setting("cache_enabled", "1") == "1"
    queue_on = db.get_setting("queue_enabled", "1") == "1"
    compress = db.get_setting("compress_files", "0") == "1"
    auto_del = db.get_setting("auto_delete_files", "1") == "1"

    text = (
        "⚡ *مراقبة الأداء*\n\n"
        f"🖥 CPU: `{cpu}%`\n"
        f"💾 RAM: `{ram_used}/{ram_total} MB`\n\n"
        f"🗂 الكاش: {'✅ مفعل' if cache_on else '❌ معطل'}\n"
        f"📋 Queue: {'✅ مفعل' if queue_on else '❌ معطل'}\n"
        f"🗜 الضغط: {'✅ مفعل' if compress else '❌ معطل'}\n"
        f"🗑 حذف تلقائي: {'✅ مفعل' if auto_del else '❌ معطل'}\n"
    )

    buttons = [
        [InlineKeyboardButton("🗂 الكاش",     callback_data="adm:perf:cache"),
         InlineKeyboardButton("📋 Queue",     callback_data="adm:perf:queue")],
        [InlineKeyboardButton("🗜 الضغط",    callback_data="adm:perf:compress"),
         InlineKeyboardButton("🗑 حذف تلقائي", callback_data="adm:perf:autodel")],
        [InlineKeyboardButton("🔄 تحديث",    callback_data="adm:performance")],
    ]
    buttons += back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# لوحة إعدادات التحميل
# ═══════════════════════════════════════════════════════════════

async def show_dl_settings(query, context) -> None:
    speed = db.get_setting("download_speed", "high")
    quality = json.loads(db.get_setting("download_quality", "{}"))

    speed_map = {"low": "⚡", "medium": "⚡⚡", "high": "⚡⚡⚡", "ultra": "⚡⚡⚡⚡"}
    text = f"🔧 *إعدادات التحميل*\n\nالسرعة الحالية: {speed_map.get(speed, '⚡⚡⚡')}\n\n"
    text += "الجودات المتاحة:\n"
    for q, enabled in quality.items():
        text += f"{'✅' if enabled else '❌'} {q}\n"

    speed_buttons = [
        InlineKeyboardButton("⚡",       callback_data="adm:dl:speed:low"),
        InlineKeyboardButton("⚡⚡",     callback_data="adm:dl:speed:medium"),
        InlineKeyboardButton("⚡⚡⚡",   callback_data="adm:dl:speed:high"),
        InlineKeyboardButton("⚡⚡⚡⚡", callback_data="adm:dl:speed:ultra"),
    ]
    quality_buttons = [
        [InlineKeyboardButton(f"{'✅' if quality.get(q) else '❌'} {q}",
                              callback_data=f"adm:dl:qual:{q}")]
        for q in ["144p", "360p", "720p", "1080p", "mp3", "best"]
    ]
    buttons = [speed_buttons] + quality_buttons + back_button()
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════
# المعالج الرئيسي لكل callback_data الخاصة بالأدمن
# ═══════════════════════════════════════════════════════════════

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    يعالج جميع callbacks التي تبدأ بـ 'adm:'
    يرجع True إذا تم التعامل مع الحدث
    """
    query = update.callback_query
    user = update.effective_user
    data = query.data

    # ========= انسخ من هنا =========
    # 🟢 معالجة فتح لوحة التحكم بظهور الأزرار مباشرة ومنفصلة
    if data == "adm_manage_keys" or data.startswith("toggle_key:"):
        if not db.is_admin(user.id):
            await query.answer("🚫 ليس لديك صلاحية!", show_alert=True)
            return True
        await query.answer()

        # إذا كان ضغط على تفعيل/إلغاء تفعيل أحد الأزرار
        if data.startswith("toggle_key:"):
            btn_target = data.split(":")[-1]
            setting_name = f"show_btn_{btn_target}"
            current_state = db.get_setting(setting_name, "1")
            db.set_setting(setting_name, "0" if current_state == "1" else "1")

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
            "🎛️ *لوحة التحكم بظهور أزرار واجهة المستخدم:*\n\nاضغط على أي زر لعكس حالته فوراً (إخفاء أو إظهار عن المستخدمين):",
            reply_markup=InlineKeyboardMarkup(visibility_keyboard),
            parse_mode="Markdown"
        )
        return True
    # ========= إلى هنا =========

    # باقي الأكواد الموجودة لديك مسبقاً (التحقق من adm: وما إلى ذلك)

    if not data.startswith("adm:"):
        return False

    if not db.is_admin(user.id):
        await query.answer("🚫 ليس لديك صلاحية!", show_alert=True)
        return True

    await query.answer()

    # ── الرئيسية
    if data == "adm:main":
        await query.edit_message_text("⚙️ *لوحة الإدارة*", parse_mode="Markdown",
                                      reply_markup=admin_main_keyboard())

    elif data == "adm:close":
        await query.message.delete()

    # ── الإحصائيات
    elif data == "adm:stats":
        await show_stats(query, context)

    # ── القنوات
    elif data == "adm:channels":
        await show_channels(query, context)

    elif data == "adm:ch:enable_all":
        db.set_setting("forced_sub_enabled", "1")
        await show_channels(query, context)

    elif data == "adm:ch:disable_all":
        db.set_setting("forced_sub_enabled", "0")
        await show_channels(query, context)

    elif data == "adm:ch:add":
        admin_states[user.id] = {"action": "add_channel"}
        await query.edit_message_text(
            "📢 أرسل معرف القناة مع الهدف (مثال):\n`@example 200`\nأو فقط: `@example`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_button("adm:channels"))
        )

    elif data.startswith("adm:ch:del:"):
        ch_id = int(data.split(":")[-1])
        db.remove_channel(ch_id)
        await show_channels(query, context)

    elif data.startswith("adm:ch:enable:"):
        ch_id = int(data.split(":")[-1])
        db.toggle_channel(ch_id, True)
        await show_channels(query, context)

    elif data.startswith("adm:ch:disable:"):
        ch_id = int(data.split(":")[-1])
        db.toggle_channel(ch_id, False)
        await show_channels(query, context)

    elif data.startswith("adm:ch:target:"):
        ch_id = int(data.split(":")[-1])
        admin_states[user.id] = {"action": "set_target", "channel_id": ch_id}
        await query.edit_message_text(
            f"🎯 أرسل الهدف الجديد (عدد مشتركين) للقناة:",
            reply_markup=InlineKeyboardMarkup(back_button("adm:channels"))
        )

    # ── واجهة المستخدم
    elif data == "adm:ui":
        await show_ui_manager(query, context)

    elif data == "adm:ui:add":
        admin_states[user.id] = {"action": "add_button_label"}
        await query.edit_message_text(
            "➕ أرسل اسم (تسمية) الزر الجديد:",
            reply_markup=InlineKeyboardMarkup(back_button("adm:ui"))
        )

    elif data.startswith("adm:ui:del:"):
        btn_id = int(data.split(":")[-1])
        db.delete_button(btn_id)
        await show_ui_manager(query, context)

    elif data.startswith("adm:ui:tog:"):
        btn_id = int(data.split(":")[-1])
        btns = db.get_all_buttons()
        btn = next((b for b in btns if b["id"] == btn_id), None)
        if btn:
            db.toggle_button_visibility(btn_id, not bool(btn["visible"]))
        await show_ui_manager(query, context)

    elif data.startswith("adm:ui:pin:"):
        btn_id = int(data.split(":")[-1])
        btns = db.get_all_buttons()
        btn = next((b for b in btns if b["id"] == btn_id), None)
        if btn:
            db.toggle_button_pin(btn_id, not bool(btn["pinned"]))
        await show_ui_manager(query, context)

    elif data.startswith("adm:ui:edit:"):
        btn_id = int(data.split(":")[-1])
        admin_states[user.id] = {"action": "edit_button_label", "button_id": btn_id}
        await query.edit_message_text(
            "✏️ أرسل الاسم الجديد للزر:",
            reply_markup=InlineKeyboardMarkup(back_button("adm:ui"))
        )

    elif data.startswith("adm:ui:up:"):
        btn_id = int(data.split(":")[-1])
        btns = db.get_all_buttons()
        idx = next((i for i, b in enumerate(btns) if b["id"] == btn_id), None)
        if idx and idx > 0:
            db.set_button_position(btn_id, btns[idx-1]["position"] - 1)
        await show_ui_manager(query, context)

    elif data.startswith("adm:ui:down:"):
        btn_id = int(data.split(":")[-1])
        btns = db.get_all_buttons()
        idx = next((i for i, b in enumerate(btns) if b["id"] == btn_id), None)
        if idx is not None and idx < len(btns) - 1:
            db.set_button_position(btn_id, btns[idx+1]["position"] + 1)
        await show_ui_manager(query, context)

    # ── الرسائل
    elif data == "adm:messages":
        await show_messages(query, context)

    elif data.startswith("adm:msg:"):
        msg_key_map = {
            "adm:msg:welcome":      ("welcome_message",  "👋 رسالة الترحيب الحالية"),
            "adm:msg:subscription": ("subscription_msg", "🔔 رسالة الاشتراك الإجباري"),
            "adm:msg:ban":          ("ban_message",      "🚫 رسالة الحظر"),
            "adm:msg:vip":          ("vip_message",      "💎 رسالة VIP"),
            "adm:msg:vip_expired":  ("vip_expired_msg",  "⏰ رسالة انتهاء VIP"),
            "adm:msg:ads":          ("ads_text",         "📢 نص الإعلانات"),
            "adm:msg:dev_link":     ("developer_link",   "🔗 رابط المطور"),
        }
        if data in msg_key_map:
            setting_key, label = msg_key_map[data]
            current = db.get_setting(setting_key)
            admin_states[user.id] = {"action": "edit_message", "key": setting_key}
            await query.edit_message_text(
                f"✏️ *{label}*\n\nالحالية:\n`{current}`\n\nأرسل النص الجديد:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(back_button("adm:messages"))
            )

    # ── الأدمن
    elif data == "adm:admins":
        await show_admins(query, context)

    elif data == "adm:adm:add_full":
        admin_states[user.id] = {"action": "add_admin", "role": "full"}
        await query.edit_message_text("👮 أرسل معرف المستخدم (ID) لإضافته أدمن كامل:",
                                      reply_markup=InlineKeyboardMarkup(back_button("adm:admins")))

    elif data == "adm:adm:add_limited":
        admin_states[user.id] = {"action": "add_admin", "role": "limited"}
        await query.edit_message_text("👮 أرسل معرف المستخدم (ID) لإضافته أدمن محدود:",
                                      reply_markup=InlineKeyboardMarkup(back_button("adm:admins")))

    elif data == "adm:adm:remove":
        admin_states[user.id] = {"action": "remove_admin"}
        await query.edit_message_text("🗑 أرسل معرف الأدمن لحذفه:",
                                      reply_markup=InlineKeyboardMarkup(back_button("adm:admins")))

    # ── الإذاعة
    elif data == "adm:broadcast":
        await show_broadcast(query, context)

    elif data.startswith("adm:bc:") and not data.startswith("adm:bc:logs"):
        target_map = {
            "adm:bc:all":    "all",
            "adm:bc:vip":    "vip",
            "adm:bc:active": "active",
            "adm:bc:today":  "today",
        }
        if data in target_map:
            admin_states[user.id] = {"action": "broadcast", "target": target_map[data]}
            await query.edit_message_text(
                "📣 أرسل نص الرسالة المراد إذاعتها\n(يمكنك إرسال نص أو صورة أو فيديو):",
                reply_markup=InlineKeyboardMarkup(back_button("adm:broadcast"))
            )

    elif data == "adm:bc:logs":
        logs = db.get_broadcast_logs()
        text = "📋 *سجل الإذاعة*\n\n"
        for log in logs[:5]:
            text += (
                f"🆔 `{log['id']}` | {log['status']}\n"
                f"   ✅ {log['sent']} | ❌ {log['failed']} | 🚫 {log['blocked']}\n"
                f"   📅 {log['started_at'][:16]}\n\n"
            )
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(back_button("adm:broadcast")))

    # ── المنصات
    elif data == "adm:platforms":
        await show_platforms(query, context)

    elif data.startswith("adm:plat:tog:"):
        platform = data.split(":")[-1]
        current = db.is_platform_enabled(platform)
        db.set_platform_enabled(platform, not current)
        await show_platforms(query, context)

    # ── المتجر
    elif data == "adm:shop":
        await show_shop(query, context)

    elif data == "adm:shop:add":
        admin_states[user.id] = {"action": "add_product_name"}
        await query.edit_message_text("🏪 أرسل اسم المنتج الجديد:",
                                      reply_markup=InlineKeyboardMarkup(back_button("adm:shop")))

    elif data.startswith("adm:shop:del:"):
        pid = int(data.split(":")[-1])
        db.delete_product(pid)
        await show_shop(query, context)

    elif data.startswith("adm:shop:edit:"):
        pid = int(data.split(":")[-1])
        admin_states[user.id] = {"action": "edit_product_price", "product_id": pid}
        await query.edit_message_text("💰 أرسل السعر الجديد (رقم فقط):",
                                      reply_markup=InlineKeyboardMarkup(back_button("adm:shop")))

    # ── الأداء
    elif data == "adm:performance":
        await show_performance(query, context)

    elif data.startswith("adm:perf:"):
        key_map = {
            "adm:perf:cache":    "cache_enabled",
            "adm:perf:queue":    "queue_enabled",
            "adm:perf:compress": "compress_files",
            "adm:perf:autodel":  "auto_delete_files",
        }
        if data in key_map:
            key = key_map[data]
            current = db.get_setting(key, "0")
            db.set_setting(key, "0" if current == "1" else "1")
            await show_performance(query, context)

    # ── إعدادات التحميل
    elif data == "adm:dl_settings":
        await show_dl_settings(query, context)

    elif data.startswith("adm:dl:speed:"):
        speed = data.split(":")[-1]
        db.set_setting("download_speed", speed)
        await show_dl_settings(query, context)

    elif data.startswith("adm:dl:qual:"):
        qual = data.split(":")[-1]
        quality = json.loads(db.get_setting("download_quality", "{}"))
        quality[qual] = not quality.get(qual, True)
        db.set_setting("download_quality", json.dumps(quality))
        await show_dl_settings(query, context)

    return True


# ═══════════════════════════════════════════════════════════════
# معالج النصوص من الأدمن (للحوارات متعددة الخطوات)
# ═══════════════════════════════════════════════════════════════

async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    يعالج النصوص المرسلة من الأدمن أثناء حوارات الإدارة
    يرجع True إذا استهلك الرسالة
    """
    user = update.effective_user
    if not db.is_admin(user.id):
        return False

    state = admin_states.get(user.id)
    if not state:
        return False

    text = update.message.text.strip()
    action = state.get("action", "")

    # ── إضافة قناة إجبارية
    if action == "add_channel":
        parts = text.split()
        channel = parts[0].lstrip("@")
        target = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        db.add_channel(channel, target)
        del admin_states[user.id]
        await update.message.reply_text(f"✅ تمت إضافة القناة @{channel} (الهدف: {target})")
        return True

    # ── تعديل هدف قناة
    elif action == "set_target" and text.isdigit():
        ch_id = state["channel_id"]
        db.update_channel_target(ch_id, int(text))
        del admin_states[user.id]
        await update.message.reply_text(f"✅ تم تحديث الهدف إلى {text}")
        return True

    # ── إضافة زر (خطوة 1: الاسم)
    elif action == "add_button_label":
        admin_states[user.id] = {"action": "add_button_action", "label": text}
        await update.message.reply_text(
            "✅ الاسم: " + text + "\n\nأرسل الآن callback_data أو الرابط للزر:"
        )
        return True

    # ── إضافة زر (خطوة 2: الإجراء)
    elif action == "add_button_action":
        label = state["label"]
        action_type = "url" if text.startswith("http") else "callback"
        db.add_button(label, text, action_type)
        del admin_states[user.id]
        await update.message.reply_text(f"✅ تمت إضافة الزر: {label}")
        return True

    # ── تعديل زر (خطوة 1: الاسم الجديد)
    elif action == "edit_button_label":
        admin_states[user.id] = {
            "action": "edit_button_action",
            "button_id": state["button_id"],
            "label": text
        }
        await update.message.reply_text("أرسل الآن callback_data أو الرابط الجديد:")
        return True

    elif action == "edit_button_action":
        btn_id = state["button_id"]
        label = state["label"]
        action_type = "url" if text.startswith("http") else "callback"
        db.edit_button(btn_id, label, text, action_type)
        del admin_states[user.id]
        await update.message.reply_text(f"✅ تم تعديل الزر: {label}")
        return True

    # ── تعديل رسالة
    elif action == "edit_message":
        key = state["key"]
        db.set_setting(key, text)
        del admin_states[user.id]
        await update.message.reply_text("✅ تم تحديث الرسالة.")
        return True

    # ── إضافة أدمن
    elif action == "add_admin":
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            uid = int(text)
            role = state.get("role", "full")
            db.add_admin(uid, added_by=user.id, role=role)
            del admin_states[user.id]
            await update.message.reply_text(f"✅ تمت إضافة الأدمن {uid} ({role})")
        else:
            await update.message.reply_text("🚫 معرف غير صالح، أرسل رقمًا فقط.")
        return True

    # ── حذف أدمن
    elif action == "remove_admin":
        if text.isdigit():
            db.remove_admin(int(text))
            del admin_states[user.id]
            await update.message.reply_text(f"✅ تم حذف الأدمن {text}")
        return True

    # ── الإذاعة
    elif action == "broadcast":
        target = state.get("target", "all")
        del admin_states[user.id]
        # نبدأ الإذاعة بشكل غير متزامن
        asyncio.create_task(
            run_broadcast(update, context, text, target)
        )
        return True

    # ── إضافة منتج (خطوة 1)
    elif action == "add_product_name":
        admin_states[user.id] = {"action": "add_product_desc", "name": text}
        await update.message.reply_text("أرسل وصف المنتج:")
        return True

    elif action == "add_product_desc":
        admin_states[user.id] = {**state, "action": "add_product_price", "desc": text}
        await update.message.reply_text("أرسل سعر المنتج (رقم):")
        return True

    elif action == "add_product_price":
        try:
            price = float(text)
            db.add_product(state["name"], state.get("desc", ""), price)
            del admin_states[user.id]
            await update.message.reply_text(f"✅ تمت إضافة المنتج: {state['name']}")
        except ValueError:
            await update.message.reply_text("🚫 أرسل رقمًا صحيحًا.")
        return True

    # ── تعديل سعر منتج
    elif action == "edit_product_price":
        try:
            price = float(text)
            db.update_product_price(state["product_id"], price)
            del admin_states[user.id]
            await update.message.reply_text(f"✅ تم تحديث السعر.")
        except ValueError:
            await update.message.reply_text("🚫 أرسل رقمًا فقط.")
        return True

    return False


# ═══════════════════════════════════════════════════════════════
# نظام الإذاعة الاحترافي
# ═══════════════════════════════════════════════════════════════

# متغيرات للتحكم في الإذاعة الجارية
broadcast_control: dict[int, dict] = {}  # log_id -> {paused, cancelled}


async def run_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        message: str, target: str) -> None:
    """نظام إذاعة احترافي مع batch ودعم عشرات الآلاف"""
    import asyncio

    admin_id = update.effective_user.id
    batch_size = int(db.get_setting("broadcast_batch_size", "40"))
    delay = float(db.get_setting("broadcast_delay", "1.5"))

    # تحديد المستخدمين المستهدفين
    if target == "all":
        user_ids = db.get_all_user_ids()
    elif target == "vip":
        user_ids = db.get_all_vip_ids()
    elif target == "active":
        from modules.database import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE date(last_seen)>=date('now','-7 days') AND is_banned=0"
            ).fetchall()
            user_ids = [r["user_id"] for r in rows]
    elif target == "today":
        from modules.database import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE date(last_seen)=date('now') AND is_banned=0"
            ).fetchall()
            user_ids = [r["user_id"] for r in rows]
    else:
        user_ids = db.get_all_user_ids()

    total = len(user_ids)
    log_id = db.create_broadcast_log(message, total)
    broadcast_control[log_id] = {"paused": False, "cancelled": False}

    sent = failed = blocked = 0

    # رسالة متابعة للأدمن
    progress_msg = await context.bot.send_message(
        chat_id=admin_id,
        text=f"📣 *بدأت الإذاعة*\nإجمالي: `{total}`\n\n⏳ جارٍ الإرسال...",
        parse_mode="Markdown"
    )

    start_time = time.time()

    for i, uid in enumerate(user_ids):
        ctrl = broadcast_control.get(log_id, {})

        # التحقق من الإلغاء
        if ctrl.get("cancelled"):
            break

        # التحقق من الإيقاف المؤقت
        while ctrl.get("paused") and not ctrl.get("cancelled"):
            await asyncio.sleep(1)
            ctrl = broadcast_control.get(log_id, {})

        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 إعلان:\n\n{message}")
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if "bot was blocked" in err or "user is deactivated" in err:
                blocked += 1
                db.delete_user(uid)  # تنظيف قاعدة البيانات
            elif "flood" in err or "retry" in err:
                # انتظر ريثما ينتهي الـ FloodWait
                try:
                    wait_time = int(''.join(filter(str.isdigit, err))) or 5
                except Exception:
                    wait_time = 5
                await asyncio.sleep(wait_time)
                try:
                    await context.bot.send_message(chat_id=uid, text=f"📢 إعلان:\n\n{message}")
                    sent += 1
                except Exception:
                    failed += 1
            else:
                failed += 1

        # تحديث كل batch
        if (i + 1) % batch_size == 0:
            pct = int((i + 1) / total * 100)
            elapsed = int(time.time() - start_time)
            try:
                await progress_msg.edit_text(
                    f"📣 *الإذاعة جارية*\n\n"
                    f"✅ أُرسل: `{sent}`\n"
                    f"❌ فشل: `{failed}`\n"
                    f"🚫 محظور: `{blocked}`\n"
                    f"⏳ متبقي: `{total - i - 1}`\n"
                    f"📊 الإنجاز: `{pct}%`\n"
                    f"⏱ الوقت: `{elapsed}s`",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⏸ إيقاف مؤقت", callback_data=f"adm:bc:pause:{log_id}"),
                         InlineKeyboardButton("❌ إلغاء",       callback_data=f"adm:bc:cancel:{log_id}")],
                    ])
                )
            except Exception:
                pass
            await asyncio.sleep(delay)

    status = "cancelled" if broadcast_control.get(log_id, {}).get("cancelled") else "done"
    db.update_broadcast_log(log_id, sent, failed, blocked, status)

    elapsed = int(time.time() - start_time)
    try:
        await progress_msg.edit_text(
            f"✅ *انتهت الإذاعة*\n\n"
            f"✅ أُرسل: `{sent}`\n"
            f"❌ فشل: `{failed}`\n"
            f"🚫 محظور: `{blocked}`\n"
            f"⏱ المدة: `{elapsed}s`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    # تنظيف
    broadcast_control.pop(log_id, None)
