import os
import tempfile
import unittest
from pathlib import Path


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        os.environ["SHOWCASE_DB"] = str(Path(self.directory.name) / "demo.sqlite3")
        os.environ["SHOWCASE_CSRF_TOKEN"] = "candidate-test-token"
        from app import main
        self.web = main

    def tearDown(self):
        self.directory.cleanup()
        os.environ.pop("SHOWCASE_DB", None)
        os.environ.pop("SHOWCASE_CSRF_TOKEN", None)

    def test_synthetic_catalog_generates_all_three_slots(self):
        target = self.web.store()
        self.web.prepare_demo(target, "2026-01-03")
        daily = target.get_list("2026-01-03")
        self.assertEqual({"video", "read", "podcast"}, {pick["kind"] for pick in daily["picks"]})
        self.assertEqual("Maps for Thought", target.book()["nonfiction_title"])

    def test_reload_keeps_a_deferred_pick_until_explicit_refresh(self):
        target = self.web.store()
        day = "2026-01-02"
        self.web.prepare_demo(target, day)
        initial = target.get_list(day)["picks"][0]
        target.feedback(initial["id"], "not_started", now="now", expected_candidate_id=initial["candidate_id"])
        self.web.prepare_demo(target, day)
        self.assertEqual("demo-video-1", target.get_list(day)["picks"][0]["candidate_id"])
        self.web.prepare_demo(target, day, refresh=True)
        self.assertEqual("demo-video-2", target.get_list(day)["picks"][0]["candidate_id"])

    def test_template_renders_the_synthetic_daily_page(self):
        target = self.web.store()
        self.web.prepare_demo(target, "2026-01-04")
        daily = target.get_list("2026-01-04")
        body = self.web.templates.get_template("home.html").render(
            daily=daily, failed_today=None, book=target.book(), saved_episodes=[], saved_by_candidate={},
            today="2026-01-04", csrf="candidate-test-token", note_saved_pick_id=None,
        )
        self.assertTrue(
            "How a small system supports attention" in body or "A second synthetic attention practice" in body
        )
        self.assertIn("An example long-form conversation", body)
        self.assertIn("Maps for Thought", body)

    def test_feedback_requires_matching_candidate_and_token(self):
        target = self.web.store()
        self.web.prepare_demo(target, "2026-01-02")
        pick = target.get_list("2026-01-02")["picks"][0]
        with self.assertRaises(Exception) as denied:
            self.web.submit_feedback(pick["id"], "completed", reason="", video_timestamp="", podcast_timestamp="", book_page="",
                                     candidate_id=pick["candidate_id"], csrf_token="wrong")
        self.assertEqual(403, denied.exception.status_code)
        with self.assertRaises(Exception) as stale:
            self.web.submit_feedback(pick["id"], "completed", reason="", video_timestamp="", podcast_timestamp="", book_page="",
                                     candidate_id="other", csrf_token="candidate-test-token")
        self.assertEqual(400, stale.exception.status_code)
        response = self.web.submit_feedback(pick["id"], "completed", reason="", video_timestamp="", podcast_timestamp="", book_page="",
                                            candidate_id=pick["candidate_id"], csrf_token="candidate-test-token")
        self.assertEqual(303, response.status_code)
        self.assertEqual("completed", target.get_list("2026-01-02")["picks"][0]["state"])


if __name__ == "__main__":
    unittest.main()
