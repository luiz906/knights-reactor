"""The story-first studio UI must affect both AI writing and shot direction.

No paid provider calls: requests are mocked. Keep existing saved settings usable.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config import Config
from phases.script import generate_script
from phases.scenes import generate_ai_scenes


class CreativeBriefTests(unittest.TestCase):
    def test_creative_brief_informs_script_writer(self):
        payload = {
            "hook": "A knight at a closed gate",
            "build": "He must make a choice",
            "reveal": "Mercy changes the outcome",
            "command": "Choose mercy",
            "script_full": "A knight faces a choice. He chooses mercy.",
            "tone": "resolute",
        }
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
        response.raise_for_status.return_value = None
        with patch.object(Config, "CREATIVE_DIRECTION", "A costly decision at a ruined chapel"), \
             patch("phases.script.requests.post", return_value=response) as api:
            script = generate_script({"idea": "The price of mercy", "category": "Shocking Revelations", "scripture": "Luke 6:36"})
        self.assertEqual(script["tone"], "resolute")
        prompt = api.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("A costly decision at a ruined chapel", prompt)
        self.assertIn("CREATIVE BRIEF", prompt)

    def test_creative_brief_informs_ai_shot_writer(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": json.dumps({
            "concept": "An abbey door opens to an injured man",
            "mood": "dawn",
            "clips": [{"image_prompt": "A knight opens a stone doorway in dawn light, photorealistic film still.",
                       "motion_prompt": "Camera pushes forward as the knight opens a doorway."}],
        })}}]}
        script = {"hook": "Mercy", "build": "Pain", "reveal": "Hope", "command": "Help",
                  "tone": "measured", "script_full": "Mercy changes the story."}
        beats = [{"index": 1, "start": 0, "length": 5.0, "text": "Mercy changes the story."}]
        with patch.object(Config, "CREATIVE_DIRECTION", "Make the decisive action shielding the enemy"), \
             patch("phases.scenes.requests.post", return_value=response) as api:
            result = generate_ai_scenes(
                script, {"idea": "Mercy", "category": "Deep Dive Analysis"},
                "a knight wearing dark steel armor", beats,
                {"dawn": "warm sunrise over an abbey"}, figure_name="The Veteran"
            )
        self.assertEqual(len(result["clips"]), 1)
        self.assertIn("Make the decisive action shielding the enemy", api.call_args.kwargs["json"]["messages"][0]["content"])

    def test_brief_and_director_present_on_desktop_and_mobile(self):
        dashboard = (Path(__file__).resolve().parents[1] / "dashboard.html").read_text()
        for target in ("d-brief-fields", "m-brief-fields", "d-director-fields", "m-director-fields"):
            self.assertIn('id="' + target + '"', dashboard)
        self.assertIn("ADVANCED SETUP", dashboard)
        self.assertIn("body:JSON.stringify({production_mode:PRODUCTION_MODE})", dashboard)

    def test_saved_brand_settings_remain_available_in_advanced(self):
        dashboard = (Path(__file__).resolve().parents[1] / "dashboard.html").read_text()
        self.assertIn("'brand_persona'", dashboard)
        self.assertIn("'brand_voice'", dashboard)
        self.assertIn("'creative_direction'", dashboard)
        self.assertIn("const panels={brief:'',director:'',settings:'',advanced:''}", dashboard)


if __name__ == "__main__":
    unittest.main()
