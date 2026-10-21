"""
Knights Reactor — Pipeline Orchestrator
Phases: Topic → Script → Voice → Transcribe (+ split into beats) → Scenes →
        [GATE: Edit Prompts] → Images → [GATE: Approve Images] → Videos →
        [GATE: Approve Videos] → Upload → Render → Captions → Publish
"""
import os, json, time, re, base64, math

from config import Config, DATA_DIR, log

# Phase functions
from phases.topics import fetch_topic, update_topic
from phases.script import generate_script
from phases.verse import build_verse_topic, build_verse_script
from phases.scenes import scene_engine
from phases.media import generate_images, generate_image_single, generate_videos, generate_video_single, generate_voiceover, transcribe_voiceover
from phases.render import get_s3_client, upload_to_r2, upload_assets, create_srt, render_video
from phases.publish import generate_captions, publish_everywhere
from phases.timing import build_beats, scene_limit

# Re-export for server.py imports
from phases.topics import (
    load_topics, save_topics, add_topic, delete_topic,
    fetch_next_topic, generate_topics_ai, seed_default_topics,
)


class PipelineCancelled(Exception):
    """Raised from inside progress_cb (by the caller, e.g. server.py) to stop
    a run at its next phase boundary — not instantly: a phase already in
    flight (a slow Replicate/Shotstack call) runs to completion first, its
    result is just discarded instead of being checkpointed."""
    pass


# Bumped whenever the phase order changes, so a checkpoint saved by an older
# order is never resumed into the wrong phase.
PIPELINE_VERSION = 2


def run_pipeline(progress_cb=None, resume_from: int = 0, topic_id: str = None,
                 manual_clips: list = None, manual_voiceover: str = None,
                 verse_mode: bool = False) -> dict:
    """Execute the full pipeline with checkpoint/resume and approval gates.

    Phase order (v2): the voiceover is recorded right after the script, so
    the narration can be split into beats and every scene timed to the exact
    line being spoken (phases/timing.py). Cuts land where the voice moves on.

      0 Fetch Topic   1 Generate Script   2 Voiceover   3 Transcribe (+ beats)
      4 Scene Engine  → GATE prompts
      5 Generate Images → GATE images
      6 Generate Videos → GATE videos
      7 Upload Assets   8 Final Render   9 Captions   10 Publish

    resume_from: phase index to resume from (0 = start fresh).
    topic_id: specific topic ID to use (None = next available).
    manual_clips: video URLs to use instead of AI generation (skips 4-6).
    manual_voiceover: voiceover audio URL. With manual_clips this skips all AI
                      generation; Whisper transcribes it and GPT derives the
                      topic/captions from the transcript.
    verse_mode: Verse of the Day — topic and script come straight from a real
                KJV verse (no GPT script); everything after is unchanged.

    Checkpoints are saved after each phase to <brand dir>/pipeline_checkpoint.json.
    """
    _brands_dir = DATA_DIR / "brands"
    _ab_file = DATA_DIR / "active_brand.txt"
    _brand = _ab_file.read_text().strip() if _ab_file.exists() else "knights"
    _bd = _brands_dir / _brand; _bd.mkdir(exist_ok=True)
    CHECKPOINT_FILE = str(_bd / "pipeline_checkpoint.json")
    start = time.time()
    result = {"status": "running", "phases": [], "error": None}

    ckpt = {}
    if resume_from > 0:
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                ckpt = json.load(f)
            log.info(f"♻️  Resuming from phase {resume_from} (checkpoint loaded)")
        except Exception as e:
            log.error(f"No checkpoint found: {e}")
            return {"status": "failed", "error": f"No checkpoint found for resume: {e}", "phases": []}
        if ckpt.get("_version") != PIPELINE_VERSION:
            return {"status": "failed", "phases": [],
                    "error": "This run was started before the app was updated and can't be resumed. "
                             "Press Cancel / Reset, then start a new run."}

    # Manual inputs live in the checkpoint so a resumed run (which is started
    # without them) still uses them — they're consumed only after the voice step.
    if resume_from <= 0:
        ckpt.update({"manual_clips": manual_clips, "manual_voiceover": manual_voiceover})
    manual_clips = manual_clips or ckpt.get("manual_clips")
    manual_voiceover = manual_voiceover or ckpt.get("manual_voiceover")
    full_manual = bool(manual_clips and manual_voiceover)

    def save_checkpoint(phase_idx, data):
        ckpt.update(data)
        ckpt["_last_phase"] = phase_idx
        ckpt["_version"] = PIPELINE_VERSION
        try:
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(ckpt, f)
        except Exception as e:
            log.warning(f"Checkpoint save failed: {e}")

    def notify(idx, name, status):
        if progress_cb:
            try:
                progress_cb(idx, name, status)
            except PipelineCancelled:
                raise
            except Exception:
                pass

    def done(idx, name, status="done"):
        result["phases"].append({"name": name, "status": status})
        notify(idx, name, "done")

    try:
        # ── Phase 0: Fetch topic ────────────────────────────────
        if full_manual and resume_from <= 0:
            # Topic is derived from the voiceover transcript in phase 3.
            notify(0, "Fetch Topic", "running")
            topic = {"id": f"manual_{int(time.time())}", "idea": "Manual Upload", "category": "Manual", "scripture": ""}
            save_checkpoint(0, {"topic": topic})
            done(0, "Fetch Topic", "skipped")
        elif verse_mode and resume_from <= 0:
            notify(0, "Fetch Topic", "running")
            topic = build_verse_topic()
            save_checkpoint(0, {"topic": topic})
            done(0, "Fetch Topic")
        elif resume_from <= 0:
            notify(0, "Fetch Topic", "running")
            topic = fetch_topic(topic_id)
            update_topic(topic["id"], {"Status": "Processing"})
            save_checkpoint(0, {"topic": topic})
            done(0, "Fetch Topic")
        else:
            topic = ckpt["topic"]
            done(0, "Fetch Topic")
        result["topic"] = topic

        # ── Phase 1: Script ─────────────────────────────────────
        if full_manual and resume_from <= 1:
            # Replaced with the real transcript in phase 3.
            notify(1, "Generate Script", "running")
            script = {"hook": "", "build": "", "reveal": "", "command": "", "script_full": "", "tone": "manual"}
            save_checkpoint(1, {"script": script})
            done(1, "Generate Script", "skipped")
        elif resume_from <= 1:
            notify(1, "Generate Script", "running")
            script = build_verse_script(topic) if verse_mode else generate_script(topic)
            save_checkpoint(1, {"script": script})
            done(1, "Generate Script")
        else:
            script = ckpt["script"]
            done(1, "Generate Script")
        result["script"] = script

        # ── Phase 2: Voiceover ──────────────────────────────────
        if resume_from <= 2:
            notify(2, "Voiceover", "running")
            if manual_voiceover:
                log.info(f"🔊 Using manual voiceover: {manual_voiceover[:80]}...")
                import requests as rq
                vo_r = rq.get(manual_voiceover, timeout=120, allow_redirects=True)
                vo_r.raise_for_status()
                audio = vo_r.content
            else:
                audio = generate_voiceover(script)
            save_checkpoint(2, {"audio_b64": base64.b64encode(audio).decode()})
            done(2, "Voiceover")
        else:
            audio = base64.b64decode(ckpt["audio_b64"])
            done(2, "Voiceover")
        result["voiceover_size"] = len(audio)

        # ── Phase 3: Transcribe + split into beats ──────────────
        if resume_from <= 3:
            notify(3, "Transcribe", "running")
            transcription = transcribe_voiceover(audio)
            audio_duration = transcription.get("duration", 0)
            if not audio_duration and transcription.get("words"):
                audio_duration = transcription["words"][-1].get("end", 0)
            log.info(f"   ⏱️  Audio duration: {audio_duration:.1f}s")

            if full_manual and transcription.get("text"):
                topic, script = _derive_from_transcript(transcription["text"], topic, script)
                result["topic"], result["script"] = topic, script

            count, max_scene = _scene_settings()
            if verse_mode:
                # Verses vary from one line to a whole passage, so the clip
                # count follows the reading (as it always has), not Settings.
                count = max(1, math.ceil((audio_duration or 0) / max_scene))
            beats = build_beats(transcription, count, max_scene)
            log.info(f"   🎬 {len(beats)} scenes, cut at the narration's sentences: " +
                     " | ".join(f"{b['length']:.1f}s" for b in beats))
            save_checkpoint(3, {"transcription": transcription, "audio_duration": audio_duration,
                                "beats": beats, "topic": topic, "script": script})
            done(3, "Transcribe")
        else:
            transcription = ckpt["transcription"]
            audio_duration = ckpt.get("audio_duration") or transcription.get("duration", 0)
            beats = ckpt.get("beats") or build_beats(transcription, *_scene_settings())
            done(3, "Transcribe")

        # ── Phases 4-6: scenes, images, videos ─────────────────
        if manual_clips and resume_from <= 6:
            log.info(f"📦 Manual mode: {len(manual_clips)} clips provided, skipping phases 4-6")
            clips = [{"index": i + 1, "image_prompt": "manual upload", "motion_prompt": "manual upload",
                      "image_url": "", "video_url": url} for i, url in enumerate(manual_clips)]
            for ph_idx, ph_name in [(4, "Scene Engine"), (5, "Generate Images"), (6, "Generate Videos")]:
                notify(ph_idx, ph_name, "running")
                done(ph_idx, ph_name, "skipped")
            save_checkpoint(6, {"clips_with_videos": clips, "manual_mode": True})

        elif ckpt.get("manual_mode") and resume_from > 6:
            clips = ckpt["clips_with_videos"]
            for ph_idx, ph_name in [(4, "Scene Engine"), (5, "Generate Images"), (6, "Generate Videos")]:
                done(ph_idx, ph_name, "skipped")

        else:
            # ── Phase 4: Scene engine ──────────────────────────
            if resume_from <= 4:
                notify(4, "Scene Engine", "running")
                clips = scene_engine(script, topic, beats)
                save_checkpoint(4, {"clips": clips})
                done(4, "Scene Engine")

                # ═══ GATE: Prompt editing ═══
                result.update({"status": "awaiting_prompt_approval", "gate": "prompts", "gate_phase": 5,
                               "clips": clips})
                log.info("⏸️  Gate: awaiting prompt approval — edit prompts then resume")
                return result
            clips = ckpt.get("clips_edited") or ckpt.get("clips")
            done(4, "Scene Engine")

            # ── Phase 5: Images ────────────────────────────────
            if resume_from <= 5:
                notify(5, "Generate Images", "running")
                clips = ckpt.get("clips_with_images") if resume_from == 5 and ckpt.get("clips_with_images") else generate_images(clips)
                result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt", "")} for c in clips]
                save_checkpoint(5, {"clips_with_images": clips})
                done(5, "Generate Images")

                # ═══ GATE: Image approval ═══
                # The images are the first frame of every video clip, so a bad
                # one is cheaper to fix here than after video generation.
                result.update({"status": "awaiting_image_approval", "gate": "images", "gate_phase": 6,
                               "clips": clips})
                log.info("⏸️  Gate: awaiting image approval — review/regenerate images then resume")
                return result
            clips = ckpt.get("clips_images_approved") or ckpt.get("clips_with_images")
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt", "")} for c in clips]
            done(5, "Generate Images")

            # ── Phase 6: Videos ────────────────────────────────
            if resume_from <= 6:
                notify(6, "Generate Videos", "running")
                clips = ckpt.get("clips_with_videos") if resume_from == 6 and ckpt.get("clips_with_videos") else generate_videos(clips)
                result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
                save_checkpoint(6, {"clips_with_videos": clips})
                done(6, "Generate Videos")

                # ═══ GATE: Video approval ═══
                result.update({"status": "awaiting_video_approval", "gate": "videos", "gate_phase": 7,
                               "clips": clips})
                log.info("⏸️  Gate: awaiting video approval — review clips then resume")
                return result
            clips = ckpt.get("clips_approved") or ckpt.get("clips_with_videos")
            done(6, "Generate Videos")
        result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]

        # ── Phase 7: Upload to R2 ──────────────────────────────
        if resume_from <= 7:
            notify(7, "Upload Assets", "running")
            folder = re.sub(r'[^a-zA-Z0-9_-]', '_', f"{topic['id']}_{topic['idea'][:30]}")
            srt = create_srt(script["script_full"], transcription)
            urls = upload_assets(folder, clips, audio, srt)
            save_checkpoint(7, {"folder": folder, "urls": urls, "clips_uploaded": clips})
            done(7, "Upload Assets")
        else:
            folder, urls = ckpt["folder"], ckpt["urls"]
            clips = ckpt.get("clips_uploaded", clips)
            done(7, "Upload Assets")

        # ── Phase 8: Final render ──────────────────────────────
        if resume_from <= 8:
            notify(8, "Final Render", "running")
            _fix_webm_clips(clips)
            final_url = render_video(clips, urls["voiceover"], urls["srt"], audio_duration=audio_duration)
            final_r2_url = upload_to_r2(folder, "final.mp4", final_url, "video/mp4")
            save_checkpoint(8, {"final_r2_url": final_r2_url})
            done(8, "Final Render")
        else:
            final_r2_url = ckpt["final_r2_url"]
            done(8, "Final Render")
        result["final_video"] = final_r2_url

        # ── Phase 9: Captions ──────────────────────────────────
        if resume_from <= 9:
            notify(9, "Captions", "running")
            captions = generate_captions(script, topic)
            save_checkpoint(9, {"captions": captions})
            done(9, "Captions")
        else:
            captions = ckpt["captions"]
            done(9, "Captions")
        result["captions"] = captions

        # ── Phase 10: Publish ───────────────────────────────────
        notify(10, "Publish", "running")
        result["publish_status"] = publish_everywhere(final_r2_url, captions, topic)
        done(10, "Publish")

        update_topic(topic["id"], {"Status": "Executed", "Final Video URL": final_r2_url})
        result["status"] = "complete"
        elapsed = round(time.time() - start, 1)
        result["duration"] = f"{elapsed}s"
        log.info(f"\n✅ Pipeline complete in {elapsed}s — {final_r2_url}")
        try: os.remove(CHECKPOINT_FILE)
        except: pass

    except PipelineCancelled:
        result["status"] = "cancelled"
        result["error"] = None
        result["failed_phase"] = ckpt.get("_last_phase", 0) + 1 if ckpt.get("_last_phase") is not None else 0
        log.info(f"\n⏹ Pipeline cancelled at phase {result['failed_phase']}")
        if "topic" in result:
            update_topic(result["topic"]["id"], {"Status": "Cancelled"})

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        result["failed_phase"] = ckpt.get("_last_phase", 0) + 1 if ckpt.get("_last_phase") is not None else 0
        log.error(f"\n❌ Pipeline failed at phase {result['failed_phase']}: {e}")
        if "topic" in result:
            update_topic(result["topic"]["id"], {"Status": "Failed", "Error": str(e)})

    return result


def _scene_settings():
    """(scene count, longest scene) from Settings → Video Generation."""
    return int(Config.CLIP_COUNT), scene_limit(Config.VIDEO_MODEL, Config.CLIP_DURATION)


def _derive_from_transcript(transcript_text: str, topic: dict, script: dict):
    """Full-manual mode: derive a topic title/category/scripture from the
    voiceover transcript, and use the transcript as the script."""
    log.info(f"🧠 Deriving topic from transcript ({len(transcript_text)} chars)...")
    import requests as rq
    derive_prompt = f"""Listen to this voiceover transcript and extract:
1. A short topic/title (5-10 words) that describes what this is about
2. A category from this list: Shocking Revelations, Behind-the-Scenes, Myths Debunked, Deep Dive Analysis, Shocking Reveal
3. Any scripture reference mentioned (or "none")

Transcript: "{transcript_text}"

Return JSON only:
{{"idea": "short topic title", "category": "category name", "scripture": "verse or none"}}"""
    try:
        dr = rq.post("https://api.openai.com/v1/chat/completions", headers={
            "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json",
        }, json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": derive_prompt}],
                 "temperature": 0.3, "max_tokens": 200}, timeout=30)
        dr.raise_for_status()
        raw = dr.json()["choices"][0]["message"]["content"]
        raw = re.sub(r'^```json\s*\n?', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\n?```\s*$', '', raw).strip()
        derived = json.loads(raw)
        topic["idea"] = derived.get("idea", topic["idea"])
        topic["category"] = derived.get("category", topic["category"])
        topic["scripture"] = derived.get("scripture", "")
        log.info(f"   Derived topic: {topic['idea']} [{topic['category']}]")
    except Exception as e:
        log.warning(f"   Topic derivation failed: {e}, using transcript as title")
        topic["idea"] = transcript_text[:80]
    script["script_full"] = transcript_text
    return topic, script


def _fix_webm_clips(clips: list):
    """Some video models return WebM under a .mp4 name, which Shotstack
    rejects — re-upload those under a .webm key before rendering."""
    s3 = get_s3_client()
    import requests as rq
    for clip in clips:
        r2_url = clip.get("r2_url", "")
        if not r2_url or not r2_url.endswith(".mp4"):
            continue
        try:
            pr = rq.get(r2_url, timeout=15, headers={"Range": "bytes=0-63"})
            sample = pr.content[:64] if pr.status_code in (200, 206) else b''
            ct = pr.headers.get("content-type", "").lower()
            is_webm = ((len(sample) >= 4 and sample[:4] == b'\x1a\x45\xdf\xa3') or
                       (len(sample) >= 64 and b'webm' in sample[:64]) or "webm" in ct)
            if is_webm:
                log.warning(f"   Fixing {r2_url} — WebM detected, renaming to .webm")
                full = rq.get(r2_url, timeout=120)
                old_key = r2_url.split(Config.R2_PUBLIC_URL + "/")[-1]
                new_key = old_key.rsplit(".", 1)[0] + ".webm"
                s3.put_object(Bucket=Config.R2_BUCKET, Key=new_key, Body=full.content, ContentType="video/webm")
                clip["r2_url"] = f"{Config.R2_PUBLIC_URL}/{new_key}"
        except Exception as e:
            log.warning(f"   Format check failed for {r2_url}: {e}")


if __name__ == "__main__":
    run_pipeline()
