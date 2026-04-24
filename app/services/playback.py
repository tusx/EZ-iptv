from __future__ import annotations

from urllib.parse import urlparse

from app.models import MediaItem


class PlaybackError(RuntimeError):
    pass


def resolve_playback_payload(item: MediaItem) -> dict:
    if item.item_type == "series":
        raise PlaybackError("Series records are containers. Choose an episode to start playback.")

    if not item.stream_url:
        raise PlaybackError("This item does not have a playable stream URL yet.")

    extension = guess_extension(item.stream_url)
    mime_type = {
        "m3u8": "application/x-mpegURL",
        "mp4": "video/mp4",
        "ts": "video/mp2t",
        "mkv": "video/x-matroska",
    }.get(extension, "application/octet-stream")

    return {
        "id": item.id,
        "title": item.title,
        "stream_url": item.stream_url,
        "mime_type": mime_type,
        "use_hls": extension == "m3u8",
        "item_type": item.item_type,
    }


def guess_extension(url: str) -> str:
    path = urlparse(url).path.rsplit("/", maxsplit=1)[-1]
    if "." not in path:
        return ""
    return path.rsplit(".", maxsplit=1)[-1].lower()
