"""
Knights Reactor — Scene timing
Splits the narration into "beats" so every scene in the video lines up with
the words being spoken: one scene per beat, cut where the voice pauses, each
scene exactly as long as its beat.

Beats are capped at MAX_SCENE_SECONDS because the video models only make
fixed-length clips (Seedance 1 on Replicate: 5 or 10 s, default 5). A beat
longer than its clip would freeze on the last frame — the "hiccup" the old
fixed 10-second slots caused with 5-second clips.
"""
import math
import re

MAX_SCENE_SECONDS = 5.0     # every video model in Settings makes clips at least this long by default
_FORCE_CUT_AT = MAX_SCENE_SECONDS - 0.8   # leave room for the pause halves added at each cut
_SENTENCE_MIN = 1.5         # a sentence this long gets its own scene
_NATURAL_MIN = 3.0          # a mid-sentence pause only ends a scene after this long
_SENTENCE_GAP = 0.45        # a gap this long reads as a sentence break (if Whisper gave no segments)
_PAUSE = 0.25               # a gap this long is a usable mid-sentence break
_DANGLING = 1.0             # a leftover tail shorter than this joins the previous scene
_TAIL = 0.4                 # hold after the last word before the CTA / end


def _split_at_best_pause(group: list) -> int:
    """Index to split a word group at its longest internal pause, keeping the
    first part at least _NATURAL_MIN long when possible."""
    best, best_gap = len(group), -1.0
    for j in range(1, len(group)):
        if group[j - 1]["end"] - group[0]["start"] < _NATURAL_MIN:
            continue
        gap = group[j]["start"] - group[j - 1]["end"]
        if gap > best_gap:
            best, best_gap = j, gap
    return best


def build_beats(transcription: dict) -> list:
    """Beats from Whisper word timestamps. Each beat:
    {"index", "start", "end", "length", "text"} — contiguous, starting at 0,
    covering the whole narration."""
    words = [w for w in (transcription or {}).get("words", []) if "start" in w and "end" in w]
    if not words:
        return estimate_beats((transcription or {}).get("text", ""))

    seg_ends = [float(s["end"]) for s in (transcription.get("segments") or []) if "end" in s]

    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            break
        span = w["end"] - cur[0]["start"]
        gap = nxt["start"] - w["end"]
        sentence_break = any(abs(w["end"] - t) < 0.08 for t in seg_ends) or gap >= _SENTENCE_GAP
        # Cut at every sentence end; cut mid-sentence only at a pause once the
        # scene has run a while, or when the next word would overrun a clip.
        if (sentence_break and span >= _SENTENCE_MIN) or (gap >= _PAUSE and span >= _NATURAL_MIN):
            groups.append(cur)
            cur = []
        elif nxt["end"] - cur[0]["start"] > _FORCE_CUT_AT:
            j = _split_at_best_pause(cur)
            groups.append(cur[:j])
            cur = cur[j:]
    if cur:
        # Only a dangling word or two joins the previous scene (if it fits);
        # a closing sentence like the call to action keeps its own scene.
        if groups and cur[-1]["end"] - groups[-1][0]["start"] <= _FORCE_CUT_AT and \
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


def estimate_beats(text: str, words_per_sec: float = 2.8) -> list:
    """Approximate beats from script text alone (no audio yet) — used by
    Script Only previews and as a fallback if Whisper returns no words."""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or "").strip()) if s.strip()]
    chunks = []
    max_words = max(1, int(_FORCE_CUT_AT * words_per_sec))
    for s in sentences:
        toks = s.split()
        n = math.ceil(len(toks) / max_words)
        size = math.ceil(len(toks) / n)
        chunks += [" ".join(toks[i:i + size]) for i in range(0, len(toks), size)]
    if not chunks:
        chunks = [""]
    beats, t = [], 0.0
    for k, c in enumerate(chunks):
        length = round(max(len(c.split()) / words_per_sec, 1.5), 3)
        beats.append({"index": k + 1, "start": round(t, 3), "end": round(t + length, 3),
                      "length": length, "text": c})
        t += length
    return beats
