from __future__ import annotations

import asyncio
import copy
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.modules.planning.application.projects import (
    ClosureSummary,
    CreateProject,
    ProjectLifecycleEffects,
    ProjectService,
)
from app.modules.planning.domain.projects import (
    ClosureSnapshot,
    Confidence,
    DeadlineDayPolicy,
    GoalType,
    Project,
    ProjectStatus,
    RouteClosureReason,
    RouteView,
    TerminalReason,
)

NOW = datetime(2026, 7, 16, 4, 0, tzinfo=UTC)


def make_project(user_id: UUID, status: ProjectStatus = ProjectStatus.ACTIVE) -> Project:
    return Project(
        id=uuid4(),
        user_id=user_id,
        name="Learn",
        description="Finish a useful outcome",
        goal_type=GoalType.OUTCOME,
        predecessor_project_id=None,
        status=status,
        target_date=date(2026, 7, 31),
        deadline_day_policy=DeadlineDayPolicy.DATE_INCLUSIVE,
        priority=50,
        minimum_weekly_minutes=60,
        confidence=Confidence.MEDIUM,
        route_revision=3,
        plan_revision=4,
        project_revision=5,
        task_event_revision=0,
        terminal_reason=None,
        ended_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeEffects(ProjectLifecycleEffects):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def pause(self, project: Project, now: datetime) -> None:
        del project, now
        self.calls.append("pause")

    async def resume(self, project: Project, now: datetime) -> None:
        del project, now
        self.calls.append("resume")

    async def complete(self, project: Project, now: datetime) -> None:
        del project, now
        self.calls.append("complete")

    async def archive(self, project: Project, now: datetime) -> None:
        del project, now
        self.calls.append("archive")

    async def deadline_close(self, project: Project, now: datetime) -> None:
        del project, now
        self.calls.append("deadline_close")


class FakeProjectRepository:
    def __init__(self, *projects: Project) -> None:
        self.projects = {project.id: copy.deepcopy(project) for project in projects}
        self.freeze_calls: list[RouteClosureReason] = []
        self.snapshot: ClosureSnapshot | None = None
        self._save_lock = asyncio.Lock()

    async def create(self, user_id: UUID, command: CreateProject, now: datetime) -> Project:
        if command.predecessor_project_id:
            predecessor = self.projects.get(command.predecessor_project_id)
            if (
                predecessor is None
                or predecessor.user_id != user_id
                or predecessor.status is not ProjectStatus.CLOSED
            ):
                raise AppError(
                    "PROJECT_PREDECESSOR_INVALID", "invalid predecessor", status_code=409
                )
        created = make_project(user_id, ProjectStatus.DRAFT)
        created.name = command.name
        created.description = command.description
        created.goal_type = command.goal_type
        created.target_date = command.target_date
        created.predecessor_project_id = command.predecessor_project_id
        created.created_at = now
        created.updated_at = now
        created.project_revision = 1
        created.route_revision = 1
        created.plan_revision = 1
        self.projects[created.id] = copy.deepcopy(created)
        return created

    async def get(self, user_id: UUID, project_id: UUID) -> Project | None:
        value = self.projects.get(project_id)
        return copy.deepcopy(value) if value and value.user_id == user_id else None

    async def list(self, user_id: UUID) -> list[Project]:
        return [
            copy.deepcopy(value) for value in self.projects.values() if value.user_id == user_id
        ]

    async def lock(self, user_id: UUID, project_id: UUID) -> Project | None:
        await asyncio.sleep(0)
        return await self.get(user_id, project_id)

    async def save(self, project: Project) -> Project:
        async with self._save_lock:
            current = self.projects.get(project.id)
            if current is None:
                raise AppError("PROJECT_NOT_FOUND", "not found", status_code=404)
            if current.project_revision != project.project_revision - 1:
                raise AppError(
                    "PROJECT_REVISION_CONFLICT", "concurrent project write", status_code=409
                )
            self.projects[project.id] = copy.deepcopy(project)
            return copy.deepcopy(project)

    async def route(self, user_id: UUID, project_id: UUID) -> RouteView | None:
        if await self.get(user_id, project_id) is None:
            return None
        return RouteView(project_id, 1, None, (), ())

    async def closure(self, user_id: UUID, project_id: UUID) -> ClosureSnapshot | None:
        if (
            self.snapshot
            and self.snapshot.user_id == user_id
            and self.snapshot.project_id == project_id
        ):
            return self.snapshot
        return None

    async def freeze_open_route(
        self,
        user_id: UUID,
        project_id: UUID,
        reason: RouteClosureReason,
        now: datetime,
    ) -> None:
        del user_id, project_id, now
        self.freeze_calls.append(reason)

    async def create_closure_snapshot(
        self, project: Project, summary: ClosureSummary, now: datetime
    ) -> ClosureSnapshot:
        assert project.target_date is not None
        self.snapshot = ClosureSnapshot(
            uuid4(),
            project.id,
            project.user_id,
            TerminalReason.DEADLINE_REACHED,
            project.target_date,
            project.deadline_day_policy,
            summary.last_feasibility_status,
            summary.last_risk_detected_at,
            summary.completed_task_count,
            summary.unfinished_task_count,
            summary.completed_estimated_minutes,
            summary.completed_actual_minutes,
            summary.unfinished_estimated_minutes,
            summary.snapshot or {},
            now,
        )
        return self.snapshot


@pytest.mark.asyncio
async def test_complete_is_explicit_and_freezes_route_with_revisions() -> None:
    user_id = uuid4()
    aggregate = make_project(user_id)
    repository = FakeProjectRepository(aggregate)
    effects = FakeEffects()
    service = ProjectService(repository, effects, FrozenClock(NOW))

    completed = await service.complete(user_id, aggregate.id, 5)
    assert completed.status is ProjectStatus.COMPLETED
    assert completed.terminal_reason is TerminalReason.USER_COMPLETED
    assert completed.project_revision == 6
    assert completed.route_revision == 4
    assert completed.plan_revision == 5
    assert repository.freeze_calls == [RouteClosureReason.PROJECT_COMPLETED]
    assert effects.calls == ["complete"]


@pytest.mark.asyncio
async def test_paused_project_cannot_be_completed_and_stale_revision_is_rejected() -> None:
    user_id = uuid4()
    paused = make_project(user_id, ProjectStatus.PAUSED)
    repository = FakeProjectRepository(paused)
    service = ProjectService(repository, FakeEffects(), FrozenClock(NOW))

    with pytest.raises(AppError) as invalid_state:
        await service.complete(user_id, paused.id, 5)
    assert invalid_state.value.code == "STATE_TRANSITION_NOT_ALLOWED"
    with pytest.raises(AppError) as stale:
        await service.resume(user_id, paused.id, 4)
    assert stale.value.code == "PROJECT_REVISION_CONFLICT"
    unchanged = repository.projects[paused.id]
    assert unchanged.status is ProjectStatus.PAUSED and unchanged.project_revision == 5


@pytest.mark.asyncio
async def test_concurrent_terminal_operations_have_one_serialized_winner() -> None:
    user_id = uuid4()
    aggregate = make_project(user_id)
    repository = FakeProjectRepository(aggregate)
    service = ProjectService(repository, FakeEffects(), FrozenClock(NOW))

    results = await asyncio.gather(
        service.pause(user_id, aggregate.id, 5),
        service.complete(user_id, aggregate.id, 5),
        return_exceptions=True,
    )
    assert sum(isinstance(result, Project) for result in results) == 1
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(failures) == 1 and failures[0].code == "PROJECT_REVISION_CONFLICT"
    assert repository.projects[aggregate.id].project_revision == 6


@pytest.mark.asyncio
async def test_deadline_close_requires_passed_date_and_creates_snapshot() -> None:
    user_id = uuid4()
    aggregate = make_project(user_id)
    aggregate.target_date = date(2026, 7, 15)
    repository = FakeProjectRepository(aggregate)
    effects = FakeEffects()
    service = ProjectService(repository, effects, FrozenClock(NOW))
    closed, snapshot = await service.close_for_deadline(
        user_id,
        aggregate.id,
        5,
        ClosureSummary(unfinished_task_count=2, snapshot={"schema_version": 1}),
    )
    assert closed.status is ProjectStatus.CLOSED
    assert closed.terminal_reason is TerminalReason.DEADLINE_REACHED
    assert snapshot.unfinished_task_count == 2
    assert repository.freeze_calls == [RouteClosureReason.PROJECT_CLOSED]


@pytest.mark.asyncio
async def test_successor_must_reference_same_user_closed_project() -> None:
    user_id, other_user = uuid4(), uuid4()
    open_project = make_project(user_id)
    foreign_closed = make_project(other_user, ProjectStatus.CLOSED)
    foreign_closed.terminal_reason = TerminalReason.DEADLINE_REACHED
    foreign_closed.ended_at = NOW
    repository = FakeProjectRepository(open_project, foreign_closed)
    service = ProjectService(repository, FakeEffects(), FrozenClock(NOW))
    base = CreateProject(
        "Next",
        "Continue",
        GoalType.OUTCOME,
        None,
        DeadlineDayPolicy.DATE_INCLUSIVE,
        50,
        0,
        open_project.id,
    )
    with pytest.raises(AppError) as not_closed:
        await service.create(user_id, base)
    assert not_closed.value.code == "PROJECT_PREDECESSOR_INVALID"
    with pytest.raises(AppError) as cross_tenant:
        await service.create(
            user_id,
            CreateProject(
                "Next",
                "Continue",
                GoalType.OUTCOME,
                None,
                DeadlineDayPolicy.DATE_INCLUSIVE,
                50,
                0,
                foreign_closed.id,
            ),
        )
    assert cross_tenant.value.code == "PROJECT_PREDECESSOR_INVALID"
