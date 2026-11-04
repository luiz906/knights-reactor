"""Regression tests for standalone versus series topic routing."""
import unittest
from unittest.mock import patch
from phases.topics import _select_topic, peek_next_topic, topic_mode
from phases.story import scene_story_block

class ProductionModeTests(unittest.TestCase):
    def setUp(self):
        self.topics=[
            {"id":"ep1","status":"new","idea":"Episode 1","episode":{"code":"S1E01"}},
            {"id":"stand1","status":"new","idea":"Independent story"},
            {"id":"ep2","status":"executed","episode":{"code":"S1E02"}},
        ]

    def test_mode_classifies_episodes(self):
        self.assertEqual(topic_mode(self.topics[0]),"series")
        self.assertEqual(topic_mode(self.topics[1]),"standalone")

    def test_series_finds_only_queued_episode(self):
        self.assertEqual(_select_topic(self.topics,production_mode="series")["id"],"ep1")

    def test_standalone_skips_queued_series(self):
        self.assertEqual(_select_topic(self.topics,production_mode="standalone")["id"],"stand1")

    def test_legacy_unfiltered_behavior(self):
        self.assertEqual(_select_topic(self.topics)["id"],"ep1")

    def test_specific_topic_cannot_cross_mode(self):
        with self.assertRaisesRegex(RuntimeError,"not a standalone"):
            _select_topic(self.topics,topic_id="ep1",production_mode="standalone")

    def test_filtered_queue_has_clear_error(self):
        with self.assertRaisesRegex(RuntimeError,"No new topics for series"):
            _select_topic([self.topics[1]],production_mode="series")

    def test_preview_has_no_side_effects(self):
        with patch("phases.topics.load_topics",return_value=self.topics):
            preview=peek_next_topic(production_mode="series")
        self.assertEqual(preview["id"],"ep1")
        self.assertEqual(self.topics[0]["status"],"new")

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            _select_topic(self.topics,production_mode="invalid")

    def test_standalone_does_not_import_series_world(self):
        with patch("phases.story.load_story") as bible:
            block=scene_story_block({"idea":"Mercy"}, "The Veteran")
        self.assertEqual(block,"")
        bible.assert_not_called()

if __name__ == "__main__":
    unittest.main()
