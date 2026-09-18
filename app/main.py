"""Public demonstration entrypoint using only the bundled synthetic catalog."""
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .store import Store
from .time import HKT, hkt_date

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SHOWCASE_DB", str(ROOT.parent / "var" / "showcase.sqlite3")))
CATALOG_PATH = ROOT.parent / "examples" / "catalog.json"
CSRF_TOKEN = os.environ.get("SHOWCASE_CSRF_TOKEN", secrets.token_urlsafe(32))
app = FastAPI(title="Information Diet showcase", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def store() -> Store:
    result = Store(DB_PATH)
    result.setup()
    return result


def load_demo_catalog() -> dict:
    """The public app deliberately has no source refresh, remote reads, or private configuration."""
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def prepare_demo(target: Store, day: str | None = None, refresh: bool = False) -> None:
    catalog = load_demo_catalog()
    target.seed_books(catalog["book"])
    target.generate(day or hkt_date(), catalog, datetime.now(HKT).isoformat(), refresh=refresh)


def csrf(token: str) -> None:
    if not secrets.compare_digest(token, CSRF_TOKEN):
        raise HTTPException(403, "Invalid form token")


@app.get("/healthz")
def healthz():
    try:
        store().setup()
        return {"ok": True, "database": "candidate-local"}
    except Exception as error:
        return JSONResponse({"ok": False, "database": "unavailable", "detail": str(error)}, status_code=503)


@app.get("/status")
def status():
    target = store()
    return {"timezone": "Asia/Hong_Kong", "today": (target.get_list(hkt_date()) or {}).get("date"), "demo": True}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    target = store()
    prepare_demo(target)
    daily = target.get_list(hkt_date())
    saved_episodes = target.list_saved_episodes()
    saved_note = request.query_params.get("note_saved", "")
    return templates.TemplateResponse(request, "home.html", {
        "daily": daily, "failed_today": None, "book": target.book(), "saved_episodes": saved_episodes,
        "saved_by_candidate": {episode["candidate_id"]: episode for episode in saved_episodes if episode.get("candidate_id")},
        "today": hkt_date(), "csrf": CSRF_TOKEN, "note_saved_pick_id": int(saved_note) if saved_note.isdigit() else None,
    })


@app.post("/saved-episodes")
def add_saved_episode(title: str = Form(...), show: str = Form(...), url: str = Form(""), csrf_token: str = Form(...)):
    csrf(csrf_token)
    try:
        episode = store().add_saved_episode(title, show, url=url, now=datetime.now(HKT).isoformat())
    except ValueError as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/#saved-episode-{episode['id']}", status_code=303)


@app.post("/save-podcast-pick/{pick_id}")
def save_podcast_pick(pick_id: int, show: str = Form(...), candidate_id: str = Form(...), csrf_token: str = Form(...)):
    csrf(csrf_token)
    target = store()
    prepare_demo(target)
    pick = next((item for item in target.get_list(hkt_date())["picks"] if item["id"] == pick_id), None)
    if pick is None or pick["kind"] != "podcast" or pick["candidate_id"] != candidate_id:
        raise HTTPException(400, "This recommendation changed. Reload before saving it.")
    try:
        episode = target.add_saved_episode(pick["title"], show, url=pick.get("url") or "", candidate_id=candidate_id,
                                            now=datetime.now(HKT).isoformat())
        if pick["state"] == "active":
            target.feedback(pick_id, "continue", now=datetime.now(HKT).isoformat(), expected_candidate_id=candidate_id)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/#saved-episode-{episode['id']}", status_code=303)


@app.post("/saved-episodes/{episode_id}/progress")
def update_saved_episode(episode_id: int, state: str = Form(...), position: str = Form(""), csrf_token: str = Form(...)):
    csrf(csrf_token)
    target = store()
    try:
        episode = target.update_saved_episode(episode_id, state, position=position, now=datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    if episode.get("candidate_id") and state in {"listening", "completed"}:
        latest = target.latest_list()
        pick = next((item for item in latest["picks"] if item["candidate_id"] == episode["candidate_id"]), None) if latest else None
        if pick and pick["kind"] == "podcast" and pick["state"] != "completed":
            target.feedback(pick["id"], "completed" if state == "completed" else "continue", now=datetime.now(HKT).isoformat(),
                            expected_candidate_id=episode["candidate_id"], podcast_timestamp=position)
    return RedirectResponse(f"/#saved-episode-{episode_id}", status_code=303)


@app.post("/saved-episodes/{episode_id}/notes")
def save_saved_episode_note(episode_id: int, note: str = Form(...), csrf_token: str = Form(...)):
    csrf(csrf_token)
    try:
        store().save_saved_episode_note(episode_id, note, now=datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/#saved-episode-{episode_id}", status_code=303)


@app.post("/feedback/{pick_id}")
def submit_feedback(pick_id: int, disposition: str = Form(...), reason: str = Form(""), video_timestamp: str = Form(""),
                    podcast_timestamp: str = Form(""), book_page: str = Form(""), candidate_id: str = Form(...), csrf_token: str = Form(...)):
    csrf(csrf_token)
    try:
        store().feedback(pick_id, disposition, reason, video_timestamp, int(book_page) if book_page else None,
                         datetime.now(HKT).isoformat(), candidate_id, podcast_timestamp=podcast_timestamp)
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse("/", status_code=303)


@app.post("/video-note/{pick_id}")
def save_video_note(pick_id: int, note: str = Form(...), candidate_id: str = Form(...), csrf_token: str = Form(...)):
    csrf(csrf_token)
    try:
        store().save_media_note(pick_id, candidate_id, note, datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/?note_saved={pick_id}#video-note-{pick_id}", status_code=303)


@app.post("/podcast-note/{pick_id}")
def save_podcast_note(pick_id: int, note: str = Form(...), candidate_id: str = Form(...), csrf_token: str = Form(...)):
    csrf(csrf_token)
    try:
        store().save_media_note(pick_id, candidate_id, note, datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/?note_saved={pick_id}#podcast-note-{pick_id}", status_code=303)


@app.post("/book-position")
def book_position(book_page: int = Form(...), csrf_token: str = Form(...)):
    csrf(csrf_token)
    try:
        store().report_book_page(book_page)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse("/", status_code=303)


@app.post("/prepare")
def update_recommendations(csrf_token: str = Form(...)):
    csrf(csrf_token)
    prepare_demo(store(), refresh=True)
    return RedirectResponse("/", status_code=303)
