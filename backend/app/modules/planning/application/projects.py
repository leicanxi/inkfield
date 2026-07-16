from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.core.clock import Clock, shanghai_business_date
from app.core.errors import AppError
from app.modules.planning.domain.projects import (
    ClosureSnapshot,
    DeadlineDayPolicy,
    GoalType,
    Project,
    ProjectStatus,
    RouteClosureReason,
    RouteView,
    TerminalReason,
)
from app.modules.planning.domain.state_machines import transition_project


@dataclass(frozen=True, slots=True)
class CreateProject:
    name: str
    description: str
    goal_type: GoalType
    target_date: date | None
    deadline_day_policy: DeadlineDayPolicy
    priority: int
    minimum_weekly_minutes: int
    predecessor_project_id: UUID | None = None

    def validate(self) -> None:
        if not self.name.strip() or len(self.name) > 120:
            raise AppError(
                "PROJECT_INVALID", "Project name is required and at most 120 characters."
            )
        if not self.description.strip():
            raise AppError("PROJECT_INVALID", "Project description is required.")
        if not 1 <= self.priority <= 100:
            raise AppError("PROJECT_INVALID", "Project priority must be between 1 and 100.")
        if self.minimum_weekly_minutes < 0:
            raise AppError("PROJECT_INVALID", "Minimum weekly minutes cannot be negative.")


@dataclass(frozen=True, slots=True)
class ClosureSummary:
    last_feasibility_status: str = "unknown"
    last_risk_detected_at: datetime | None = None
    completed_task_count: int = 0
    unfinished_task_count: int = 0
    completed_estimated_minutes: int = 0
    completed_actual_minutes: int = 0
    unfinished_estimated_minutes: int = 0
    snapshot: dict[str, object] | None = None


class ProjectRepository(Protocol):
    async def create(self, user_id: UUID, command: CreateProject, now: datetime) -> Project: ...

    async def get(self, user_id: UUID, project_id: UUID) -> Project | None: ...

    async def list(self, user_id: UUID) -> list[Project]: ...

    async def lock(self, user_id: UUID, project_id: UUID) -> Project | None: ...

    async def save(self, project: Project) -> Project: ...

    async def route(self, user_id: UUID, project_id: UUID) -> RouteView | None: ...

    async def closure(self, user_id: UUID, project_id: UUID) -> ClosureSnapshot | None: ...

    async def freeze_open_route(
        self,
        user_id: UUID,
        project_id: UUID,
        reason: RouteClosureReason,
        now: datetime,
    ) -> None: ...

    async def create_closure_snapshot(
        self,
        project: Project,
        summary: ClosureSummary,
        now: datetime,
    ) -> ClosureSnapshot: ...


class ProjectLifecycleEffects(Protocol):
    async def pause(self, project: Project, now: datetime) -> None: ...

    async def resume(self, project: Project, now: datetime) -> None: ...

    async def complete(self, project: Project, now: datetime) -> None: ...

    async def archive(self, project: Project, now: datetime) -> None: ...

    async def deadline_close(self, project: Project, now: datetime) -> None: ...


class NoopProjectLifecycleEffects:
    """Extension seam populated by capacity/tasks/planning tasks in later slices."""

    async def pause(self, project: Project, now: datetime) -> None:
        del project, now

    async def resume(self, project: Project, now: datetime) -> None:
        del project, now

    async def complete(self, project: Project, now: datetime) -> None:
        del project, now

    async def archive(self, project: Project, now: datetime) -> None:
        del project, now

    async def deadline_close(self, project: Project, now: datetime) -> None:
        del project, now


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        effects: ProjectLifecycleEffects,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._effects = effects
        self._clock = clock

    async def create(self, user_id: UUID, command: CreateProject) -> Project:
        command.validate()
        return await self._repository.create(user_id, command, self._clock.now())

    async def get(self, user_id: UUID, project_id: UUID) -> Project:
        project = await self._repository.get(user_id, project_id)
        if project is None:
            raise AppError("PROJECT_NOT_FOUND", "Project not found.", status_code=404)
        return project

    async def list(self, user_id: UUID) -> list[Project]:
        return await self._repository.list(user_id)

    async def route(self, user_id: UUID, project_id: UUID) -> RouteView:
        route = await self._repository.route(user_id, project_id)
        if route is None:
            raise AppError("PROJECT_NOT_FOUND", "Project not found.", status_code=404)
        route.validate_disjoint()
        return route

    async def closure(self, user_id: UUID, project_id: UUID) -> ClosureSnapshot:
        snapshot = await self._repository.closure(user_id, project_id)
        if snapshot is None:
            raise AppError(
                "PROJECT_CLOSURE_NOT_FOUND", "Closure snapshot not found.", status_code=404
            )
        return snapshot

    async def rename(
        self, user_id: UUID, project_id: UUID, expected_revision: int, name: str
    ) -> Project:
        if not name.strip() or len(name) > 120:
            raise AppError(
                "PROJECT_INVALID", "Project name is required and at most 120 characters."
            )
        project = await self._locked(user_id, project_id, expected_revision)
        if project.status is ProjectStatus.ARCHIVED:
            raise AppError(
                "STATE_TRANSITION_NOT_ALLOWED", "Archived projects are read-only.", status_code=409
            )
        project.name = name.strip()
        project.project_revision += 1
        project.updated_at = self._clock.now()
        return await self._repository.save(project)

    async def start_planning(
        self, user_id: UUID, project_id: UUID, expected_revision: int
    ) -> Project:
        project = await self._locked(user_id, project_id, expected_revision)
        if project.target_date and project.target_date < shanghai_business_date(self._clock):
            raise AppError(
                "PROJECT_TARGET_DATE_PASSED",
                "The target date has passed and must be reconfirmed.",
                status_code=409,
            )
        transition_project(project, ProjectStatus.PLANNING, self._clock.now())
        return await self._repository.save(project)

    async def activate(self, user_id: UUID, project_id: UUID, expected_revision: int) -> Project:
        project = await self._locked(user_id, project_id, expected_revision)
        if project.target_date and project.target_date < shanghai_business_date(self._clock):
            raise AppError(
                "PROJECT_TARGET_DATE_PASSED",
                "The target date has passed and cannot be activated.",
                status_code=409,
            )
        transition_project(project, ProjectStatus.ACTIVE, self._clock.now())
        return await self._repository.save(project)

    async def pause(self, user_id: UUID, project_id: UUID, expected_revision: int) -> Project:
        project = await self._locked(user_id, project_id, expected_revision)
        transition_project(project, ProjectStatus.PAUSED, self._clock.now())
        await self._effects.pause(project, self._clock.now())
        return await self._repository.save(project)

    async def resume(self, user_id: UUID, project_id: UUID, expected_revision: int) -> Project:
        project = await self._locked(user_id, project_id, expected_revision)
        transition_project(project, ProjectStatus.ACTIVE, self._clock.now())
        await self._effects.resume(project, self._clock.now())
        return await self._repository.save(project)

    async def complete(self, user_id: UUID, project_id: UUID, expected_revision: int) -> Project:
        project = await self._locked(user_id, project_id, expected_revision)
        now = self._clock.now()
        transition_project(
            project,
            ProjectStatus.COMPLETED,
            now,
            terminal_reason=TerminalReason.USER_COMPLETED,
        )
        await self._repository.freeze_open_route(
            user_id, project_id, RouteClosureReason.PROJECT_COMPLETED, now
        )
        project.route_revision += 1
        project.plan_revision += 1
        await self._effects.complete(project, now)
        return await self._repository.save(project)

    async def archive(self, user_id: UUID, project_id: UUID, expected_revision: int) -> Project:
        project = await self._locked(user_id, project_id, expected_revision)
        now = self._clock.now()
        transition_project(project, ProjectStatus.ARCHIVED, now)
        await self._repository.freeze_open_route(
            user_id, project_id, RouteClosureReason.PROJECT_ARCHIVED, now
        )
        project.route_revision += 1
        await self._effects.archive(project, now)
        return await self._repository.save(project)

    async def close_for_deadline(
        self,
        user_id: UUID,
        project_id: UUID,
        expected_revision: int,
        summary: ClosureSummary,
    ) -> tuple[Project, ClosureSnapshot]:
        project = await self._locked(user_id, project_id, expected_revision)
        business_date = shanghai_business_date(self._clock)
        if project.target_date is None or business_date <= project.target_date:
            raise AppError(
                "PROJECT_DEADLINE_NOT_REACHED",
                "The project deadline has not passed.",
                status_code=409,
            )
        now = self._clock.now()
        transition_project(
            project,
            ProjectStatus.CLOSED,
            now,
            terminal_reason=TerminalReason.DEADLINE_REACHED,
        )
        await self._repository.freeze_open_route(
            user_id, project_id, RouteClosureReason.PROJECT_CLOSED, now
        )
        project.route_revision += 1
        project.plan_revision += 1
        await self._effects.deadline_close(project, now)
        saved = await self._repository.save(project)
        snapshot = await self._repository.create_closure_snapshot(saved, summary, now)
        return saved, snapshot

    async def _locked(self, user_id: UUID, project_id: UUID, expected_revision: int) -> Project:
        project = await self._repository.lock(user_id, project_id)
        if project is None:
            raise AppError("PROJECT_NOT_FOUND", "Project not found.", status_code=404)
        if project.project_revision != expected_revision:
            raise AppError(
                "PROJECT_REVISION_CONFLICT",
                "Project changed; reload and try again.",
                status_code=409,
                details={"expected": expected_revision, "actual": project.project_revision},
            )
        return project
