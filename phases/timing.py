"""
Knights Reactor — Scene timing
Splits the narration into "beats" so every scene in the video lines up with
the words being spoken: one scene per beat, each scene exactly as long as
its beat, back to back.

The app plans the scenes itself — no clip settings needed. It cuts at
sentence ends wherever it can (else at a pause), aims for scenes of about
IDEAL_SCENE seconds, never lets a scene outlast the clip the video model can
make (or the clip would freeze on its last frame), and weighs what each
extra image and second of footage costs — so a short script gets a few
clips, a longer one gets more, and money isn't spent on footage nobody sees.
"""
import math

from phases.costs import planning_prices
from phases.model_info import model_inputs

IDEAL_SCENE = 6.0           # a scene this long reads well on a short-form video
DEFAULT_CLIP = 5.0          # clip length assumed for models we can't ask for a length
MAX_SCENE = 10.0            # longest scene, even on models that can make longer clips
_PAUSE = 0.25               # a gap this long is a usable mid-sentence break
_SENTENCE_GAP = 0.45        # a gap this long reads as a sentence break (if Whisper gave no segments)
_TAIL = 0.4                 # hold after the last word before the CTA / end
_CUT_COST = {"sentence": 0.0, "pause": 2.0, "word": 6.0}   # how much worse each kind of cut is
_SHORT = 2.0                # a scene shorter than this flashes by
_EVEN = 8.0                 # how much scenes far from IDEAL_SCENE are avoided
_PER_DOLLAR = 3.0           # how much a dollar of images/footage weighs against a worse cut


def clip_lengths(video_model: str):
    """Clip lengths (s) the model can be asked for, read from its Replicate
    schema — or None if it takes no length setting and makes its own default
    length. Without the schema: Seedance 1 takes 5 or 10 s, Seedance 2 any
    whole second."""
    info = model_inputs(video_model)
    if info is not None:
        return info["durations"]
    m = (video_model or "").lower()
    if "seedance-2" in m:
        return list(range(5, 11))
    if "seedance" in m:
        return [5, 10]
    return None


def _default_clip(video_model: str) -> float:
    """Length the model makes when it can't be asked for one."""
    info = model_inputs(video_model)
    return (info or {}).get("default_duration") or DEFAULT_CLIP


def scene_limit(video_model: str) -> float:
    """Longest a scene may run on this model without its clip freezing."""
    lengths = clip_lengths(video_model)
    if lengths:
        return float(min(max(lengths), MAX_SCENE))
    return min(_default_clip(video_model), MAX_SCENE)


def clip_duration(scene_length: float, video_model: str):
    """Shortest clip length the model offers that covers the scene — None if
    the model takes no length setting."""
    lengths = clip_lengths(video_model)
    if not lengths:
        return None
    return next((d for d in lengths if (scene_length or 0) <= d + 1e-6), lengths[-1])


def clip_seconds(scene_length: float, video_model: str) -> float:
    """Seconds of clip that get generated (and paid for) for a scene."""
    return clip_duration(scene_length, video_model) or _default_clip(video_model)


def _plan(words: list, sentence_end: list, video_model: str, image_model: str,
          pacing: str = "auto", target_clips: int = None) -> list:
    """Choose narration-aligned cuts under the model's actual clip-length limit.

    Auto retains the original cost-aware sentence-break planner. Slow/dynamic
    change the preferred shot length; manual uses an exact-count dynamic
    program when feasible and the closest feasible count otherwise. Never
    stretch a scene beyond the video model's maximum usable duration.
    """
    n = len(words)
    if not n:
        return []
    pacing = pacing if pacing in ("auto", "slow", "dynamic", "manual") else "auto"
    tail = words[-1]["end"] + _TAIL
    limit = scene_limit(video_model)
    per_sec, per_img = planning_prices(video_model, image_model)
    allowed = sorted(clip_lengths(video_model) or [])
    fallback_seconds = _default_clip(video_model)

    def generated_seconds(length):
        if not allowed:
            return fallback_seconds
        return next((v for v in allowed if length <= v + 1e-6), allowed[-1])

    ideal = {"auto": IDEAL_SCENE, "slow": 8.0, "dynamic": 3.8}.get(pacing, IDEAL_SCENE)
    if pacing == "manual" and target_clips:
        ideal = max(1.5, min(limit, tail / max(1, target_clips)))

    def t(b):
        if b == 0:
            return 0.0
        if b == n:
            return tail
        return (words[b - 1]["end"] + words[b]["start"]) / 2

    def cut_cost(b):
        if b == n:
            return 0.0
        if sentence_end[b - 1]:
            return _CUT_COST["sentence"]
        if words[b]["start"] - words[b - 1]["end"] >= _PAUSE:
            return _CUT_COST["pause"]
        return _CUT_COST["word"]

    def score(a, b):
        length = t(b) - t(a)
        if length <= 0 or length > limit + 1e-6:
            return None
        return (
            cut_cost(b) + _EVEN * ((length - ideal) / max(ideal, 1)) ** 2
            + (5.0 if length < _SHORT else 0.0)
            + _PER_DOLLAR * (generated_seconds(length) * per_sec + per_img)
        )

    INF = float("inf")
    if pacing == "manual" and target_clips is not None:
        target = max(2, min(12, int(target_clips)))
        # The actual audio can exceed the requested duration. Search enough
        # counts to cover it without pretending that impossible counts work.
        max_count = min(n, max(target, math.ceil(tail / limit) + 3))
        best = [[INF] * (n + 1) for _ in range(max_count + 1)]
        back = [[-1] * (n + 1) for _ in range(max_count + 1)]
        best[0][0] = 0.0
        for count in range(1, max_count + 1):
            for end in range(count, n + 1):
                for start in range(end - 1, count - 2, -1):
                    extra = score(start, end)
                    if extra is None:
                        if t(end) - t(start) > limit:
                            break
                        continue
                    if best[count - 1][start] == INF:
                        continue
                    candidate = best[count - 1][start] + extra
                    if candidate < best[count][end]:
                        best[count][end], back[count][end] = candidate, start
        feasible = [k for k in range(1, max_count + 1) if best[k][n] != INF]
        if feasible:
            count = min(feasible, key=lambda k: (abs(k - target), best[k][n]))
            groups, end = [], n
            while count > 0:
                start = back[count][end]
                groups.append(words[start:end])
                end = start
                count -= 1
            return groups[::-1]

    # Original one-dimensional planner: use it for Auto, Slow and Dynamic,
    # or if an extreme manual target could not be reached.
    best, back = [0.0] + [INF] * n, [0] * (n + 1)
    for end in range(1, n + 1):
        for start in range(end - 1, -1, -1):
            extra = score(start, end)
            if extra is None:
                if t(end) - t(start) > limit:
                    break
                continue
            if best[start] == INF:
                continue
            candidate = best[start] + extra
            if candidate < best[end]:
                best[end], back[end] = candidate, start
    if best[n] == INF:
        # A single transcribed word lasts longer than any supported video
        # clip. Keep every word, and make the limitation visible in the plan.
        return [[w] for w in words]
    groups, end = [], n
    while end > 0:
        groups.append(words[back[end]:end])
        end = back[end]
    return groups[::-1]


def _to_beats(groups: list) -> list:
    beats = []
    for k, g in enumerate(groups):
        start = 0.0 if k == 0 else round((groups[k - 1][-1]["end"] + g[0]["start"]) / 2, 3)
        beats.append({"index": k + 1, "start": start,
                      "text": " ".join(w.get("word", "").strip() for w in g).strip()})
    for k, b in enumerate(beats):
        b["end"] = beats[k + 1]["start"] if k + 1 < len(beats) else round(groups[-1][-1]["end"] + _TAIL, 3)
        b["length"] = round(b["end"] - b["start"], 3)
    return beats


def build_beats(transcription: dict, video_model: str = "", image_model: str = "",
                pacing: str = "auto", target_clips: int = None) -> list:
    """Beats from Whisper word timestamps. Each beat:
    {"index", "start", "end", "length", "text"} — contiguous, starting at 0,
    covering the whole narration."""
    words = [w for w in (transcription or {}).get("words", []) if "start" in w and "end" in w]
    if not words:
        return estimate_beats((transcription or {}).get("text", ""), video_model, image_model,
                              pacing=pacing, target_clips=target_clips)
    seg_ends = [float(s["end"]) for s in (transcription.get("segments") or []) if "end" in s]
    sentence_end = []
    for i, w in enumerate(words):
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0
        sentence_end.append(any(abs(w["end"] - e) < 0.08 for e in seg_ends) or gap >= _SENTENCE_GAP
                            or str(w.get("word", "")).strip().endswith((".", "!", "?")))
    return _to_beats(_plan(words, sentence_end, video_model, image_model,
                           pacing=pacing, target_clips=target_clips))


def estimate_beats(text: str, video_model: str = "", image_model: str = "",
                   words_per_sec: float = 2.8, pacing: str = "auto",
                   target_clips: int = None) -> list:
    """Approximate beats from script text alone (no audio yet) — used by
    Script Only previews and as a fallback if Whisper returns no words."""
    words, sentence_end = _synthetic_words(text, words_per_sec)
    return _to_beats(_plan(words, sentence_end, video_model, image_model,
                           pacing=pacing, target_clips=target_clips))


def _synthetic_words(text: str, words_per_sec: float, seconds: float = None):
    """Word timings for text that hasn't been spoken yet: a pause after each
    sentence and comma, stretched to `seconds` of narration if given."""
    toks = (text or "").split() or [""]
    words, sentence_end, t = [], [], 0.0
    for tok in toks:
        words.append({"word": tok, "start": t, "end": t + 1 / words_per_sec})
        t += 1 / words_per_sec
        end = tok.endswith((".", "!", "?"))
        sentence_end.append(end)
        t += 0.45 if end else (0.25 if tok.endswith((",", ";", ":", "—")) else 0)
    scale = seconds / words[-1]["end"] if seconds else 1.0
    for w in words:
        w["start"], w["end"] = round(w["start"] * scale, 3), round(w["end"] * scale, 3)
    return words, sentence_end


def video_plan(beats: list, video_model: str, image_model: str, cta_seconds: float = 0.0,
               pacing: str = "auto", target_clips: int = None) -> dict:
    """What a run will make and roughly cost — shown on the dashboard."""
    from phases.costs import estimate
    clips = [clip_seconds(b["length"], video_model) for b in beats]
    narration = beats[-1]["end"] if beats else 0.0
    return {
        "clips": len(beats),
        "pacing": pacing,
        "target_clips": int(target_clips) if pacing == "manual" and target_clips else None,
        "target_met": (len(beats) == int(target_clips)) if pacing == "manual" and target_clips else None,
        "max_clip_seconds": scene_limit(video_model),
        "scene_seconds": [round(b["length"], 1) for b in beats],
        "clip_seconds": clips,
        "narration_seconds": round(narration, 1),
        "cta_seconds": round(cta_seconds or 0, 1),
        "video_seconds": round(narration + (cta_seconds or 0), 1),
        "video_model": video_model, "image_model": image_model,
        "cost": estimate(clips, video_model, image_model),
    }


def estimate_plan(script_words: int, video_model: str, image_model: str, cta_seconds: float = 0.0,
                  seconds_per_word: float = None, pacing: str = "auto",
                  target_clips: int = None) -> dict:
    """Plan for a script of about script_words words (before one exists),
    with a typical mix of sentence lengths. seconds_per_word is the brand's
    real reading pace (pauses included) measured from past videos; without
    it a standard 3 words/sec is assumed."""
    words, toks, k = max(1, int(script_words or 0)), [], 0
    pattern = [8, 12, 10, 14, 6, 11]
    while len(toks) < words:
        n = min(pattern[k % len(pattern)], words - len(toks))
        toks += ["word"] * (n - 1) + ["word."]
        k += 1
    text = " ".join(toks)
    seconds = words * seconds_per_word if seconds_per_word else None
    tw, ends = _synthetic_words(text, 3.0, seconds)
    beats = _to_beats(_plan(tw, ends, video_model, image_model,
                            pacing=pacing, target_clips=target_clips))
    plan = video_plan(beats, video_model, image_model, cta_seconds,
                      pacing=pacing, target_clips=target_clips)
    plan["estimated"] = True
    plan["script_words"] = words
    return plan
