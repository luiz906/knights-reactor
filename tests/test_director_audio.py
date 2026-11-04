"""Credential-free regression tests for opt-in Knights Reactor music and audio."""
import unittest
from unittest.mock import patch, Mock

from phases.music import build_music_prompt, generate_music
from phases.render import render_video


class MusicTests(unittest.TestCase):
    def test_prompt_is_instrumental_and_story_driven(self):
        with patch("phases.music.Config.MUSIC_PROMPT_OVERRIDE", ""):
            prompt = build_music_prompt(
                {"hook": "Mercy costs something"},
                [{"line": "The knight lowers his sword"}, {"line": "He saves his enemy"}],
            )
        self.assertIn("Mercy costs something", prompt)
        self.assertIn("He saves his enemy", prompt)
        self.assertIn("No words", prompt)

    def test_music_uses_existing_key_with_instrumental_flag(self):
        response = Mock(ok=True, content=b"ID3fake", headers={"content-type": "audio/mpeg"})
        with patch("phases.music.Config.ELEVEN_KEY", "test-key"), patch(
            "phases.music.requests.post", return_value=response
        ) as post:
            music = generate_music({"script_full": "Mercy"}, [], 30, "Original score")
        self.assertEqual(music, b"ID3fake")
        self.assertEqual(post.call_args.kwargs["json"]["model_id"], "music_v2_5")
        self.assertEqual(post.call_args.kwargs["json"]["music_length_ms"], 30000)
        self.assertTrue(post.call_args.kwargs["json"]["force_instrumental"])
        self.assertEqual(post.call_args.kwargs["json"]["prompt"], "Original score")

    def test_missing_key_does_not_call_paid_api(self):
        with patch("phases.music.Config.ELEVEN_KEY", ""), patch(
            "phases.music.requests.post"
        ) as post:
            with self.assertRaises(RuntimeError):
                generate_music({}, [], 30)
        post.assert_not_called()


class RenderAudioTests(unittest.TestCase):
    def _render(self, music=False, sfx=False):
        clips = [{"index": 1, "r2_url": "https://example.test/clip.mp4",
                  "start": 0, "length": 10}]
        posted = {}
        def post(url, **kwargs):
            posted["payload"] = kwargs["json"]
            return Mock(status_code=200, json=lambda: {"response": {"id": "test-job"}},
                        raise_for_status=lambda: None)
        def get(url, **kwargs):
            if "/render/" in url:
                return Mock(status_code=200, json=lambda: {"response": {
                    "status": "done", "url": "https://example.test/final.mp4"}},
                    raise_for_status=lambda: None)
            return Mock(status_code=404, text="not found")
        with patch("phases.render.Config.CTA_ENABLED", False), patch(
            "phases.render.Config.LOGO_ENABLED", False
        ), patch("phases.render.Config.CAPTIONS_ENABLED", False), patch(
            "phases.render.Config.SFX_ENABLED", sfx
        ), patch("phases.render.Config.SFX_VOLUME", 0.25), patch(
            "phases.render.requests.post", side_effect=post
        ), patch("phases.render.requests.get", side_effect=get), patch(
            "phases.render._probe_duration", return_value=10
        ), patch("phases.render.time.sleep"):
            url = render_video(clips, "https://example.test/voice.mp3", "",
                               music_url="https://example.test/music.mp3" if music else None)
        self.assertEqual(url, "https://example.test/final.mp4")
        return posted["payload"]["timeline"]["tracks"]

    def test_music_is_independent_audio_track(self):
        tracks = self._render(music=True)
        srcs = [clip["asset"].get("src") for t in tracks for clip in t["clips"]]
        self.assertIn("https://example.test/voice.mp3", srcs)
        self.assertIn("https://example.test/music.mp3", srcs)

    def test_source_video_audio_defaults_muted(self):
        tracks = self._render()
        video = next(c["asset"] for t in tracks for c in t["clips"]
                     if c["asset"]["type"] == "video")
        self.assertEqual(video["volume"], 0)

    def test_sfx_can_be_explicitly_enabled(self):
        tracks = self._render(sfx=True)
        video = next(c["asset"] for t in tracks for c in t["clips"]
                     if c["asset"]["type"] == "video")
        self.assertEqual(video["volume"], 0.25)


if __name__ == "__main__":
    unittest.main()
