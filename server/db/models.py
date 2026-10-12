"""SQLAlchemy models. Weights are stored in kilograms; every user-owned row has `user_id`.

Schema is created with `Base.metadata.create_all` (no Alembic; see server/db/init_db.py).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

KG = Numeric(8, 3)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable lookup key for seeded/demo users (e.g. "demo"). OAuth subjects later.
    external_key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))

    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint("unit IN ('lb', 'kg')", name="ck_profile_unit"),
        CheckConstraint("days_per_week BETWEEN 1 AND 7", name="ck_profile_days"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    unit: Mapped[str] = mapped_column(String(2), default="lb")
    bar_weight_kg: Mapped[Decimal] = mapped_column(KG)
    goal: Mapped[str | None] = mapped_column(String(30))
    days_per_week: Mapped[int | None] = mapped_column(Integer)
    # IANA name; decides what "today" and "this week" mean for the user.
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    user: Mapped[User] = relationship(back_populates="profile")


class Exercise(Base):
    """Shared reference data (not per user)."""

    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(
            "equipment IN ('barbell', 'dumbbell', 'machine', 'cable', 'bodyweight')",
            name="ck_exercise_equipment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # Bodyweight moves are logged with weight 0; barbell lifts use the plate calculator.
    equipment: Mapped[str] = mapped_column(String(20))
    form_cues: Mapped[list[str]] = mapped_column(JSON, default=list)

    aliases: Mapped[list["ExerciseAlias"]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )


class ExerciseAlias(Base):
    __tablename__ = "exercise_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"))
    # Stored normalized (see exercise_resolver.normalize).
    alias: Mapped[str] = mapped_column(String(100), unique=True)

    exercise: Mapped[Exercise] = relationship(back_populates="aliases")


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        Index(
            "uq_plans_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)

    days: Mapped[list["PlanDay"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanDay.day_index"
    )


class PlanDay(Base):
    __tablename__ = "plan_days"
    __table_args__ = (UniqueConstraint("plan_id", "day_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    day_index: Mapped[int] = mapped_column(Integer)  # 0-based order within the plan
    name: Mapped[str] = mapped_column(String(100))
    # Scheduled day of the week, 0 = Monday. None = unscheduled (done in rotation).
    weekday: Mapped[int | None] = mapped_column(Integer)

    plan: Mapped[Plan] = relationship(back_populates="days")
    exercises: Mapped[list["PlanExercise"]] = relationship(
        back_populates="plan_day", cascade="all, delete-orphan", order_by="PlanExercise.position"
    )


class PlanExercise(Base):
    __tablename__ = "plan_exercises"
    __table_args__ = (UniqueConstraint("plan_day_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(ForeignKey("plan_days.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    position: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)

    plan_day: Mapped[PlanDay] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()


class WorkoutSession(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'finished')", name="ck_session_status"),
        Index(
            "uq_sessions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_day_id: Mapped[int | None] = mapped_column(ForeignKey("plan_days.id"))
    status: Mapped[str] = mapped_column(String(10), default="active")
    # Position in `exercises`: which exercise, and how many sets of it are done.
    current_position: Mapped[int] = mapped_column(Integer, default=0)
    current_set: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan_day: Mapped["PlanDay | None"] = relationship()
    exercises: Mapped[list["SessionExercise"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionExercise.position"
    )


class SessionExercise(Base):
    """Snapshot of a guided session's exercises and targets, taken when it starts."""

    __tablename__ = "session_exercises"
    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        CheckConstraint(
            "status IN ('pending', 'done', 'skipped')", name="ck_session_exercise_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    sets: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    # None until known (no history yet); 0 for bodyweight. Updated if the user changes weight.
    target_weight_kg: Mapped[Decimal | None] = mapped_column(KG)
    status: Mapped[str] = mapped_column(String(10), default="pending")

    session: Mapped[WorkoutSession] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()


class LoggedSet(Base):
    __tablename__ = "logged_sets"
    __table_args__ = (
        Index("ix_logged_sets_user_exercise_time", "user_id", "exercise_id", "logged_at"),
        Index("ix_logged_sets_user_time", "user_id", "logged_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), index=True
    )
    # Sets logged by one request share a batch, so undo removes them together.
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    # Set only by complete_set: the guided-session exercise this set counts toward.
    session_exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_exercises.id", ondelete="SET NULL"), index=True
    )
    reps: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[Decimal] = mapped_column(KG)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    exercise: Mapped[Exercise] = relationship()


class BodyMetric(Base):
    __tablename__ = "body_metrics"
    __table_args__ = (Index("ix_body_metrics_user_time", "user_id", "measured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    bodyweight_kg: Mapped[Decimal] = mapped_column(KG)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Insight(TimestampMixin, Base):
    __tablename__ = "insights"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(Date)  # Monday of the ISO week
    text: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(String(100))


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_job_status"),
        Index("ix_jobs_user_kind_status", "user_id", "kind", "status"),
        Index("ix_jobs_status_run_after", "status", "run_after"),
        # At most one queued job per user and kind: new requests reschedule it (debounce).
        Index(
            "uq_jobs_one_queued_per_user_kind",
            "user_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(10), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Not run before this time (debounce and retry backoff).
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
