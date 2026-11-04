"""An approved preview must be exactly the film the pipeline begins shooting."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import run_pipeline
from server import verify_approved_screenplay


CAST = {
    "name": "Ser Bramble", "cast_key": "The Knight",
    "description": "blackened armor covered in roses", "ref_image": "",
    "who": "", "wound": "", "desire": "", "arc": "",
    "signature_object": "rose-wrapped shield",
}


def approved_script():
    return {
        "hook": "He recognized the enemy.",
        "build": "This man had betrayed him.",
        "reveal": "He lowered his sword.",
        "command": "He saved him instead.",
        "script_full": "He recognized the enemy. This man had betrayed him. "
                       "He lowered his sword. He saved him instead.",
        "tone": "natural",
        "film_blueprint": {
            "title": "Mercy", "logline": "A knight saves his betrayer.",
            "setting": "Ruined abbey", "goal": "Protect a wounded man",
            "obstacle": "His anger", "stakes": "A man's life",
            "theme": "Mercy is courageous", "final_choice": "Help the enemy",
            "character": CAST,
            "visual_story": [
                {"phase": phase, "dramatic_purpose": phase,
                 "visible_action": "A clear action in " + phase,
                 "change": "The situation changes"}
                for phase in ("setup", "conflict", "choice", "consequence")
            ],
        }
    }


class ApprovedScreenplayTests(unittest.TestCase):
    def test_run_uses_approved_script_without_rewriting(self):
        script = approved_script()
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pipeline.BRAND_DIR", Path(tmp)), \
             patch("pipeline.fetch_topic", return_value={
                 "id": "t1", "idea": "Mercy", "category": "Shocking Revelations",
             }), \
             patch("pipeline.update_topic"), \
             patch("pipeline.generate_script") as write, \
             patch("pipeline.generate_voiceover", side_effect=RuntimeError("test stop")) as voice:
            outcome = run_pipeline(approved_script=script)
            write.assert_not_called()
            self.assertEqual(voice.call_args.args[0], script)
            self.assertEqual(outcome["script"], script)
            checkpoint = json.loads((Path(tmp) / "pipeline_checkpoint.json").read_text())
            self.assertEqual(checkpoint["script"], script)

    def test_cast_reference_cannot_be_changed_at_run_time(self):
        with patch("phases.scenes.get_scene_data", return_value=(
            [{"name": "The Knight", "desc": CAST["description"], "ref_image": ""}],
            {}, {}, {}, {}, [],
        )):
            self.assertEqual(
                verify_approved_screenplay(approved_script())["film_blueprint"]["character"],
                CAST,
            )
            forged = approved_script()
            forged["film_blueprint"]["character"] = {**CAST, "ref_image": "https://fake"}
            with self.assertRaisesRegex(ValueError, "reference"):
                verify_approved_screenplay(forged)

    def test_studio_approval_is_required_and_passed_to_run(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "director-studio.html").read_text()
        js = (root / "director-studio.js").read_text()
        server = (root / "server.py").read_text()
        self.assertIn('id="approve-screenplay"', html)
        self.assertIn('state.approvedDraft=state.draft', js)
        self.assertIn('approved_script:draft.script', js)
        self.assertIn('verify_approved_screenplay(approved_script)', server)


if __name__ == "__main__":
    unittest.main()
