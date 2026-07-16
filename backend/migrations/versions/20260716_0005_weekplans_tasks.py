"""create week plans, tasks, dependencies and immutable task events"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0005"
down_revision: str | None = "20260716_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "week_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("project_plan_revision", sa.BigInteger(), nullable=False),
        sa.Column("budget_minutes", sa.Integer(), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("creation_source", sa.String(30), nullable=False),
        sa.Column("source_planning_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        sa.CheckConstraint(
            "status IN ('prepared', 'active', 'settled', 'superseded')", name="status_values"
        ),
        sa.CheckConstraint("generation > 0 AND version > 0", name="positive_versions"),
        sa.CheckConstraint(
            "budget_minutes >= 0 AND planned_minutes >= 0 AND planned_minutes <= budget_minutes",
            name="planned_within_budget",
        ),
        sa.CheckConstraint(
            "creation_source IN ('initial_planning', 'allocation_shell', 'weekly_review', "
            "'temporary_replan', 'recovery', 'calibration_hold')",
            name="creation_source_values",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_week_plans_project_user",
        ),
        sa.ForeignKeyConstraint(
            ["allocation_id", "user_id", "project_id"],
            [
                "user_week_allocations.id",
                "user_week_allocations.user_id",
                "user_week_allocations.project_id",
            ],
            name="fk_week_plans_allocation_user_project",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_week_plans"),
        sa.UniqueConstraint(
            "project_id", "week_start", "generation", name="uq_week_plans_project_week_generation"
        ),
        sa.UniqueConstraint("id", "user_id", "project_id", name="uq_week_plans_id_user_project"),
    )
    op.create_index(
        "uq_week_plans_one_current",
        "week_plans",
        ["project_id", "week_start"],
        unique=True,
        postgresql_where=sa.text("status IN ('prepared', 'active')"),
    )
    op.create_index("ix_week_plans_user_week", "week_plans", ["user_id", "week_start", "status"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_task_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("task_kind", sa.String(20), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("actual_minutes", sa.Integer()),
        sa.Column("first_completed_at", sa.DateTime(timezone=True)),
        sa.Column("necessity", sa.String(10), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("order_key", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("source_command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "task_kind IN ('main', 'review', 'remediation', 'exploration', 'rest')",
            name="task_kind_values",
        ),
        sa.CheckConstraint("estimated_minutes > 0", name="estimated_minutes_positive"),
        sa.CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0", name="actual_minutes_nonnegative"
        ),
        sa.CheckConstraint("necessity IN ('required', 'optional')", name="necessity_values"),
        sa.CheckConstraint(
            "status IN ('planned', 'completed', 'skipped', 'deferred', 'cancelled', 'replaced')",
            name="status_values",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint("origin_task_id IS DISTINCT FROM id", name="origin_not_self"),
        sa.ForeignKeyConstraint(
            ["week_plan_id", "user_id", "project_id"],
            ["week_plans.id", "week_plans.user_id", "week_plans.project_id"],
            name="fk_tasks_week_plan_user_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_milestone_id", "user_id", "project_id"],
            ["milestones.id", "milestones.user_id", "milestones.project_id"],
            name="fk_tasks_milestone_user_project",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.UniqueConstraint("week_plan_id", "order_key", name="uq_tasks_week_order"),
        sa.UniqueConstraint("id", "user_id", "project_id", name="uq_tasks_id_user_project"),
        sa.ForeignKeyConstraint(
            ["origin_task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
            name="fk_tasks_origin_user_project",
        ),
    )
    op.create_index(
        "ix_tasks_user_week_status_order",
        "tasks",
        ["user_id", "week_plan_id", "status", "order_key"],
    )
    op.create_index("ix_tasks_user_due_status", "tasks", ["user_id", "due_date", "status"])
    op.create_index(
        "ix_tasks_project_week_status", "tasks", ["project_id", "week_plan_id", "status"]
    )
    op.create_index("ix_tasks_milestone_status", "tasks", ["source_milestone_id", "status"])

    op.create_table(
        "task_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prerequisite_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependent_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("prerequisite_task_id <> dependent_task_id", name="not_self"),
        sa.ForeignKeyConstraint(
            ["prerequisite_task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
            name="fk_task_dependencies_prerequisite_user_project",
        ),
        sa.ForeignKeyConstraint(
            ["dependent_task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
            name="fk_task_dependencies_dependent_user_project",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_task_dependencies"),
        sa.UniqueConstraint(
            "prerequisite_task_id",
            "dependent_task_id",
            name="uq_task_dependencies_edge",
        ),
    )
    op.create_index("ix_task_dependencies_dependent", "task_dependencies", ["dependent_task_id"])

    op.create_table(
        "task_events",
        sa.Column(
            "event_seq",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_event_revision", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("actual_minutes", sa.Integer()),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("note", sa.Text()),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('completed', 'reopened', 'skipped', 'restored', 'deferred', "
            "'cancelled', 'replaced', 'duration_recorded')",
            name="event_type_values",
        ),
        sa.CheckConstraint(
            "previous_status IN ('planned', 'completed', 'skipped', 'deferred', 'cancelled', "
            "'replaced') AND new_status IN ('planned', 'completed', 'skipped', 'deferred', "
            "'cancelled', 'replaced')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0", name="actual_minutes_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id", "project_id"],
            ["tasks.id", "tasks.user_id", "tasks.project_id"],
            name="fk_task_events_task_user_project",
        ),
        sa.PrimaryKeyConstraint("event_seq", name="pk_task_events"),
        sa.UniqueConstraint("id", name="uq_task_events_id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_task_events_user_key"),
        sa.UniqueConstraint(
            "project_id", "project_event_revision", name="uq_task_events_project_revision"
        ),
    )
    op.create_index(
        "ix_task_events_project_revision",
        "task_events",
        ["project_id", "project_event_revision"],
    )
    op.create_index("ix_task_events_task_seq", "task_events", ["task_id", "event_seq"])

    op.execute(
        """
        CREATE FUNCTION validate_task_due_date_in_week() RETURNS trigger AS $$
        DECLARE plan_week date;
        BEGIN
          IF NEW.due_date IS NULL THEN RETURN NEW; END IF;
          SELECT week_start INTO plan_week FROM week_plans WHERE id = NEW.week_plan_id;
          IF plan_week IS NULL OR NEW.due_date < plan_week OR NEW.due_date > plan_week + 6 THEN
            RAISE EXCEPTION 'task due_date must fall within its week plan'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_tasks_due_date_in_week
        BEFORE INSERT OR UPDATE OF due_date, week_plan_id ON tasks FOR EACH ROW
        EXECUTE FUNCTION validate_task_due_date_in_week();
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_task_event_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'task events are immutable' USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_task_events_immutable
        BEFORE UPDATE OR DELETE ON task_events FOR EACH ROW
        EXECUTE FUNCTION reject_task_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_task_events_immutable ON task_events")
    op.execute("DROP FUNCTION IF EXISTS reject_task_event_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_tasks_due_date_in_week ON tasks")
    op.execute("DROP FUNCTION IF EXISTS validate_task_due_date_in_week()")
    op.drop_table("task_events")
    op.drop_table("task_dependencies")
    op.drop_table("tasks")
    op.drop_table("week_plans")
