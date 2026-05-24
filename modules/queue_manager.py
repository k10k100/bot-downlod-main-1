"""
وحدة إدارة قائمة الانتظار والتحميل
Queue Manager + Smart Cache
"""
import requests
import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

from modules import database as db

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# قائمة الانتظار العالمية
_queue: asyncio.Queue = asyncio.Queue()
_active_tasks: dict[int, asyncio.Task] = {}
_queue_position: dict[int, int] = {}   # user_id -> position
_workers_running = False


def _make_cache_key(url: str) -> str:
    """إنشاء مفتاح كاش من الرابط"""
    return hashlib.md5(url.encode()).hexdigest()


def _get_format_string() -> str:
    """يحدد صيغة الجودة مع مرونة عالية للمنصات مثل بنترست"""
    import json
    try:
        quality_raw = db.get_setting("download_quality", "{}")
        quality = json.loads(quality_raw)
    except Exception:
        quality = {"best": True}

    # القاعدة الذهبية: حاول تحميل الأفضل بصيغة mp4، وإذا لم تجد، حمل أفضل فيديو وصوت متاحين مهما كانت الصيغة
    base_fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

    if quality.get("1080p"):
        fmt = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"
    elif quality.get("720p"):
        fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"
    elif quality.get("360p"):
        fmt = "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]"
    elif quality.get("mp3"):
        fmt = "bestaudio/best"
    else:
        fmt = base_fmt

    # إضافة خيار احتياطي (Fallback) لكل الصيغ لضمان عدم الفشل
    return f"{fmt}/best"


async def download_video(url: str, user_id: int) -> Optional[Path]:
    """
    تحميل فيديو/صورة من أي منصة مدعومة
    - Pinterest: يستخدم وحدة pinterest_downloader المتخصصة (4 طرق fallback)
    - بقية المنصات: yt-dlp مع إعدادات محسّنة
    """
    # 1. فحص الكاش
    if db.get_setting("cache_enabled", "1") == "1":
        cache_key = _make_cache_key(url)
        cached = db.get_cache(cache_key)
        if cached and cached.get("file_id"):
            return cached

    # 2. Pinterest: استخدام الوحدة المتخصصة
    if "pinterest.com" in url or "pin.it" in url:
        try:
            from modules.pinterest_downloader import download_pinterest
            result = await download_pinterest(url, user_id)
            if result:
                return result
            logger.warning("[Queue] Pinterest downloader returned None, continuing to yt-dlp fallback")
        except Exception as e:
            logger.error(f"[Queue] Pinterest module error: {e}")
        # Fallback إضافي: محاولة yt-dlp مباشرة
        logger.info("[Queue] Trying yt-dlp as last resort for Pinterest...")

    # 3. قالب مسار الإخراج
    filename = f"{user_id}_{int(time.time())}.%(ext)s"
    output_template = str(DOWNLOAD_DIR / filename)

    # 4. إعدادات yt-dlp العامة المحسّنة
    opts = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "format": _get_format_string(),
        "ignoreerrors": True,
        "nocheckcertificate": True,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
    }

    if imageio_ffmpeg is not None:
        opts["ffmpeg_location"] = imageio_ffmpeg.get_ffmpeg_exe()
        opts["merge_output_format"] = "mp4"

    # إضافة cookies لـ Pinterest إذا وُجدت
    if "pinterest.com" in url or "pin.it" in url:
        cookies_file = Path("www.pinterest.com_cookies.txt")
        if cookies_file.exists():
            opts["cookiefile"] = str(cookies_file)

    loop = asyncio.get_event_loop()

    def _do_download():
        if not url:
            return None
        try:
            with YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=True)
                if not result:
                    return None
                if "entries" in result:
                    result = result["entries"][0]
                file_path = Path(ydl.prepare_filename(result))
                if file_path.exists():
                    return file_path
                for ext in [".mp4", ".mkv", ".webm", ".jpg", ".jpeg", ".png"]:
                    alt_path = file_path.with_suffix(ext)
                    if alt_path.exists():
                        return alt_path
        except Exception as e:
            logger.error(f"[Queue] yt-dlp download failed: {e}")
            return None
        return None

    try:
        return await loop.run_in_executor(None, _do_download)
    except Exception as exc:
        logger.error(f"[Queue] Executor error: {exc}")
        return None

# ─────────────────────────────────────────────────────────────
# نظام Queue
# ─────────────────────────────────────────────────────────────

class DownloadJob:
    def __init__(self, user_id: int, url: str, message, context):
        self.user_id = user_id
        self.url = url
        self.message = message    # رسالة الانتظار
        self.context = context
        self.event = asyncio.Event()
        self.result = None


async def _worker(worker_id: int) -> None:
    """عامل queue واحد"""
    logger.info(f"Worker {worker_id} started")
    while True:
        try:
            job: DownloadJob = await _queue.get()
            try:
                await _process_job(job)
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                job.result = None
                job.event.set()
            finally:
                _queue.task_done()
                _queue_position.pop(job.user_id, None)
        except asyncio.CancelledError:
            break


async def _process_job(job: DownloadJob) -> None:
    """معالجة وظيفة تحميل واحدة"""
    from modules.database import record_download
    from bot_helpers import detect_platform

    platform = detect_platform(job.url)
    record_download(job.user_id, job.url, platform)

    try:
        await job.message.edit_text("⬇️ جارٍ التحميل...")
    except Exception:
        pass

    result = await download_video(job.url, job.user_id)
    job.result = result
    job.event.set()


async def start_workers(num_workers: int = 3) -> None:
    """تشغيل عمال Queue"""
    global _workers_running
    if _workers_running:
        return
    _workers_running = True
    for i in range(num_workers):
        asyncio.create_task(_worker(i + 1))
    logger.info(f"✅ {num_workers} Queue workers started")


async def enqueue_download(user_id: int, url: str, message, context) -> Optional[Path]:
    """
    إضافة طلب تحميل إلى Queue
    يرجع المسار أو None
    """
    if db.get_setting("queue_enabled", "1") != "1":
        # بدون Queue — تحميل مباشر
        return await download_video(url, user_id)

    job = DownloadJob(user_id, url, message, context)
    pos = _queue.qsize() + 1
    _queue_position[user_id] = pos

    if pos > 1:
        try:
            await message.edit_text(f"⏳ في قائمة الانتظار\n📍 ترتيبك: `{pos}`", parse_mode="Markdown")
        except Exception:
            pass

    await _queue.put(job)
    await job.event.wait()
    return job.result
