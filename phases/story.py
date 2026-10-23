"""
Knights Reactor — The Last Watch (story bible)
The saga every video lives in: the world, the cast, and the episodes. The
Story tab saves edits to <BRAND_DIR>/story.json; until then the original in
story/story.json is used (story/story_bible.md is its readable version).

- Episodes become topics (episode_topics), run in order.
- The script writer tells the episode's moment (script_story_block).
- The scene writer films it in the world's look and places, with the right
  knight carrying his signature object (scene_story_block, cast_profile).
"""
import json
from pathlib import Path

from config import BRAND_DIR, log

STORY_FILE = Path(__file__).parent.parent / "story" / "story.json"   # the original
SAVED_FILE = BRAND_DIR / "story.json"                                # edits from the Story tab
_KEYS = ("title", "tagline", "world", "look", "places", "motifs", "cast", "supporting", "seasons")


def story_source() -> str:
    return "saved" if SAVED_FILE.exists() else "original"


def load_story() -> dict:
    """The story bible (Story tab edits, else the original), or {} if broken."""
    for f in (SAVED_FILE, STORY_FILE):
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception as e:
                log.warning(f"   Story bible {f} not readable ({e})")
    return {}


def save_story(data: dict):
    """Save Story tab edits. Raises ValueError on a malformed story."""
    if not isinstance(data, dict) or not isinstance(data.get("cast"), list) \
            or not isinstance(data.get("seasons"), list) or not isinstance(data.get("places"), dict):
        raise ValueError("story needs cast (list), places (map) and seasons (list)")
    for season in data["seasons"]:
        season["number"] = int(season.get("number") or 1)
        for i, ep in enumerate(season.get("episodes") or [], 1):
            ep["number"] = int(ep.get("number") or i)
    SAVED_FILE.write_text(json.dumps({k: data[k] for k in _KEYS if k in data}, indent=2))


def reset_story():
    """Drop Story tab edits and go back to the original."""
    if SAVED_FILE.exists():
        SAVED_FILE.unlink()


def current_episode(topic: dict) -> dict:
    """An episode topic's episode, with the latest Story tab edits applied
    (matched by code, e.g. S1E03). {} for a normal topic."""
    ep = topic.get("episode") or {}
    if not ep.get("code"):
        return ep
    for season in load_story().get("seasons", []):
        for e in season.get("episodes", []):
            if f"S{season['number']}E{int(e['number']):02d}" == ep["code"]:
                return {**ep, **e, "code": ep["code"], "season": season["number"]}
    return ep


def cast_profile(figure_name: str) -> dict:
    """The story profile for a cast figure ("The Veteran"…), or {}."""
    return next((c for c in load_story().get("cast", []) if c.get("figure") == figure_name), {})


def episode_topics() -> list:
    """Every episode as a topic: (idea, category, scripture, episode)."""
    out = []
    for season in load_story().get("seasons", []):
        for ep in season.get("episodes", []):
            code = f"S{season['number']}E{int(ep['number']):02d}"
            episode = {"code": code, "season": season["number"], "season_title": season.get("title", ""),
                       **{k: ep.get(k, "") for k in ("number", "title", "knight", "place", "weather", "moment", "battle")}}
            out.append((f"{code} · {ep['title']} — {ep['moment']}", ep.get("category", "Deep Dive Analysis"),
                        ep.get("scripture", ""), episode))
    return out


def script_story_block(topic: dict) -> str:
    """Extra script-prompt context for an episode topic ("" for other topics)."""
    ep = current_episode(topic)
    story = load_story()
    if not ep or not story:
        return ""
    knight = cast_profile(ep["knight"])
    return f"""

## STORY — THIS VIDEO IS AN EPISODE OF "{story['title'].upper()}"
Season {ep['season']}, Episode {ep['number']}: "{ep['title']}".
The world: {story['world']}
This episode's knight: {knight.get('name', ep['knight'])} ("{ep['knight']}") — {knight.get('who', '')}. His wound: {knight.get('wound', '')}.
The moment the video shows: {ep['moment']}
The battle this episode is about: {ep['battle']}.

How to use it: the scenes show this moment. Open the narration inside it (you may name the knight once and say what he is doing), then turn it on the viewer's own battle with {ep['battle']}. Do not recap the plot or explain the world — someone who has never seen another episode must still get the lesson, and a returning viewer should recognize the story. Still end with one clear action for today."""


def scene_story_block(topic: dict, figure_name: str) -> str:
    """Scene-writer context: the world's look and places, the knight's
    profile, and — for an episode — the exact moment to film."""
    story = load_story()
    if not story:
        return ""
    places = "\n".join(f"- {k}: {v}" for k, v in story.get("places", {}).items())
    knight = cast_profile(figure_name)
    lines = [f"""
WORLD — every video is set in "{story['title']}": {story['world']}
LOOK: {story['look']}
PLACES (film in one of these unless the script clearly needs another):
{places}
MOTIFS you may use: {story.get('motifs', '')}"""]
    if knight:
        lines.append(f"THE KNIGHT IN THIS VIDEO: {knight['name']} (\"{figure_name}\"), {knight['who']}. "
                     f"His battle: {knight['battle']}. He always carries {knight['object']} — show it in at least one shot.")
    ep = current_episode(topic)
    if ep:
        lines.append(f"""THIS VIDEO IS EPISODE {ep['code']} "{ep['title']}". The concept IS this moment — film it, don't invent a different metaphor:
{ep['moment']}
Place: {ep['place']}. Season and light: {ep['weather']}.""")
    return "\n".join(lines) + "\n"
