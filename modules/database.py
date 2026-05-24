"""
وحدة قاعدة البيانات - SQLite
تحتوي على جميع الجداول والعمليات المطلوبة
"""
import sqlite3
import json
import time
import logging
from pathlib import Path
from datetime import datetime, date
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("bot_data.db")


def get_conn() -> sqlite3.Connection:
    """الحصول على اتصال بقاعدة البيانات مع دعم row_factory"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """إنشاء جميع الجداول إذا لم تكن موجودة"""
    with get_conn() as conn:
        conn.executescript("""
        -- جدول المستخدمين
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT DEFAULT '',
            first_name  TEXT DEFAULT '',
            language    TEXT DEFAULT 'ar',
            country     TEXT DEFAULT '',
            joined_at   TEXT DEFAULT (datetime('now')),
            last_seen   TEXT DEFAULT (datetime('now')),
            is_banned   INTEGER DEFAULT 0,
            messages_sent INTEGER DEFAULT 0
        );

        -- جدول الأدمن
        CREATE TABLE IF NOT EXISTS admins (
            user_id     INTEGER PRIMARY KEY,
            added_by    INTEGER DEFAULT 0,
            role        TEXT DEFAULT 'full',   -- full / limited
            permissions TEXT DEFAULT '{}',
            added_at    TEXT DEFAULT (datetime('now'))
        );

        -- جدول VIP
        CREATE TABLE IF NOT EXISTS vip (
            user_id     INTEGER PRIMARY KEY,
            added_by    INTEGER DEFAULT 0,
            expires_at  TEXT DEFAULT '',
            added_at    TEXT DEFAULT (datetime('now'))
        );

        -- جدول القنوات الإجبارية
        CREATE TABLE IF NOT EXISTS forced_subscriptions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel     TEXT NOT NULL,
            target      INTEGER DEFAULT 0,   -- الهدف المطلوب من الأعضاء
            current_count INTEGER DEFAULT 0,
            enabled     INTEGER DEFAULT 1,
            completed   INTEGER DEFAULT 0,
            added_at    TEXT DEFAULT (datetime('now'))
        );

        -- جدول أزرار واجهة المستخدم
        CREATE TABLE IF NOT EXISTS buttons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT NOT NULL,
            action      TEXT NOT NULL,   -- callback_data أو url
            action_type TEXT DEFAULT 'callback',  -- callback / url / command
            visible     INTEGER DEFAULT 1,
            position    INTEGER DEFAULT 0,
            pinned      INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- جدول الإعدادات العامة
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );

        -- جدول الإحصائيات
        CREATE TABLE IF NOT EXISTS statistics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            user_id     INTEGER DEFAULT 0,
            platform    TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- جدول التحميلات
        CREATE TABLE IF NOT EXISTS downloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            url         TEXT NOT NULL,
            platform    TEXT DEFAULT 'other',
            status      TEXT DEFAULT 'pending',
            file_size   INTEGER DEFAULT 0,
            duration    REAL DEFAULT 0,
            cache_key   TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- جدول الكاش (للروابط المكررة)
        CREATE TABLE IF NOT EXISTS cache (
            cache_key   TEXT PRIMARY KEY,
            file_id     TEXT DEFAULT '',
            file_path   TEXT DEFAULT '',
            url         TEXT DEFAULT '',
            platform    TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            expires_at  TEXT DEFAULT ''
        );

        -- جدول سجل الإذاعة
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message     TEXT DEFAULT '',
            total       INTEGER DEFAULT 0,
            sent        INTEGER DEFAULT 0,
            failed      INTEGER DEFAULT 0,
            blocked     INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'pending',  -- pending/running/paused/done/cancelled
            started_at  TEXT DEFAULT (datetime('now')),
            ended_at    TEXT DEFAULT ''
        );

        -- جدول منتجات المتجر
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            price       REAL DEFAULT 0,
            currency    TEXT DEFAULT 'USD',
            enabled     INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        """)

        # إدراج إعدادات افتراضية إذا لم تكن موجودة
        defaults = {
            "welcome_message":    "أهلاً {name}!\\n\\nهذا بوت تحميل متعدد المنصات.\\nأرسل رابط الفيديو أو اختر من القائمة.",
            "subscription_msg":   "🔔 يجب الاشتراك في القنوات التالية أولاً:\\n{channels}\\nثم اضغط ✅ تحقق من الاشتراك",
            "ban_message":        "🚫 أنت محظور من استخدام البوت.",
            "vip_message":        "💎 أنت عضو VIP! تستمتع بميزات إضافية.",
            "vip_expired_msg":    "⏰ انتهت صلاحية اشتراكك VIP.",
            "ads_text":           "🔥 اشترك في القناة لدعم البوت!",
            "developer_link":     "@YourDeveloper",
            "forced_sub_enabled": "1",
            "platforms_enabled":  json.dumps({
                "youtube": True, "tiktok": True, "instagram": True,
                "facebook": True, "twitter": True, "snapchat": True,
                "pinterest": True, "other": True,
            }),
            "download_quality":   json.dumps({
                "144p": False, "360p": True, "720p": True,
                "1080p": True, "mp3": True, "best": True,
            }),
            "cache_enabled":      "1",
            "queue_enabled":      "1",
            "compress_files":     "0",
            "auto_delete_files":  "1",
            "broadcast_batch_size": "40",
            "broadcast_delay":    "1.5",
            "broadcast_workers":  "3",
            "download_speed":     "high",  # low/medium/high/ultra
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
    logger.info("✅ قاعدة البيانات جاهزة")


# ─────────────────────────────────────────────────────────────
# دوال المستخدمين
# ─────────────────────────────────────────────────────────────

def record_user(user) -> None:
    today = date.today().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_seen)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_seen  = datetime('now')
        """, (user.id, user.username or "", user.first_name or ""))
        # إحصائية
        conn.execute(
            "INSERT INTO statistics (event_type, user_id, created_at) VALUES ('user_active', ?, date('now'))",
            (user.id,)
        )
        conn.commit()


def get_user_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_today_users() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE date(last_seen) = date('now')"
        ).fetchone()[0]


def get_active_users() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE date(last_seen) >= date('now', '-7 days')"
        ).fetchone()[0]


def is_banned(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row["is_banned"])


def ban_user(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
        conn.commit()


def unban_user(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        conn.commit()


def delete_user(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()


def get_all_user_ids() -> list[int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
        return [r["user_id"] for r in rows]


def increment_messages(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET messages_sent = messages_sent + 1 WHERE user_id=?", (user_id,)
        )
        conn.commit()


def get_total_messages() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COALESCE(SUM(messages_sent),0) FROM users").fetchone()[0]


# ─────────────────────────────────────────────────────────────
# دوال الأدمن
# ─────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    with get_conn() as conn:
        return bool(conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone())


def add_admin(user_id: int, added_by: int = 0, role: str = "full") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, role) VALUES (?,?,?)",
            (user_id, added_by, role)
        )
        conn.commit()


def remove_admin(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        conn.commit()


def get_all_admins() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM admins").fetchall()
        return [dict(r) for r in rows]


def get_admin_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]


# ─────────────────────────────────────────────────────────────
# دوال VIP
# ─────────────────────────────────────────────────────────────

def is_vip(user_id: int) -> bool:
    with get_conn() as conn:
        return bool(conn.execute("SELECT 1 FROM vip WHERE user_id=?", (user_id,)).fetchone())


def add_vip(user_id: int, added_by: int = 0) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO vip (user_id, added_by) VALUES (?,?)",
            (user_id, added_by)
        )
        conn.commit()


def remove_vip(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM vip WHERE user_id=?", (user_id,))
        conn.commit()


def get_vip_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM vip").fetchone()[0]


def get_all_vip_ids() -> list[int]:
    with get_conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM vip").fetchall()]


# ─────────────────────────────────────────────────────────────
# دوال القنوات الإجبارية
# ─────────────────────────────────────────────────────────────

def add_channel(channel: str, target: int = 0) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO forced_subscriptions (channel, target) VALUES (?,?)",
            (channel.strip().lstrip("@"), target)
        )
        conn.commit()
        return cur.lastrowid


def remove_channel(channel_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM forced_subscriptions WHERE id=?", (channel_id,))
        conn.commit()


def get_all_channels() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM forced_subscriptions ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_enabled_channels() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM forced_subscriptions WHERE enabled=1 AND completed=0 ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_channel_count(channel_id: int, count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE forced_subscriptions SET current_count=? WHERE id=?", (count, channel_id)
        )
        conn.commit()


def mark_channel_completed(channel_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE forced_subscriptions SET completed=1, enabled=0 WHERE id=?", (channel_id,)
        )
        conn.commit()


def toggle_channel(channel_id: int, enabled: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE forced_subscriptions SET enabled=? WHERE id=?", (int(enabled), channel_id)
        )
        conn.commit()


def update_channel_target(channel_id: int, target: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE forced_subscriptions SET target=?, completed=0 WHERE id=?", (target, channel_id)
        )
        conn.commit()


def get_channel_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM forced_subscriptions").fetchone()[0]


# ─────────────────────────────────────────────────────────────
# دوال الأزرار
# ─────────────────────────────────────────────────────────────

def get_all_buttons() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM buttons ORDER BY pinned DESC, position ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_visible_buttons() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM buttons WHERE visible=1 ORDER BY pinned DESC, position ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_button(label: str, action: str, action_type: str = "callback") -> int:
    with get_conn() as conn:
        max_pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM buttons").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO buttons (label, action, action_type, position) VALUES (?,?,?,?)",
            (label, action, action_type, max_pos + 1)
        )
        conn.commit()
        return cur.lastrowid


def edit_button(btn_id: int, label: str, action: str, action_type: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE buttons SET label=?, action=?, action_type=? WHERE id=?",
            (label, action, action_type, btn_id)
        )
        conn.commit()


def delete_button(btn_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM buttons WHERE id=?", (btn_id,))
        conn.commit()


def toggle_button_visibility(btn_id: int, visible: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE buttons SET visible=? WHERE id=?", (int(visible), btn_id))
        conn.commit()


def set_button_position(btn_id: int, position: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE buttons SET position=? WHERE id=?", (position, btn_id))
        conn.commit()


def toggle_button_pin(btn_id: int, pinned: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE buttons SET pinned=? WHERE id=?", (int(pinned), btn_id))
        conn.commit()


# ─────────────────────────────────────────────────────────────
# دوال الإعدادات
# ─────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
        conn.commit()


def get_platforms() -> dict:
    raw = get_setting("platforms_enabled", "{}")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def set_platform_enabled(platform: str, enabled: bool) -> None:
    platforms = get_platforms()
    platforms[platform] = enabled
    set_setting("platforms_enabled", json.dumps(platforms))


def is_platform_enabled(platform: str) -> bool:
    return get_platforms().get(platform, True)


# ─────────────────────────────────────────────────────────────
# دوال التحميل والكاش
# ─────────────────────────────────────────────────────────────

def record_download(user_id: int, url: str, platform: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO downloads (user_id, url, platform) VALUES (?,?,?)",
            (user_id, url, platform)
        )
        conn.commit()
        return cur.lastrowid


def get_download_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]


def get_top_platform() -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM downloads GROUP BY platform ORDER BY cnt DESC LIMIT 1"
        ).fetchone()
        return row["platform"] if row else "—"


def get_cache(cache_key: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cache WHERE cache_key=?", (cache_key,)).fetchone()
        if row:
            return dict(row)
        return None


def set_cache(cache_key: str, file_id: str, url: str, platform: str) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO cache (cache_key, file_id, url, platform)
            VALUES (?,?,?,?)
            ON CONFLICT(cache_key) DO UPDATE SET file_id=excluded.file_id
        """, (cache_key, file_id, url, platform))
        conn.commit()


# ─────────────────────────────────────────────────────────────
# دوال المتجر
# ─────────────────────────────────────────────────────────────

def get_all_products() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def add_product(name: str, description: str, price: float, currency: str = "USD") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO products (name, description, price, currency) VALUES (?,?,?,?)",
            (name, description, price, currency)
        )
        conn.commit()
        return cur.lastrowid


def delete_product(product_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()


def update_product_price(product_id: int, price: float) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE products SET price=? WHERE id=?", (price, product_id))
        conn.commit()


# ─────────────────────────────────────────────────────────────
# دوال الإذاعة
# ─────────────────────────────────────────────────────────────

def create_broadcast_log(message: str, total: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO broadcast_logs (message, total, status) VALUES (?,?,'running')",
            (message, total)
        )
        conn.commit()
        return cur.lastrowid


def update_broadcast_log(log_id: int, sent: int, failed: int, blocked: int, status: str) -> None:
    with get_conn() as conn:
        ended = datetime.now().isoformat() if status in ("done", "cancelled") else ""
        conn.execute("""
            UPDATE broadcast_logs SET sent=?, failed=?, blocked=?, status=?, ended_at=?
            WHERE id=?
        """, (sent, failed, blocked, status, ended, log_id))
        conn.commit()


def get_broadcast_logs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM broadcast_logs ORDER BY id DESC LIMIT 20"
        ).fetchall()
        return [dict(r) for r in rows]
