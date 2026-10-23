"""
Knights Reactor — The Last Watch (story bible)
The saga every video lives in: the world, the cast, and the episodes, read
from story/story.json (story/story_bible.md is the readable version).

- Episodes become topics (episode_topics), run in order.
- The script writer tells the episode's moment (script_story_block).
- The scene writer films it in the world's look and places, with the right
  knight carrying his signature object (scene_story_block, cast_profile).
"""
import json
from pathlib import Path

from config import log

STORY_FILE = Path(__file__).parent.parent / "story" / "story.json"
_CACHE = {}


def load_story() -> dict:
    """The story bible, or {} if it's missing or broken."""
    if "story" not in _CACHE:
        try:
            _CACHE["story"] = json.loads(STORY_FILE.read_text())
        except Exception as e:
            log.warning(f"   Story bible not loaded ({e}) — scenes run without it")
            _CACHE["story"] = {}
    return _CACHE["story"]


def cast_profile(figure_name: str) -> dict:
    """The story profile for a cast figure ("The Veteran"…), or {}."""
    return next((c for c in load_story().get("cast", []) if c.get("figure") == figure_name), {})


def episode_topics() -> list:
    """Every episode as a topic: (idea, category, scripture, episode)."""
    out = []
    for season in load_story().get("seasons", []):
        for ep in season.get("episodes", []):
            code = f"S{season['number']}E{ep['number']:02d}"
            episode = {"code": code, "season": season["number"], "season_title": season.get("title", ""),
                       **{k: ep[k] for k in ("number", "title", "knight", "place", "weather", "moment", "battle")}}
            out.append((f"{code} · {ep['title']} — {ep['moment']}", ep.get("category", "Deep Dive Analysis"),
                        ep.get("scripture", ""), episode))
    return out


def script_story_block(topic: dict) -> str:
    """Extra script-prompt context for an episode topic ("" for other topics)."""
    ep = topic.get("episode")
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
    ep = topic.get("episode")
    if ep:
        lines.append(f"""THIS VIDEO IS EPISODE {ep['code']} "{ep['title']}". The concept IS this moment — film it, don't invent a different metaphor:
{ep['moment']}
Place: {ep['place']}. Season and light: {ep['weather']}.""")
    return "\n".join(lines) + "\n"
