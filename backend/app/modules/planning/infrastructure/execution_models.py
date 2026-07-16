from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class UserWeekCapacityModel(Base):
    __tablename__ = "user_week_capacities"
    __table_args__ = (
        CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        CheckConstraint(
            "total_minutes >= 0 AND allocatable_minutes >= 0 AND buffer_minutes >= 0 "
            "AND allocated_minutes >= 0 AND planned_minutes >= 0 AND actual_minutes >= 0",
            name="minute_summaries_nonnegative",
        ),
        CheckConstraint(
            "allocatable_minutes + buffer_minutes <= total_minutes",
            name="safe_capacity_total",
        ),
        CheckConstraint(
            "allocated_minutes <= allocatable_minutes", name="allocated_within_capacity"
        ),
        CheckConstraint(
            "status IN ('draft', 'allocated', 'active', 'settled')", name="status_values"
        ),
        UniqueConstraint("user_id", "week_start"),
        UniqueConstraint("id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    allocatable_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    preference_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active_allocation_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserWeekAllocationSetModel(Base):
    __tablename__ = "user_week_allocation_sets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'settled')", name="status_values"
        ),
        CheckConstraint("allocated_minutes >= 0", name="allocated_minutes_nonnegative"),
        CheckConstraint(
            "reason IN ('initial', 'rollover', 'new_project', 'capacity_change', 'recovery')",
            name="reason_values",
        ),
        ForeignKeyConstraint(
            ["user_week_capacity_id", "user_id"],
            ["user_week_capacities.id", "user_week_capacities.user_id"],
        ),
        UniqueConstraint("user_week_capacity_id", "allocation_revision"),
        UniqueConstraint("id", "user_id", "user_week_capacity_id"),
        Index(
            "uq_allocation_sets_one_active_per_capacity",
            "user_week_capacity_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_week_capacity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    allocation_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    allocated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    source_user_week_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_week_runs.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserWeekAllocationModel(Base):
    __tablename__ = "user_week_allocations"
    __table_args__ = (
        CheckConstraint(
            "budget_minutes >= 0 AND minimum_minutes >= 0 AND planned_minutes >= 0 "
            "AND actual_minutes >= 0",
            name="minute_values_nonnegative",
        ),
        CheckConstraint("priority_snapshot BETWEEN 1 AND 100", name="priority_range"),
        CheckConstraint(
            "deadline_risk IN ('none', 'low', 'medium', 'high')", name="deadline_risk_values"
        ),
        CheckConstraint(
            "allocation_reason IN ('scheduled', 'capacity_shortage')",
            name="allocation_reason_values",
        ),
        CheckConstraint(
            "status IN ('reserved', 'active', 'unfunded', 'released', 'settled')",
            name="status_values",
        ),
        CheckConstraint(
            "(budget_minutes = 0 AND allocation_reason = 'capacity_shortage' "
            "AND status IN ('unfunded', 'released', 'settled')) OR "
            "(budget_minutes > 0 AND allocation_reason = 'scheduled' AND status <> 'unfunded')",
            name="unfunded_consistency",
        ),
        CheckConstraint(
            "planned_minutes <= budget_minutes OR status IN ('released', 'settled')",
            name="planned_within_live_budget",
        ),
        ForeignKeyConstraint(
            ["allocation_set_id", "user_id", "user_week_capacity_id"],
            [
                "user_week_allocation_sets.id",
                "user_week_allocation_sets.user_id",
                "user_week_allocation_sets.user_week_capacity_id",
            ],
        ),
        ForeignKeyConstraint(
            ["user_week_capacity_id", "user_id"],
            ["user_week_capacities.id", "user_week_capacities.user_id"],
        ),
        ForeignKeyConstraint(["project_id", "user_id"], ["projects.id", "projects.user_id"]),
        UniqueConstraint("allocation_set_id", "project_id"),
        UniqueConstraint("id", "user_id", "project_id"),
        Index("ix_allocations_capacity_project", "user_week_capacity_id", "project_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_week_capacity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    allocation_set_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    budget_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_snapshot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    project_revision_snapshot: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deadline_risk: Mapped[str] = mapped_column(String(10), nullable=False)
    allocation_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserWeekRunModel(Base):
    __tablename__ = "user_week_runs"
    __table_args__ = (
        CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        CheckConstraint(
            "run_type IN ('rollover', 'reallocation', 'recovery')", name="run_type_values"
        ),
        CheckConstraint(
            "status IN ('pending', 'promoting_baseline', 'allocating', 'dispatching_projects', "
            "'planning_projects', 'completed', 'partial_failed', 'failed')",
            name="status_values",
        ),
        CheckConstraint(
            "expected_projects >= 0 AND succeeded_projects >= 0 AND failed_projects >= 0 "
            "AND succeeded_projects + failed_projects <= expected_projects",
            name="project_counts_valid",
        ),
        UniqueConstraint("idempotency_key"),
        Index(
            "uq_user_week_runs_rollover",
            "user_id",
            "week_start",
            unique=True,
            postgresql_where=text("run_type = 'rollover'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_ref: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    expected_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promotion_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allocation_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_week_allocation_sets.id")
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeekPlanModel(Base):
    __tablename__ = "week_plans"
    __table_args__ = (
        CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        CheckConstraint(
            "status IN ('prepared', 'active', 'settled', 'superseded')", name="status_values"
        ),
        CheckConstraint("generation > 0 AND version > 0", name="positive_versions"),
        CheckConstraint(
            "budget_minutes >= 0 AND planned_minutes >= 0 AND planned_minutes <= budget_minutes",
            name="planned_within_budget",
        ),
        CheckConstraint(
            "creation_source IN ('initial_planning', 'allocation_shell', 'weekly_review', "
            "'temporary_replan', 'recovery', 'calibration_hold')",
            name="creation_source_values",
        ),
        ForeignKeyConstraint(["project_id", "user_id"], ["projects.id", "projects.user_id"]),
        ForeignKeyConstraint(
            ["allocation_id", "user_id", "project_id"],
            [
                "user_week_allocations.id",
                "user_week_allocations.user_id",
                "user_week_allocations.project_id",
            ],
        ),
        UniqueConstraint("project_id", "week_start", "generation"),
        UniqueConstraint("id", "user_id", "project_id"),
        Index(
            "uq_week_plans_one_current",
            "project_id",
            "week_start",
            unique=True,
            postgresql_where=text("status IN ('prepared', 'active')"),
        ),
        Index("ix_week_plans_user_week", "user_id", "week_start", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    allocation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    project_plan_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    budget_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    creation_source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_planning_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "task_kind IN ('main', 'review', 'remediation', 'exploration', 'rest')",
            name="task_kind_values",
        ),
        CheckConstraint("estimated_minutes > 0", name="estimated_minutes_positive"),
        CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0", name="actual_minutes_nonnegative"
        ),
        CheckConstraint("necessity IN ('required', 'optional')", name="necessity_values"),
        CheckConstraint(
            "status IN ('planned', 'completed', 'skipped', 'deferred', 'cancelled', 'replaced')",
            name="status_values",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("origin_task_id IS DISTINCT FROM id", name="origin_not_self"),
        ForeignKeyConstraint(
            ["week_plan_id", "user_id", "project_id"],
            ["week_plans.id", "week_plans.user_id", "week_plans.project_id"],
        ),
        ForeignKeyConstraint(
            ["source_milestone_id", "user_id", "project_id"],
            ["milestones.id", "milestones.user_id", "milestones.project_id"],
        ),
        ForeignKeyConstraint(
            ["origin_task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
        ),
        UniqueConstraint("week_plan_id", "order_key"),
        UniqueConstraint("id", "user_id", "project_id"),
        Index("ix_tasks_user_week_status_order", "user_id", "week_plan_id", "status", "order_key"),
        Index("ix_tasks_user_due_status", "user_id", "due_date", "status"),
        Index("ix_tasks_project_week_status", "project_id", "week_plan_id", "status"),
        Index("ix_tasks_milestone_status", "source_milestone_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    week_plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_milestone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    origin_task_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    first_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    necessity: Mapped[str] = mapped_column(String(10), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    order_key: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    source_command_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskDependencyModel(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint("prerequisite_task_id <> dependent_task_id", name="not_self"),
        ForeignKeyConstraint(
            ["prerequisite_task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
        ),
        ForeignKeyConstraint(
            ["dependent_task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
        ),
        UniqueConstraint("prerequisite_task_id", "dependent_task_id"),
        Index("ix_task_dependencies_dependent", "dependent_task_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    prerequisite_task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    dependent_task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskEventModel(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('completed', 'reopened', 'skipped', 'restored', 'deferred', "
            "'cancelled', 'replaced', 'duration_recorded')",
            name="event_type_values",
        ),
        CheckConstraint(
            "previous_status IN ('planned', 'completed', 'skipped', 'deferred', 'cancelled', "
            "'replaced') AND new_status IN ('planned', 'completed', 'skipped', 'deferred', "
            "'cancelled', 'replaced')",
            name="status_values",
        ),
        CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0", name="actual_minutes_nonnegative"
        ),
        ForeignKeyConstraint(
            ["task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
        ),
        UniqueConstraint("id"),
        UniqueConstraint("user_id", "idempotency_key"),
        UniqueConstraint("project_id", "project_event_revision"),
        Index("ix_task_events_project_revision", "project_id", "project_event_revision"),
        Index("ix_task_events_task_seq", "task_id", "event_seq"),
    )

    event_seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_event_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    reason_code: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
