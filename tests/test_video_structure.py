"""Narration-aligned clip structure and estimate regression tests.

No Replicate, ElevenLabs or Shotstack calls. Clip limits are deterministic.
"""
import unittest
from unittest.mock import patch

from phases.timing import build_beats, estimate_beats, estimate_plan, scene_limit, video_plan


VIDEO = "bytedance/seedance-1-lite"
IMAGE = "black-forest-labs/flux-1.1-pro"
SCRIPT = " ".join(["Mercy is stronger than the sword."] * 8)


class VideoStructureTests(unittest.TestCase):
    def setUp(self):
        self.model = patch("phases.timing.model_inputs", return_value=None)
        self.model.start()

    def tearDown(self):
        self.model.stop()

    def test_manual_target_is_met_when_feasible(self):
        beats = estimate_beats(SCRIPT, VIDEO, IMAGE, pacing="manual", target_clips=8)
        self.assertEqual(len(beats), 8)
        self.assertTrue(all(b["length"] <= scene_limit(VIDEO) + 1e-6 for b in beats))
        self.assertEqual(beats[0]["start"], 0)
        self.assertTrue(all(a["end"] == b["start"] for a, b in zip(beats, beats[1:])))

    def test_manual_impossible_count_falls_back_to_closest_feasible(self):
        beats = estimate_beats(SCRIPT, VIDEO, IMAGE, pacing="manual", target_clips=2)
        self.assertGreater(len(beats), 2)
        self.assertTrue(all(b["length"] <= scene_limit(VIDEO) + 1e-6 for b in beats))
        plan = video_plan(beats, VIDEO, IMAGE, pacing="manual", target_clips=2)
        self.assertEqual(plan["target_clips"], 2)
        self.assertFalse(plan["target_met"])

    def test_manual_target_is_clamped(self):
        beats = estimate_beats(SCRIPT, VIDEO, IMAGE, pacing="manual", target_clips=999)
        self.assertGreaterEqual(len(beats), 1)

    def test_auto_and_pacing_modes_cover_same_narration(self):
        plans = [estimate_beats(SCRIPT, VIDEO, IMAGE, pacing=p) for p in ("auto", "slow", "dynamic")]
        self.assertTrue(all(p for p in plans))
        self.assertEqual(len({round(p[-1]["end"], 1) for p in plans}), 1)
        self.assertTrue(all(all(b["length"] <= scene_limit(VIDEO) + 1e-6 for b in p) for p in plans))

    def test_word_estimate_uses_same_pacing_and_cost_planner(self):
        plan = estimate_plan(45, VIDEO, IMAGE, cta_seconds=5, pacing="manual", target_clips=6)
        self.assertTrue(plan["estimated"])
        self.assertEqual(plan["target_clips"], 6)
        self.assertEqual(plan["clips"], len(plan["scene_seconds"]))
        self.assertEqual(plan["cost"]["footage_seconds"], sum(plan["clip_seconds"]))
        self.assertAlmostEqual(plan["video_seconds"], plan["narration_seconds"] + 5, places=1)

    def test_whisper_and_script_only_share_planning_mode(self):
        text = SCRIPT
        estimated = estimate_beats(text, VIDEO, IMAGE, pacing="manual", target_clips=8)
        words = []
        ts = 0.0
        for token in text.split():
            words.append({"word": token, "start": ts, "end": ts + 0.35})
            ts += 0.4
        actual = build_beats({"words": words}, VIDEO, IMAGE, pacing="manual", target_clips=8)
        self.assertEqual(len(actual), 8)
        self.assertEqual(estimated[0]["index"], 1)

    def test_legacy_auto_signature_still_works(self):
        beats = estimate_beats(SCRIPT, VIDEO, IMAGE)
        self.assertTrue(beats)
        self.assertIsNone(video_plan(beats, VIDEO, IMAGE)["target_clips"])


if __name__ == "__main__":
    unittest.main()
