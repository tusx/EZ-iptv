from __future__ import annotations

from app.models import Category, MediaItem, Source, SyncJob


def serialize_source(source: Source, sync_job: SyncJob | None = None, queue_position: int | None = None) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "enabled": source.enabled,
        "m3u_url": source.m3u_url,
        "xtream_base_url": source.xtream_base_url,
        "username": source.username,
        "password": source.password,
        "user_agent": source.user_agent,
        "last_sync_status": source.last_sync_status,
        "last_sync_at": source.last_sync_at.isoformat() if source.last_sync_at else None,
        "last_error": source.last_error,
        "last_sync_count": source.last_sync_count,
        "sync": serialize_sync_job(sync_job, queue_position=queue_position) if sync_job else None,
    }


def serialize_sync_job(job: SyncJob | None, queue_position: int | None = None) -> dict | None:
    if job is None:
        return None

    return {
        "id": job.id,
        "source_id": job.source_id,
        "generation": job.generation,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "error": job.error,
        "claimed_by": job.claimed_by,
        "timeout_minutes": job.timeout_minutes,
        "timeout_applies": job.timeout_applies,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "items_count": job.items_count,
        "total_items": job.total_items,
        "remaining_items": job.remaining_items,
        "categories_count": job.categories_count,
        "queue_position": queue_position,
    }


def serialize_category(category: Category) -> dict:
    return {
        "id": category.id,
        "source_id": category.source_id,
        "external_id": category.external_id,
        "content_type": category.content_type,
        "category_key": category.category_key,
        "name": category.name,
    }


def serialize_media_item(item: MediaItem, include_children: bool = False) -> dict:
    payload = {
        "id": item.id,
        "source_id": item.source_id,
        "category_id": item.category_id,
        "parent_id": item.parent_id,
        "external_id": item.external_id,
        "item_type": item.item_type,
        "title": item.title,
        "description": item.description,
        "artwork_url": item.artwork_url,
        "backdrop_url": item.backdrop_url,
        "stream_url": item.stream_url,
        "season_number": item.season_number,
        "episode_number": item.episode_number,
        "category_name": item.category.name if item.category else None,
        "source_name": item.source.name if item.source else None,
        "is_playable": bool(item.stream_url),
        "children_count": len(item.children),
        "watch_path": f"/watch/{item.id}" if item.stream_url else None,
        "raw_metadata": item.raw_metadata or {},
    }

    if include_children:
        ordered_children = sorted(
            item.children,
            key=lambda child: (
                child.season_number or 0,
                child.episode_number or 0,
                child.title.lower(),
            ),
        )
        payload["children"] = [serialize_media_item(child) for child in ordered_children]

    return payload
