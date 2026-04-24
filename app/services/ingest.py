from __future__ import annotations

from hashlib import sha1

import requests
from sqlalchemy import delete, func, insert, select

from app.extensions import db
from app.models import Category, MediaItem, Source
from app.services.m3u import parse_m3u
from app.services.xtream import XtreamClient

INSERT_BATCH_SIZE = 5000


def sync_source(source: Source, progress=None) -> dict:
    if source.source_type == "m3u":
        return sync_m3u_source(source, progress=progress)
    if source.source_type == "xtream":
        return sync_xtream_source(source, progress=progress)
    raise ValueError(f"Unsupported source type: {source.source_type}")


def ensure_series_episodes(item: MediaItem) -> None:
    if item.item_type != "series" or item.source.source_type != "xtream" or item.children:
        return

    client = XtreamClient(item.source)
    series_info = client.get_series_info(item.external_id or "")
    info_block = series_info.get("info") or {}
    item.description = item.description or info_block.get("plot")
    item.artwork_url = item.artwork_url or info_block.get("cover")
    item.backdrop_url = item.backdrop_url or pick_backdrop(info_block.get("backdrop_path"))

    episode_count = 0
    for season_key, episodes in (series_info.get("episodes") or {}).items():
        for episode in episodes:
            episode_id = episode.get("id") or episode.get("episode_id") or episode.get("stream_id")
            if not episode_id:
                continue

            info = episode.get("info") or {}
            extension = info.get("container_extension") or episode.get("container_extension") or "mp4"
            db.session.add(
                MediaItem(
                    source_id=item.source_id,
                    category_id=item.category_id,
                    parent_id=item.id,
                    external_id=str(episode_id),
                    item_key=f"xtream:episode:{item.external_id}:{episode_id}",
                    item_type="episode",
                    title=episode.get("title") or episode.get("name") or f"Episode {episode_count + 1}",
                    description=info.get("plot") or item.description,
                    artwork_url=info.get("movie_image") or item.artwork_url,
                    stream_url=client.build_stream_url("episode", episode_id, extension),
                    season_number=to_int(episode.get("season") or season_key),
                    episode_number=to_int(
                        episode.get("episode_num") or episode.get("episode_number") or episode.get("sort")
                    ),
                    raw_metadata=episode,
                )
            )
            episode_count += 1

    db.session.commit()


def sync_m3u_source(source: Source, progress=None) -> dict:
    headers = {"User-Agent": source.user_agent} if source.user_agent else None
    emit_progress(progress, "fetching", "Downloading the M3U playlist from the provider.", timeout_applies=True)
    response = requests.get(source.m3u_url, headers=headers, timeout=30)
    response.raise_for_status()

    emit_progress(progress, "parsing", "Parsing playlist entries from the downloaded M3U file.", timeout_applies=False)
    parsed_items = parse_m3u(response.text)
    total_items = len(parsed_items)
    existing_counts = get_source_catalog_counts(source.id)
    emit_progress(
        progress,
        "clearing_catalog",
        (
            "Clearing the existing local catalog before importing "
            f"{total_items} parsed items. Removing {existing_counts['items_count']} existing items "
            f"across {existing_counts['categories_count']} categories."
        ),
        items_count=0,
        total_items=total_items,
        remaining_items=total_items,
        categories_count=existing_counts["categories_count"],
        timeout_applies=False,
    )
    clear_source_catalog(source)
    emit_progress(
        progress,
        "replacing_catalog",
        f"Replacing the local catalog with {total_items} parsed items.",
        items_count=0,
        total_items=total_items,
        remaining_items=total_items,
        categories_count=0,
        timeout_applies=False,
    )

    categories: dict[tuple[str, str], Category] = {}
    items_count = 0
    pending_rows: list[dict] = []

    for entry in parsed_items:
        category = get_or_create_category(
            categories=categories,
            source=source,
            content_type=entry["item_type"],
            name=entry["group_name"],
            external_id=None,
        )
        url_hash = sha1(entry["stream_url"].encode("utf-8")).hexdigest()
        pending_rows.append(
            {
                "source_id": source.id,
                "category_id": category.id,
                "external_id": entry["external_id"],
                "item_key": f"m3u:{url_hash}",
                "item_type": entry["item_type"],
                "title": entry["title"],
                "artwork_url": entry["artwork_url"],
                "stream_url": entry["stream_url"],
                "raw_metadata": entry["raw_metadata"],
            }
        )
        items_count += 1
        if len(pending_rows) >= INSERT_BATCH_SIZE:
            flush_pending_media_rows(
                pending_rows,
                progress=progress,
                total_items=total_items,
                items_count=items_count,
                categories_count=len(categories),
                item_descriptor="parsed",
            )

    flush_pending_media_rows(
        pending_rows,
        progress=progress,
        total_items=total_items,
        items_count=items_count,
        categories_count=len(categories),
        item_descriptor="parsed",
    )
    emit_progress(
        progress,
        "finalizing",
        f"Finalizing catalog changes for {items_count} imported playlist items.",
        items_count=items_count,
        total_items=total_items,
        remaining_items=0,
        categories_count=len(categories),
        timeout_applies=False,
    )
    return {
        "categories_count": len(categories),
        "items_count": items_count,
    }


def sync_xtream_source(source: Source, progress=None) -> dict:
    client = XtreamClient(source)
    emit_progress(progress, "fetching", "Fetching Xtream categories.", timeout_applies=True)
    live_categories = index_by_key(client.get_live_categories(), "category_id")
    vod_categories = index_by_key(client.get_vod_categories(), "category_id")
    series_categories = index_by_key(client.get_series_categories(), "category_id")
    emit_progress(progress, "fetching", "Fetching Xtream live streams, movies, and series.", timeout_applies=True)
    live_streams = list(client.get_live_streams())
    vod_streams = list(client.get_vod_streams())
    series_rows = list(client.get_series())
    total_items = len(live_streams) + len(vod_streams) + len(series_rows)
    existing_counts = get_source_catalog_counts(source.id)

    emit_progress(
        progress,
        "clearing_catalog",
        (
            "Clearing the existing local catalog before importing "
            f"{total_items} fetched items. Removing {existing_counts['items_count']} existing items "
            f"across {existing_counts['categories_count']} categories."
        ),
        items_count=0,
        total_items=total_items,
        remaining_items=total_items,
        categories_count=existing_counts["categories_count"],
        timeout_applies=False,
    )
    clear_source_catalog(source)
    emit_progress(
        progress,
        "replacing_catalog",
        f"Replacing the local Xtream catalog with {total_items} fetched items.",
        items_count=0,
        total_items=total_items,
        remaining_items=total_items,
        categories_count=0,
        timeout_applies=False,
    )

    categories: dict[tuple[str, str], Category] = {}
    items_count = 0
    pending_rows: list[dict] = []

    for stream in live_streams:
        category = get_or_create_category(
            categories=categories,
            source=source,
            content_type="live",
            name=lookup_category_name(live_categories, stream.get("category_id")),
            external_id=stream.get("category_id"),
        )
        extension = stream.get("container_extension") or "ts"
        pending_rows.append(
            {
                "source_id": source.id,
                "category_id": category.id,
                "external_id": str(stream.get("stream_id")),
                "item_key": f"xtream:live:{stream.get('stream_id')}",
                "item_type": "live",
                "title": stream.get("name") or "Untitled Channel",
                "description": stream.get("plot"),
                "artwork_url": stream.get("stream_icon"),
                "stream_url": client.build_stream_url("live", stream.get("stream_id"), extension),
                "raw_metadata": stream,
            }
        )
        items_count += 1
        if len(pending_rows) >= INSERT_BATCH_SIZE:
            flush_pending_media_rows(
                pending_rows,
                progress=progress,
                total_items=total_items,
                items_count=items_count,
                categories_count=len(categories),
                item_descriptor="fetched",
            )
    for stream in vod_streams:
        category = get_or_create_category(
            categories=categories,
            source=source,
            content_type="movie",
            name=lookup_category_name(vod_categories, stream.get("category_id")),
            external_id=stream.get("category_id"),
        )
        extension = stream.get("container_extension") or "mp4"
        pending_rows.append(
            {
                "source_id": source.id,
                "category_id": category.id,
                "external_id": str(stream.get("stream_id")),
                "item_key": f"xtream:movie:{stream.get('stream_id')}",
                "item_type": "movie",
                "title": stream.get("name") or "Untitled Movie",
                "description": stream.get("plot"),
                "artwork_url": stream.get("stream_icon"),
                "stream_url": client.build_stream_url("movie", stream.get("stream_id"), extension),
                "raw_metadata": stream,
            }
        )
        items_count += 1
        if len(pending_rows) >= INSERT_BATCH_SIZE:
            flush_pending_media_rows(
                pending_rows,
                progress=progress,
                total_items=total_items,
                items_count=items_count,
                categories_count=len(categories),
                item_descriptor="fetched",
            )
    for series in series_rows:
        category = get_or_create_category(
            categories=categories,
            source=source,
            content_type="series",
            name=lookup_category_name(series_categories, series.get("category_id")),
            external_id=series.get("category_id"),
        )
        pending_rows.append(
            {
                "source_id": source.id,
                "category_id": category.id,
                "external_id": str(series.get("series_id")),
                "item_key": f"xtream:series:{series.get('series_id')}",
                "item_type": "series",
                "title": series.get("name") or "Untitled Series",
                "description": series.get("plot"),
                "artwork_url": series.get("cover"),
                "backdrop_url": pick_backdrop(series.get("backdrop_path")),
                "raw_metadata": series,
            }
        )
        items_count += 1
        if len(pending_rows) >= INSERT_BATCH_SIZE:
            flush_pending_media_rows(
                pending_rows,
                progress=progress,
                total_items=total_items,
                items_count=items_count,
                categories_count=len(categories),
                item_descriptor="fetched",
            )

    flush_pending_media_rows(
        pending_rows,
        progress=progress,
        total_items=total_items,
        items_count=items_count,
        categories_count=len(categories),
        item_descriptor="fetched",
    )
    emit_progress(
        progress,
        "finalizing",
        f"Finalizing Xtream catalog changes for {items_count} imported items.",
        items_count=items_count,
        total_items=total_items,
        remaining_items=0,
        categories_count=len(categories),
        timeout_applies=False,
    )
    return {
        "categories_count": len(categories),
        "items_count": items_count,
    }


def clear_source_catalog(source: Source) -> None:
    db.session.execute(delete(MediaItem).where(MediaItem.source_id == source.id))
    db.session.execute(delete(Category).where(Category.source_id == source.id))


def get_source_catalog_counts(source_id: int) -> dict[str, int]:
    items_count = db.session.execute(
        select(func.count()).select_from(MediaItem).where(MediaItem.source_id == source_id)
    ).scalar_one()
    categories_count = db.session.execute(
        select(func.count()).select_from(Category).where(Category.source_id == source_id)
    ).scalar_one()
    return {
        "items_count": items_count,
        "categories_count": categories_count,
    }


def get_or_create_category(
    *,
    categories: dict[tuple[str, str], Category],
    source: Source,
    content_type: str,
    name: str,
    external_id: str | int | None,
) -> Category:
    category_name = (name or "Uncategorized").strip()
    external = str(external_id) if external_id not in (None, "") else None
    key_value = external or slugify(category_name)
    category_key = (content_type, key_value)

    if category_key not in categories:
        category = Category(
            source_id=source.id,
            external_id=external,
            content_type=content_type,
            category_key=key_value,
            name=category_name,
        )
        db.session.add(category)
        db.session.flush()
        categories[category_key] = category

    return categories[category_key]


def flush_pending_media_rows(
    pending_rows: list[dict],
    *,
    progress,
    total_items: int,
    items_count: int,
    categories_count: int,
    item_descriptor: str,
) -> None:
    if not pending_rows:
        return

    db.session.execute(insert(MediaItem), pending_rows)
    pending_rows.clear()

    remaining_items = max(total_items - items_count, 0)
    emit_progress(
        progress,
        "replacing_catalog",
        f"Added {items_count} of {total_items} {item_descriptor} items to the catalog. {remaining_items} left.",
        items_count=items_count,
        total_items=total_items,
        remaining_items=remaining_items,
        categories_count=categories_count,
        timeout_applies=False,
    )


def slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    compact = "-".join(part for part in cleaned.split("-") if part)
    return compact or "uncategorized"


def lookup_category_name(categories: dict[str, dict], category_id) -> str:
    if category_id is None:
        return "Uncategorized"
    category = categories.get(str(category_id))
    return (category or {}).get("category_name") or "Uncategorized"


def index_by_key(items: list[dict], key: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for item in items or []:
        value = item.get(key)
        if value is not None:
            indexed[str(value)] = item
    return indexed


def pick_backdrop(backdrop_value):
    if isinstance(backdrop_value, list) and backdrop_value:
        return backdrop_value[0]
    if isinstance(backdrop_value, str):
        return backdrop_value
    return None


def to_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def emit_progress(
    progress,
    stage: str,
    message: str,
    *,
    items_count: int | None = None,
    total_items: int | None = None,
    remaining_items: int | None = None,
    categories_count: int | None = None,
    timeout_applies: bool | None = None,
):
    if progress is not None:
        progress(
            stage,
            message,
            items_count=items_count,
            total_items=total_items,
            remaining_items=remaining_items,
            categories_count=categories_count,
            timeout_applies=timeout_applies,
        )
