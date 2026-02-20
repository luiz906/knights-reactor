"""
Knights Reactor — Publishing
Caption generation (GPT-4o) and multi-platform publishing (Blotato).
"""
import json, re
from datetime import datetime, timedelta
import requests
from config import Config, log

CAPTION_PROMPT = """You are a social media expert. Create platform-optimized content from this viral video.

Video Script: {script}
Topic: {topic}
Category: {category}

PLATFORM REQUIREMENTS:

VIDEO PLATFORMS (with captions):
- TikTok: 300 chars max, trendy casual, 3-5 hashtags
- YouTube Shorts: 500 chars max, searchable keywords, 5-8 hashtags. Also provide a title.
- Instagram Reels: 400 chars max, hashtag-rich, 8-12 hashtags
- Facebook Reels: 400 chars max, conversational, 3-5 hashtags

Use line breaks to separate thoughts. MINIMAL emojis (0-2 per caption).
CTA must be on its own line. Hashtags grouped at end.

Return as JSON:
{{
  "tiktok": "caption text",
  "youtube": "caption text",
  "youtube_title": "short title",
  "instagram": "caption text",
  "facebook": "caption text"
}}
"""

TEXT_POST_PROMPT = """You are a multi-platform content strategist. Transform this viral video into TEXT-ONLY content.

Video Script: {script}
Topic: {topic}
Category: {category}

1. X/TWITTER: Single viral tweet, 280 chars max, NO hashtags
2. THREADS: Conversational, 500 chars max
3. PINTEREST: 400-500 chars, educational, 5-7 hashtags

Return as JSON:
{{
  "twitter": "tweet text",
  "threads": "threads text",
  "pinterest": "pinterest caption"
}}
"""

def generate_captions(script: dict, topic: dict) -> dict:
    """Generate platform-specific captions via GPT-4o."""
    log.info("💬 Phase 10: Generating captions via GPT-4o...")

    captions = {}

    for label, prompt_tpl in [("video", CAPTION_PROMPT), ("text", TEXT_POST_PROMPT)]:
        prompt = prompt_tpl.format(
            script=script["script_full"],
            topic=topic["idea"],
            category=topic["category"],
        )

        r = requests.post("https://api.openai.com/v1/chat/completions", headers={
            "Authorization": f"Bearer {Config.OPENAI_KEY}",
            "Content-Type": "application/json",
        }, json={
            "model": Config.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 2000,
        })
        r.raise_for_status()

        text = r.json()["choices"][0]["message"]["content"]
        raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
        raw = re.sub(r'\n?```\s*$', '', raw).strip()

        try:
            parsed = json.loads(raw)
            captions.update(parsed)
        except json.JSONDecodeError:
            log.warning(f"   Failed to parse {label} captions")

    log.info(f"   Captions: {len(captions)} platforms")
    return captions


# ══════════════════════════════════════════════════════════════
# PHASE 11: PUBLISH VIA BLOTATO
# ══════════════════════════════════════════════════════════════

def blotato_upload_media(video_url: str) -> str:
    """Upload video to Blotato, return media URL."""
    r = requests.post("https://backend.blotato.com/v2/media", headers={
        "Authorization": f"Bearer {Config.BLOTATO_KEY}",
        "Content-Type": "application/json",
    }, json={"url": video_url})
    r.raise_for_status()
    return r.json().get("url", video_url)


def blotato_post(account_id: str, platform: str, caption: str,
                 media_urls: list = None, schedule_time: str = None, **kwargs):
    """Post to a platform via Blotato."""
    if not account_id:
        log.info(f"   ⏭️  {platform}: no account ID, skipping")
        return None

    payload = {
        "post": {
            "accountId": account_id,
            "content": {
                "text": caption,
                "mediaUrls": media_urls or [],
                "platform": platform,
            },
            "target": {"targetType": platform, **kwargs},
        },
    }
    if schedule_time:
        payload["scheduledTime"] = schedule_time

    r = requests.post("https://backend.blotato.com/v2/posts", headers={
        "Authorization": f"Bearer {Config.BLOTATO_KEY}",
        "Content-Type": "application/json",
    }, json=payload, timeout=30)

    if r.ok:
        log.info(f"   ✓ {platform}")
    else:
        log.warning(f"   ✗ {platform}: {r.status_code}")

    return r.json() if r.ok else None


def publish_everywhere(final_video_url: str, captions: dict, topic: dict):
    """Publish video + text to all platforms via Blotato."""
    log.info("📡 Phase 11: Publishing to all platforms via Blotato...")

    acct = Config.BLOTATO_ACCOUNTS

    # Upload media to Blotato
    media_url = blotato_upload_media(final_video_url)

    # Schedule times (tomorrow, optimal hours EST→UTC)
    tomorrow = datetime.now() + timedelta(days=1)
    times = {
        "tiktok":    tomorrow.replace(hour=20, minute=0).isoformat() + "Z",  # 3pm EST
        "youtube":   tomorrow.replace(hour=18, minute=30).isoformat() + "Z",
        "instagram": tomorrow.replace(hour=17, minute=0).isoformat() + "Z",
        "facebook":  tomorrow.replace(hour=19, minute=0).isoformat() + "Z",
    }

    # Video platforms
    blotato_post(acct["tiktok"], "tiktok", captions.get("tiktok", ""),
                 [media_url], times["tiktok"],
                 privacyLevel="PUBLIC_TO_EVERYONE", isAiGenerated=True)

    blotato_post(acct["youtube"], "youtube", captions.get("youtube", ""),
                 [media_url], times["youtube"],
                 title=captions.get("youtube_title", topic["idea"]),
                 privacyStatus="public", shouldNotifySubscribers=True)

    blotato_post(acct["instagram"], "instagram", captions.get("instagram", ""),
                 [media_url], times["instagram"])

    blotato_post(acct["facebook"], "facebook", captions.get("facebook", ""),
                 [media_url], times["facebook"],
                 pageId=acct.get("facebook_page"))

    # Text platforms
    blotato_post(acct["twitter"], "twitter", captions.get("twitter", ""))
    blotato_post(acct["threads"], "threads", captions.get("threads", ""))


# ══════════════════════════════════════════════════════════════
# MAIN PIPELINE
