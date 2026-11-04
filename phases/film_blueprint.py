"""A film's single creative source of truth: cast, dramatic beats and narration.

Pure validation/shot alignment lives here so the screenplay can be reviewed
without image/video generation, and every downstream stage uses the same story.
"""
from __future__ import annotations

import json


STORY_PHASES = ("setup", "conflict", "choice", "consequence")


def select_character(topic: dict) -> dict:
    """Cast ONCE before writing, then carry the same identity into all shots."""
    from config import Config
    from phases.story import cast_profile, current_episode
    from phases.scenes import get_scene_data, normalize_figures, pick_no_repeat

    figures = normalize_figures(get_scene_data()[0])
    if not figures:
        raise ValueError("A film needs at least one character in the cast library")

    episode = current_episode(topic)
    episode_knight = episode.get("knight", "")
    forced = str(getattr(Config, "SCENE_FIGURE", "auto") or "auto").strip()
    if episode_knight:
        selected = next((f for f in figures if f["name"] == episode_knight), None)
        if selected is None:
            raise ValueError("The series character is missing from the visual cast: " + episode_knight)
    elif forced != "auto":
        selected = next((f for f in figures
                         if forced in (f["name"], f["desc"]) or f["desc"].startswith(forced)), None)
        if selected is None:
            raise ValueError("Selected character is missing from the cast library: " + forced)
    else:
        selected = pick_no_repeat(figures)

    profile = cast_profile(selected["name"]) if episode_knight else {}
    return {
        "name": profile.get("name") or selected["name"] or "The Knight",
        "cast_key": selected["name"],
        "description": selected["desc"],
        "ref_image": selected.get("ref_image", ""),
        "who": profile.get("who", ""),
        "wound": profile.get("wound", ""),
        "desire": profile.get("battle", ""),
        "arc": profile.get("arc", ""),
        "signature_object": profile.get("object", ""),
    }


def film_assignment(character: dict) -> str:
    """Creative assignment for the screenwriter, not a separate scene prompt."""
    return """
FILM STUDIO RULES — these supersede any old motivational-video instructions:
You are writing an ACTUAL short film. Its protagonist has a concrete goal,
an obstacle, escalating stakes and an observable final decision. Write the
screenplay and spoken narration as ONE coherent dramatic work, in the same
response. The camera must be able to show the story without the narration.
The voiceover should add emotional perspective, not describe everything seen.

LOCKED CAST (must drive the screenplay and be used by the shot director):
""" + json.dumps(character, ensure_ascii=False) + """

Write for modern teenage and young adult men in plain, natural English.
No pseudo-medieval diction, forced slogans, motivational commands,
cliches, vague hero poses, abstract spiritual battles or artificial slang.
Keep faith authentic and grounded in decisions and consequences; do not
insert scripture that conflicts with the topic or character.

Write the full voiceover first and ensure it fits the requested word count.
The four legacy hook/build/reveal/command fields must split that SAME
voiceover in chronological order for existing voiceover/timing consumers.

In film_blueprint.visual_story, write FOUR connected dramatic beats: setup,
conflict, choice, consequence. Each beat MUST describe (a) what physically
happens ON SCREEN, (b) what changes, (c) why this beat matters. The choice
must be observable in the character's ACTION, not just the narration. The
consequence must follow from that choice. Use ONE coherent primary location
unless a change of location is essential. Each beat should be filmable in
short video clips without impossible transformations.

Return JSON only, matching this complete schema:
{
 "hook": "opening part of the voiceover",
 "build": "next part of the voiceover",
 "reveal": "next part of the voiceover",
 "command": "final part of the voiceover (not necessarily an imperative)",
 "script_full": "same four parts in one continuous narration paragraph",
 "tone": "natural, restrained",
 "film_blueprint": {
   "title": "short film title",
   "logline": "character, want, obstacle, stakes and choice in one sentence",
   "character": {"name": "same locked name", "cast_key": "same locked key",
      "description": "same locked physical description", "ref_image": "same locked URL",
      "who": "who they are", "wound": "inner vulnerability",
      "desire": "what they want", "arc": "what changes",
      "signature_object": "distinctive prop"},
   "setting": "specific physical location, time and weather",
   "goal": "tangible objective",
   "obstacle": "specific visible person or circumstance",
   "stakes": "what is lost if the character fails",
   "theme": "one clear human truth",
   "final_choice": "specific irreversible or costly action",
   "visual_story": [
      {"phase":"setup", "dramatic_purpose":"...", "visible_action":"...",
       "change":"...", "narration_intent":"..."},
      {"phase":"conflict", "dramatic_purpose":"...", "visible_action":"...",
       "change":"...", "narration_intent":"..."},
      {"phase":"choice", "dramatic_purpose":"...", "visible_action":"...",
       "change":"...", "narration_intent":"..."},
      {"phase":"consequence", "dramatic_purpose":"...", "visible_action":"...",
       "change":"...", "narration_intent":"..."}
   ]
 }
}
Do NOT generate disconnected portraits or shots. The visual_story is the
screenplay that the cinematographer MUST film, not mood-board suggestions.
"""


def validate_film_blueprint(raw: dict, locked_character: dict) -> dict:
    """Reject incomplete films rather than quietly make random stock footage."""
    if not isinstance(raw, dict):
        raise ValueError("Missing film blueprint: screenplay must be a JSON object")
    required = ("title", "logline", "setting", "goal", "obstacle", "stakes",
                "theme", "final_choice")
    for key in required:
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError("Film blueprint missing dramatic requirement: " + key)
    beats = raw.get("visual_story")
    if not isinstance(beats, list) or len(beats) != 4:
        raise ValueError("Film blueprint needs exactly four screenplay beats")
    for index, (beat, phase) in enumerate(zip(beats, STORY_PHASES)):
        if not isinstance(beat, dict) or beat.get("phase") != phase:
            raise ValueError(f"Screenplay beat {index+1} must be {phase}")
        for field in ("dramatic_purpose", "visible_action", "change"):
            if not isinstance(beat.get(field), str) or not beat[field].strip():
                raise ValueError(f"Screenplay beat {phase} missing {field}")
    # Never trust a generated name/reference image over the selected cast.
    result = dict(raw)
    result["character"] = dict(locked_character)
    result["visual_story"] = [dict(b) for b in beats]
    return result


def shot_assignment(blueprint: dict, narration_beats: list) -> list:
    """Bind timed clips to the screenplay arc, rather than inventing new plots.

    A scene may span several clips. Assign shots by their midpoint within the
    total narration duration; preserve order, with a distinct action per shot.
    """
    if not narration_beats:
        return []
    story = blueprint["visual_story"]
    start = float(narration_beats[0].get("start", 0))
    end = float(narration_beats[-1]["end"])
    duration = max(end - start, 0.001)
    assignments = []
    for beat in narration_beats:
        mid = (float(beat["start"]) + float(beat["end"])) / 2
        progress = max(0.0, min(0.999999, (mid - start) / duration))
        phase_index = min(3, int(progress * 4))
        assignment = dict(story[phase_index])
        assignment["shot_index"] = beat["index"]
        assignment["narration"] = beat.get("text", "")
        assignment["seconds"] = beat.get("length", 0)
        assignments.append(assignment)
    return assignments
