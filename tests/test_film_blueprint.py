"""No-paid-provider regression tests for the screenplay-first foundation."""
import unittest
from pathlib import Path

from phases.film_blueprint import (STORY_PHASES, validate_film_blueprint,
                                  film_assignment, shot_assignment)


ROOT = Path(__file__).resolve().parents[1]
CAST = {
    "name": "Ser Bramble",
    "cast_key": "01_Ser_Bramble",
    "description": "blackened armor covered in roses",
    "ref_image": "https://example.com/approved-reference.png",
    "who": "", "wound": "", "desire": "", "arc": "",
    "signature_object": "rose-wrapped shield",
}


def example_blueprint():
    return {
        "title": "The Price of Mercy",
        "logline": "A knight chooses whether to save his wounded enemy.",
        "setting": "Ruined abbey courtyard, winter morning",
        "goal": "Reach a wounded man", "obstacle": "The man betrayed him",
        "stakes": "The man will die", "theme": "Mercy costs something",
        "final_choice": "He lowers his sword and lifts the man",
        "character": {"name": "AN UNAPPROVED REPLACEMENT", "ref_image": "fake"},
        "visual_story": [
            {"phase": phase, "dramatic_purpose": phase + " matters",
             "visible_action": "A concrete action for " + phase,
             "change": "Something changes during " + phase,
             "narration_intent": "Let the audience see the meaning"}
            for phase in STORY_PHASES
        ],
    }


class FilmBlueprintTests(unittest.TestCase):
    def test_cast_is_locked_even_when_model_tries_to_replace_it(self):
        result = validate_film_blueprint(example_blueprint(), CAST)
        self.assertEqual(result["character"], CAST)
        self.assertEqual(result["visual_story"][2]["phase"], "choice")

    def test_missing_dramatic_action_refuses_generation(self):
        data = example_blueprint()
        data["visual_story"][2]["visible_action"] = ""
        with self.assertRaisesRegex(ValueError, "visible_action"):
            validate_film_blueprint(data, CAST)

    def test_missing_consequence_is_not_a_complete_short_film(self):
        data = example_blueprint()
        data["visual_story"].pop()
        with self.assertRaisesRegex(ValueError, "four screenplay beats"):
            validate_film_blueprint(data, CAST)

    def test_timed_shots_follow_screenplay_instead_of_prompt_randomness(self):
        data = validate_film_blueprint(example_blueprint(), CAST)
        narrated = [
            {"index": i + 1, "start": i * 2.0, "end": (i + 1) * 2.0,
             "length": 2.0, "text": str(i)}
            for i in range(4)
        ]
        result = shot_assignment(data, narrated)
        self.assertEqual([x["phase"] for x in result], list(STORY_PHASES))
        self.assertEqual(result[2]["visible_action"], "A concrete action for choice")

    def test_screenwriter_and_director_are_wired_to_same_blueprint(self):
        script = (ROOT / "phases/script.py").read_text()
        scenes = (ROOT / "phases/scenes.py").read_text()
        self.assertIn("locked_character = select_character(topic)", script)
        self.assertIn("validate_film_blueprint(", script)
        self.assertIn("locked_cast = (film_blueprint or {}).get", scenes)
        self.assertIn("shot_assignment(blueprint, beats)", scenes)
        self.assertIn("stopped rather than insert unrelated stock scenes", scenes)

    def test_film_prompt_requires_real_actions_not_motivational_montage(self):
        instructions = film_assignment(CAST)
        self.assertIn("ONE coherent dramatic work", instructions)
        self.assertIn("decisions and consequences", instructions)
        self.assertIn("modern teenage and young adult men", instructions)


if __name__ == "__main__":
    unittest.main()
