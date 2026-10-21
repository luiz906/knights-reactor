"""
Knights Reactor — Cost estimate
Approximate Replicate prices for the image and video models in Settings, so
the dashboard can show what each video costs. These are list prices at each
model's default settings (the app doesn't change resolution), checked
October 2026 — Replicate can change them, so everything shown is "≈".
A model not listed here shows as "price not on file" instead of a guess.

Voice (ElevenLabs) and render (Shotstack) come out of those plans' monthly
allowances, so they aren't priced per video.
"""

# Video: dollars per second of clip generated (each model's default resolution).
VIDEO_PER_SECOND = {
    "seedance-1-lite": 0.036,    # 720p — Replicate: $0.09 (480p 5s) … $0.72 (1080p 10s)
    "seedance-2": 0.18,          # 720p
    "kling-v3": 0.224,           # no audio
    "veo-3.1": 0.40,             # with audio (Veo's default)
}

# Images: dollars per image.
IMAGE_EACH = {
    "nano-banana-pro": 0.15,
    "nano-banana": 0.039,        # base Nano Banana (checked after -pro / -2 so those don't match it)
    "flux-1.1-pro": 0.04,
    "flux-schnell": 0.003,
    "flux-dev": 0.025,
    "imagen-4": 0.04,
    "ideogram-v3-quality": 0.09,
    "ideogram-v3-turbo": 0.03,
    "recraft-v3": 0.04,
    "stable-diffusion-3.5-large": 0.065,
}

WRITING = 0.03   # GPT script + scene prompts + captions + Whisper, per video

# Used only to weigh cost when planning scenes for a model not listed above.
_FALLBACK_VIDEO = 0.05
_FALLBACK_IMAGE = 0.04


def _lookup(table: dict, model: str):
    m = (model or "").lower()
    if "nano-banana-2" in m:          # not on file; don't let it match "nano-banana"
        return None
    for key, price in table.items():
        if key in m:
            return price
    return None


def video_price(model: str):
    return _lookup(VIDEO_PER_SECOND, model)


def image_price(model: str):
    return _lookup(IMAGE_EACH, model)


def planning_prices(video_model: str, image_model: str):
    """(per video second, per image) for weighing scene plans — falls back to
    typical prices when a model isn't on file."""
    v = video_price(video_model)
    i = image_price(image_model)
    return (_FALLBACK_VIDEO if v is None else v), (_FALLBACK_IMAGE if i is None else i)


def estimate(clip_seconds: list, video_model: str, image_model: str) -> dict:
    """Cost of one video: one image + one clip per scene, plus writing.
    clip_seconds: the length each clip is generated at."""
    n = len(clip_seconds)
    footage = sum(clip_seconds)
    v, i = video_price(video_model), image_price(image_model)
    video = round(footage * v, 2) if v is not None else None
    images = round(n * i, 2) if i is not None else None
    known = [x for x in (video, images) if x is not None]
    return {
        "images": images, "video": video, "writing": WRITING,
        "footage_seconds": footage,
        "total": round(sum(known) + WRITING, 2),
        "complete": video is not None and images is not None,
        "missing": [name for name, x in (("video", video), ("images", images)) if x is None],
    }
