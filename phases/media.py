"""
Knights Reactor — Media Generation
Replicate (images, videos), ElevenLabs (voiceover), Whisper (transcribe).
"""
import time, re
import requests
from config import Config, log
from phases.timing import clip_duration, DEFAULT_CLIP
from phases.model_info import model_inputs, pick_aspect
from phases.scenes import figure_supports_reference

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


_SAME_CHARACTER = ("\nKeep the character exactly as in the reference image — same armor, helm, cape, "
                   "face and build. Use the reference only for the character; the setting, pose, "
                   "lighting and camera follow this description.")


def _image_input(clip: dict, model: str, ref: str = "") -> dict:
    """Replicate input for one scene image. Built from the model's own schema
    when Replicate can describe it (any model), else from built-in guesses.
    ref: an image the character must match (a cast photo or scene 1)."""
    quality = getattr(Config, 'IMAGE_QUALITY', 'high')
    params = {"prompt": clip["image_prompt"] + (_SAME_CHARACTER if ref else "")}
    info = model_inputs(model)
    if info is not None:
        ar = pick_aspect(info, Config.RENDER_ASPECT)
        if ar:
            params["aspect_ratio"] = ar
        if "quality" in info["inputs"] and quality in info["enums"].get("quality", [quality]):
            params["quality"] = quality
        if ref and info["ref_field"]:
            params[info["ref_field"]] = [ref] if info["ref_is_list"] else ref
        return params

    # Built-in guesses (Replicate unreachable)
    if ref and figure_supports_reference(model):
        params["image_input"] = [ref]
    if "gpt-image" in model:
        # GPT Image only accepts 1:1 / 3:2 / 2:3 — 2:3 is the closest portrait.
        params["aspect_ratio"] = "2:3"
        params["quality"] = quality
    elif any(k in model for k in ("grok-imagine", "nano-banana", "seedream", "ideogram", "recraft", "imagen")):
        params["aspect_ratio"] = "9:16"
    else:
        params["aspect_ratio"] = "9:16"
        params["quality"] = quality
    return params


def _character_ref(clip: dict, model: str) -> str:
    """The image this scene's character must match — the cast photo if one is
    set, else scene 1's image — if the image model can take a reference."""
    ref = (clip.get("ref_image") or clip.get("character_ref") or "").strip()
    if ref and not figure_supports_reference(model):
        log.warning(f"   ⚠️  Clip {clip.get('index','')}: {model} can't take a reference image — "
                    f"the character may look different from scene to scene.")
        return ""
    return ref


def generate_images(clips: list) -> list:
    """Generate the scene images. So the character looks the same in every
    scene, scene 1 is made first and used as the reference for the rest
    (when no cast photo is set and the model can take a reference)."""
    model = Config.IMAGE_MODEL
    log.info(f"🖼️  Phase 4: Generating images via Replicate ({model}) | Aspect: {Config.RENDER_ASPECT}")

    rest = clips
    if len(clips) > 1 and not any(c.get("ref_image") for c in clips) and figure_supports_reference(model):
        first = clips[0]
        first["image_url"] = replicate_poll(replicate_create(model, _image_input(first, model)))
        log.info(f"   Clip {first['index']}: image ready ✓ — the reference for the other scenes")
        for c in clips[1:]:
            c["character_ref"] = first["image_url"]
        rest = clips[1:]

    for clip in rest:
        clip["image_poll_url"] = replicate_create(model, _image_input(clip, model, _character_ref(clip, model)))
        log.info(f"   Clip {clip['index']}: submitted")
        time.sleep(8)  # Avoid 429 rate limits

    for clip in rest:
        clip["image_url"] = replicate_poll(clip["image_poll_url"])
        log.info(f"   Clip {clip['index']}: image ready ✓")

    return clips


# ══════════════════════════════════════════════════════════════
# PHASE 4b: REGENERATE SINGLE IMAGE
# ══════════════════════════════════════════════════════════════

def generate_image_single(clip: dict) -> dict:
    """Regenerate a single image for one clip. Used by the image approval
    gate — lets one image be redone (after editing its prompt, or just to
    reroll) without regenerating the whole batch."""
    model = Config.IMAGE_MODEL
    log.info(f"🖼️  Regenerating image for clip {clip.get('index','')} via {model}...")
    url = replicate_create(model, _image_input(clip, model, _character_ref(clip, model)))
    clip["image_poll_url"] = url
    clip["image_url"] = replicate_poll(url)
    log.info(f"   Clip {clip.get('index','')}: image regenerated ✓")
    return clip


# ══════════════════════════════════════════════════════════════
# PHASE 5: GENERATE VIDEOS (Replicate)
# ══════════════════════════════════════════════════════════════

def _video_input(clip: dict, model: str) -> dict:
    """Replicate input for one clip: the scene image as the start frame, the
    motion prompt, the video's aspect ratio, and the shortest clip length
    that covers the scene. Built from the model's own schema when Replicate
    can describe it (any model), else from built-in guesses."""
    dur = clip_duration(clip.get("length") or DEFAULT_CLIP, model)
    info = model_inputs(model)
    if info is not None:
        params = {info["image_field"] or "image": clip["image_url"], "prompt": clip["motion_prompt"]}
        ar = pick_aspect(info, Config.RENDER_ASPECT)
        if ar:
            params["aspect_ratio"] = ar
        if dur:
            params["duration"] = dur
        return params

    # Built-in guesses (Replicate unreachable)
    m = model.lower()
    if "grok-imagine" in m:
        params = {"image_url": clip["image_url"], "prompt": clip["motion_prompt"], "mode": "normal"}
    elif "minimax" in m or "hailuo" in m:
        params = {"first_frame_image": clip["image_url"], "prompt": clip["motion_prompt"]}
    elif "kling" in m or "luma" in m or "ray-" in m:
        params = {"start_image": clip["image_url"], "prompt": clip["motion_prompt"]}
    else:
        params = {"image": clip["image_url"], "prompt": clip["motion_prompt"]}
    if "seedance" in m or "wan" in m:
        params["aspect_ratio"] = "9:16"
    if dur:
        params["duration"] = dur
    return params


def generate_videos(clips: list) -> list:
    """Animate each scene image into a clip."""
    model = Config.VIDEO_MODEL
    log.info(f"🎥 Phase 5: Generating videos via {model}...")

    for clip in clips:
        clip["video_poll_url"] = replicate_create(model, _video_input(clip, model))
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
    url = replicate_create(model, _video_input(clip, model))
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
            "timestamp_granularities[]": ["word", "segment"],  # segments = sentence ends, used to cut scenes on pauses
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    words = data.get("words", [])
    log.info(f"   Transcription: {len(words)} words")
    return data

