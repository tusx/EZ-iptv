from __future__ import annotations

import re
from hashlib import sha1


ATTRIBUTE_PATTERN = re.compile(r'([\w-]+)="([^"]*)"')


def parse_m3u(text: str) -> list[dict]:
    entries: list[dict] = []
    current_info: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#EXTINF:"):
            info = line[len("#EXTINF:") :]
            _, _, title = info.partition(",")
            attributes = dict(ATTRIBUTE_PATTERN.findall(info))
            current_info = {
                "title": title.strip() or attributes.get("tvg-name") or "Untitled Stream",
                "attributes": attributes,
            }
            continue

        if line.startswith("#"):
            continue

        info = current_info or {"title": "Untitled Stream", "attributes": {}}
        attributes = info["attributes"]
        item_type = classify_item_type(info["title"], attributes)
        entries.append(
            {
                "title": info["title"],
                "stream_url": line,
                "external_id": attributes.get("tvg-id") or attributes.get("channel-id") or sha1(line.encode("utf-8")).hexdigest(),
                "artwork_url": attributes.get("tvg-logo"),
                "group_name": attributes.get("group-title") or "Uncategorized",
                "item_type": item_type,
                "raw_metadata": attributes,
            }
        )
        current_info = None

    return entries


def classify_item_type(title: str, attributes: dict) -> str:
    hints = " ".join(
        filter(
            None,
            [
                title,
                attributes.get("group-title"),
                attributes.get("type"),
                attributes.get("tvg-type"),
            ],
        )
    ).lower()

    if any(marker in hints for marker in ("movie", "vod", "film", "cinema")):
        return "movie"
    return "live"
