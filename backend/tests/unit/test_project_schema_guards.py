from pathlib import Path
from typing import cast

from sqlalchemy import Table

from app.modules.planning.infrastructure.models import MilestoneModel, ProjectModel, StageModel


def test_project_route_metadata_contains_tenant_and_single_active_guards() -> None:
    project_table = cast(Table, ProjectModel.__table__)
    stage_table = cast(Table, StageModel.__table__)
    milestone_table = cast(Table, MilestoneModel.__table__)
    project_constraints = {constraint.name for constraint in project_table.constraints}
    assert "uq_projects_id" in project_constraints
    assert "ck_projects_terminal_state_consistency" in project_constraints

    stage_indexes = {str(index.name): index for index in stage_table.indexes}
    milestone_indexes = {str(index.name): index for index in milestone_table.indexes}
    assert stage_indexes["uq_stages_one_active_per_project"].unique is True
    assert milestone_indexes["uq_milestones_one_active_per_project"].unique is True
    assert milestone_indexes["uq_milestones_stage_order"].unique is True


def test_migration_installs_frozen_route_and_immutable_snapshot_triggers() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260716_0003_projects_route.py"
    ).read_text(encoding="utf-8")
    assert "trg_stages_frozen_definition" in migration
    assert "trg_milestones_frozen_definition" in migration
    assert "OLD.status IN ('advanced', 'superseded', 'closed')" in migration
    assert "trg_closure_snapshot_immutable" in migration
