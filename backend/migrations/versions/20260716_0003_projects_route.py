"""create projects, route and immutable closure snapshots"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0003"
down_revision: str | None = "20260716_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("goal_type", sa.String(30), nullable=False),
        sa.Column("predecessor_project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("target_date", sa.Date()),
        sa.Column(
            "deadline_day_policy", sa.String(20), nullable=False, server_default="date_inclusive"
        ),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="50"),
        sa.Column("minimum_weekly_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="low"),
        sa.Column("route_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("plan_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("project_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("task_event_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("terminal_reason", sa.String(30)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "goal_type IN ('deadline', 'outcome', 'capability', 'continuous')",
            name="goal_type_values",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'planning', 'active', 'paused', "
            "'completed', 'closed', 'archived')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "deadline_day_policy IN ('event_exclusive', 'date_inclusive')",
            name="deadline_day_policy_values",
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 100", name="priority_range"),
        sa.CheckConstraint("minimum_weekly_minutes >= 0", name="minimum_weekly_nonnegative"),
        sa.CheckConstraint("confidence IN ('low', 'medium', 'high')", name="confidence_values"),
        sa.CheckConstraint(
            "predecessor_project_id IS DISTINCT FROM id", name="predecessor_not_self"
        ),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_projects_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("id", "user_id", name="uq_projects_id_user"),
        sa.ForeignKeyConstraint(
            ["predecessor_project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_projects_predecessor_user",
        ),
    )
    op.create_index(
        "ix_projects_user_status_priority",
        "projects",
        ["user_id", "status", sa.text("priority DESC")],
    )
    op.create_index("ix_projects_user_target_date", "projects", ["user_id", "target_date"])

    op.create_table(
        "stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_key", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "strategy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_start_week", sa.Date()),
        sa.Column("target_end_week", sa.Date()),
        sa.Column("created_route_revision", sa.BigInteger(), nullable=False),
        sa.Column("updated_route_revision", sa.BigInteger(), nullable=False),
        sa.Column("advanced_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closure_reason", sa.String(30)),
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'advanced', 'paused', 'superseded', 'closed')",
            name="status_values",
        ),
        sa.CheckConstraint("estimated_minutes >= 0", name="estimated_minutes_nonnegative"),
        sa.CheckConstraint(
            "closure_reason IS NULL OR closure_reason IN "
            "('project_completed', 'project_closed', 'project_archived')",
            name="closure_reason_values",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_stages_project_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stages"),
        sa.UniqueConstraint("id", "user_id", "project_id", name="uq_stages_id_user_project"),
    )
    op.create_index(
        "uq_stages_route_order",
        "stages",
        ["project_id", "order_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'superseded'"),
    )
    op.create_index(
        "uq_stages_one_active_per_project",
        "stages",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_key", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "coverage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "progression_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_week_start", sa.Date()),
        sa.Column(
            "hard_prerequisites",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_route_revision", sa.BigInteger(), nullable=False),
        sa.Column("updated_route_revision", sa.BigInteger(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("advanced_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closure_reason", sa.String(30)),
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'advanced', 'paused', 'superseded', 'closed')",
            name="status_values",
        ),
        sa.CheckConstraint("estimated_minutes >= 0", name="estimated_minutes_nonnegative"),
        sa.CheckConstraint(
            "closure_reason IS NULL OR closure_reason IN "
            "('project_completed', 'project_closed', 'project_archived')",
            name="closure_reason_values",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id", "user_id", "project_id"],
            ["stages.id", "stages.user_id", "stages.project_id"],
            name="fk_milestones_stage_user_project",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_milestones"),
        sa.UniqueConstraint("id", "user_id", "project_id", name="uq_milestones_id_user_project"),
    )
    op.create_index(
        "uq_milestones_stage_order",
        "milestones",
        ["stage_id", "order_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'superseded'"),
    )
    op.create_index(
        "uq_milestones_one_active_per_project",
        "milestones",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "project_closure_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("closure_reason", sa.String(30), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("deadline_day_policy", sa.String(20), nullable=False),
        sa.Column("last_feasibility_status", sa.String(20), nullable=False),
        sa.Column("last_risk_detected_at", sa.DateTime(timezone=True)),
        sa.Column("completed_task_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unfinished_task_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_estimated_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_actual_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unfinished_estimated_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("closure_reason = 'deadline_reached'", name="closure_reason_value"),
        sa.CheckConstraint(
            "deadline_day_policy IN ('event_exclusive', 'date_inclusive')",
            name="deadline_day_policy_values",
        ),
        sa.CheckConstraint(
            "last_feasibility_status IN ('feasible', 'at_risk', 'infeasible', 'unknown')",
            name="feasibility_status_values",
        ),
        sa.CheckConstraint(
            "completed_task_count >= 0 AND unfinished_task_count >= 0 AND "
            "completed_estimated_minutes >= 0 AND completed_actual_minutes >= 0 AND "
            "unfinished_estimated_minutes >= 0",
            name="nonnegative_summaries",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_closure_user"),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_closure_project_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_closure_snapshots"),
        sa.UniqueConstraint("project_id", name="uq_project_closure_project"),
    )

    op.execute(
        """
        CREATE FUNCTION reject_frozen_stage_definition_change() RETURNS trigger AS $$
        BEGIN
          IF OLD.status IN ('advanced', 'superseded', 'closed') AND (
            NEW.order_key IS DISTINCT FROM OLD.order_key OR
            NEW.title IS DISTINCT FROM OLD.title OR
            NEW.objective IS DISTINCT FROM OLD.objective OR
            NEW.strategy IS DISTINCT FROM OLD.strategy OR
            NEW.estimated_minutes IS DISTINCT FROM OLD.estimated_minutes OR
            NEW.target_start_week IS DISTINCT FROM OLD.target_start_week OR
            NEW.target_end_week IS DISTINCT FROM OLD.target_end_week
          ) THEN
            RAISE EXCEPTION 'frozen stage definition cannot be modified' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_stages_frozen_definition
        BEFORE UPDATE ON stages FOR EACH ROW
        EXECUTE FUNCTION reject_frozen_stage_definition_change();
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_frozen_milestone_definition_change() RETURNS trigger AS $$
        BEGIN
          IF OLD.status IN ('advanced', 'superseded', 'closed') AND (
            NEW.stage_id IS DISTINCT FROM OLD.stage_id OR
            NEW.order_key IS DISTINCT FROM OLD.order_key OR
            NEW.title IS DISTINCT FROM OLD.title OR
            NEW.objective IS DISTINCT FROM OLD.objective OR
            NEW.coverage IS DISTINCT FROM OLD.coverage OR
            NEW.progression_references IS DISTINCT FROM OLD.progression_references OR
            NEW.estimated_minutes IS DISTINCT FROM OLD.estimated_minutes OR
            NEW.target_week_start IS DISTINCT FROM OLD.target_week_start OR
            NEW.hard_prerequisites IS DISTINCT FROM OLD.hard_prerequisites
          ) THEN
            RAISE EXCEPTION 'frozen milestone definition cannot be modified'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_milestones_frozen_definition
        BEFORE UPDATE ON milestones FOR EACH ROW
        EXECUTE FUNCTION reject_frozen_milestone_definition_change();
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_closure_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'project closure snapshot is immutable' USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_closure_snapshot_immutable
        BEFORE UPDATE OR DELETE ON project_closure_snapshots FOR EACH ROW
        EXECUTE FUNCTION reject_closure_snapshot_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_closure_snapshot_immutable ON project_closure_snapshots")
    op.execute("DROP FUNCTION IF EXISTS reject_closure_snapshot_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_milestones_frozen_definition ON milestones")
    op.execute("DROP FUNCTION IF EXISTS reject_frozen_milestone_definition_change()")
    op.execute("DROP TRIGGER IF EXISTS trg_stages_frozen_definition ON stages")
    op.execute("DROP FUNCTION IF EXISTS reject_frozen_stage_definition_change()")
    op.drop_table("project_closure_snapshots")
    op.drop_table("milestones")
    op.drop_table("stages")
    op.drop_table("projects")
