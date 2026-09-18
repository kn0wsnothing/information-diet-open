import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS daily_lists (
  date TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready', source_status TEXT NOT NULL DEFAULT 'ok', source_message TEXT, book_target INTEGER
);
CREATE TABLE IF NOT EXISTS picks (
  id INTEGER PRIMARY KEY, list_date TEXT NOT NULL REFERENCES daily_lists(date), slot TEXT NOT NULL,
  candidate_id TEXT, title TEXT NOT NULL, kind TEXT NOT NULL, summary TEXT, why TEXT, url TEXT,
  duration_minutes INTEGER, podcast_url TEXT, podcast_verified INTEGER NOT NULL DEFAULT 0, snipd_url TEXT, snipd_direct INTEGER NOT NULL DEFAULT 0,
  stopping_point TEXT, provenance TEXT, inspection_method TEXT, inspected_at TEXT,
  state TEXT NOT NULL DEFAULT 'active', last_video_timestamp TEXT, last_podcast_timestamp TEXT, UNIQUE(list_date, slot)
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY, pick_id INTEGER NOT NULL REFERENCES picks(id), disposition TEXT NOT NULL,
  candidate_id TEXT, reason TEXT, video_timestamp TEXT, podcast_timestamp TEXT, book_page INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY CHECK(id=1), nonfiction_title TEXT NOT NULL, author TEXT, total_pages INTEGER,
  reported_page INTEGER NOT NULL, daily_pace INTEGER NOT NULL, fiction_title TEXT
);
CREATE TABLE IF NOT EXISTS video_notes (
  id INTEGER PRIMARY KEY, pick_id INTEGER NOT NULL REFERENCES picks(id), candidate_id TEXT NOT NULL,
  note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_episodes (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, show TEXT NOT NULL, episode_url TEXT,
  canonical_url TEXT, identity_key TEXT NOT NULL UNIQUE, candidate_id TEXT, snipd_url TEXT,
  state TEXT NOT NULL DEFAULT 'saved', playback_position TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_episode_notes (
  id INTEGER PRIMARY KEY, episode_id INTEGER NOT NULL REFERENCES saved_episodes(id),
  note TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

SAVED_EPISODE_STATES = {"saved", "listening", "completed"}
MAX_TITLE_LENGTH = 500
MAX_SHOW_LENGTH = 300
MAX_URL_LENGTH = 2048
MAX_POSITION_LENGTH = 100
MAX_NOTE_LENGTH = 10000


def _clean_text(value, field, maximum, required=False):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} is too long")
    return cleaned


def _canonical_episode_url(value):
    if not isinstance(value, str):
        raise ValueError("episode url must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > MAX_URL_LENGTH:
        raise ValueError("episode url is too long")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("episode url must be a direct https link")
    host = parsed.hostname.lower() if parsed.hostname else ""
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("episode url must be a direct https link") from error
    if port and port != 443:
        host = f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in {"fbclid", "gclid"} and not key.casefold().startswith("utm_")
        ),
        doseq=True,
    )
    return urlunparse(("https", host, path, "", query, ""))


def _validated_snipd_episode_url(value):
    if not isinstance(value, str):
        raise ValueError("Snipd url must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > MAX_URL_LENGTH:
        raise ValueError("Snipd url is too long")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "share.snipd.com"
        or not parsed.path.startswith("/episode/")
        or not parsed.path[len("/episode/") :].strip("/")
    ):
        raise ValueError("Snipd url must be a direct episode share link")
    return value


def _saved_episode_identity(title, show, canonical_url):
    if canonical_url:
        return f"url:{canonical_url}"
    return f"name:{show.casefold()}|{title.casefold()}"


def _saved_episode_timestamp(value):
    if value == "":
        return datetime.now(timezone.utc).isoformat()
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be text")
    return value


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)

    @contextmanager
    def tx(self):
        conn = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def setup(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)
            columns = {r[1] for r in conn.execute("PRAGMA table_info(daily_lists)")}
            if "book_target" not in columns:
                conn.execute("ALTER TABLE daily_lists ADD COLUMN book_target INTEGER")
            pick_columns = {r[1] for r in conn.execute("PRAGMA table_info(picks)")}
            if "last_video_timestamp" not in pick_columns:
                conn.execute("ALTER TABLE picks ADD COLUMN last_video_timestamp TEXT")
            if "last_podcast_timestamp" not in pick_columns:
                conn.execute("ALTER TABLE picks ADD COLUMN last_podcast_timestamp TEXT")
            if "snipd_url" not in pick_columns:
                conn.execute("ALTER TABLE picks ADD COLUMN snipd_url TEXT")
            if "snipd_direct" not in pick_columns:
                conn.execute("ALTER TABLE picks ADD COLUMN snipd_direct INTEGER NOT NULL DEFAULT 0")
            feedback_columns = {r[1] for r in conn.execute("PRAGMA table_info(feedback)")}
            if "candidate_id" not in feedback_columns:
                conn.execute("ALTER TABLE feedback ADD COLUMN candidate_id TEXT")
                conn.execute(
                    "UPDATE feedback SET candidate_id=(SELECT candidate_id FROM picks WHERE picks.id=feedback.pick_id)"
                )
            if "podcast_timestamp" not in feedback_columns:
                conn.execute("ALTER TABLE feedback ADD COLUMN podcast_timestamp TEXT")
            saved_episode_columns = {r[1] for r in conn.execute("PRAGMA table_info(saved_episodes)")}
            if "candidate_id" not in saved_episode_columns:
                conn.execute("ALTER TABLE saved_episodes ADD COLUMN candidate_id TEXT")
            conn.execute("PRAGMA journal_mode=WAL")

    def seed_books(self, book: dict):
        reported, pace, total = (
            int(book.get("reported_page", 0)),
            int(book.get("daily_pace", 7)),
            book.get("total_pages"),
        )
        total = int(total) if total is not None else None
        if reported < 0 or pace < 0 or (total is not None and (total < 0 or reported > total)):
            raise ValueError("invalid nonfiction page state")
        with self.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO books VALUES (1,?,?,?,?,?,?)",
                (book["nonfiction_title"], book.get("author"), total, reported, pace, book.get("fiction_title")),
            )

    def book(self):
        with sqlite3.connect(self.path) as c:
            c.row_factory = sqlite3.Row
            row = c.execute("SELECT * FROM books WHERE id=1").fetchone()
            return dict(row) if row else None

    def get_list(self, day):
        with sqlite3.connect(self.path) as c:
            c.row_factory = sqlite3.Row
            daily = c.execute("SELECT * FROM daily_lists WHERE date=?", (day,)).fetchone()
            if not daily:
                return None
            picks = c.execute("SELECT * FROM picks WHERE list_date=? ORDER BY id", (day,)).fetchall()
            result = dict(daily)
            result["picks"] = [dict(x) for x in picks]
            for pick in result["picks"]:
                pick["note_history"] = []
                if pick["kind"] in {"video", "podcast"}:
                    pick["note_history"] = [
                        dict(note)
                        for note in c.execute(
                            "SELECT note, created_at FROM video_notes WHERE candidate_id=? AND note<>'' ORDER BY id DESC",
                            (pick["candidate_id"],),
                        )
                    ]
            return result

    def latest_list(self):
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT date FROM daily_lists WHERE status='ready' ORDER BY date DESC LIMIT 1").fetchone()
        return self.get_list(row[0]) if row else None

    def feedback(
        self,
        pick_id,
        disposition,
        reason="",
        video_timestamp="",
        book_page=None,
        now="",
        expected_candidate_id=None,
        podcast_timestamp="",
    ):
        if disposition not in {"completed", "continue", "not_started", "not_interesting"}:
            raise ValueError("bad disposition")
        with self.tx() as c:
            pick = c.execute("SELECT * FROM picks WHERE id=?", (pick_id,)).fetchone()
            if not pick:
                raise KeyError("pick not found")
            if expected_candidate_id is not None and pick["candidate_id"] != expected_candidate_id:
                raise ValueError("This recommendation changed. Reload the page before saving feedback.")
            state = {
                "completed": "completed",
                "continue": "continue",
                "not_started": "active",
                "not_interesting": "dropped",
            }[disposition]
            c.execute(
                """UPDATE picks SET state=?,
                    last_video_timestamp=CASE WHEN ? <> '' THEN ? ELSE last_video_timestamp END,
                    last_podcast_timestamp=CASE WHEN ? <> '' THEN ? ELSE last_podcast_timestamp END
                    WHERE id=?""",
                (state, video_timestamp, video_timestamp, podcast_timestamp, podcast_timestamp, pick_id),
            )
            c.execute(
                """INSERT INTO feedback(pick_id,disposition,candidate_id,reason,video_timestamp,podcast_timestamp,book_page,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (pick_id, disposition, pick["candidate_id"], reason, video_timestamp, podcast_timestamp, book_page, now),
            )
            if book_page is not None:
                book = c.execute("SELECT total_pages FROM books WHERE id=1").fetchone()
                if int(book_page) < 0 or (
                    book and book["total_pages"] is not None and int(book_page) > book["total_pages"]
                ):
                    raise ValueError("invalid book page")
                c.execute("UPDATE books SET reported_page=? WHERE id=1", (int(book_page),))

    def save_media_note(self, pick_id, candidate_id, note, now):
        if not isinstance(note, str) or not note.strip():
            raise ValueError("A note cannot be empty")
        with self.tx() as c:
            pick = c.execute("SELECT candidate_id, kind FROM picks WHERE id=?", (pick_id,)).fetchone()
            if not pick:
                raise KeyError("pick not found")
            if pick["candidate_id"] != candidate_id:
                raise ValueError("This recommendation changed. Reload before saving a note.")
            if pick["kind"] not in {"video", "podcast"}:
                raise ValueError("Notes are available for videos and podcasts only")
            c.execute(
                "INSERT INTO video_notes(pick_id,candidate_id,note,created_at) VALUES (?,?,?,?)",
                (pick_id, candidate_id, note.strip(), now),
            )

    def save_video_note(self, pick_id, candidate_id, note, now):
        """Compatibility wrapper for callers that still use the video-specific name."""
        self.save_media_note(pick_id, candidate_id, note, now)

    def list_saved_episodes(self):
        with sqlite3.connect(self.path) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT * FROM saved_episodes
                ORDER BY CASE state WHEN 'listening' THEN 0 WHEN 'saved' THEN 1 ELSE 2 END,
                    updated_at DESC, id DESC"""
            ).fetchall()
            return [self._saved_episode_with_notes(c, row) for row in rows]

    def add_saved_episode(self, title, show, url="", snipd_url="", now="", candidate_id=""):
        title = _clean_text(title, "title", MAX_TITLE_LENGTH, required=True)
        show = _clean_text(show, "show", MAX_SHOW_LENGTH, required=True)
        canonical_url = _canonical_episode_url(url)
        snipd_url = _validated_snipd_episode_url(snipd_url)
        candidate_id = _clean_text(candidate_id, "candidate id", MAX_TITLE_LENGTH)
        timestamp = _saved_episode_timestamp(now)
        with self.tx() as c:
            existing = self._matching_saved_episode(c, title, show, canonical_url, candidate_id)
            if existing:
                updates = {}
                if candidate_id and not existing["candidate_id"]:
                    updates["candidate_id"] = candidate_id
                if canonical_url and not existing["canonical_url"]:
                    updates["episode_url"] = canonical_url
                    updates["canonical_url"] = canonical_url
                if snipd_url and not existing["snipd_url"]:
                    updates["snipd_url"] = snipd_url
                if updates:
                    updates["updated_at"] = timestamp
                    assignments = ",".join(f"{field}=?" for field in updates)
                    c.execute(f"UPDATE saved_episodes SET {assignments} WHERE id=?", (*updates.values(), existing["id"]))
                    existing = c.execute("SELECT * FROM saved_episodes WHERE id=?", (existing["id"],)).fetchone()
                return self._saved_episode_with_notes(c, existing)
            identity = _saved_episode_identity(title, show, canonical_url)
            inserted = c.execute(
                """INSERT INTO saved_episodes(
                    title,show,episode_url,canonical_url,identity_key,candidate_id,snipd_url,state,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,'saved',?,?)""",
                (title, show, canonical_url, canonical_url, identity, candidate_id or None, snipd_url, timestamp, timestamp),
            )
            row = c.execute("SELECT * FROM saved_episodes WHERE id=?", (inserted.lastrowid,)).fetchone()
            return self._saved_episode_with_notes(c, row)

    def update_saved_episode(self, episode_id, state, position="", now=""):
        if state not in SAVED_EPISODE_STATES:
            raise ValueError("invalid saved episode state")
        position = _clean_text(position, "playback position", MAX_POSITION_LENGTH)
        timestamp = _saved_episode_timestamp(now)
        with self.tx() as c:
            existing = c.execute("SELECT * FROM saved_episodes WHERE id=?", (episode_id,)).fetchone()
            if not existing:
                raise KeyError("saved episode not found")
            c.execute(
                "UPDATE saved_episodes SET state=?, playback_position=?, updated_at=? WHERE id=?",
                (state, position or None, timestamp, episode_id),
            )
            row = c.execute("SELECT * FROM saved_episodes WHERE id=?", (episode_id,)).fetchone()
            return self._saved_episode_with_notes(c, row)

    def save_saved_episode_note(self, episode_id, note, now=""):
        note = _clean_text(note, "note", MAX_NOTE_LENGTH, required=True)
        timestamp = _saved_episode_timestamp(now)
        with self.tx() as c:
            if not c.execute("SELECT 1 FROM saved_episodes WHERE id=?", (episode_id,)).fetchone():
                raise KeyError("saved episode not found")
            c.execute(
                "INSERT INTO saved_episode_notes(episode_id,note,created_at) VALUES (?,?,?)",
                (episode_id, note, timestamp),
            )
            c.execute("UPDATE saved_episodes SET updated_at=? WHERE id=?", (timestamp, episode_id))

    def _saved_episode_with_notes(self, c, row):
        result = dict(row)
        notes = [
            {"note": note["note"], "created_at": note["created_at"], "source": "saved", "id": note["id"]}
            for note in c.execute(
                "SELECT id,note,created_at FROM saved_episode_notes WHERE episode_id=?", (row["id"],)
            )
        ]
        if row["candidate_id"]:
            notes.extend(
                {"note": note["note"], "created_at": note["created_at"], "source": "pick", "id": note["id"]}
                for note in c.execute(
                    "SELECT id,note,created_at FROM video_notes WHERE candidate_id=? AND note<>''", (row["candidate_id"],)
                )
            )
            if not result["playback_position"]:
                position = c.execute(
                    """SELECT last_podcast_timestamp FROM picks
                    WHERE candidate_id=? AND last_podcast_timestamp<>''
                    ORDER BY list_date DESC, id DESC LIMIT 1""",
                    (row["candidate_id"],),
                ).fetchone()
                if position:
                    result["playback_position"] = position["last_podcast_timestamp"]
        deduplicated = {}
        for note in notes:
            deduplicated.setdefault((note["note"], note["created_at"]), note)
        result["notes"] = [
            {"note": note["note"], "created_at": note["created_at"]}
            for note in sorted(
                deduplicated.values(),
                key=lambda note: (note["created_at"], note["source"] == "saved", note["id"]),
                reverse=True,
            )
        ]
        return result

    def _matching_saved_episode(self, c, title, show, canonical_url, candidate_id):
        rows = c.execute("SELECT * FROM saved_episodes ORDER BY id").fetchall()
        normalized_name = _saved_episode_identity(title, show, None)
        for row in rows:
            if candidate_id and row["candidate_id"] == candidate_id:
                return row
        for row in rows:
            if canonical_url and row["canonical_url"] == canonical_url:
                return row
        for row in rows:
            if _saved_episode_identity(row["title"], row["show"], None) == normalized_name:
                return row
        return None

    def rejected_ids(self):
        with sqlite3.connect(self.path) as c:
            return {
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT candidate_id FROM feedback "
                    "WHERE disposition='not_interesting' AND candidate_id IS NOT NULL"
                )
            }

    def report_book_page(self, page):
        page = int(page)
        with self.tx() as c:
            book = c.execute("SELECT total_pages FROM books WHERE id=1").fetchone()
            if not book:
                raise RuntimeError("Book state is not seeded")
            if page < 0 or (book["total_pages"] is not None and page > book["total_pages"]):
                raise ValueError("invalid book page")
            c.execute("UPDATE books SET reported_page=? WHERE id=1", (page,))

    def record_source_failure(self, day, now, message):
        """Keep ready picks readable; a failure is status, never fabricated content."""
        with self.tx() as c:
            row = c.execute("SELECT status FROM daily_lists WHERE date=?", (day,)).fetchone()
            if row:
                c.execute(
                    "UPDATE daily_lists SET source_status='failed', source_message=? WHERE date=?", (message, day)
                )
            else:
                c.execute(
                    "INSERT INTO daily_lists(date,created_at,status,source_status,source_message) VALUES (?,?,'failed','failed',?)",
                    (day, now, message),
                )

    def generate(self, day, catalog, now, source_failure=None, refresh=False):
        """Create once; explicit refresh only replaces reconsiderable picks."""
        with self.tx() as c:
            existing = c.execute("SELECT status FROM daily_lists WHERE date=?", (day,)).fetchone()
            if existing:
                if existing["status"] == "failed":
                    # A later good source recovers the marker and creates today's list.
                    c.execute("DELETE FROM daily_lists WHERE date=?", (day,))
                    existing = None
                else:
                    c.execute("UPDATE daily_lists SET source_status='ok', source_message=NULL WHERE date=?", (day,))
                # Explicit refresh changes only candidates the user dropped. It never
                # overwrites a completed, active, or continuing item.
                if existing and not refresh:
                    return False
                if existing:
                    return self._refresh(c, day, catalog)
            if source_failure:
                last = c.execute(
                    "SELECT date FROM daily_lists WHERE status='ready' ORDER BY date DESC LIMIT 1"
                ).fetchone()
                c.execute(
                    "INSERT INTO daily_lists(date,created_at,status,source_status,source_message) VALUES (?,?, 'failed','failed',?)",
                    (day, now, source_failure),
                )
                return bool(last)
            book = c.execute("SELECT * FROM books WHERE id=1").fetchone()
            if not book:
                raise RuntimeError("book state is not seeded")
            target = book["reported_page"] + book["daily_pace"]
            if book["total_pages"] is not None:
                target = min(target, book["total_pages"])
            c.execute(
                "INSERT INTO daily_lists(date,created_at,status,book_target) VALUES (?,?, 'ready',?)",
                (day, now, target),
            )
            # Every unresolved slot carries. A plain "didn't start" is neither a
            # rejection nor backlog: the new day may select a different candidate.
            carry = self._carry_for_slot(c, "lunch", day)
            if carry:
                self._insert_pick(c, day, "lunch", dict(carry), "active")
            else:
                excluded = self._excluded_ids(c)
                deferred = self._temporarily_deferred_ids(c, day)
                videos = [
                    x
                    for x in catalog["candidates"]
                    if x["kind"] == "video" and x["id"] not in excluded and x["id"] not in deferred
                ]
                if videos:
                    self._insert_pick(c, day, "lunch", videos[0], "active")
            carry = self._carry_for_slot(c, "listen", day)
            if carry:
                self._insert_pick(c, day, "listen", dict(carry), "active")
            else:
                excluded = self._excluded_ids(c)
                deferred = self._temporarily_deferred_ids(c, day)
                podcasts = [
                    x
                    for x in catalog["candidates"]
                    if x["kind"] == "podcast" and x["id"] not in excluded and x["id"] not in deferred
                ]
                if podcasts:
                    self._insert_pick(c, day, "listen", podcasts[0], "active")
            carry = self._carry_for_slot(c, "gap_read", day)
            if carry:
                self._insert_pick(c, day, "gap_read", dict(carry), "active")
            else:
                excluded = self._excluded_ids(c)
                deferred = self._temporarily_deferred_ids(c, day)
                reads = [
                    x
                    for x in catalog["candidates"]
                    if x["kind"] == "read" and x["id"] not in excluded and x["id"] not in deferred
                ]
                if reads:
                    self._insert_pick(c, day, "gap_read", reads[0], "active")
            return True

    def _carry_for_slot(self, c, slot, day):
        return c.execute(
            """SELECT p.* FROM picks p WHERE p.slot=? AND p.list_date < ? AND p.state IN ('active','continue')
                AND COALESCE((SELECT f.disposition FROM feedback f
                    WHERE f.pick_id=p.id AND f.candidate_id=p.candidate_id
                    ORDER BY f.id DESC LIMIT 1), '') IN ('','continue')
                AND NOT EXISTS (SELECT 1 FROM picks later WHERE later.slot=p.slot AND later.candidate_id=p.candidate_id
                    AND later.list_date>p.list_date AND later.list_date<?)
                AND NOT EXISTS (SELECT 1 FROM saved_episodes saved
                    WHERE saved.candidate_id=p.candidate_id AND saved.state='completed')
                ORDER BY p.list_date DESC LIMIT 1""",
            (slot, day, day),
        ).fetchone()

    def _excluded_ids(self, c):
        return {
            r[0]
            for r in c.execute(
                """SELECT DISTINCT candidate_id FROM feedback WHERE disposition IN ('completed','not_interesting')
                UNION SELECT DISTINCT candidate_id FROM saved_episodes
                WHERE state='completed' AND candidate_id IS NOT NULL"""
            )
        }

    def _latest_disposition(self, c, pick):
        row = c.execute(
            "SELECT disposition FROM feedback WHERE pick_id=? AND candidate_id=? ORDER BY id DESC LIMIT 1",
            (pick["id"], pick["candidate_id"]),
        ).fetchone()
        return row["disposition"] if row else None

    def _temporarily_deferred_ids(self, c, day):
        """Skip yesterday's not-started candidates once without rejecting them."""
        rows = c.execute(
            """SELECT p.* FROM picks p
            WHERE p.list_date=(
                SELECT MAX(date) FROM daily_lists WHERE status='ready' AND date < ?
            )""",
            (day,),
        ).fetchall()
        return {pick["candidate_id"] for pick in rows if self._latest_disposition(c, pick) == "not_started"}

    def _refresh(self, c, day, catalog):
        # Explicit refresh can reconsider a not-started slot. It does not make it
        # a rejection or create an overdue item.
        excluded = self._excluded_ids(c)
        present = {r[0] for r in c.execute("SELECT candidate_id FROM picks WHERE list_date=?", (day,))}
        changed = False
        picks = c.execute("SELECT * FROM picks WHERE list_date=?", (day,)).fetchall()
        for pick in picks:
            current = next((x for x in catalog["candidates"] if x["id"] == pick["candidate_id"]), None)
            if current and self._update_pick_metadata(c, pick, current):
                changed = True
            if self._latest_disposition(c, pick) not in {"not_started", "not_interesting"}:
                continue
            candidate = next(
                (
                    x
                    for x in catalog["candidates"]
                    if x["kind"] == pick["kind"] and x["id"] not in excluded and x["id"] not in present
                ),
                None,
            )
            if candidate:
                self._replace_pick(c, pick["id"], candidate)
                present.add(candidate["id"])
                changed = True
        has_listen = any(pick["slot"] == "listen" for pick in picks)
        if not has_listen:
            deferred = self._temporarily_deferred_ids(c, day)
            podcast = next(
                (
                    candidate
                    for candidate in catalog["candidates"]
                    if candidate["kind"] == "podcast"
                    and candidate["id"] not in excluded
                    and candidate["id"] not in present
                    and candidate["id"] not in deferred
                ),
                None,
            )
            if podcast:
                self._insert_pick(c, day, "listen", podcast, "active")
                changed = True
        return changed

    def _update_pick_metadata(self, c, pick, item):
        """Hydrate delivery details without changing selection or progress."""
        fields = (
            "title",
            "summary",
            "why",
            "url",
            "duration_minutes",
            "podcast_url",
            "podcast_verified",
            "snipd_url",
            "snipd_direct",
            "stopping_point",
            "provenance",
            "inspection_method",
            "inspected_at",
        )
        values = [item.get(field, 0 if field in {"podcast_verified", "snipd_direct"} else None) for field in fields]
        if all(pick[field] == value for field, value in zip(fields, values, strict=True)):
            return False
        assignments = ",".join(f"{field}=?" for field in fields)
        c.execute(f"UPDATE picks SET {assignments} WHERE id=?", (*values, pick["id"]))
        return True

    def _insert_pick(self, c, day, slot, item, state):
        c.execute(
            """INSERT INTO picks(list_date,slot,candidate_id,title,kind,summary,why,url,duration_minutes,podcast_url,podcast_verified,snipd_url,snipd_direct,stopping_point,provenance,inspection_method,inspected_at,state,last_video_timestamp,last_podcast_timestamp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                day,
                slot,
                item.get("candidate_id", item.get("id")),
                item["title"],
                item["kind"],
                item.get("summary"),
                item.get("why"),
                item.get("url"),
                item.get("duration_minutes"),
                item.get("podcast_url"),
                item.get("podcast_verified", 0),
                item.get("snipd_url"),
                item.get("snipd_direct", 0),
                item.get("stopping_point"),
                item.get("provenance"),
                item.get("inspection_method"),
                item.get("inspected_at"),
                state,
                item.get("last_video_timestamp"),
                item.get("last_podcast_timestamp"),
            ),
        )

    def _replace_pick(self, c, pick_id, item):
        c.execute(
            """UPDATE picks SET candidate_id=?,title=?,summary=?,why=?,url=?,duration_minutes=?,podcast_url=?,podcast_verified=?,snipd_url=?,snipd_direct=?,stopping_point=?,provenance=?,inspection_method=?,inspected_at=?,state='active',last_video_timestamp=NULL,last_podcast_timestamp=NULL WHERE id=?""",
            (
                item["id"],
                item["title"],
                item.get("summary"),
                item.get("why"),
                item.get("url"),
                item.get("duration_minutes"),
                item.get("podcast_url"),
                item.get("podcast_verified", 0),
                item.get("snipd_url"),
                item.get("snipd_direct", 0),
                item.get("stopping_point"),
                item.get("provenance"),
                item.get("inspection_method"),
                item.get("inspected_at"),
                pick_id,
            ),
        )
