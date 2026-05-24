"""
مساعدات البوت - دوال مشتركة
"""
import re

URL_REGEX = re.compile(r"https?://[\w./?=&%+\-#@!~:]+")


def detect_platform(url: str) -> str:
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "tiktok.com" in lower:
        return "tiktok"
    if "instagram.com" in lower:
        return "instagram"
    if "twitter.com" in lower or "x.com" in lower:
        return "twitter"
    if "facebook.com" in lower or "fb.watch" in lower:
        return "facebook"
    if "pinterest.com" in lower or "pin.it" in lower:
        return "pinterest"
    if "snapchat.com" in lower or "snap.com" in lower:
        return "snapchat"
    if "reddit.com" in lower or "redd.it" in lower:
        return "reddit"
    if "threads.net" in lower:
        return "threads"
    if "vimeo.com" in lower:
        return "vimeo"
    if "dailymotion.com" in lower or "dai.ly" in lower:
        return "dailymotion"
    if "soundcloud.com" in lower:
        return "soundcloud"
    return "other"


def is_url(text: str) -> bool:
    return bool(URL_REGEX.search(text))


def format_channel(channel: str) -> str:
    if not channel:
        return ""
    channel = channel.strip().lstrip("@#")
    return f"@{channel}"


def format_developer_link(link: str) -> str:
    if not link:
        return ""
    link = link.strip()
    if link.startswith("http"):
        return link
    return f"https://t.me/{link.lstrip('@')}"
