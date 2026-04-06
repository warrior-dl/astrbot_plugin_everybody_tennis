from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ...shared.time import utc_now


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("platform", "external_group_id", name="uq_groups_platform_external_group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    external_group_id: Mapped[str] = mapped_column(String(128), nullable=False)
    group_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_group_status_created", "group_id", "status", "created_at"),
        Index("ix_matches_group_status_expires", "group_id", "status", "expires_at"),
        Index("ix_matches_group_confirmed_at", "group_id", "confirmed_at"),
        Index("ix_matches_source_image_sha256", "source_image_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_image_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_extraction_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    set_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    game_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_rally_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class MatchPlayerStat(Base):
    __tablename__ = "match_player_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "side", name="uq_match_player_stats_match_side"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    side: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_winner: Mapped[bool] = mapped_column(nullable=False, default=False)
    points_won: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    serve_points_won: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    double_faults: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_play_rate: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
