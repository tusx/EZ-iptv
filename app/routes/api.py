from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func

from app.extensions import db
from app.models import Category, MediaItem, Source
from app.services.ingest import ensure_series_episodes
from app.services.playback import PlaybackError, resolve_playback_payload
from app.services.serializers import serialize_category, serialize_media_item, serialize_source
from app.services.sync_queue import (
    SourceNotFoundError,
    get_default_theme,
    enqueue_all_enabled_sources,
    enqueue_source_sync,
    ensure_sync_runner,
    get_library_results_per_page,
    get_live_jobs_by_source,
    get_queue_snapshot,
    get_sync_timeout_minutes,
    has_active_sync_jobs,
    set_default_theme,
    set_library_results_per_page,
    set_sync_timeout_minutes,
    wake_sync_runner,
)
from app.services.validation import (
    ValidationError,
    normalize_settings_payload,
    normalize_source_payload,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")
SOURCE_CREATE_BLOCKED_MESSAGE = (
    "New sources cannot be added while a sync is in progress. "
    "Please wait until the current sync has finished."
)


def error_response(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.get("/sources")
def list_sources():
    ensure_sync_runner(current_app._get_current_object())
    wake_sync_runner(current_app._get_current_object())
    live_jobs = get_live_jobs_by_source()
    sources = Source.query.order_by(Source.name.asc()).all()
    items = []
    for source in sources:
        sync_job, queue_position = live_jobs.get(source.id, (None, None))
        items.append(serialize_source(source, sync_job=sync_job, queue_position=queue_position))
    return jsonify({"items": items})


@api_bp.get("/settings")
def get_settings():
    return jsonify(
        {
            "sync_timeout_minutes": get_sync_timeout_minutes(),
            "library_results_per_page": get_library_results_per_page(),
            "default_theme": get_default_theme(),
        }
    )


@api_bp.patch("/settings")
def update_settings():
    payload = request.get_json(silent=True) or {}

    try:
        normalized = normalize_settings_payload(
            payload,
            min_minutes=current_app.config["MIN_SYNC_TIMEOUT_MINUTES"],
            max_minutes=current_app.config["MAX_SYNC_TIMEOUT_MINUTES"],
            min_results_per_page=current_app.config["MIN_LIBRARY_RESULTS_PER_PAGE"],
            max_results_per_page=current_app.config["MAX_LIBRARY_RESULTS_PER_PAGE"],
        )
    except ValidationError as exc:
        return error_response(str(exc), 400)

    if "sync_timeout_minutes" in normalized:
        set_sync_timeout_minutes(normalized["sync_timeout_minutes"])
    if "library_results_per_page" in normalized:
        set_library_results_per_page(normalized["library_results_per_page"])
    if "default_theme" in normalized:
        set_default_theme(normalized["default_theme"])

    return jsonify(
        {
            "sync_timeout_minutes": get_sync_timeout_minutes(),
            "library_results_per_page": get_library_results_per_page(),
            "default_theme": get_default_theme(),
        }
    )


@api_bp.post("/sources")
def create_source():
    if has_active_sync_jobs():
        return error_response(SOURCE_CREATE_BLOCKED_MESSAGE, 409)

    payload = request.get_json(silent=True) or {}

    try:
        normalized = normalize_source_payload(payload)
    except ValidationError as exc:
        return error_response(str(exc), 400)

    source = Source(**normalized)
    db.session.add(source)
    db.session.commit()
    return jsonify({"item": serialize_source(source)}), 201


@api_bp.get("/sources/<int:source_id>")
def get_source(source_id: int):
    source = db.get_or_404(Source, source_id)
    return jsonify({"item": serialize_source(source)})


@api_bp.patch("/sources/<int:source_id>")
def update_source(source_id: int):
    source = db.get_or_404(Source, source_id)
    payload = request.get_json(silent=True) or {}

    merged = serialize_source(source)
    merged.update(payload)

    try:
        normalized = normalize_source_payload(merged, partial=True)
    except ValidationError as exc:
        return error_response(str(exc), 400)

    for key, value in normalized.items():
        setattr(source, key, value)

    db.session.commit()
    return jsonify({"item": serialize_source(source)})


@api_bp.delete("/sources/<int:source_id>")
def delete_source(source_id: int):
    source = db.get_or_404(Source, source_id)
    db.session.delete(source)
    db.session.commit()
    return jsonify({"status": "deleted"})


@api_bp.post("/sources/<int:source_id>/sync")
def sync_one_source(source_id: int):
    try:
        result = enqueue_source_sync(source_id)
    except SourceNotFoundError as exc:
        return error_response(str(exc), 404)

    wake_sync_runner(current_app._get_current_object())
    source = db.session.get(Source, source_id)
    live_jobs = get_live_jobs_by_source()
    sync_job, queue_position = live_jobs.get(source_id, (result.get("job"), None))
    payload = {
        "queued": result["queued"],
        "reason": result["reason"],
        "item": serialize_source(source, sync_job=sync_job, queue_position=queue_position) if source else None,
    }
    return jsonify(payload), 202


@api_bp.post("/sources/<int:source_id>/sync/force-restart")
def force_restart_source_sync(source_id: int):
    try:
        result = enqueue_source_sync(source_id, force_restart=True)
    except SourceNotFoundError as exc:
        return error_response(str(exc), 404)

    wake_sync_runner(current_app._get_current_object())
    source = db.session.get(Source, source_id)
    live_jobs = get_live_jobs_by_source()
    sync_job, queue_position = live_jobs.get(source_id, (result.get("job"), None))
    payload = {
        "queued": result["queued"],
        "reason": result["reason"],
        "item": serialize_source(source, sync_job=sync_job, queue_position=queue_position) if source else None,
    }
    return jsonify(payload), 202


@api_bp.post("/sync")
def sync_enabled_sources():
    result = enqueue_all_enabled_sources()
    wake_sync_runner(current_app._get_current_object())
    return (
        jsonify(
            {
                "queued_count": len(result["queued_jobs"]),
                "queued_jobs": [job.id for job in result["queued_jobs"]],
                "skipped_sources": result["skipped_sources"],
            }
        ),
        202,
    )


@api_bp.get("/sync/status")
def get_sync_status():
    ensure_sync_runner(current_app._get_current_object())
    wake_sync_runner(current_app._get_current_object())
    snapshot = get_queue_snapshot()
    snapshot["sync_timeout_minutes"] = get_sync_timeout_minutes()
    return jsonify(snapshot)


@api_bp.get("/categories")
def list_categories():
    query = Category.query.join(MediaItem, MediaItem.category_id == Category.id)

    content_type = request.args.get("type")
    source_id = request.args.get("source_id", type=int)

    query = query.filter(MediaItem.parent_id.is_(None))
    if content_type:
        query = query.filter(MediaItem.item_type == content_type)
    if source_id:
        query = query.filter(Category.source_id == source_id)

    categories = query.distinct().order_by(Category.name.asc()).all()
    return jsonify({"items": [serialize_category(category) for category in categories]})


@api_bp.get("/items")
def list_items():
    default_per_page = get_library_results_per_page()
    max_per_page = current_app.config["MAX_LIBRARY_RESULTS_PER_PAGE"]

    query = MediaItem.query

    item_type = request.args.get("type")
    source_id = request.args.get("source_id", type=int)
    category_id = request.args.get("category_id", type=int)
    parent_id = request.args.get("parent_id", type=int)
    search = request.args.get("q", "").strip()
    page = request.args.get("page", type=int) or 1
    per_page = request.args.get("per_page", type=int)

    page = max(page, 1)
    if per_page is None:
        per_page = default_per_page
    per_page = min(max(per_page, 1), max_per_page)

    if item_type:
        query = query.filter(MediaItem.item_type == item_type)
    if source_id:
        query = query.filter(MediaItem.source_id == source_id)
    if category_id:
        query = query.filter(MediaItem.category_id == category_id)

    if parent_id is None:
        query = query.filter(MediaItem.parent_id.is_(None))
    else:
        query = query.filter(MediaItem.parent_id == parent_id)
        query = query.order_by(
            MediaItem.season_number.asc().nullsfirst(),
            MediaItem.episode_number.asc().nullsfirst(),
            MediaItem.title.asc(),
        )

    if search:
        query = query.filter(MediaItem.title.ilike(f"%{search}%"))

    if parent_id is None:
        query = query.order_by(
            MediaItem.title.asc(),
            MediaItem.id.asc(),
        )

    total_items = query.order_by(None).with_entities(func.count()).scalar() or 0
    total_pages = max((total_items + per_page - 1) // per_page, 1)
    page = min(page, total_pages)
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        {
            "items": [serialize_media_item(item) for item in items],
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }
    )


@api_bp.get("/items/<int:item_id>")
def get_item(item_id: int):
    item = db.get_or_404(MediaItem, item_id)

    if item.item_type == "series":
        ensure_series_episodes(item)
        db.session.refresh(item)

    return jsonify({"item": serialize_media_item(item, include_children=True)})


@api_bp.get("/items/<int:item_id>/playback")
def get_playback(item_id: int):
    item = db.get_or_404(MediaItem, item_id)

    try:
        payload = resolve_playback_payload(item)
    except PlaybackError as exc:
        return error_response(str(exc), 400)

    return jsonify({"item": payload})
