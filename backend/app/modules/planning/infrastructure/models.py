from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ProjectModel(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "goal_type IN ('deadline', 'outcome', 'capability', 'continuous')",
            name="goal_type_values",
        ),
        CheckConstraint(
            "status IN ('draft', 'planning', 'active', 'paused', "
            "'completed', 'closed', 'archived')",
            name="status_values",
        ),
        CheckConstraint(
            "deadline_day_policy IN ('event_exclusive', 'date_inclusive')",
            name="deadline_day_policy_values",
        ),
        CheckConstraint("priority BETWEEN 1 AND 100", name="priority_range"),
        CheckConstraint("minimum_weekly_minutes >= 0", name="minimum_weekly_nonnegative"),
        CheckConstraint("confidence IN ('low', 'medium', 'high')", name="confidence_values"),
        CheckConstraint("predecessor_project_id IS DISTINCT FROM id", name="predecessor_not_self"),
        CheckConstraint(
            "(status = 'completed' AND terminal_reason = 'user_completed' "
            "AND ended_at IS NOT NULL) OR "
            "(status = 'closed' AND terminal_reason = 'deadline_reached' "
            "AND ended_at IS NOT NULL) OR "
            "(status IN ('draft', 'planning', 'active', 'paused') AND terminal_reason IS NULL "
            "AND ended_at IS NULL) OR "
            "(status = 'archived' AND ((terminal_reason IS NULL AND ended_at IS NULL) OR "
            "(terminal_reason IN ('user_completed', 'deadline_reached') "
            "AND ended_at IS NOT NULL)))",
            name="terminal_state_consistency",
        ),
        ForeignKeyConstraint(
            ["predecessor_project_id", "user_id"],
            ["projects.id", "projects.user_id"],
        ),
        UniqueConstraint("id", "user_id"),
        Index("ix_projects_user_status_priority", "user_id", "status", text("priority DESC")),
        Index("ix_projects_user_target_date", "user_id", "target_date"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    goal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    predecessor_project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    target_date: Mapped[date | None] = mapped_column(Date)
    deadline_day_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="date_inclusive"
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=50)
    minimum_weekly_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="low")
    route_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    plan_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    project_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    task_event_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    terminal_reason: Mapped[str | None] = mapped_column(String(30))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StageModel(Base):
    __tablename__ = "stages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'active', 'advanced', 'paused', 'superseded', 'closed')",
            name="status_values",
        ),
        CheckConstraint("estimated_minutes >= 0", name="estimated_minutes_nonnegative"),
        CheckConstraint(
            "closure_reason IS NULL OR closure_reason IN "
            "('project_completed', 'project_closed', 'project_archived')",
            name="closure_reason_values",
        ),
        ForeignKeyConstraint(["project_id", "user_id"], ["projects.id", "projects.user_id"]),
        UniqueConstraint("id", "user_id", "project_id"),
        Index(
            "uq_stages_route_order",
            "project_id",
            "order_key",
            unique=True,
            postgresql_where=text("status <> 'superseded'"),
        ),
        Index(
            "uq_stages_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    order_key: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_start_week: Mapped[date | None] = mapped_column(Date)
    target_end_week: Mapped[date | None] = mapped_column(Date)
    created_route_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_route_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    advanced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_reason: Mapped[str | None] = mapped_column(String(30))


class MilestoneModel(Base):
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'active', 'advanced', 'paused', 'superseded', 'closed')",
            name="status_values",
        ),
        CheckConstraint("estimated_minutes >= 0", name="estimated_minutes_nonnegative"),
        CheckConstraint(
            "closure_reason IS NULL OR closure_reason IN "
            "('project_completed', 'project_closed', 'project_archived')",
            name="closure_reason_values",
        ),
        ForeignKeyConstraint(
            ["stage_id", "user_id", "project_id"],
            ["stages.id", "stages.user_id", "stages.project_id"],
        ),
        UniqueConstraint("id", "user_id", "project_id"),
        Index(
            "uq_milestones_stage_order",
            "stage_id",
            "order_key",
            unique=True,
            postgresql_where=text("status <> 'superseded'"),
        ),
        Index(
            "uq_milestones_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    stage_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    order_key: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    progression_references: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_week_start: Mapped[date | None] = mapped_column(Date)
    hard_prerequisites: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_route_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_route_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    advanced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_reason: Mapped[str | None] = mapped_column(String(30))


class ProjectClosureSnapshotModel(Base):
    __tablename__ = "project_closure_snapshots"
    __table_args__ = (
        CheckConstraint("closure_reason = 'deadline_reached'", name="closure_reason_value"),
        CheckConstraint(
            "deadline_day_policy IN ('event_exclusive', 'date_inclusive')",
            name="deadline_day_policy_values",
        ),
        CheckConstraint(
            "last_feasibility_status IN ('feasible', 'at_risk', 'infeasible', 'unknown')",
            name="feasibility_status_values",
        ),
        CheckConstraint(
            "completed_task_count >= 0 AND unfinished_task_count >= 0 AND "
            "completed_estimated_minutes >= 0 AND completed_actual_minutes >= 0 AND "
            "unfinished_estimated_minutes >= 0",
            name="nonnegative_summaries",
        ),
        ForeignKeyConstraint(["project_id", "user_id"], ["projects.id", "projects.user_id"]),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    closure_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline_day_policy: Mapped[str] = mapped_column(String(20), nullable=False)
    last_feasibility_status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_risk_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unfinished_task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_actual_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unfinished_estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
