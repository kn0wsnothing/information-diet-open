import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import cli
from app.store import Store


CATALOG = {
    "book": {"nonfiction_title": "A user book", "reported_page": 12, "daily_pace": 4, "fiction_title": ""},
    "candidates": [
        {"id": "video-one", "kind": "video", "title": "A user video", "summary": "A real user summary.",
         "why": "A real reason.", "url": "https://www.youtube.com/watch?v=user-video",
         "source_url": "https://www.youtube.com/watch?v=user-video", "duration_minutes": 20,
         "inspection_method": "user review", "inspected_at": "2026-01-01T00:00:00+00:00", "provenance": "user catalog"},
        {"id": "read-one", "kind": "read", "title": "A user read", "summary": "A real user summary.",
         "why": "A real reason.", "url": "https://example.invalid/user-read", "inspection_method": "user review",
         "inspected_at": "2026-01-01T00:00:00+00:00", "provenance": "user catalog"},
        {"id": "podcast-one", "kind": "podcast", "title": "A user podcast", "summary": "A real user summary.",
         "why": "A real reason.", "url": "https://example.invalid/user-podcast", "duration_minutes": 45,
         "inspection_method": "user review", "inspected_at": "2026-01-01T00:00:00+00:00", "provenance": "user catalog"},
    ],
}


class CandidateTests(unittest.TestCase):
    def test_empty_template_rejects_before_database_then_user_catalog_prepares_all_slots(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"INFORMATION_DIET_DATA_DIR": directory}, clear=False):
            self.assertEqual(0, cli.main(["init"]))
            catalog_path = Path(directory) / "catalog.json"
            self.assertEqual([], json.loads(catalog_path.read_text())["candidates"])
            database = Path(directory) / "information-diet.sqlite3"
            with self.assertRaises(SystemExit) as validate_error:
                cli.main(["validate"])
            self.assertEqual(2, validate_error.exception.code)
            with self.assertRaises(SystemExit) as prepare_error:
                cli.main(["prepare"])
            self.assertEqual(2, prepare_error.exception.code)
            self.assertFalse(database.exists())
            catalog_path.write_text(json.dumps(CATALOG), encoding="utf-8")
            self.assertEqual(0, cli.main(["validate"]))
            self.assertEqual(0, cli.main(["prepare"]))
            reopened = Store(database)
            daily = reopened.get_list(cli.hkt_date())
            self.assertEqual({"video", "read", "podcast"}, {pick["kind"] for pick in daily["picks"]})
            self.assertEqual("A user book", reopened.book()["nonfiction_title"])
            self.assertEqual(0, cli.main(["prepare"]))

    def test_catalog_with_video_and_podcast_can_omit_optional_read(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"INFORMATION_DIET_DATA_DIR": directory}, clear=False):
            catalog_path = Path(directory) / "catalog.json"
            catalog = {**CATALOG, "candidates": [item for item in CATALOG["candidates"] if item["kind"] != "read"]}
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            self.assertEqual(0, cli.main(["validate"]))
            self.assertEqual(0, cli.main(["prepare"]))
            daily = Store(Path(directory) / "information-diet.sqlite3").get_list(cli.hkt_date())
            self.assertEqual({"video", "podcast"}, {pick["kind"] for pick in daily["picks"]})

    def test_saved_episode_progress_and_notes_survive_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "state.sqlite3"
            store = Store(database)
            store.setup()
            store.seed_books(CATALOG["book"])
            store.generate("2026-01-02", CATALOG, "now")
            podcast = next(item for item in store.get_list("2026-01-02")["picks"] if item["kind"] == "podcast")
            saved = store.add_saved_episode(podcast["title"], "A user show", candidate_id=podcast["candidate_id"], now="now")
            store.update_saved_episode(saved["id"], "listening", "12:34", "later")
            store.save_saved_episode_note(saved["id"], "Useful idea", "later")
            reopened = Store(database).list_saved_episodes()[0]
            self.assertEqual("listening", reopened["state"])
            self.assertEqual("12:34", reopened["playback_position"])
            self.assertEqual("Useful idea", reopened["notes"][0]["note"])

    def test_empty_state_guides_manual_initialization(self):
        from app.main import templates

        body = templates.get_template("home.html").render(
            daily=None, failed_today=None, book=None, saved_episodes=[], saved_by_candidate={}, today="2026-01-02",
            csrf="test-token", note_saved_pick_id=None, catalog_exists=False,
        )
        self.assertIn("information-diet init", body)
        self.assertNotIn("synthetic", body.casefold())


if __name__ == "__main__":
    unittest.main()
