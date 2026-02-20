"""
Knights Reactor — Pipeline Orchestrator v2
Phases: Topic → Script → Scenes → [GATE: Edit Prompts] → Images → Videos →
        [GATE: Approve Videos] → Voice → Transcribe → Upload → Render → Captions → Publish
"""
import os, json, time, re, base64

from config import Config, DATA_DIR, log

# Phase functions
from phases.topics import fetch_topic, update_airtable
from phases.script import generate_script
from phases.scenes import scene_engine
from phases.media import generate_images, generate_videos, generate_video_single, generate_voiceover, transcribe_voiceover
from phases.render import get_s3_client, upload_to_r2, upload_assets, create_srt, render_video
from phases.publish import generate_captions, publish_everywhere

# Re-export for server.py imports
from phases.topics import (
    load_topics, save_topics, add_topic, delete_topic,
    fetch_next_topic, generate_topics_ai, seed_default_topics,
)


def run_pipeline(progress_cb=None, resume_from: int = 0, topic_id: str = None) -> dict:
    """Execute the full pipeline with checkpoint/resume and approval gates.

    resume_from: Phase index to resume from (0 = start fresh).
    topic_id: Specific topic ID to use (None = next available).

    Gates:
      - After phase 2 (Scene Engine): pauses for prompt editing (gate="prompts")
      - After phase 4 (Generate Videos): pauses for video approval (gate="videos")

    Checkpoints saved after each phase to DATA_DIR/pipeline_checkpoint.json
    """
    CHECKPOINT_FILE = str(DATA_DIR / "pipeline_checkpoint.json")
    start = time.time()
    result = {"status": "running", "phases": [], "error": None}

    # Load checkpoint if resuming
    ckpt = {}
    if resume_from > 0:
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                ckpt = json.load(f)
            log.info(f"♻️  Resuming from phase {resume_from} (checkpoint loaded)")
        except Exception as e:
            log.error(f"No checkpoint found: {e}")
            return {"status": "failed", "error": f"No checkpoint found for resume: {e}", "phases": []}

    def save_checkpoint(phase_idx, data):
        ckpt.update(data)
        ckpt["_last_phase"] = phase_idx
        try:
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(ckpt, f)
        except Exception as e:
            log.warning(f"Checkpoint save failed: {e}")

    def notify(idx, name, status):
        if progress_cb:
            try: progress_cb(idx, name, status)
            except: pass

    try:
        # ── Phase 0: Fetch topic ────────────────────────────────
        if resume_from <= 0:
            notify(0, "Fetch Topic", "running")
            topic = fetch_topic(topic_id)
            update_airtable(topic["id"], {"Status": "Processing"})
            result["phases"].append({"name": "Fetch Topic", "status": "done"})
            result["topic"] = topic
            save_checkpoint(0, {"topic": topic})
            notify(0, "Fetch Topic", "done")
        else:
            topic = ckpt["topic"]
            result["topic"] = topic
            result["phases"].append({"name": "Fetch Topic", "status": "done"})
            notify(0, "Fetch Topic", "done")

        # ── Phase 1: Generate script ────────────────────────────
        if resume_from <= 1:
            notify(1, "Generate Script", "running")
            script = generate_script(topic) if resume_from < 1 else ckpt.get("script") or generate_script(topic)
            result["phases"].append({"name": "Generate Script", "status": "done"})
            result["script"] = script
            save_checkpoint(1, {"script": script})
            notify(1, "Generate Script", "done")
        else:
            script = ckpt["script"]
            result["script"] = script
            result["phases"].append({"name": "Generate Script", "status": "done"})
            notify(1, "Generate Script", "done")

        # ── Phase 2: Scene engine ───────────────────────────────
        if resume_from <= 2:
            notify(2, "Scene Engine", "running")
            clips = scene_engine(script, topic) if resume_from < 2 else ckpt.get("clips") or scene_engine(script, topic)
            result["phases"].append({"name": "Scene Engine", "status": "done"})
            save_checkpoint(2, {"clips": clips})
            notify(2, "Scene Engine", "done")

            # ═══ GATE 1: Prompt Editing ═══
            result["status"] = "awaiting_prompt_approval"
            result["gate"] = "prompts"
            result["gate_phase"] = 3
            result["clips"] = clips
            result["script"] = script
            log.info("⏸️  Gate 1: Awaiting prompt approval — edit prompts then resume")
            return result
        else:
            clips = ckpt.get("clips_edited") or ckpt.get("clips")
            result["phases"].append({"name": "Scene Engine", "status": "done"})
            notify(2, "Scene Engine", "done")

        # ── Phase 3: Generate images ────────────────────────────
        if resume_from <= 3:
            notify(3, "Generate Images", "running")
            clips = generate_images(clips) if resume_from < 3 else (ckpt.get("clips_with_images") or generate_images(clips))
            result["phases"].append({"name": "Generate Images", "status": "done"})
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt","")} for c in clips]
            save_checkpoint(3, {"clips_with_images": clips})
            notify(3, "Generate Images", "done")
        else:
            clips = ckpt["clips_with_images"]
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt","")} for c in clips]
            result["phases"].append({"name": "Generate Images", "status": "done"})
            notify(3, "Generate Images", "done")

        # ── Phase 4: Generate videos ────────────────────────────
        if resume_from <= 4:
            notify(4, "Generate Videos", "running")
            clips = generate_videos(clips) if resume_from < 4 else (ckpt.get("clips_with_videos") or generate_videos(clips))
            result["phases"].append({"name": "Generate Videos", "status": "done"})
            result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
            save_checkpoint(4, {"clips_with_videos": clips})
            notify(4, "Generate Videos", "done")

            # ═══ GATE 2: Video Approval ═══
            result["status"] = "awaiting_video_approval"
            result["gate"] = "videos"
            result["gate_phase"] = 5
            result["clips"] = clips
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt","")} for c in clips]
            result["script"] = script
            log.info("⏸️  Gate 2: Awaiting video approval — review clips then resume")
            return result
        else:
            clips = ckpt.get("clips_approved") or ckpt.get("clips_with_videos")
            result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
            result["phases"].append({"name": "Generate Videos", "status": "done"})
            notify(4, "Generate Videos", "done")

        # ── Phase 5: Voiceover ──────────────────────────────────
        if resume_from <= 5:
            notify(5, "Voiceover", "running")
            audio = generate_voiceover(script)
            result["phases"].append({"name": "Voiceover", "status": "done"})
            result["voiceover_size"] = len(audio)
            save_checkpoint(5, {"audio_b64": base64.b64encode(audio).decode()})
            notify(5, "Voiceover", "done")
        else:
            audio = base64.b64decode(ckpt["audio_b64"])
            result["voiceover_size"] = len(audio)
            result["phases"].append({"name": "Voiceover", "status": "done"})
            notify(5, "Voiceover", "done")

        # ── Phase 6: Transcribe ─────────────────────────────────
        if resume_from <= 6:
            notify(6, "Transcribe", "running")
            transcription = transcribe_voiceover(audio)
            result["phases"].append({"name": "Transcribe", "status": "done"})
            save_checkpoint(6, {"transcription": transcription})
            notify(6, "Transcribe", "done")
        else:
            transcription = ckpt["transcription"]
            result["phases"].append({"name": "Transcribe", "status": "done"})
            notify(6, "Transcribe", "done")

        # ── Phase 7: Upload to R2 ──────────────────────────────
        if resume_from <= 7:
            notify(7, "Upload Assets", "running")
            folder = f"{topic['id']}_{topic['idea'][:30]}"
            folder = re.sub(r'[^a-zA-Z0-9_-]', '_', folder)
            srt = create_srt(script["script_full"])
            urls = upload_assets(folder, clips, audio, srt)
            result["phases"].append({"name": "Upload to R2", "status": "done"})
            save_checkpoint(7, {"folder": folder, "urls": urls, "clips_uploaded": clips})
            notify(7, "Upload Assets", "done")
        else:
            folder = ckpt["folder"]
            urls = ckpt["urls"]
            clips = ckpt.get("clips_uploaded", clips)
            result["phases"].append({"name": "Upload to R2", "status": "done"})
            notify(7, "Upload Assets", "done")

        # ── Phase 8: Final render ──────────────────────────────
        if resume_from <= 8:
            notify(8, "Final Render", "running")
            # Fix-up: ensure R2 clips have correct format/extension
            s3 = get_s3_client()
            for clip in clips:
                r2_url = clip.get("r2_url", "")
                if not r2_url or not r2_url.endswith(".mp4"):
                    continue
                try:
                    import requests as rq
                    pr = rq.get(r2_url, timeout=15, headers={"Range": "bytes=0-63"})
                    if pr.status_code in (200, 206):
                        sample = pr.content[:64]
                    else:
                        sample = b''
                    ct = pr.headers.get("content-type", "").lower()
                    is_webm = (
                        (len(sample) >= 4 and sample[:4] == b'\x1a\x45\xdf\xa3') or
                        (len(sample) >= 64 and b'webm' in sample[:64]) or
                        "webm" in ct
                    )
                    log.info(f"   Format check {r2_url.split('/')[-1]}: ct={ct}, magic={sample[:4].hex() if sample else '?'}, webm={is_webm}")
                    if is_webm:
                        log.warning(f"   Fixing {r2_url} — WebM detected, renaming to .webm")
                        full = rq.get(r2_url, timeout=120)
                        old_key = r2_url.split(Config.R2_PUBLIC_URL + "/")[-1]
                        new_key = old_key.rsplit(".", 1)[0] + ".webm"
                        s3.put_object(Bucket=Config.R2_BUCKET, Key=new_key, Body=full.content, ContentType="video/webm")
                        clip["r2_url"] = f"{Config.R2_PUBLIC_URL}/{new_key}"
                        log.info(f"   Fixed: {clip['r2_url']}")
                except Exception as e:
                    log.warning(f"   Format check failed for {r2_url}: {e}")

            final_url = render_video(clips, urls["voiceover"], urls["srt"])
            final_r2_url = upload_to_r2(folder, "final.mp4", final_url, "video/mp4")
            result["phases"].append({"name": "Final Render", "status": "done"})
            result["final_video"] = final_r2_url
            save_checkpoint(8, {"final_r2_url": final_r2_url})
            notify(8, "Final Render", "done")
        else:
            final_r2_url = ckpt["final_r2_url"]
            result["final_video"] = final_r2_url
            result["phases"].append({"name": "Final Render", "status": "done"})
            notify(8, "Final Render", "done")

        # ── Phase 9: Captions ──────────────────────────────────
        if resume_from <= 9:
            notify(9, "Captions", "running")
            captions = generate_captions(script, topic)
            result["phases"].append({"name": "Generate Captions", "status": "done"})
            save_checkpoint(9, {"captions": captions})
            notify(9, "Captions", "done")
        else:
            captions = ckpt["captions"]
            result["phases"].append({"name": "Generate Captions", "status": "done"})
            notify(9, "Captions", "done")

        # ── Phase 10: Publish ───────────────────────────────────
        notify(10, "Publish", "running")
        publish_everywhere(final_r2_url, captions, topic)
        result["phases"].append({"name": "Publish", "status": "done"})
        notify(10, "Publish", "done")

        # Update topic status
        update_airtable(topic["id"], {"Status": "Published", "Final Video URL": final_r2_url})

        result["status"] = "complete"
        elapsed = round(time.time() - start, 1)
        result["duration"] = f"{elapsed}s"
        log.info(f"\n✅ Pipeline complete in {elapsed}s — {final_r2_url}")

        try: os.remove(CHECKPOINT_FILE)
        except: pass

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        result["failed_phase"] = ckpt.get("_last_phase", 0) + 1 if ckpt.get("_last_phase") is not None else 0
        log.error(f"\n❌ Pipeline failed at phase {result['failed_phase']}: {e}")

        if "topic" in result:
            update_airtable(result["topic"]["id"], {"Status": "Failed", "Error": str(e)})

    return result


if __name__ == "__main__":
    run_pipeline()
