"""create user-week capacities, immutable allocations and coordinator runs"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0004"
down_revision: str | None = "20260716_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_week_capacities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("total_minutes", sa.Integer(), nullable=False),
        sa.Column("allocatable_minutes", sa.Integer(), nullable=False),
        sa.Column("buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("allocated_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("planned_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("preference_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "active_allocation_revision", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        sa.CheckConstraint(
            "total_minutes >= 0 AND allocatable_minutes >= 0 AND buffer_minutes >= 0 "
            "AND allocated_minutes >= 0 AND planned_minutes >= 0 AND actual_minutes >= 0",
            name="minute_summaries_nonnegative",
        ),
        sa.CheckConstraint(
            "allocatable_minutes + buffer_minutes <= total_minutes", name="safe_capacity_total"
        ),
        sa.CheckConstraint(
            "allocated_minutes <= allocatable_minutes", name="allocated_within_capacity"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'allocated', 'active', 'settled')", name="status_values"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_capacity_user"),
        sa.PrimaryKeyConstraint("id", name="pk_user_week_capacities"),
        sa.UniqueConstraint("user_id", "week_start", name="uq_capacity_user_week"),
        sa.UniqueConstraint("id", "user_id", name="uq_capacity_id_user"),
    )

    op.create_table(
        "user_week_allocation_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_week_capacity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocation_revision", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("allocated_minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("source_user_week_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'settled')", name="status_values"
        ),
        sa.CheckConstraint("allocated_minutes >= 0", name="allocated_minutes_nonnegative"),
        sa.CheckConstraint(
            "reason IN ('initial', 'rollover', 'new_project', 'capacity_change', 'recovery')",
            name="reason_values",
        ),
        sa.ForeignKeyConstraint(
            ["user_week_capacity_id", "user_id"],
            ["user_week_capacities.id", "user_week_capacities.user_id"],
            name="fk_allocation_sets_capacity_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_week_allocation_sets"),
        sa.UniqueConstraint(
            "user_week_capacity_id",
            "allocation_revision",
            name="uq_allocation_sets_capacity_revision",
        ),
        sa.UniqueConstraint(
            "id", "user_id", "user_week_capacity_id", name="uq_allocation_sets_id_user_capacity"
        ),
    )
    op.create_index(
        "uq_allocation_sets_one_active_per_capacity",
        "user_week_allocation_sets",
        ["user_week_capacity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "user_week_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_week_capacity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocation_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_minutes", sa.Integer(), nullable=False),
        sa.Column("minimum_minutes", sa.Integer(), nullable=False),
        sa.Column("priority_snapshot", sa.SmallInteger(), nullable=False),
        sa.Column("project_revision_snapshot", sa.BigInteger(), nullable=False),
        sa.Column("deadline_risk", sa.String(10), nullable=False),
        sa.Column("allocation_reason", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "budget_minutes >= 0 AND minimum_minutes >= 0 AND planned_minutes >= 0 "
            "AND actual_minutes >= 0",
            name="minute_values_nonnegative",
        ),
        sa.CheckConstraint("priority_snapshot BETWEEN 1 AND 100", name="priority_range"),
        sa.CheckConstraint(
            "deadline_risk IN ('none', 'low', 'medium', 'high')", name="deadline_risk_values"
        ),
        sa.CheckConstraint(
            "allocation_reason IN ('scheduled', 'capacity_shortage')",
            name="allocation_reason_values",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'active', 'unfunded', 'released', 'settled')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "(budget_minutes = 0 AND allocation_reason = 'capacity_shortage' "
            "AND status IN ('unfunded', 'released', 'settled')) OR "
            "(budget_minutes > 0 AND allocation_reason = 'scheduled' AND status <> 'unfunded')",
            name="unfunded_consistency",
        ),
        sa.CheckConstraint(
            "planned_minutes <= budget_minutes OR status IN ('released', 'settled')",
            name="planned_within_live_budget",
        ),
        sa.ForeignKeyConstraint(
            ["allocation_set_id", "user_id", "user_week_capacity_id"],
            [
                "user_week_allocation_sets.id",
                "user_week_allocation_sets.user_id",
                "user_week_allocation_sets.user_week_capacity_id",
            ],
            name="fk_allocations_set_user_capacity",
        ),
        sa.ForeignKeyConstraint(
            ["user_week_capacity_id", "user_id"],
            ["user_week_capacities.id", "user_week_capacities.user_id"],
            name="fk_allocations_capacity_user",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_allocations_project_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_week_allocations"),
        sa.UniqueConstraint("allocation_set_id", "project_id", name="uq_allocations_set_project"),
        sa.UniqueConstraint("id", "user_id", "project_id", name="uq_allocations_id_user_project"),
    )
    op.create_index(
        "ix_allocations_capacity_project",
        "user_week_allocations",
        ["user_week_capacity_id", "project_id"],
    )

    op.create_table(
        "user_week_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("run_type", sa.String(20), nullable=False),
        sa.Column("trigger_ref", sa.String(200)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("expected_projects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_projects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_projects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("promotion_completed_at", sa.DateTime(timezone=True)),
        sa.Column("allocation_set_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        sa.CheckConstraint(
            "run_type IN ('rollover', 'reallocation', 'recovery')", name="run_type_values"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'promoting_baseline', 'allocating', 'dispatching_projects', "
            "'planning_projects', 'completed', 'partial_failed', 'failed')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "expected_projects >= 0 AND succeeded_projects >= 0 AND failed_projects >= 0 "
            "AND succeeded_projects + failed_projects <= expected_projects",
            name="project_counts_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_week_runs_user"),
        sa.ForeignKeyConstraint(
            ["allocation_set_id"],
            ["user_week_allocation_sets.id"],
            name="fk_user_week_runs_allocation_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_week_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_user_week_runs_idempotency_key"),
    )
    op.create_index(
        "uq_user_week_runs_rollover",
        "user_week_runs",
        ["user_id", "week_start"],
        unique=True,
        postgresql_where=sa.text("run_type = 'rollover'"),
    )
    op.create_foreign_key(
        "fk_allocation_sets_source_run",
        "user_week_allocation_sets",
        "user_week_runs",
        ["source_user_week_run_id"],
        ["id"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_applied_allocation_set_definition_change() RETURNS trigger AS $$
        BEGIN
          IF OLD.status <> 'draft' AND (
            NEW.user_id IS DISTINCT FROM OLD.user_id OR
            NEW.user_week_capacity_id IS DISTINCT FROM OLD.user_week_capacity_id OR
            NEW.allocation_revision IS DISTINCT FROM OLD.allocation_revision OR
            NEW.allocated_minutes IS DISTINCT FROM OLD.allocated_minutes OR
            NEW.reason IS DISTINCT FROM OLD.reason OR
            NEW.source_user_week_run_id IS DISTINCT FROM OLD.source_user_week_run_id OR
            NEW.created_at IS DISTINCT FROM OLD.created_at
          ) THEN
            RAISE EXCEPTION 'applied allocation set definition is immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_allocation_sets_immutable_definition
        BEFORE UPDATE ON user_week_allocation_sets FOR EACH ROW
        EXECUTE FUNCTION reject_applied_allocation_set_definition_change();
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_applied_allocation_item_definition_change() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM user_week_allocation_sets s
            WHERE s.id = OLD.allocation_set_id AND s.status <> 'draft'
          ) AND (
            NEW.user_id IS DISTINCT FROM OLD.user_id OR
            NEW.user_week_capacity_id IS DISTINCT FROM OLD.user_week_capacity_id OR
            NEW.allocation_set_id IS DISTINCT FROM OLD.allocation_set_id OR
            NEW.project_id IS DISTINCT FROM OLD.project_id OR
            NEW.budget_minutes IS DISTINCT FROM OLD.budget_minutes OR
            NEW.minimum_minutes IS DISTINCT FROM OLD.minimum_minutes OR
            NEW.priority_snapshot IS DISTINCT FROM OLD.priority_snapshot OR
            NEW.project_revision_snapshot IS DISTINCT FROM OLD.project_revision_snapshot OR
            NEW.deadline_risk IS DISTINCT FROM OLD.deadline_risk
          ) THEN
            RAISE EXCEPTION 'applied allocation item definition is immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_allocation_items_immutable_definition
        BEFORE UPDATE ON user_week_allocations FOR EACH ROW
        EXECUTE FUNCTION reject_applied_allocation_item_definition_change();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_allocation_items_immutable_definition "
        "ON user_week_allocations"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_applied_allocation_item_definition_change()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_allocation_sets_immutable_definition "
        "ON user_week_allocation_sets"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_applied_allocation_set_definition_change()")
    op.drop_constraint(
        "fk_allocation_sets_source_run", "user_week_allocation_sets", type_="foreignkey"
    )
    op.drop_table("user_week_runs")
    op.drop_table("user_week_allocations")
    op.drop_table("user_week_allocation_sets")
    op.drop_table("user_week_capacities")
