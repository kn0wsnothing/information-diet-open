"""Validated private source catalog.  Catalog JSON stays outside this repository."""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

REQUIRED = ("id", "kind", "title", "summary", "why", "url", "inspection_method", "inspected_at", "provenance")


def validate_candidate(item: dict) -> dict:
    if not isinstance(item, dict):
        raise ValueError("candidate must be an object")
    missing = [key for key in REQUIRED if not item.get(key)]
    if missing:
        raise ValueError("candidate missing: " + ", ".join(missing))
    if item["kind"] not in {"video", "podcast", "read"}:
        raise ValueError("candidate kind must be video, podcast, or read")
    if not all(isinstance(item[key], str) for key in REQUIRED):
        raise ValueError("candidate required fields must be strings")
    if item["kind"] in {"video", "podcast"} and (
        not isinstance(item.get("duration_minutes"), int) or item["duration_minutes"] < 1
    ):
        raise ValueError(f"{item['kind']} requires positive duration_minutes")
    if urlparse(item["url"]).scheme not in {"https", "http"}:
        raise ValueError("candidate url must be a direct http(s) link")
    if item["kind"] == "video":
        if not isinstance(item.get("source_url"), str) or urlparse(item["source_url"]).scheme not in {"https", "http"}:
            raise ValueError("video requires original source_url")
        source = urlparse(item["source_url"])
        youtube_host = source.hostname == "youtube.com" or (source.hostname or "").endswith(".youtube.com")
        youtube_watch = youtube_host and source.path == "/watch" and bool(parse_qs(source.query).get("v"))
        youtube_short = source.hostname == "youtu.be" and bool(source.path.strip("/"))
        if source.scheme != "https" or not (youtube_watch or youtube_short):
            raise ValueError("video source_url must be a native YouTube watch URL")
        reader_url = item.get("reader_url")
        if item["url"] != item["source_url"]:
            raise ValueError("video url must equal source_url")
        if reader_url is not None:
            if not isinstance(reader_url, str):
                raise ValueError("reader_url must be a verified Readwise Reader document")
            reader = urlparse(reader_url)
            if reader.scheme != "https" or reader.netloc != "read.readwise.io" or not reader.path.startswith("/read/"):
                raise ValueError("reader_url must be a verified Readwise Reader document")
    if item["kind"] == "podcast" and (
        urlparse(item["url"]).scheme != "https" or not urlparse(item["url"]).netloc
    ):
        raise ValueError("podcast url must be a direct https episode link")
    # A podcast URL is only usable when an inspection explicitly verified it.
    if "podcast_verified" in item and not isinstance(item["podcast_verified"], bool):
        raise ValueError("podcast_verified must be boolean")
    if item.get("podcast_url") and item.get("podcast_verified") is not True:
        raise ValueError("podcast_url requires podcast_verified=true")
    if item.get("podcast_url") and urlparse(item["podcast_url"]).scheme not in {"https", "http"}:
        raise ValueError("podcast_url must be http(s)")
    if "snipd_direct" in item and not isinstance(item["snipd_direct"], bool):
        raise ValueError("snipd_direct must be boolean")
    snipd_url = item.get("snipd_url")
    if snipd_url:
        parsed_snipd = urlparse(snipd_url)
        if parsed_snipd.scheme != "https" or parsed_snipd.netloc != "share.snipd.com":
            raise ValueError("snipd_url must be a verified Snipd share URL")
        if not parsed_snipd.path.startswith(("/show/", "/episode/")):
            raise ValueError("snipd_url must identify a Snipd show or episode")
    if item.get("snipd_direct") is True and not item.get("snipd_url"):
        raise ValueError("snipd_direct requires snipd_url")
    if item.get("snipd_direct") is True and not urlparse(snipd_url).path.startswith("/episode/"):
        raise ValueError("snipd_direct requires an exact Snipd episode URL")
    try:
        datetime.fromisoformat(item["inspected_at"])
    except ValueError as error:
        raise ValueError("inspected_at must be ISO-8601") from error
    return item


def validate_catalog(payload: dict) -> dict:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("catalog requires candidates list")
    seen = set()
    for candidate in candidates:
        validate_candidate(candidate)
        if candidate["id"] in seen:
            raise ValueError("duplicate candidate id: " + candidate["id"])
        seen.add(candidate["id"])
    return payload
