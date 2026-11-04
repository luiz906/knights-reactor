"""Director Studio structural regression tests (no paid providers)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class DirectorStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "director-studio.html").read_text()
        cls.js = (ROOT / "director-studio.js").read_text()
        cls.css = (ROOT / "director-studio.css").read_text()
        cls.server = (ROOT / "server.py").read_text()

    def test_parallel_review_route_does_not_replace_classic(self):
        self.assertIn('@app.get("/studio")', self.server)
        self.assertIn('@app.get("/", response_class=HTMLResponse)', self.server)
        self.assertIn('director-studio.html', self.server)

    def test_original_prototype_stages_exist(self):
        for name in ("story-panel", "continuity-panel", "timeline-panel"):
            self.assertIn('id="' + name + '"', self.html)
        for name in ("story-goal", "story-conflict", "story-choice"):
            self.assertIn('id="' + name + '"', self.html)
        for word in ("CREATIVE BRIEF", "VISUAL CONTINUITY", "AUDIO &amp; TIMELINE"):
            self.assertIn(word, self.html)

    def test_studio_is_wired_to_existing_api(self):
        for path in (
            "/api/login", "/api/settings", "/api/topics", "/api/scenes",
            "/api/story", "/api/plan-estimate", "/api/run",
            "/api/status", "/api/prompts", "/api/prompts/save",
            "/api/images/review", "/api/images/approve",
            "/api/videos/review", "/api/videos/approve", "/api/resume",
        ):
            self.assertIn(path, self.js, path)

    def test_no_unmapped_static_dom_ids(self):
        declared = set(re.findall(r'\bid="([^"]+)"', self.html))
        accessed = set(re.findall(r'\$\("([^"]+)"\)', self.js))
        self.assertFalse(accessed - declared, accessed - declared)
        self.assertEqual(len(declared), len(re.findall(r'\bid="([^"]+)"', self.html)))

    def test_live_operations_confirmed(self):
        self.assertIn('confirmAction("Start paid production?"', self.js)
        self.assertIn('confirmAction("Approve this production stage?"', self.js)
        self.assertIn('confirmAction("Regenerate this "+kind+"?"', self.js)
        self.assertIn("possibly AUTOMATICALLY PUBLISH", self.js)

    def test_existing_creative_brief_receives_story_pillars(self):
        for key in ("story_goal", "story_conflict", "story_choice"):
            self.assertIn('s.' + key, self.js)
            self.assertIn('s.get("' + key + '")', self.server)
        self.assertIn('Config.CREATIVE_DIRECTION', self.server)

    def test_mobile_navigation_available(self):
        self.assertIn('class="mobile-nav"', self.html)
        self.assertIn('.mobile-nav{display:flex', self.css)


if __name__ == "__main__":
    unittest.main()
