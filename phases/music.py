"""Optional ElevenLabs instrumental soundtrack for the Knights Reactor pipeline.
This module uses the same API key as ElevenLabs narration. No music is generated
unless MUSIC_ENABLED is explicitly enabled in settings.
"""
import requests
from config import Config, log


def build_music_prompt(script: dict, clips: list) -> str:
    """Build one continuous score whose three sections follow narrative beats."""
    override = str(getattr(Config, "MUSIC_PROMPT_OVERRIDE", "") or "").strip()
    if override:
        return override[:4100]
    style = str(getattr(Config, "MUSIC_STYLE", "") or "").strip()
    lines = [str(c.get("line", "")).strip() for c in clips if c.get("line")]
    arc = " / ".join(lines[:8])
    topic = str(script.get("hook", "") or script.get("script_full", ""))[:300]
    return (
        f"Create a single instrumental film score. Musical style: {style}. "
        f"Story: {topic}. The visual emotional beats are: {arc}. "
        "Begin with tension and uncertainty, develop intimate moral conflict, "
        "and resolve with restrained hope and reverence. Smooth transitions, "
        "one continuous composition with a gentle ending. The soundtrack must "
        "sit quietly beneath a low male narration. No words, voices, singing, "
        "choir, narration, dialogue, or environmental sound effects."
    )[:4100]


def generate_music(script: dict, clips: list, duration_seconds: float, prompt_override: str = "") -> bytes:
    """Generate a single MP3; raise on failure so a paid operation is never silent."""
    if not Config.ELEVEN_KEY:
        raise RuntimeError("ElevenLabs API key is missing (required for Music)")
    # Eleven Music accepts 3-600 seconds in milliseconds, with text-prompt mode.
    milliseconds = max(3000, min(600000, round(float(duration_seconds) * 1000)))
    payload = {
        "prompt": (prompt_override.strip()[:4100] if prompt_override and prompt_override.strip() else build_music_prompt(script, clips)),
        "music_length_ms": milliseconds,
        "model_id": getattr(Config, "MUSIC_MODEL", "music_v2_5"),
        "force_instrumental": True,
    }
    r = requests.post(
        "https://api.elevenlabs.io/v1/music",
        headers={"xi-api-key": Config.ELEVEN_KEY, "Content-Type": "application/json"},
        params={"output_format": "mp3_48000_192"},
        json=payload,
        timeout=240,
    )
    if not r.ok:
        raise RuntimeError(f"ElevenLabs Music failed (HTTP {r.status_code}): {r.text[:300]}")
    if not r.content or not r.headers.get("content-type", "").lower().startswith("audio/"):
        raise RuntimeError("ElevenLabs Music did not return an audio file")
    log.info("🎵 Generated independent instrumental soundtrack (%s bytes)", len(r.content))
    return r.content
