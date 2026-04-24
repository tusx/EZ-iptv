from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


class Source(db.Model):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(db.String(20), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True)
    m3u_url: Mapped[str | None] = mapped_column(db.Text)
    xtream_base_url: Mapped[str | None] = mapped_column(db.Text)
    username: Mapped[str | None] = mapped_column(db.String(255))
    password: Mapped[str | None] = mapped_column(db.String(255))
    user_agent: Mapped[str | None] = mapped_column(db.String(255))
    last_sync_status: Mapped[str] = mapped_column(db.String(20), nullable=False, default="never")
    last_sync_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(db.Text)
    last_sync_count: Mapped[int | None] = mapped_column(db.Integer)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    categories: Mapped[list["Category"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    items: Mapped[list["MediaItem"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    sync_jobs: Mapped[list["SyncJob"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(db.String(120), primary_key=True)
    value: Mapped[str] = mapped_column(db.String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("source_id", "content_type", "category_key", name="uq_category_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(db.ForeignKey("sources.id"), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(db.String(255))
    content_type: Mapped[str] = mapped_column(db.String(20), nullable=False, index=True)
    category_key: Mapped[str] = mapped_column(db.String(255), nullable=False)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    source: Mapped[Source] = relationship(back_populates="categories")
    items: Mapped[list["MediaItem"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class MediaItem(db.Model):
    __tablename__ = "media_items"
    __table_args__ = (
        UniqueConstraint("source_id", "item_key", name="uq_item_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(db.ForeignKey("sources.id"), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(db.ForeignKey("categories.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(db.ForeignKey("media_items.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(db.String(255), index=True)
    item_key: Mapped[str] = mapped_column(db.String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(db.String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(db.String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(db.Text)
    artwork_url: Mapped[str | None] = mapped_column(db.Text)
    backdrop_url: Mapped[str | None] = mapped_column(db.Text)
    stream_url: Mapped[str | None] = mapped_column(db.Text)
    season_number: Mapped[int | None] = mapped_column(db.Integer)
    episode_number: Mapped[int | None] = mapped_column(db.Integer)
    raw_metadata: Mapped[dict] = mapped_column(db.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    source: Mapped[Source] = relationship(back_populates="items")
    category: Mapped[Category | None] = relationship(back_populates="items")
    parent: Mapped["MediaItem | None"] = relationship(
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["MediaItem"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class SyncJob(db.Model):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(db.ForeignKey("sources.id"), nullable=False, index=True)
    generation: Mapped[int] = mapped_column(db.Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(db.String(20), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(db.String(64))
    message: Mapped[str | None] = mapped_column(db.Text)
    error: Mapped[str | None] = mapped_column(db.Text)
    claimed_by: Mapped[str | None] = mapped_column(db.String(255))
    timeout_minutes: Mapped[int | None] = mapped_column(db.Integer)
    timeout_applies: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True)
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    items_count: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    total_items: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    remaining_items: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    categories_count: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    source: Mapped[Source] = relationship(back_populates="sync_jobs")
