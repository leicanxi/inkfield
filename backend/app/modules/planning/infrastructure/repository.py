from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.database.session import transaction_scope
from app.modules.planning.application.projects import ClosureSummary, CreateProject
from app.modules.planning.domain.projects import (
    ClosureSnapshot,
    Confidence,
    CurrentRouteNode,
    DeadlineDayPolicy,
    FutureMilestone,
    GoalType,
    HistoryMilestone,
    Project,
    ProjectStatus,
    RouteClosureReason,
    RouteStatus,
    RouteView,
    TerminalReason,
)
from app.modules.planning.infrastructure.models import (
    MilestoneModel,
    ProjectClosureSnapshotModel,
    ProjectModel,
    StageModel,
)


def _project(row: ProjectModel) -> Project:
    return Project(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        description=row.description,
        goal_type=GoalType(row.goal_type),
        predecessor_project_id=row.predecessor_project_id,
        status=ProjectStatus(row.status),
        target_date=row.target_date,
        deadline_day_policy=DeadlineDayPolicy(row.deadline_day_policy),
        priority=row.priority,
        minimum_weekly_minutes=row.minimum_weekly_minutes,
        confidence=Confidence(row.confidence),
        route_revision=row.route_revision,
        plan_revision=row.plan_revision,
        project_revision=row.project_revision,
        task_event_revision=row.task_event_revision,
        terminal_reason=TerminalReason(row.terminal_reason) if row.terminal_reason else None,
        ended_at=row.ended_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _closure(row: ProjectClosureSnapshotModel) -> ClosureSnapshot:
    return ClosureSnapshot(
        id=row.id,
        project_id=row.project_id,
        user_id=row.user_id,
        closure_reason=TerminalReason(row.closure_reason),
        target_date=row.target_date,
        deadline_day_policy=DeadlineDayPolicy(row.deadline_day_policy),
        last_feasibility_status=row.last_feasibility_status,
        last_risk_detected_at=row.last_risk_detected_at,
        completed_task_count=row.completed_task_count,
        unfinished_task_count=row.unfinished_task_count,
        completed_estimated_minutes=row.completed_estimated_minutes,
        completed_actual_minutes=row.completed_actual_minutes,
        unfinished_estimated_minutes=row.unfinished_estimated_minutes,
        snapshot=row.snapshot,
        created_at=row.created_at,
    )


class SqlProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: UUID, command: CreateProject, now: datetime) -> Project:
        async with transaction_scope(self._session):
            if command.predecessor_project_id:
                await self._validate_predecessor(user_id, command.predecessor_project_id)
            row = ProjectModel(
                id=uuid4(),
                user_id=user_id,
                name=command.name.strip(),
                description=command.description.strip(),
                goal_type=command.goal_type.value,
                predecessor_project_id=command.predecessor_project_id,
                status=ProjectStatus.DRAFT.value,
                target_date=command.target_date,
                deadline_day_policy=command.deadline_day_policy.value,
                priority=command.priority,
                minimum_weekly_minutes=command.minimum_weekly_minutes,
                confidence=Confidence.LOW.value,
                route_revision=1,
                plan_revision=1,
                project_revision=1,
                task_event_revision=0,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
            await self._session.flush()
            return _project(row)

    async def get(self, user_id: UUID, project_id: UUID) -> Project | None:
        row = await self._session.scalar(
            select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
                ProjectModel.deleted_at.is_(None),
            )
        )
        return _project(row) if row else None

    async def list(self, user_id: UUID) -> list[Project]:
        rows = (
            await self._session.scalars(
                select(ProjectModel)
                .where(ProjectModel.user_id == user_id, ProjectModel.deleted_at.is_(None))
                .order_by(ProjectModel.priority.desc(), ProjectModel.created_at)
            )
        ).all()
        return [_project(row) for row in rows]

    async def lock(self, user_id: UUID, project_id: UUID) -> Project | None:
        row = await self._session.scalar(
            select(ProjectModel)
            .where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
                ProjectModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return _project(row) if row else None

    async def save(self, project: Project) -> Project:
        async with transaction_scope(self._session):
            row = await self._session.scalar(
                update(ProjectModel)
                .where(ProjectModel.id == project.id, ProjectModel.user_id == project.user_id)
                .values(
                    name=project.name,
                    status=project.status.value,
                    route_revision=project.route_revision,
                    plan_revision=project.plan_revision,
                    project_revision=project.project_revision,
                    task_event_revision=project.task_event_revision,
                    terminal_reason=(
                        project.terminal_reason.value if project.terminal_reason else None
                    ),
                    ended_at=project.ended_at,
                    updated_at=project.updated_at,
                )
                .returning(ProjectModel)
            )
            if row is None:
                raise AppError("PROJECT_NOT_FOUND", "Project not found.", status_code=404)
            return _project(row)

    async def route(self, user_id: UUID, project_id: UUID) -> RouteView | None:
        project = await self._session.scalar(
            select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
                ProjectModel.deleted_at.is_(None),
            )
        )
        if project is None:
            return None
        rows = (
            await self._session.execute(
                select(StageModel, MilestoneModel)
                .join(
                    MilestoneModel,
                    (MilestoneModel.stage_id == StageModel.id)
                    & (MilestoneModel.project_id == StageModel.project_id)
                    & (MilestoneModel.user_id == StageModel.user_id),
                )
                .where(StageModel.project_id == project_id, StageModel.user_id == user_id)
                .order_by(
                    StageModel.order_key,
                    StageModel.created_route_revision,
                    MilestoneModel.order_key,
                    MilestoneModel.created_route_revision,
                    MilestoneModel.id,
                )
            )
        ).all()
        current: CurrentRouteNode | None = None
        history: list[HistoryMilestone] = []
        future: list[FutureMilestone] = []
        for stage, milestone in rows:
            status = RouteStatus(milestone.status)
            if status is RouteStatus.ACTIVE:
                if RouteStatus(stage.status) is not RouteStatus.ACTIVE:
                    raise RuntimeError("active milestone must belong to the active stage")
                if current is not None:
                    raise RuntimeError("project has more than one active milestone")
                current = CurrentRouteNode(
                    stage.id,
                    stage.title,
                    milestone.id,
                    milestone.title,
                    status,
                )
            elif status in {
                RouteStatus.ADVANCED,
                RouteStatus.SUPERSEDED,
                RouteStatus.CLOSED,
            }:
                history.append(
                    HistoryMilestone(
                        milestone.id,
                        milestone.title,
                        stage.title,
                        status,
                        milestone.advanced_at or milestone.closed_at,
                    )
                )
            elif status in {RouteStatus.PLANNED, RouteStatus.PAUSED}:
                future.append(
                    FutureMilestone(
                        milestone.id,
                        milestone.title,
                        stage.title,
                        status,
                        milestone.target_week_start,
                    )
                )
        result = RouteView(
            project.id, project.route_revision, current, tuple(history), tuple(future)
        )
        result.validate_disjoint()
        return result

    async def closure(self, user_id: UUID, project_id: UUID) -> ClosureSnapshot | None:
        row = await self._session.scalar(
            select(ProjectClosureSnapshotModel).where(
                ProjectClosureSnapshotModel.project_id == project_id,
                ProjectClosureSnapshotModel.user_id == user_id,
            )
        )
        return _closure(row) if row else None

    async def freeze_open_route(
        self,
        user_id: UUID,
        project_id: UUID,
        reason: RouteClosureReason,
        now: datetime,
    ) -> None:
        async with transaction_scope(self._session):
            statuses = [
                RouteStatus.PLANNED.value,
                RouteStatus.ACTIVE.value,
                RouteStatus.PAUSED.value,
            ]
            await self._session.execute(
                update(MilestoneModel)
                .where(
                    MilestoneModel.user_id == user_id,
                    MilestoneModel.project_id == project_id,
                    MilestoneModel.status.in_(statuses),
                )
                .values(status=RouteStatus.CLOSED.value, closed_at=now, closure_reason=reason.value)
            )
            await self._session.execute(
                update(StageModel)
                .where(
                    StageModel.user_id == user_id,
                    StageModel.project_id == project_id,
                    StageModel.status.in_(statuses),
                )
                .values(status=RouteStatus.CLOSED.value, closed_at=now, closure_reason=reason.value)
            )

    async def create_closure_snapshot(
        self,
        project: Project,
        summary: ClosureSummary,
        now: datetime,
    ) -> ClosureSnapshot:
        if project.target_date is None:
            raise ValueError("closed deadline project requires target_date")
        values = (
            summary.completed_task_count,
            summary.unfinished_task_count,
            summary.completed_estimated_minutes,
            summary.completed_actual_minutes,
            summary.unfinished_estimated_minutes,
        )
        if any(value < 0 for value in values):
            raise AppError("PROJECT_CLOSURE_INVALID", "Closure counters cannot be negative.")
        async with transaction_scope(self._session):
            row = ProjectClosureSnapshotModel(
                id=uuid4(),
                project_id=project.id,
                user_id=project.user_id,
                closure_reason=TerminalReason.DEADLINE_REACHED.value,
                target_date=project.target_date,
                deadline_day_policy=project.deadline_day_policy.value,
                last_feasibility_status=summary.last_feasibility_status,
                last_risk_detected_at=summary.last_risk_detected_at,
                completed_task_count=summary.completed_task_count,
                unfinished_task_count=summary.unfinished_task_count,
                completed_estimated_minutes=summary.completed_estimated_minutes,
                completed_actual_minutes=summary.completed_actual_minutes,
                unfinished_estimated_minutes=summary.unfinished_estimated_minutes,
                snapshot=summary.snapshot or {},
                created_at=now,
            )
            self._session.add(row)
            await self._session.flush()
            return _closure(row)

    async def _validate_predecessor(self, user_id: UUID, predecessor_id: UUID) -> None:
        current_id: UUID | None = predecessor_id
        seen: set[UUID] = set()
        first = True
        while current_id is not None:
            if current_id in seen:
                raise AppError(
                    "PROJECT_PREDECESSOR_INVALID",
                    "The predecessor chain contains a cycle.",
                    status_code=409,
                )
            seen.add(current_id)
            row = await self._session.scalar(
                select(ProjectModel)
                .where(ProjectModel.id == current_id, ProjectModel.user_id == user_id)
                .with_for_update()
            )
            if row is None or (first and row.status != ProjectStatus.CLOSED.value):
                raise AppError(
                    "PROJECT_PREDECESSOR_INVALID",
                    "A predecessor must be a closed project owned by the same user.",
                    status_code=409,
                )
            first = False
            current_id = row.predecessor_project_id
