"""
وحدة تحميل Pinterest - نظام متعدد الطرق مع Fallback كامل
Pinterest Downloader - Multi-method with full fallback support

الطرق المدعومة:
1. استخراج contentUrl مباشرة من HTML
2. استخراج من JSON-LD
3. استخراج من v.pinimg.com
4. yt-dlp مع User-Agent Chrome
5. yt-dlp مع cookies
6. تحميل مباشر للصور

يدعم:
- Pins (صور + فيديو)
- روابط pin.it المختصرة
- روابط pinterest.com/pin/...
- روابط pinterest.com/.../ (بدون /pin/)
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Optional, Union
import json

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────
# Headers احترافية لتجاوز الحماية
# ─────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


# ─────────────────────────────────────────────────────────────
# دوال مساعدة
# ─────────────────────────────────────────────────────────────

def _expand_short_url(url: str) -> str:
    """توسيع روابط pin.it المختصرة"""
    try:
        import requests
        r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
        expanded = r.url.split("?")[0].rstrip("/")
        logger.info(f"[Pinterest] Expanded: {url} -> {expanded}")
        return expanded
    except Exception as e:
        logger.warning(f"[Pinterest] expand failed: {e}")
        return url


def _fetch_page(url: str) -> str:
    """جلب محتوى الصفحة"""
    try:
        import requests
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning(f"[Pinterest] page fetch failed: {e}")
        return ""


def _extract_video_url_from_html(html: str) -> Optional[str]:
    """استخراج رابط الفيديو من HTML بعدة طرق"""

    # طريقة 1: contentUrl في JSON داخل الصفحة
    patterns = [
        r'"contentUrl"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
        r'"contentUrl":"(https://v\.pinimg\.com/[^"]+)"',
        r'"video_url"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
        r'"url"\s*:\s*"(https://v\.pinimg\.com/videos/[^"]+\.mp4[^"]*)"',
        r'(https://v\.pinimg\.com/videos/mc/[^"\'\\]+\.mp4)',
        r'(https://v\.pinimg\.com/[^"\'\\]+\.mp4)',
    ]

    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            raw = match.group(1).replace("\\/", "/").replace("\\u002F", "/")
            logger.info(f"[Pinterest] Found video URL via pattern: {raw[:80]}...")
            return raw

    # طريقة 2: JSON-LD
    ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if ld_match:
        try:
            data = json.loads(ld_match.group(1))
            if isinstance(data, dict):
                for key in ("contentUrl", "url", "embedUrl"):
                    val = data.get(key, "")
                    if val and (".mp4" in val or "v.pinimg.com" in val):
                        return val
        except Exception:
            pass

    # طريقة 3: initialReduxState
    redux_match = re.search(r'P\.redux\.initialReduxState\s*=\s*(\{.*?\});', html, re.DOTALL)
    if redux_match:
        try:
            redux = json.loads(redux_match.group(1))
            # البحث في عمق JSON عن روابط mp4
            text = json.dumps(redux)
            mp4_match = re.search(r'"(https://v\.pinimg\.com/[^"]+\.mp4[^"]*)"', text)
            if mp4_match:
                return mp4_match.group(1).replace("\\/", "/")
        except Exception:
            pass

    return None


def _extract_image_url_from_html(html: str) -> Optional[str]:
    """استخراج رابط الصورة الكبيرة"""
    patterns = [
        r'"og:image"\s+content="(https://i\.pinimg\.com/originals/[^"]+)"',
        r'"og:image"\s+content="(https://i\.pinimg\.com/[^"]+)"',
        r'"image"\s*:\s*"(https://i\.pinimg\.com/originals/[^"]+)"',
        r'(https://i\.pinimg\.com/originals/[^\s"\']+)',
        r'(https://i\.pinimg\.com/736x/[^\s"\']+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return None


def _download_direct(direct_url: str, output_path: Path) -> Optional[Path]:
    """تحميل مباشر من رابط URL"""
    try:
        import requests
        r = requests.get(direct_url, headers=HEADERS, stream=True, timeout=30)
        r.raise_for_status()

        # تحديد الامتداد من Content-Type
        ct = r.headers.get("Content-Type", "")
        if "mp4" in ct or direct_url.endswith(".mp4"):
            ext = ".mp4"
        elif "webm" in ct:
            ext = ".webm"
        elif "jpeg" in ct or "jpg" in ct:
            ext = ".jpg"
        elif "png" in ct:
            ext = ".png"
        else:
            ext = ".mp4" if "video" in ct else ".jpg"

        final_path = output_path.with_suffix(ext)
        with open(final_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if final_path.exists() and final_path.stat().st_size > 1024:
            logger.info(f"[Pinterest] Direct download OK: {final_path}")
            return final_path

    except Exception as e:
        logger.warning(f"[Pinterest] Direct download failed: {e}")
    return None


def _download_via_ytdlp(url: str, output_template: str, use_cookies: bool = False) -> Optional[Path]:
    """تحميل عبر yt-dlp"""
    try:
        from yt_dlp import YoutubeDL

        opts = {
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "format": "best[ext=mp4]/best",
            "ignoreerrors": False,
            "nocheckcertificate": True,
            "user_agent": HEADERS["User-Agent"],
            "http_headers": HEADERS,
            "socket_timeout": 20,
            "retries": 3,
        }

        if use_cookies:
            cookies_file = Path("www.pinterest.com_cookies.txt")
            if cookies_file.exists():
                opts["cookiefile"] = str(cookies_file)

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None
            if "entries" in info:
                info = info["entries"][0]

            file_path = Path(ydl.prepare_filename(info))
            if file_path.exists():
                return file_path

            for ext in [".mp4", ".mkv", ".webm", ".jpg", ".jpeg", ".png"]:
                alt = file_path.with_suffix(ext)
                if alt.exists():
                    return alt

    except Exception as e:
        logger.warning(f"[Pinterest] yt-dlp failed (cookies={use_cookies}): {e}")
    return None


# ─────────────────────────────────────────────────────────────
# الدالة الرئيسية
# ─────────────────────────────────────────────────────────────

async def download_pinterest(url: str, user_id: int) -> Optional[Path]:
    """
    تحميل محتوى Pinterest بنظام Fallback متعدد الطرق
    يعيد مسار الملف المحمّل أو None عند الفشل الكامل
    """
    loop = asyncio.get_event_loop()

    # ── توسيع الرابط المختصر
    if "pin.it" in url:
        url = await loop.run_in_executor(None, _expand_short_url, url)

    # ── قالب مسار الإخراج
    base_name = f"{user_id}_{int(time.time())}"
    output_template = str(DOWNLOAD_DIR / f"{base_name}.%(ext)s")
    output_base = DOWNLOAD_DIR / base_name

    logger.info(f"[Pinterest] Downloading: {url}")

    # ══════════════════════════════════════════════
    # الطريقة 1: جلب الصفحة واستخراج الرابط المباشر
    # ══════════════════════════════════════════════
    def method_1_html_parse():
        html = _fetch_page(url)
        if not html:
            return None

        # محاولة استخراج فيديو أولاً
        video_url = _extract_video_url_from_html(html)
        if video_url:
            result = _download_direct(video_url, output_base)
            if result:
                return result

        # محاولة استخراج صورة
        image_url = _extract_image_url_from_html(html)
        if image_url:
            result = _download_direct(image_url, output_base)
            if result:
                return result

        return None

    result = await loop.run_in_executor(None, method_1_html_parse)
    if result:
        return result
    logger.info("[Pinterest] Method 1 (HTML parse) failed, trying method 2...")

    # ══════════════════════════════════════════════
    # الطريقة 2: yt-dlp بدون cookies
    # ══════════════════════════════════════════════
    def method_2_ytdlp():
        return _download_via_ytdlp(url, output_template, use_cookies=False)

    result = await loop.run_in_executor(None, method_2_ytdlp)
    if result:
        return result
    logger.info("[Pinterest] Method 2 (yt-dlp no cookies) failed, trying method 3...")

    # ══════════════════════════════════════════════
    # الطريقة 3: yt-dlp مع cookies
    # ══════════════════════════════════════════════
    def method_3_ytdlp_cookies():
        return _download_via_ytdlp(url, output_template, use_cookies=True)

    result = await loop.run_in_executor(None, method_3_ytdlp_cookies)
    if result:
        return result
    logger.info("[Pinterest] Method 3 (yt-dlp + cookies) failed, trying method 4...")

    # ══════════════════════════════════════════════
    # الطريقة 4: محاولة تحميل الصورة من og:image كبديل نهائي
    # ══════════════════════════════════════════════
    def method_4_fallback_image():
        html = _fetch_page(url)
        if not html:
            return None
        # البحث في أي مكان عن صورة
        og_match = re.search(r'content="(https://i\.pinimg\.com/[^"]+)"', html)
        if og_match:
            return _download_direct(og_match.group(1), output_base)
        return None

    result = await loop.run_in_executor(None, method_4_fallback_image)
    if result:
        return result

    logger.error(f"[Pinterest] All 4 methods failed for URL: {url}")
    return None
