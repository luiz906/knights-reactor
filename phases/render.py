"""
Knights Reactor — Render & Storage
R2 upload, Shotstack video render, SRT generation.
"""
import time, re
import requests
import boto3
from config import Config, log

def get_s3_client():
    return boto3.client("s3",
        endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY,
        aws_secret_access_key=Config.R2_SECRET_KEY,
        region_name="auto",
    )


def upload_to_r2(folder: str, filename: str, data, content_type: str) -> str:
    """Upload a file to R2, return public URL."""
    s3 = get_s3_client()
    key = f"{folder}/{filename}"

    if isinstance(data, bytes):
        # Check if bytes are actually webm when named mp4
        if filename.endswith(".mp4") and data[:4] == b'\x1a\x45\xdf\xa3':
            filename = filename.rsplit(".", 1)[0] + ".webm"
            content_type = "video/webm"
            key = f"{folder}/{filename}"
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    elif isinstance(data, str) and data.startswith("http"):
        # URL — download first, detect real format
        r = requests.get(data, timeout=120)
        r.raise_for_status()
        body = r.content
        hdr_ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
        src_ext = data.rsplit(".", 1)[-1].split("?")[0].lower() if "." in data else ""

        # Detect format: source URL ext → response header → magic bytes
        real_ct = content_type
        is_webm = False

        # 1) Source URL extension (Replicate URLs often end in .webm)
        if src_ext == "webm" or "webm" in hdr_ct:
            is_webm = True
        # 2) Magic bytes: WebM/MKV (EBML header)
        elif len(body) >= 4 and body[:4] == b'\x1a\x45\xdf\xa3':
            is_webm = True
        # 3) Extended WebM detection: check for 'webm' doctype in first 64 bytes
        elif len(body) >= 64 and b'webm' in body[:64]:
            is_webm = True

        if is_webm:
            real_ct = "video/webm"
            key = key.rsplit(".", 1)[0] + ".webm"
        elif len(body) >= 8 and (body[4:8] == b'ftyp' or body[:4] in (b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c', b'\x00\x00\x00\x20')):
            real_ct = "video/mp4"
        elif len(body) >= 3 and (body[:3] == b'ID3' or body[:2] == b'\xff\xfb' or body[:2] == b'\xff\xf3'):
            real_ct = "audio/mpeg"
        elif "mp4" in hdr_ct:
            real_ct = "video/mp4"
        elif "mpeg" in hdr_ct or "mp3" in hdr_ct:
            real_ct = "audio/mpeg"

        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=body, ContentType=real_ct)
        log.info(f"   R2 upload: {key} ({real_ct}, {len(body)//1024}KB) [src_ext={src_ext}, hdr={hdr_ct}]")
    elif isinstance(data, str):
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data.encode(), ContentType=content_type)

    url = f"{Config.R2_PUBLIC_URL}/{key}"
    return url


def upload_assets(folder: str, clips: list, audio: bytes, srt: str) -> dict:
    """Upload all assets to R2."""
    log.info("☁️  Phase 8: Uploading assets to R2...")

    urls = {"clips": []}

    for clip in clips:
        url = upload_to_r2(folder, f"clip_{clip['index']}.mp4", clip["video_url"], "video/mp4")
        clip["r2_url"] = url
        urls["clips"].append(url)
        log.info(f"   clip_{clip['index']}.mp4 ✓")

    urls["voiceover"] = upload_to_r2(folder, "voiceover.mp3", audio, "audio/mpeg")
    log.info("   voiceover.mp3 ✓")

    urls["srt"] = upload_to_r2(folder, "subtitles.srt", srt, "text/plain")
    log.info("   subtitles.srt ✓")

    return urls


# ══════════════════════════════════════════════════════════════
# PHASE 9: FINAL RENDER (Shotstack)
# ══════════════════════════════════════════════════════════════

def caption_case(text: str, is_first_chunk: bool = False) -> str:
    """Lowercase captions. Only the very first letter of the entire text
    and proper nouns are capitalized. Sentence starts are NOT capitalized.
    Example: 'the battle rages within. you fight not against flesh but spirit.'
    Only the first chunk gets a capital first letter.
    """
    PROPER = {
        "god", "jesus", "christ", "lord", "holy", "spirit", "bible", "scripture",
        "father", "son", "ephesians", "psalms", "proverbs", "romans", "matthew",
        "mark", "luke", "john", "genesis", "revelation", "isaiah", "david",
        "moses", "paul", "peter", "abraham", "solomon", "israel", "satan",
        "heaven", "hell", "king", "knight", "knights",
    }
    text = text.lower()
    words = text.split()
    for i, w in enumerate(words):
        # First word of first chunk only
        if i == 0 and is_first_chunk:
            words[i] = w[0].upper() + w[1:] if w else w
        # Proper nouns
        elif w.rstrip('.,!?;:\'\"') in PROPER:
            clean = w.rstrip('.,!?;:\'\"')
            trail = w[len(clean):]
            words[i] = clean.capitalize() + trail
        # "I" standalone
        elif w in ('i', "i'm", "i've", "i'll", "i'd"):
            words[i] = w[0].upper() + w[1:]
    return " ".join(words)


def create_srt(script_text: str, transcription: dict = None) -> str:
    """Create SRT from Whisper word timestamps (3-4 words per cue) or fallback."""
    if not transcription or "words" not in transcription:
        return f"1\n00:00:00,000 --> 00:59:59,000\n{caption_case(script_text, is_first_chunk=True)}\n"

    words = transcription["words"]
    if not words:
        return f"1\n00:00:00,000 --> 00:59:59,000\n{caption_case(script_text, is_first_chunk=True)}\n"

    # Group words into 3-4 word chunks for readable captions
    srt_lines = []
    chunk_size = 4

    def fmt(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    idx = 1
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        start_t = chunk[0].get("start", 0)
        end_t = chunk[-1].get("end", start_t + 1)
        text_chunk = " ".join(w.get("word", "") for w in chunk).strip()
        if not text_chunk:
            continue
        text_chunk = caption_case(text_chunk, is_first_chunk=(i == 0))
        srt_lines.append(f"{idx}\n{fmt(start_t)} --> {fmt(end_t)}\n{text_chunk}\n")
        idx += 1

    return "\n".join(srt_lines) if srt_lines else f"1\n00:00:00,000 --> 00:59:59,000\n{caption_case(script_text, is_first_chunk=True)}\n"


def render_video(clips: list, voiceover_url: str, srt_url: str, audio_duration: float = 0) -> str:
    """Render final video via Shotstack. Returns download URL.
    
    audio_duration: actual voiceover length in seconds (from Whisper).
                    If provided, the timeline auto-adjusts so audio never gets cut off.
    """
    ss_env = getattr(Config, 'SHOTSTACK_ENV', 'v1')
    ss_base = f"https://api.shotstack.io/edit/{ss_env}"
    log.info(f"🎞️  Phase 9: Rendering final video via Shotstack ({ss_env}) | {Config.RENDER_RES}p {Config.RENDER_ASPECT} {Config.RENDER_FPS}fps")

    # Build video clips timeline
    video_clips = []
    cursor = 0.0
    for clip in clips:
        dur = Config.CLIP_DURATION
        video_clips.append({
            "asset": {"type": "video", "src": clip["r2_url"], "volume": 0, "transcode": True},
            "start": round(cursor, 3),
            "length": dur,
            "fit": "cover",
        })
        cursor += dur

    # CTA clip at end
    cta_dur = 0
    if getattr(Config, 'CTA_ENABLED', False) and getattr(Config, 'CTA_URL', ''):
        cta_dur = getattr(Config, 'CTA_DURATION', 4.0)
        cta_url = Config.CTA_URL
        # Re-upload CTA to working bucket with correct format detection
        try:
            cta_r2_url = upload_to_r2("_assets", "cta_clip.mp4", cta_url, "video/mp4")
            cta_url = cta_r2_url
            log.info(f"   CTA re-uploaded: {cta_url}")
        except Exception as e:
            log.warning(f"   CTA re-upload failed: {e}, using original URL")
        # Detect type from final URL extension
        cta_type = "video" if cta_url.lower().endswith(('.mp4','.webm','.mov')) else "image"
        cta_asset = {"type": cta_type, "src": cta_url}
        if cta_type == "video":
            cta_asset["volume"] = 0
            cta_asset["transcode"] = True
        video_clips.append({
            "asset": cta_asset,
            "start": round(cursor, 3),
            "length": cta_dur,
            "fit": "cover",
        })
        cursor += cta_dur
        log.info(f"   CTA clip: {cta_dur}s from {cta_url}")

    total_dur = round(cursor, 3)

    # ── AUDIO-DRIVEN TIMING ──────────────────────────────────
    # If we know the real audio length, adjust video timeline to match.
    # Audio is the source of truth — video must be long enough to cover it.
    if audio_duration and audio_duration > 0:
        # Audio needs: voiceover + CTA silence (CTA plays after voice ends)
        audio_needs = round(audio_duration + cta_dur + 1.0, 3)  # +1s padding
        clip_total = total_dur

        log.info(f"   ⏱️  TIMING: audio={audio_duration:.1f}s | clips={clip_total:.1f}s | cta={cta_dur:.1f}s | need={audio_needs:.1f}s")

        if audio_needs > clip_total:
            # Audio is longer than video — extend last content clip (not CTA)
            gap = round(audio_needs - clip_total, 3)
            # Find last non-CTA clip
            last_content_idx = len(video_clips) - 1
            if cta_dur > 0:
                last_content_idx = len(video_clips) - 2

            if last_content_idx >= 0:
                old_len = video_clips[last_content_idx]["length"]
                new_len = round(old_len + gap, 3)
                video_clips[last_content_idx]["length"] = new_len
                log.info(f"   ⏱️  EXTENDED clip {last_content_idx+1}: {old_len}s → {new_len}s (+{gap}s)")

                # Recalculate CTA start if present
                if cta_dur > 0 and last_content_idx + 1 < len(video_clips):
                    new_cta_start = round(video_clips[last_content_idx]["start"] + new_len, 3)
                    video_clips[last_content_idx + 1]["start"] = new_cta_start

                total_dur = round(audio_needs, 3)
            else:
                log.warning(f"   ⏱️  No content clip to extend!")

        elif clip_total > audio_needs + 5:
            # Video is way longer than audio — trim last content clip
            excess = round(clip_total - audio_needs, 3)
            last_content_idx = len(video_clips) - 1
            if cta_dur > 0:
                last_content_idx = len(video_clips) - 2

            if last_content_idx >= 0:
                old_len = video_clips[last_content_idx]["length"]
                new_len = max(round(old_len - excess, 3), 3.0)  # min 3s
                actual_trim = round(old_len - new_len, 3)
                if actual_trim > 0:
                    video_clips[last_content_idx]["length"] = new_len
                    log.info(f"   ⏱️  TRIMMED clip {last_content_idx+1}: {old_len}s → {new_len}s (-{actual_trim}s)")

                    # Recalculate CTA start
                    if cta_dur > 0 and last_content_idx + 1 < len(video_clips):
                        new_cta_start = round(video_clips[last_content_idx]["start"] + new_len, 3)
                        video_clips[last_content_idx + 1]["start"] = new_cta_start

                    total_dur = round(total_dur - actual_trim, 3)

        else:
            log.info(f"   ⏱️  TIMING OK — within tolerance")
    else:
        log.info(f"   ⏱️  No audio duration provided — using fixed clip timing ({total_dur}s)")

    caption_track = None
    # Subtitle overlay — built first, inserted as top (front) layer
    # Position: lower-center of screen (above bottom safe zone)
    captions_on = getattr(Config, "CAPTIONS_ENABLED", True)
    if captions_on in (False, "false", "False", 0, "0", "off"):
        captions_on = False
    if srt_url and captions_on:
        caption_track = {"clips": [{
            "asset": {
                "type": "caption",
                "src": srt_url,
                "background": {
                    "color": "#000000",
                    "padding": 50,
                    "borderRadius": 18,
                    "opacity": 0.6,
                },
                "font": {
                    "color": "#ffffff",
                    "family": "Montserrat ExtraBold",
                    "size": 35,
                    "lineHeight": 1.5,
                },
            },
            "start": 0, "length": "end",
            "position": "bottom",
            "offset": {"x": 0, "y": 0.18},
        }]}
        log.info(f"   Subtitles: {srt_url}")

    tracks = []

    # Captions on top (front layer)
    if caption_track:
        tracks.append(caption_track)

    # Logo overlay (conditional)
    logo_on = getattr(Config, "LOGO_ENABLED", True)
    if logo_on in (False, "false", "False", 0, "0", "off"):
        logo_on = False
    if logo_on and Config.LOGO_URL:
        logo_url = Config.LOGO_URL
        # Re-upload logo to our working R2 bucket to guarantee Shotstack can access it
        try:
            log.info(f"   Fetching logo from {logo_url}...")
            lr = requests.get(logo_url, timeout=15)
            lr.raise_for_status()
            # Detect format from content-type or magic bytes
            ct = lr.headers.get("content-type", "image/png").split(";")[0].strip()
            body = lr.content
            ext = "png"
            if body[:4] == b'\x89PNG':
                ct = "image/png"; ext = "png"
            elif body[:2] == b'\xff\xd8':
                ct = "image/jpeg"; ext = "jpg"
            elif body[:4] == b'RIFF' and body[8:12] == b'WEBP':
                ct = "image/webp"; ext = "webp"
            s3 = get_s3_client()
            logo_key = f"_assets/logo.{ext}"
            s3.put_object(Bucket=Config.R2_BUCKET, Key=logo_key, Body=body, ContentType=ct)
            logo_url = f"{Config.R2_PUBLIC_URL}/{logo_key}"
            log.info(f"   Logo re-uploaded to {logo_url} ({ct}, {len(body)//1024}KB)")
        except Exception as e:
            log.warning(f"   Logo fetch/upload failed: {e}, skipping logo overlay")
            logo_url = None

        if logo_url:
            # Offset map for positions
            offsets = {
                "topRight": {"x": -0.03, "y": 0.03},
                "topLeft": {"x": 0.03, "y": 0.03},
                "bottomRight": {"x": -0.03, "y": -0.03},
                "bottomLeft": {"x": 0.03, "y": -0.03},
                "center": {"x": 0, "y": 0},
            }
            tracks.append({"clips": [{
                "asset": {"type": "image", "src": logo_url},
                "start": 0, "length": total_dur,
                "position": Config.LOGO_POSITION,
                "offset": offsets.get(Config.LOGO_POSITION, {"x": -0.05, "y": 0.05}),
                "scale": 0.08, "opacity": Config.LOGO_OPACITY,
                "fit": "none",
            }]})

    # Video clips
    tracks.append({"clips": video_clips})

    # Audio
    tracks.append({"clips": [{
        "asset": {"type": "audio", "src": voiceover_url},
        "start": 0, "length": total_dur,
    }]})


    timeline = {
        "tracks": tracks,
        "background": Config.RENDER_BG,
    }

    payload = {
        "timeline": timeline,
        "output": {
            "format": "mp4",
            "resolution": Config.RENDER_RES,
            "aspectRatio": Config.RENDER_ASPECT,
            "fps": Config.RENDER_FPS,
        },
    }

    # Pre-flight: probe all asset URLs to catch format issues early
    all_asset_urls = []
    for track in tracks:
        for clip in track.get("clips", []):
            asset = clip.get("asset", {})
            src = asset.get("src", "")
            if src:
                all_asset_urls.append((asset.get("type", "?"), src))

    for atype, aurl in all_asset_urls:
        if atype == "caption":
            log.info(f"   Caption SRT: {aurl.split('/')[-1]} (skip probe)")
            continue
        try:
            encoded_url = requests.utils.quote(aurl, safe='')
            probe_r = requests.get(f"{ss_base}/probe/{aurl}",
                                   headers={"x-api-key": Config.SHOTSTACK_KEY}, timeout=15)
            if probe_r.status_code == 200:
                probe_data = probe_r.json().get("response", {}).get("metadata", {})
                streams = probe_data.get("streams", [])
                fmt = probe_data.get("format", {}).get("format_name", "?")
                log.info(f"   Probe OK: {atype} — {fmt} — {aurl.split('/')[-1]}")
            else:
                log.warning(f"   Probe FAIL ({probe_r.status_code}): {atype} — {aurl}")
                log.warning(f"   Response: {probe_r.text[:300]}")
        except Exception as e:
            log.warning(f"   Probe error for {aurl}: {e}")

    r = requests.post(f"{ss_base}/render", headers={
        "x-api-key": Config.SHOTSTACK_KEY,
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    if r.status_code >= 400:
        log.error(f"   Shotstack error {r.status_code}: {r.text[:1000]}")
        # Dump the payload for debugging
        try:
            payload_dump = json.dumps(payload, indent=2)
            log.error(f"   Shotstack payload:\n{payload_dump[:3000]}")
        except: pass
    r.raise_for_status()
    job_id = r.json()["response"]["id"]
    log.info(f"   Render job: {job_id}")

    # Poll for completion
    for _ in range(60):
        time.sleep(15)
        r = requests.get(f"{ss_base}/render/{job_id}", headers={
            "x-api-key": Config.SHOTSTACK_KEY,
        })
        r.raise_for_status()
        data = r.json()["response"]
        status = data.get("status")

        if status == "done":
            download_url = data["url"]
            log.info(f"   Render complete ✓")
            return download_url
        elif status == "failed":
            raise RuntimeError(f"Shotstack render failed: {data}")

    raise TimeoutError("Shotstack render timed out")

