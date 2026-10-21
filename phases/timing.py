"""
Knights Reactor — Scene timing
Splits the narration into "beats" so every scene in the video lines up with
the words being spoken: one scene per beat, each scene exactly as long as
its beat, back to back.

The number of scenes is the Settings → Video Generation "Clips" count and no
scene runs longer than the "Clip Duration", so the video keeps the length and
clip count the brand is set to. Within that, the cuts are placed at sentence
ends wherever possible (else at a pause), and the scenes are kept close to
even, so the picture changes when the narration moves on instead of on a
fixed clock.
"""
import math
import re

DEFAULT_CLIPS = 3
DEFAULT_CLIP_SECONDS = 10.0
_PAUSE = 0.25               # a gap this long is a usable mid-sentence break
_SENTENCE_GAP = 0.45        # a gap this long reads as a sentence break (if Whisper gave no segments)
_TAIL = 0.4                 # hold after the last word before the CTA / end
_CUT_COST = {"sentence": 0.0, "pause": 2.0, "word": 6.0}   # how much worse each kind of cut is
_SHORT = 2.0                # a scene shorter than this flashes by


def clip_duration(scene_length: float, video_model: str, setting: float = DEFAULT_CLIP_SECONDS):
    """Clip length to ask the video model for: the shortest length that covers
    the scene, never more than the Clip Duration setting. None = the model has
    no length option on Replicate, so it makes its default length.

    Seedance 1 (Lite/Pro) only takes 5 or 10 s; Seedance 2 takes any whole
    number of seconds."""
    m = (video_model or "").lower()
    setting = float(setting or DEFAULT_CLIP_SECONDS)
    need = max(5, math.ceil((scene_length or 0) - 0.01))
    if "seedance-2" in m:
        return int(min(setting, need))
    if "seedance" in m:
        return 5 if need <= 5 else 10
    return None


def scene_limit(video_model: str, setting: float = DEFAULT_CLIP_SECONDS) -> float:
    """Longest a scene may run: the Clip Duration setting, or the longest clip
    the model can actually make if that's shorter (Seedance 1 tops out at
    10 s), so no scene outlasts its clip and freezes."""
    setting = float(setting or DEFAULT_CLIP_SECONDS)
    m = (video_model or "").lower()
    if "seedance" in m and "seedance-2" not in m:
        return min(setting, 10.0)
    return setting


def _plan(words: list, sentence_end: list, count: int, max_scene: float) -> list:
    """Pick count-1 cut points between words (dynamic programming): every
    scene at most max_scene long, cuts at sentence ends > pauses > anywhere,
    scenes close to even. Returns word groups."""
    n = len(words)
    tail = words[-1]["end"] + _TAIL

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

    count = max(1, min(count, n))
    while True:
        target = tail / count
        INF = float("inf")
        best = [[INF] * (n + 1) for _ in range(count + 1)]
        back = [[0] * (n + 1) for _ in range(count + 1)]
        best[0][0] = 0.0
        for k in range(1, count + 1):
            for b in range(k, n + 1):
                cb = cut_cost(b)
                for a in range(k - 1, b):
                    if best[k - 1][a] == INF:
                        continue
                    length = t(b) - t(a)
                    if length > max_scene:
                        continue
                    cost = best[k - 1][a] + cb + 4 * ((length - target) / target) ** 2 \
                        + (5.0 if length < _SHORT else 0.0)
                    if cost < best[k][b]:
                        best[k][b], back[k][b] = cost, a
        if best[count][n] < INF or count >= n:
            break
        # The narration is longer than Clips × Clip Duration can cover —
        # add a scene rather than let a clip freeze on its last frame.
        count += 1
    if best[count][n] == INF:   # a single word longer than a clip: just split per word
        return [[w] for w in words]
    groups, b = [], n
    for k in range(count, 0, -1):
        a = back[k][b]
        groups.append(words[a:b])
        b = a
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


def build_beats(transcription: dict, count: int = DEFAULT_CLIPS,
                max_scene: float = DEFAULT_CLIP_SECONDS) -> list:
    """Beats from Whisper word timestamps. Each beat:
    {"index", "start", "end", "length", "text"} — contiguous, starting at 0,
    covering the whole narration."""
    words = [w for w in (transcription or {}).get("words", []) if "start" in w and "end" in w]
    if not words:
        return estimate_beats((transcription or {}).get("text", ""), count, max_scene)
    seg_ends = [float(s["end"]) for s in (transcription.get("segments") or []) if "end" in s]
    sentence_end = []
    for i, w in enumerate(words):
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0
        sentence_end.append(any(abs(w["end"] - e) < 0.08 for e in seg_ends) or gap >= _SENTENCE_GAP
                            or str(w.get("word", "")).strip().endswith((".", "!", "?")))
    return _to_beats(_plan(words, sentence_end, count, max_scene))


def estimate_beats(text: str, count: int = DEFAULT_CLIPS, max_scene: float = DEFAULT_CLIP_SECONDS,
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
    return _to_beats(_plan(words, sentence_end, count, max_scene))
