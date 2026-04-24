from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select, text

from app.extensions import db
from app.models import AppSetting, Source, SyncJob
from app.services.ingest import sync_source
from app.services.serializers import serialize_sync_job


SYNC_TIMEOUT_SETTING_KEY = "sync_timeout_minutes"
LIBRARY_RESULTS_PER_PAGE_SETTING_KEY = "library_results_per_page"
DEFAULT_THEME_SETTING_KEY = "default_theme"
UNFINISHED_STATUSES = ("queued", "running")
RUNNER_SLEEP_SECONDS = 2

_RUNNER_LOCK = threading.Lock()
_RUNNER_THREAD: threading.Thread | None = None
_RUNNER_WAKE_EVENT = threading.Event()


class SyncQueueError(RuntimeError):
    pass


class SourceNotFoundError(SyncQueueError):
    pass


class JobSupersededError(SyncQueueError):
    pass


def ensure_default_sync_settings() -> None:
    defaults = {
        SYNC_TIMEOUT_SETTING_KEY: current_app.config["DEFAULT_SYNC_TIMEOUT_MINUTES"],
        LIBRARY_RESULTS_PER_PAGE_SETTING_KEY: current_app.config["DEFAULT_LIBRARY_RESULTS_PER_PAGE"],
        DEFAULT_THEME_SETTING_KEY: current_app.config["DEFAULT_THEME"],
    }
    created_any = False

    for key, value in defaults.items():
        setting = db.session.get(AppSetting, key)
        if setting is None:
            db.session.add(AppSetting(key=key, value=str(value)))
            created_any = True

    if created_any:
        db.session.commit()


def get_sync_timeout_minutes() -> int:
    setting = db.session.get(AppSetting, SYNC_TIMEOUT_SETTING_KEY)
    if setting is None:
        return current_app.config["DEFAULT_SYNC_TIMEOUT_MINUTES"]

    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return current_app.config["DEFAULT_SYNC_TIMEOUT_MINUTES"]


def get_library_results_per_page() -> int:
    setting = db.session.get(AppSetting, LIBRARY_RESULTS_PER_PAGE_SETTING_KEY)
    if setting is None:
        return current_app.config["DEFAULT_LIBRARY_RESULTS_PER_PAGE"]

    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return current_app.config["DEFAULT_LIBRARY_RESULTS_PER_PAGE"]


def get_default_theme() -> str:
    setting = db.session.get(AppSetting, DEFAULT_THEME_SETTING_KEY)
    if setting is None:
        return current_app.config["DEFAULT_THEME"]

    theme = (setting.value or "").strip().lower()
    if theme not in {"dark", "light"}:
        return current_app.config["DEFAULT_THEME"]
    return theme


def has_active_sync_jobs() -> bool:
    active_job_id = db.session.execute(
        select(SyncJob.id)
        .where(SyncJob.status.in_(UNFINISHED_STATUSES))
        .limit(1)
    ).scalar_one_or_none()
    return active_job_id is not None


def set_sync_timeout_minutes(minutes: int) -> int:
    setting = db.session.get(AppSetting, SYNC_TIMEOUT_SETTING_KEY)
    if setting is None:
        setting = AppSetting(key=SYNC_TIMEOUT_SETTING_KEY, value=str(minutes))
        db.session.add(setting)
    else:
        setting.value = str(minutes)

    db.session.commit()
    current_app.logger.info("Updated sync timeout to %s minute(s).", minutes)
    return minutes


def set_library_results_per_page(results_per_page: int) -> int:
    setting = db.session.get(AppSetting, LIBRARY_RESULTS_PER_PAGE_SETTING_KEY)
    if setting is None:
        setting = AppSetting(key=LIBRARY_RESULTS_PER_PAGE_SETTING_KEY, value=str(results_per_page))
        db.session.add(setting)
    else:
        setting.value = str(results_per_page)

    db.session.commit()
    current_app.logger.info("Updated library results per page to %s.", results_per_page)
    return results_per_page


def set_default_theme(theme: str) -> str:
    setting = db.session.get(AppSetting, DEFAULT_THEME_SETTING_KEY)
    if setting is None:
        setting = AppSetting(key=DEFAULT_THEME_SETTING_KEY, value=theme)
        db.session.add(setting)
    else:
        setting.value = theme

    db.session.commit()
    current_app.logger.info("Updated default theme to %s.", theme)
    return theme


def ensure_sync_runner(app) -> None:
    global _RUNNER_THREAD

    with _RUNNER_LOCK:
        if _RUNNER_THREAD is not None and _RUNNER_THREAD.is_alive():
            return

        _RUNNER_THREAD = threading.Thread(
            target=_runner_loop,
            args=(app,),
            name=f"sync-runner-{os.getpid()}",
            daemon=True,
        )
        _RUNNER_THREAD.start()


def wake_sync_runner(app) -> None:
    ensure_sync_runner(app)
    _RUNNER_WAKE_EVENT.set()


def enqueue_source_sync(source_id: int, *, force_restart: bool = False) -> dict:
    now = utcnow()
    _begin_immediate()

    source = db.session.get(Source, source_id)
    if source is None:
        db.session.rollback()
        raise SourceNotFoundError(f"Source {source_id} was not found.")

    existing_jobs = db.session.execute(
        select(SyncJob)
        .where(
            SyncJob.source_id == source_id,
            SyncJob.status.in_(UNFINISHED_STATUSES),
        )
        .order_by(SyncJob.created_at.asc())
    ).scalars().all()

    if existing_jobs and not force_restart:
        db.session.commit()
        return {
            "queued": False,
            "job": existing_jobs[0],
            "source": source,
            "reason": "already_pending",
        }

    if force_restart and existing_jobs:
        for job in existing_jobs:
            job.status = "superseded"
            job.stage = "superseded"
            job.message = "Superseded by a forced restart request."
            job.finished_at = now
        current_app.logger.warning(
            "Force restart requested for source %s. Superseded %s unfinished job(s).",
            source.name,
            len(existing_jobs),
        )

    generation = (
        db.session.execute(
            select(func.max(SyncJob.generation)).where(SyncJob.source_id == source_id)
        ).scalar_one_or_none()
        or 0
    ) + 1
    timeout_minutes = get_sync_timeout_minutes()
    job = SyncJob(
        source_id=source_id,
        generation=generation,
        status="queued",
        stage="queued",
        message="Waiting in the background sync queue.",
        timeout_minutes=timeout_minutes,
        timeout_applies=True,
    )
    db.session.add(job)
    db.session.commit()
    current_app.logger.info(
        "Queued sync job %s for source %s (generation %s, timeout %s minute(s), force_restart=%s).",
        job.id,
        source.name,
        generation,
        timeout_minutes,
        force_restart,
    )
    return {
        "queued": True,
        "job": job,
        "source": source,
        "reason": "force_restarted" if force_restart else "queued",
    }


def enqueue_all_enabled_sources() -> dict:
    queued_jobs: list[SyncJob] = []
    skipped_sources: list[dict] = []

    for source in Source.query.filter_by(enabled=True).order_by(Source.name.asc()).all():
        result = enqueue_source_sync(source.id)
        if result["queued"]:
            queued_jobs.append(result["job"])
        else:
            skipped_sources.append(
                {
                    "source_id": source.id,
                    "name": source.name,
                    "reason": result["reason"],
                }
            )

    return {
        "queued_jobs": queued_jobs,
        "skipped_sources": skipped_sources,
    }


def get_queue_snapshot() -> dict:
    running_job = db.session.execute(
        select(SyncJob)
        .where(SyncJob.status == "running")
        .order_by(SyncJob.started_at.asc(), SyncJob.created_at.asc())
    ).scalar_one_or_none()
    queued_jobs = db.session.execute(
        select(SyncJob)
        .where(SyncJob.status == "queued")
        .order_by(SyncJob.created_at.asc())
    ).scalars().all()

    return {
        "active_job": serialize_sync_job(running_job),
        "queued_jobs": [
            serialize_sync_job(job, queue_position=index + 1)
            for index, job in enumerate(queued_jobs)
        ],
        "has_activity": bool(running_job or queued_jobs),
        "queue_length": len(queued_jobs),
    }


def get_live_jobs_by_source() -> dict[int, tuple[SyncJob, int | None]]:
    jobs = db.session.execute(
        select(SyncJob)
        .where(SyncJob.status.in_(UNFINISHED_STATUSES))
        .order_by(SyncJob.created_at.asc())
    ).scalars().all()

    source_jobs: dict[int, tuple[SyncJob, int | None]] = {}
    queue_position = 0

    for job in jobs:
        if job.status == "running":
            source_jobs[job.source_id] = (job, None)
        elif job.status == "queued":
            queue_position += 1
            source_jobs[job.source_id] = (job, queue_position)

    return source_jobs


def _runner_loop(app) -> None:
    with app.app_context():
        current_app.logger.info(
            "Background sync runner started in pid=%s thread=%s.",
            os.getpid(),
            threading.current_thread().name,
        )

    while True:
        try:
            with app.app_context():
                job_id = _claim_next_job()

            if job_id is None:
                _RUNNER_WAKE_EVENT.wait(timeout=RUNNER_SLEEP_SECONDS)
                _RUNNER_WAKE_EVENT.clear()
                continue

            _run_job(app, job_id)
        except Exception:  # pragma: no cover - safety net for long-running thread
            with app.app_context():
                current_app.logger.exception("Background sync runner loop crashed.")


def _run_job(app, job_id: int) -> None:
    worker_id = f"{os.getpid()}:{threading.current_thread().name}"

    with app.app_context():
        db.session.remove()
        job = db.session.get(SyncJob, job_id)
        if job is None or job.status != "running":
            return

        source = db.session.get(Source, job.source_id)
        if source is None:
            _finalize_failed_job(job_id, "The source for this sync job no longer exists.")
            return

        current_app.logger.info(
            "Worker %s started sync job %s for source %s.",
            worker_id,
            job.id,
            source.name,
        )

        def progress(
            stage: str,
            message: str,
            *,
            items_count: int | None = None,
            total_items: int | None = None,
            remaining_items: int | None = None,
            categories_count: int | None = None,
            timeout_applies: bool | None = None,
        ):
            _update_job_progress(
                job_id,
                stage=stage,
                message=message,
                items_count=items_count,
                total_items=total_items,
                remaining_items=remaining_items,
                categories_count=categories_count,
                timeout_applies=timeout_applies,
            )

        try:
            progress("starting", "Background worker started processing this source.")
            summary = sync_source(source, progress=progress)
            _finalize_successful_job(job_id, summary)
        except JobSupersededError:
            current_app.logger.warning(
                "Sync job %s for source %s was superseded and will stop without updating final source state.",
                job_id,
                source.name,
            )
        except Exception as exc:
            current_app.logger.exception("Sync job %s for source %s failed.", job_id, source.name)
            _finalize_failed_job(job_id, str(exc))
        finally:
            db.session.remove()
            _RUNNER_WAKE_EVENT.set()


def _update_job_progress(
    job_id: int,
    *,
    stage: str,
    message: str,
    items_count: int | None = None,
    total_items: int | None = None,
    remaining_items: int | None = None,
    categories_count: int | None = None,
    timeout_applies: bool | None = None,
) -> None:
    db.session.expire_all()
    job = db.session.get(SyncJob, job_id)

    if job is None or job.status != "running":
        raise JobSupersededError(f"Sync job {job_id} is no longer active.")

    now = utcnow()
    job.stage = stage
    job.message = message
    job.heartbeat_at = now
    timeout_minutes = job.timeout_minutes or get_sync_timeout_minutes()
    job.timeout_minutes = timeout_minutes
    if timeout_applies is not None:
        job.timeout_applies = timeout_applies
    if job.timeout_applies:
        job.lease_expires_at = now + timedelta(minutes=timeout_minutes)
    else:
        job.lease_expires_at = None
    if items_count is not None:
        job.items_count = items_count
    if total_items is not None:
        job.total_items = total_items
    if remaining_items is not None:
        job.remaining_items = remaining_items
    if categories_count is not None:
        job.categories_count = categories_count

    db.session.commit()
    current_app.logger.info(
        "Sync job %s stage=%s items=%s total=%s remaining=%s categories=%s timeout_applies=%s message=%s",
        job.id,
        stage,
        job.items_count,
        job.total_items,
        job.remaining_items,
        job.categories_count,
        job.timeout_applies,
        message,
    )


def _finalize_successful_job(job_id: int, summary: dict) -> None:
    db.session.expire_all()
    job = db.session.get(SyncJob, job_id)

    if job is None or job.status != "running":
        raise JobSupersededError(f"Sync job {job_id} is no longer active.")

    source = db.session.get(Source, job.source_id)
    now = utcnow()
    job.status = "success"
    job.stage = "complete"
    job.message = "Background sync completed successfully."
    job.error = None
    job.finished_at = now
    job.heartbeat_at = now
    job.lease_expires_at = now
    job.items_count = summary["items_count"]
    job.total_items = summary["items_count"]
    job.remaining_items = 0
    job.categories_count = summary["categories_count"]

    if source is not None:
        source.last_sync_status = "success"
        source.last_sync_at = now
        source.last_error = None
        source.last_sync_count = summary["items_count"]

    db.session.commit()
    current_app.logger.info(
        "Sync job %s finished successfully. Imported %s items across %s categories.",
        job_id,
        summary["items_count"],
        summary["categories_count"],
    )


def _finalize_failed_job(job_id: int, error_message: str) -> None:
    db.session.expire_all()
    job = db.session.get(SyncJob, job_id)

    if job is None or job.status != "running":
        return

    source = db.session.get(Source, job.source_id)
    now = utcnow()
    job.status = "failed"
    job.stage = "failed"
    job.message = error_message
    job.error = error_message
    job.finished_at = now
    job.heartbeat_at = now
    job.lease_expires_at = now
    job.remaining_items = 0

    if source is not None:
        source.last_sync_status = "failed"
        source.last_sync_at = now
        source.last_error = error_message
        source.last_sync_count = 0

    db.session.commit()
    current_app.logger.error("Sync job %s failed: %s", job_id, error_message)


def _claim_next_job() -> int | None:
    _begin_immediate()
    now = utcnow()
    _mark_stale_running_jobs(now)

    running_job = db.session.execute(
        select(SyncJob)
        .where(SyncJob.status == "running")
        .order_by(SyncJob.started_at.asc(), SyncJob.created_at.asc())
    ).scalar_one_or_none()
    if running_job is not None:
        db.session.commit()
        return None

    queued_job = db.session.execute(
        select(SyncJob)
        .where(SyncJob.status == "queued")
        .order_by(SyncJob.created_at.asc())
    ).scalar_one_or_none()
    if queued_job is None:
        db.session.commit()
        return None

    timeout_minutes = queued_job.timeout_minutes or get_sync_timeout_minutes()
    worker_id = f"{os.getpid()}:{threading.current_thread().name}"
    queued_job.status = "running"
    queued_job.stage = "starting"
    queued_job.message = "Background worker claimed this queued sync job."
    queued_job.claimed_by = worker_id
    queued_job.started_at = now
    queued_job.heartbeat_at = now
    queued_job.timeout_minutes = timeout_minutes
    queued_job.timeout_applies = True
    queued_job.lease_expires_at = now + timedelta(minutes=timeout_minutes)
    db.session.commit()
    current_app.logger.info(
        "Worker %s claimed sync job %s for source_id=%s with timeout=%s minute(s).",
        worker_id,
        queued_job.id,
        queued_job.source_id,
        timeout_minutes,
    )
    return queued_job.id


def _mark_stale_running_jobs(now: datetime) -> None:
    stale_jobs = db.session.execute(
        select(SyncJob).where(
            SyncJob.status == "running",
            SyncJob.timeout_applies.is_(True),
            SyncJob.lease_expires_at.is_not(None),
            SyncJob.lease_expires_at < now,
        )
    ).scalars().all()

    for job in stale_jobs:
        source = db.session.get(Source, job.source_id)
        timeout_minutes = job.timeout_minutes or get_sync_timeout_minutes()
        message = (
            f"Sync exceeded the {timeout_minutes}-minute timeout and was marked stale. "
            "Please restart the sync from the settings page."
        )
        job.status = "failed"
        job.stage = "failed"
        job.message = message
        job.error = message
        job.finished_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now
        if source is not None:
            source.last_sync_status = "failed"
            source.last_sync_at = now
            source.last_error = message
            source.last_sync_count = 0
        current_app.logger.warning(
            "Marked sync job %s for source_id=%s as stale after exceeding %s minute(s).",
            job.id,
            job.source_id,
            timeout_minutes,
        )


def utcnow() -> datetime:
    return datetime.now(UTC)


def _begin_immediate() -> None:
    db.session.rollback()
    db.session.execute(text("BEGIN IMMEDIATE"))
