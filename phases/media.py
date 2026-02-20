"""
Knights Reactor — Media Generation
Replicate (images, videos), ElevenLabs (voiceover), Whisper (transcribe).
"""
import time, re
import requests
from config import Config, log

def replicate_create(model: str, input_data: dict) -> str:
    """Create a Replicate prediction, return the GET URL for polling."""
    for attempt in range(5):
        r = requests.post(
            f"https://api.replicate.com/v1/models/{model}/predictions",
            headers={
                "Authorization": f"Bearer {Config.REPLICATE_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"input": input_data},
            timeout=30,
        )
        if r.status_code == 429:
            wait = min(30 * (attempt + 1), 120)
            log.warning(f"   Rate limited (429), waiting {wait}s before retry {attempt+2}/5...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["urls"]["get"]
    raise Exception("Replicate rate limit: 5 retries exhausted")


def replicate_poll(get_url: str, timeout: int = 300) -> str:
    """Poll a Replicate prediction until complete. Returns output URL."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(get_url, headers={
            "Authorization": f"Bearer {Config.REPLICATE_TOKEN}",
        })
        r.raise_for_status()
        data = r.json()
        status = data.get("status")

        if status == "succeeded":
            output = data.get("output")
            if isinstance(output, list):
                return output[0]
            return output
        elif status == "failed":
            raise RuntimeError(f"Replicate failed: {data.get('error')}")

        time.sleep(10)

    raise TimeoutError("Replicate prediction timed out")


def generate_images(clips: list) -> list:
    """Generate cinematic images via Replicate (all models support 9:16)."""
    model = Config.IMAGE_MODEL
    quality = getattr(Config, 'IMAGE_QUALITY', 'high')
    log.info(f"🖼️  Phase 4: Generating images via Replicate ({model}) | Quality: {quality} | Aspect: 9:16")

    for clip in clips:
        params = {"prompt": clip["image_prompt"]}

        # Model-specific parameter mapping
        if "grok-imagine" in model:
            # xAI Grok Aurora — uses prompt + aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "nano-banana" in model:
            # Google Nano Banana / Pro — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "seedream" in model:
            # ByteDance Seedream — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "ideogram" in model:
            # Ideogram v3 — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "recraft" in model:
            # Recraft v3 — uses aspect_ratio (no quality param)
            params["aspect_ratio"] = "9:16"
        elif "imagen" in model:
            # Google Imagen — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        else:
            # Flux, SD, and most others
            params["aspect_ratio"] = "9:16"
            params["quality"] = quality

        url = replicate_create(model, params)
        clip["image_poll_url"] = url
        log.info(f"   Clip {clip['index']}: submitted")
        time.sleep(8)  # Avoid 429 rate limits

    for clip in clips:
        clip["image_url"] = replicate_poll(clip["image_poll_url"])
        log.info(f"   Clip {clip['index']}: image ready ✓")

    return clips


# ══════════════════════════════════════════════════════════════
# PHASE 5: GENERATE VIDEOS (Replicate → Seedance-1-Lite)
# ══════════════════════════════════════════════════════════════

def generate_videos(clips: list) -> list:
    """Animate images into videos via configured provider."""
    model = Config.VIDEO_MODEL
    log.info(f"🎥 Phase 5: Generating videos via {model}...")

    # Build params based on model (different models accept different params)
    for clip in clips:
        if "grok-imagine" in model.lower():
            # xAI Grok Imagine Video — uses image_url, mode, prompt
            params = {
                "image_url": clip["image_url"],
                "prompt": clip["motion_prompt"],
                "mode": "normal",
            }
        elif "minimax" in model.lower():
            # Minimax — uses first_frame_image
            params = {
                "first_frame_image": clip["image_url"],
                "prompt": clip["motion_prompt"],
            }
        else:
            # Most models: Seedance, Wan, Kling, Luma, Veo
            params = {
                "image": clip["image_url"],
                "prompt": clip["motion_prompt"],
            }
        # Pass 9:16 where supported
        if "seedance" in model.lower() or "wan" in model.lower():
            params["aspect_ratio"] = "9:16"

        url = replicate_create(model, params)
        clip["video_poll_url"] = url
        log.info(f"   Clip {clip['index']}: submitted")
        time.sleep(3)

    for clip in clips:
        clip["video_url"] = replicate_poll(clip["video_poll_url"], timeout=600)
        log.info(f"   Clip {clip['index']}: video ready ✓")

    return clips


# ══════════════════════════════════════════════════════════════
# PHASE 5b: REGENERATE SINGLE VIDEO CLIP
# ══════════════════════════════════════════════════════════════

def generate_video_single(clip: dict) -> dict:
    """Regenerate a single video clip. Used by video approval gate."""
    model = Config.VIDEO_MODEL
    log.info(f"🎥 Regenerating clip {clip.get('index','')} via {model}...")

    if "grok-imagine" in model.lower():
        params = {"image_url": clip["image_url"], "prompt": clip["motion_prompt"], "mode": "normal"}
    elif "minimax" in model.lower():
        params = {"first_frame_image": clip["image_url"], "prompt": clip["motion_prompt"]}
    else:
        params = {"image": clip["image_url"], "prompt": clip["motion_prompt"]}
    if "seedance" in model.lower() or "wan" in model.lower():
        params["aspect_ratio"] = "9:16"

    url = replicate_create(model, params)
    clip["video_poll_url"] = url
    clip["video_url"] = replicate_poll(url, timeout=600)
    log.info(f"   Clip {clip.get('index','')}: video regenerated ✓")
    return clip


# ══════════════════════════════════════════════════════════════
# PHASE 6: VOICEOVER (ElevenLabs)
# ══════════════════════════════════════════════════════════════

def generate_voiceover(script: dict) -> bytes:
    """Generate voiceover audio via ElevenLabs."""
    log.info(f"🔊 Phase 6: Generating voiceover via ElevenLabs | Voice: {Config.VOICE_ID} | Model: {Config.VOICE_MODEL}")

    text = script["script_full"]
    # Clean for ElevenLabs (prevent chuckling)
    text = re.sub(r'["""]', '', text)

    voice_settings = {
        "stability": Config.VOICE_STABILITY,
        "similarity_boost": Config.VOICE_SIMILARITY,
    }
    if Config.VOICE_STYLE > 0:
        voice_settings["style"] = Config.VOICE_STYLE
    if Config.VOICE_SPEED != 1.0:
        voice_settings["speed"] = Config.VOICE_SPEED

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{Config.VOICE_ID}",
        headers={
            "xi-api-key": Config.ELEVEN_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": Config.VOICE_MODEL,
            "voice_settings": voice_settings,
        },
        timeout=30,
    )
    r.raise_for_status()
    audio = r.content
    log.info(f"   Voiceover: {len(audio)} bytes")
    return audio


# ══════════════════════════════════════════════════════════════
# PHASE 7: TRANSCRIBE (OpenAI Whisper)
# ══════════════════════════════════════════════════════════════

def transcribe_voiceover(audio_bytes: bytes) -> dict:
    """Transcribe voiceover for word-level timestamps via Whisper."""
    log.info("📝 Phase 7: Transcribing via OpenAI Whisper...")

    r = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {Config.OPENAI_KEY}"},
        files={"file": ("voiceover.mp3", audio_bytes, "audio/mpeg")},
        data={
            "model": "whisper-1",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    words = data.get("words", [])
    log.info(f"   Transcription: {len(words)} words")
    return data

