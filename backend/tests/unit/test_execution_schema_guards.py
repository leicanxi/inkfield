from pathlib import Path
from typing import cast

from sqlalchemy import Table

from app.modules.planning.infrastructure.execution_models import (
    TaskEventModel,
    UserWeekAllocationModel,
    UserWeekAllocationSetModel,
    WeekPlanModel,
)


def test_execution_metadata_contains_revision_and_idempotency_guards() -> None:
    sets = cast(Table, UserWeekAllocationSetModel.__table__)
    allocations = cast(Table, UserWeekAllocationModel.__table__)
    plans = cast(Table, WeekPlanModel.__table__)
    events = cast(Table, TaskEventModel.__table__)

    assert {str(index.name) for index in sets.indexes} >= {
        "uq_allocation_sets_one_active_per_capacity"
    }
    assert {str(index.name) for index in plans.indexes} >= {"uq_week_plans_one_current"}
    allocation_constraints = {str(item.name) for item in allocations.constraints}
    assert "ck_user_week_allocations_unfunded_consistency" in allocation_constraints
    event_constraints = {str(item.name) for item in events.constraints}
    assert "uq_task_events_user_id" in event_constraints
    assert "uq_task_events_project_id" in event_constraints


def test_execution_migrations_install_immutable_history_guards() -> None:
    versions = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    allocations = (versions / "20260716_0004_capacity_allocations.py").read_text(encoding="utf-8")
    tasks = (versions / "20260716_0005_weekplans_tasks.py").read_text(encoding="utf-8")

    assert "trg_allocation_sets_immutable_definition" in allocations
    assert "trg_allocation_items_immutable_definition" in allocations
    assert "status IN ('unfunded', 'released', 'settled')" in allocations
    assert "trg_task_events_immutable" in tasks
    assert "trg_tasks_due_date_in_week" in tasks
