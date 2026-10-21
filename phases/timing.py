"""
Knights Reactor — Scene timing
Splits the narration into "beats" so every scene in the video lines up with
the words being spoken: one scene per beat, cut where the voice pauses, each
scene exactly as long as its beat.

A beat can never be longer than the clip the video model makes, or the clip
would freeze on its last frame — the "hiccup" the old fixed 10-second slots
caused with 5-second clips. How long that is depends on the model, so the
selected model decides (clip_plan): Seedance can be asked for 10-second
clips, so it gets fewer, longer scenes — close to the old 3 clips for a
short script. Every other model is held to its 5-second default.
"""
import math
import re

MAX_SCENE_SECONDS = 5.0     # every video model in Settings makes clips at least this long by default
_PAUSE = 0.25               # a gap this long is a usable mid-sentence break
_SENTENCE_GAP = 0.45        # a gap this long reads as a sentence break (if Whisper gave no segments)
_DANGLING = 1.0             # a leftover tail shorter than this joins the previous scene
_TAIL = 0.4                 # hold after the last word before the CTA / end


def clip_plan(video_model: str) -> dict:
    """Longest scene this video model can cover, and the clip lengths it can
    be asked for (empty = the model has no length option; use its default)."""
    if "seedance" in (video_model or "").lower():
        return {"max_scene": 10.0, "durations": [5, 10]}
    return {"max_scene": MAX_SCENE_SECONDS, "durations": []}


def clip_duration(length: float, video_model: str):
    """Shortest clip length the model offers that still covers a scene of
    `length` seconds — None if the model takes no length setting."""
    durations = clip_plan(video_model)["durations"]
    if not durations:
        return None
    return next((d for d in durations if (length or 0) <= d), durations[-1])


def _limits(max_scene: float):
    """Cut thresholds scaled to the longest allowed scene:
    force  — a scene is split before its words run past this (room is left
             for the pause halves added at each cut)
    sent   — a sentence this long gets its own scene; shorter ones join the next
    natural — a mid-sentence pause only ends a scene after this long"""
    return max_scene - 0.8, 1.5 + (max_scene - 5.0) * 0.5, 0.6 * max_scene


def _split_index(group: list, breaks: set, natural_min: float) -> int:
    """Where to split an overlong word group: the last sentence end if there is
    one, else the longest pause that keeps the first part >= natural_min."""
    for j in range(len(group) - 1, 0, -1):
        if id(group[j - 1]) in breaks:
            return j
    best, best_gap = len(group), -1.0
    for j in range(1, len(group)):
        if group[j - 1]["end"] - group[0]["start"] < natural_min:
            continue
        gap = group[j]["start"] - group[j - 1]["end"]
        if gap > best_gap:
            best, best_gap = j, gap
    return best


def build_beats(transcription: dict, max_scene: float = MAX_SCENE_SECONDS) -> list:
    """Beats from Whisper word timestamps. Each beat:
    {"index", "start", "end", "length", "text"} — contiguous, starting at 0,
    covering the whole narration, none longer than max_scene."""
    words = [w for w in (transcription or {}).get("words", []) if "start" in w and "end" in w]
    if not words:
        return estimate_beats((transcription or {}).get("text", ""), max_scene=max_scene)
    force_cut, sentence_min, natural_min = _limits(max_scene)

    seg_ends = [float(s["end"]) for s in (transcription.get("segments") or []) if "end" in s]
    breaks = set()
    for i, w in enumerate(words[:-1]):
        gap = words[i + 1]["start"] - w["end"]
        if any(abs(w["end"] - t) < 0.08 for t in seg_ends) or gap >= _SENTENCE_GAP:
            breaks.add(id(w))

    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            break
        span = w["end"] - cur[0]["start"]
        gap = nxt["start"] - w["end"]
        # Cut at sentence ends; cut mid-sentence only at a pause once the
        # scene has run a while, or when the next word would overrun a clip.
        if (id(w) in breaks and span >= sentence_min) or (gap >= _PAUSE and span >= natural_min):
            groups.append(cur)
            cur = []
        elif nxt["end"] - cur[0]["start"] > force_cut:
            j = _split_index(cur, breaks, natural_min)
            groups.append(cur[:j])
            cur = cur[j:]
    if cur:
        # Only a dangling word or two joins the previous scene (if it fits);
        # a closing sentence like the call to action keeps its own scene.
        if groups and cur[-1]["end"] - groups[-1][0]["start"] <= force_cut and \
                cur[-1]["end"] - cur[0]["start"] < _DANGLING:
            groups[-1].extend(cur)
        else:
            groups.append(cur)

    beats = []
    for k, g in enumerate(groups):
        start = 0.0 if k == 0 else round((groups[k - 1][-1]["end"] + g[0]["start"]) / 2, 3)
        beats.append({"index": k + 1, "start": start,
                      "text": " ".join(w.get("word", "").strip() for w in g).strip()})
    for k, b in enumerate(beats):
        b["end"] = beats[k + 1]["start"] if k + 1 < len(beats) else round(groups[-1][-1]["end"] + _TAIL, 3)
        b["length"] = round(b["end"] - b["start"], 3)
    return beats


def estimate_beats(text: str, words_per_sec: float = 2.8, max_scene: float = MAX_SCENE_SECONDS) -> list:
    """Approximate beats from script text alone (no audio yet) — used by
    Script Only previews and as a fallback if Whisper returns no words."""
    force_cut, sentence_min, _ = _limits(max_scene)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or "").strip()) if s.strip()]
    max_words = max(1, int(force_cut * words_per_sec))
    chunks = []
    for s in sentences:
        toks = s.split()
        n = math.ceil(len(toks) / max_words)
        size = math.ceil(len(toks) / n)
        for i in range(0, len(toks), size):
            part = toks[i:i + size]
            # A short sentence joins the next one, as build_beats does.
            if chunks and len(chunks[-1]) / words_per_sec < sentence_min and \
                    len(chunks[-1]) + len(part) <= max_words:
                chunks[-1] += part
            else:
                chunks.append(part)
    chunks = [" ".join(c) for c in chunks] or [""]
    beats, t = [], 0.0
    for k, c in enumerate(chunks):
        length = round(max(len(c.split()) / words_per_sec, 1.5), 3)
        beats.append({"index": k + 1, "start": round(t, 3), "end": round(t + length, 3),
                      "length": length, "text": c})
        t += length
    return beats
