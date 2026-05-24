"""coach + coach_translation + team_coach."""
from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, PrimaryKeyConstraint, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Coach(Base):
    __tablename__ = "coach"
    __table_args__ = (
        Index("coach_slug_idx", "slug", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    external_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CoachTranslation(Base):
    __tablename__ = "coach_translation"

    coach_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("coach.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    name_ko: Mapped[str | None] = mapped_column(Text)
    short_name_ko: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TeamCoach(Base):
    __tablename__ = "team_coach"
    __table_args__ = (
        PrimaryKeyConstraint("team_id", "coach_id"),
        Index("team_coach_team_last_seen_idx", "team_id", "last_seen_at"),
        Index("team_coach_league_season_idx", "league_id", "season_year"),
    )

    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    coach_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("coach.id", ondelete="CASCADE"), nullable=False
    )
    league_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("league.id", ondelete="SET NULL")
    )
    season_year: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
