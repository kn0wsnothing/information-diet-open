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

from .config import catalog_path, database_path
from .service import load_catalog
from .store import Store
from .time import HKT, hkt_date

ROOT = Path(__file__).resolve().parent
DB_PATH = str(database_path())
CATALOG_PATH = str(catalog_path())
CSRF_TOKEN = os.environ.get("INFORMATION_DIET_CSRF_TOKEN", secrets.token_urlsafe(32))
app = FastAPI(title="Information Diet", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def store():
    result = Store(DB_PATH)
    result.setup()
    return result


@app.get("/healthz")
def healthz():
    try:
        Store(DB_PATH).setup()
        return {"ok": True, "database": "available"}
    except Exception as error:
        return JSONResponse({"ok": False, "database": "unavailable", "detail": str(error)}, status_code=503)


@app.get("/status")
def status():
    today = store().get_list(hkt_date())
    latest = store().latest_list()
    return {
        "timezone": "Asia/Hong_Kong",
        "today": today and today["date"],
        "latest_usable": latest and latest["date"],
        "catalog_configured": Path(CATALOG_PATH).exists(),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    target = store()
    current = target.get_list(hkt_date())
    fallback = None if current and current["status"] == "ready" else target.latest_list()
    saved_episodes = target.list_saved_episodes()
    saved_note = request.query_params.get("note_saved", "")
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "daily": current if current and current["status"] == "ready" else fallback,
            "failed_today": current if current and current["source_status"] == "failed" else None,
            "book": target.book(),
            "saved_episodes": saved_episodes,
            "saved_by_candidate": {
                episode["candidate_id"]: episode for episode in saved_episodes if episode.get("candidate_id")
            },
            "today": hkt_date(),
            "csrf": CSRF_TOKEN,
            "note_saved_pick_id": int(saved_note) if saved_note.isdigit() else None,
            "catalog_exists": Path(CATALOG_PATH).is_file(),
        },
    )


@app.post("/saved-episodes")
def add_saved_episode(
    title: str = Form(...),
    show: str = Form(...),
    url: str = Form(""),
    csrf_token: str = Form(...),
):
    csrf(csrf_token)
    try:
        episode = store().add_saved_episode(title, show, url=url, now=datetime.now(HKT).isoformat())
    except ValueError as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/#saved-episode-{episode['id']}", status_code=303)


@app.post("/save-podcast-pick/{pick_id}")
def save_podcast_pick(
    pick_id: int,
    show: str = Form(...),
    candidate_id: str = Form(...),
    csrf_token: str = Form(...),
):
    csrf(csrf_token)
    target = store()
    current = target.get_list(hkt_date())
    daily = current if current and current["status"] == "ready" else target.latest_list()
    pick = next((item for item in daily["picks"] if item["id"] == pick_id), None) if daily else None
    if pick is None or pick["kind"] != "podcast" or pick["candidate_id"] != candidate_id:
        raise HTTPException(400, "This recommendation changed. Reload before saving it.")
    try:
        episode = target.add_saved_episode(
            pick["title"], show, url=pick.get("url") or "",
            candidate_id=candidate_id, now=datetime.now(HKT).isoformat(),
        )
        if pick["state"] == "active":
            target.feedback(
                pick_id, "continue", now=datetime.now(HKT).isoformat(), expected_candidate_id=candidate_id
            )
    except ValueError as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/#saved-episode-{episode['id']}", status_code=303)


@app.post("/saved-episodes/{episode_id}/progress")
def update_saved_episode(
    episode_id: int,
    state: str = Form(...),
    position: str = Form(""),
    csrf_token: str = Form(...),
):
    csrf(csrf_token)
    target = store()
    try:
        episode = target.update_saved_episode(episode_id, state, position=position, now=datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    if episode.get("candidate_id") and state in {"listening", "completed"}:
        latest = target.latest_list()
        pick = next(
            (item for item in latest["picks"] if item["candidate_id"] == episode["candidate_id"]), None
        ) if latest else None
        if pick and pick["kind"] == "podcast" and pick["state"] != "completed":
            target.feedback(
                pick["id"], "completed" if state == "completed" else "continue",
                now=datetime.now(HKT).isoformat(), expected_candidate_id=episode["candidate_id"],
                podcast_timestamp=position,
            )
    return RedirectResponse(f"/#saved-episode-{episode_id}", status_code=303)


@app.post("/saved-episodes/{episode_id}/notes")
def save_saved_episode_note(
    episode_id: int,
    note: str = Form(...),
    csrf_token: str = Form(...),
):
    csrf(csrf_token)
    try:
        store().save_saved_episode_note(episode_id, note, now=datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/#saved-episode-{episode_id}", status_code=303)


def csrf(token: str):
    if not secrets.compare_digest(token, CSRF_TOKEN):
        raise HTTPException(403, "Invalid form token")


@app.post("/feedback/{pick_id}")
def submit_feedback(
    pick_id: int,
    disposition: str = Form(...),
    reason: str = Form(""),
    video_timestamp: str = Form(""),
    podcast_timestamp: str = Form(""),
    book_page: str = Form(""),
    candidate_id: str = Form(...),
    csrf_token: str = Form(...),
):
    csrf(csrf_token)
    try:
        store().feedback(
            pick_id,
            disposition,
            reason,
            video_timestamp,
            int(book_page) if book_page else None,
            datetime.now(HKT).isoformat(),
            candidate_id,
            podcast_timestamp=podcast_timestamp,
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse("/", status_code=303)


@app.post("/video-note/{pick_id}")
def save_video_note(
    pick_id: int,
    note: str = Form(...),
    candidate_id: str = Form(...),
    csrf_token: str = Form(...),
):
    csrf(csrf_token)
    try:
        store().save_media_note(pick_id, candidate_id, note, datetime.now(HKT).isoformat())
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error))
    return RedirectResponse(f"/?note_saved={pick_id}#video-note-{pick_id}", status_code=303)


@app.post("/podcast-note/{pick_id}")
def save_podcast_note(
    pick_id: int,
    note: str = Form(...),
    candidate_id: str = Form(...),
    csrf_token: str = Form(...),
):
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
    try:
        seed = load_catalog(CATALOG_PATH)
        target = store()
        target.seed_books(seed["book"])
        target.generate(hkt_date(), seed, datetime.now(HKT).isoformat(), refresh=True)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        store().record_source_failure(hkt_date(), datetime.now(HKT).isoformat(), f"source load failed: {error}")
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/", status_code=303)
