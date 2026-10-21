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

IDEAL_SCENE = 6.0           # a scene this long reads well on a short-form video
DEFAULT_CLIP = 5.0          # clip length assumed for models we can't ask for a length
_PAUSE = 0.25               # a gap this long is a usable mid-sentence break
_SENTENCE_GAP = 0.45        # a gap this long reads as a sentence break (if Whisper gave no segments)
_TAIL = 0.4                 # hold after the last word before the CTA / end
_CUT_COST = {"sentence": 0.0, "pause": 2.0, "word": 6.0}   # how much worse each kind of cut is
_SHORT = 2.0                # a scene shorter than this flashes by
_EVEN = 8.0                 # how much scenes far from IDEAL_SCENE are avoided
_PER_DOLLAR = 3.0           # how much a dollar of images/footage weighs against a worse cut


def clip_lengths(video_model: str):
    """Clip lengths (s) the model can be asked for on Replicate, or None if it
    takes no length setting and makes its own default length.
    Seedance 1 (Lite/Pro) takes 5 or 10 s; Seedance 2 any whole second."""
    m = (video_model or "").lower()
    if "seedance-2" in m:
        return list(range(5, 11))
    if "seedance" in m:
        return [5, 10]
    return None


def scene_limit(video_model: str) -> float:
    """Longest a scene may run on this model without its clip freezing."""
    lengths = clip_lengths(video_model)
    return float(max(lengths)) if lengths else DEFAULT_CLIP


def clip_duration(scene_length: float, video_model: str):
    """Shortest clip length the model offers that covers the scene — None if
    the model takes no length setting."""
    lengths = clip_lengths(video_model)
    if not lengths:
        return None
    return next((d for d in lengths if (scene_length or 0) <= d + 1e-6), lengths[-1])


def clip_seconds(scene_length: float, video_model: str) -> float:
    """Seconds of clip that get generated (and paid for) for a scene."""
    return clip_duration(scene_length, video_model) or DEFAULT_CLIP


def _plan(words: list, sentence_end: list, video_model: str, image_model: str) -> list:
    """Choose the cuts (dynamic programming over the word gaps) that score
    best: cuts at sentence ends > pauses > anywhere, scenes near IDEAL_SCENE,
    nothing longer than the model's clip, and the least spent on images and
    footage. Returns word groups, one per scene."""
    n = len(words)
    tail = words[-1]["end"] + _TAIL
    limit = scene_limit(video_model)
    per_sec, per_img = planning_prices(video_model, image_model)

    def t(b):   # time of a cut before word b
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

    INF = float("inf")
    best, back = [0.0] + [INF] * n, [0] * (n + 1)
    for b in range(1, n + 1):
        cb = cut_cost(b)
        for a in range(b - 1, -1, -1):
            length = t(b) - t(a)
            if length > limit:
                break
            if best[a] == INF:
                continue
            score = best[a] + cb + _EVEN * ((length - IDEAL_SCENE) / IDEAL_SCENE) ** 2 \
                + (5.0 if length < _SHORT else 0.0) \
                + _PER_DOLLAR * (clip_seconds(length, video_model) * per_sec + per_img)
            if score < best[b]:
                best[b], back[b] = score, a
    if best[n] == INF:   # a single word longer than a clip: one scene per word
        return [[w] for w in words]
    groups, b = [], n
    while b > 0:
        groups.append(words[back[b]:b])
        b = back[b]
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


def build_beats(transcription: dict, video_model: str = "", image_model: str = "") -> list:
    """Beats from Whisper word timestamps. Each beat:
    {"index", "start", "end", "length", "text"} — contiguous, starting at 0,
    covering the whole narration."""
    words = [w for w in (transcription or {}).get("words", []) if "start" in w and "end" in w]
    if not words:
        return estimate_beats((transcription or {}).get("text", ""), video_model, image_model)
    seg_ends = [float(s["end"]) for s in (transcription.get("segments") or []) if "end" in s]
    sentence_end = []
    for i, w in enumerate(words):
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0
        sentence_end.append(any(abs(w["end"] - e) < 0.08 for e in seg_ends) or gap >= _SENTENCE_GAP
                            or str(w.get("word", "")).strip().endswith((".", "!", "?")))
    return _to_beats(_plan(words, sentence_end, video_model, image_model))


def estimate_beats(text: str, video_model: str = "", image_model: str = "",
                   words_per_sec: float = 2.8) -> list:
    """Approximate beats from script text alone (no audio yet) — used by
    Script Only previews and as a fallback if Whisper returns no words."""
    toks = (text or "").split() or [""]
    words, sentence_end, t = [], [], 0.0
    for tok in toks:
        words.append({"word": tok, "start": round(t, 3), "end": round(t + 1 / words_per_sec, 3)})
        t += 1 / words_per_sec
        end = tok.endswith((".", "!", "?"))
        sentence_end.append(end)
        t += 0.45 if end else (0.25 if tok.endswith((",", ";", ":", "—")) else 0)
    return _to_beats(_plan(words, sentence_end, video_model, image_model))


def video_plan(beats: list, video_model: str, image_model: str, cta_seconds: float = 0.0) -> dict:
    """What a run will make and roughly cost — shown on the dashboard."""
    from phases.costs import estimate
    clips = [clip_seconds(b["length"], video_model) for b in beats]
    narration = beats[-1]["end"] if beats else 0.0
    return {
        "clips": len(beats),
        "scene_seconds": [round(b["length"], 1) for b in beats],
        "clip_seconds": clips,
        "narration_seconds": round(narration, 1),
        "cta_seconds": round(cta_seconds or 0, 1),
        "video_seconds": round(narration + (cta_seconds or 0), 1),
        "video_model": video_model, "image_model": image_model,
        "cost": estimate(clips, video_model, image_model),
    }


def estimate_plan(script_words: int, video_model: str, image_model: str, cta_seconds: float = 0.0) -> dict:
    """Plan for a script of about script_words words (before one exists),
    with a typical mix of sentence lengths."""
    words, toks, k = max(1, int(script_words or 0)), [], 0
    pattern = [8, 12, 10, 14, 6, 11]
    while len(toks) < words:
        n = min(pattern[k % len(pattern)], words - len(toks))
        toks += ["word"] * (n - 1) + ["word."]
        k += 1
    text = " ".join(toks)
    plan = video_plan(estimate_beats(text, video_model, image_model, words_per_sec=3.0),
                      video_model, image_model, cta_seconds)
    plan["estimated"] = True
    plan["script_words"] = words
    return plan
