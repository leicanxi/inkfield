from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AppError
from app.infrastructure.database.session import transaction_scope
from app.modules.planning.domain.projects import ProjectStatus
from app.modules.planning.infrastructure.execution_models import (
    TaskDependencyModel,
    TaskEventModel,
    TaskModel,
    UserWeekAllocationModel,
    UserWeekAllocationSetModel,
    UserWeekCapacityModel,
    WeekPlanModel,
)
from app.modules.planning.infrastructure.models import ProjectModel
from app.modules.tasks.application.service import TaskEventView, TaskQueryItem
from app.modules.tasks.domain.task_events import (
    Necessity,
    Task,
    TaskEventCommand,
    TaskEventType,
    TaskKind,
    TaskStatus,
    apply_task_event,
    assert_acyclic_dependencies,
)


def _task(row: TaskModel) -> Task:
    return Task(
        row.id,
        row.user_id,
        row.project_id,
        row.week_plan_id,
        row.source_milestone_id,
        row.origin_task_id,
        row.title,
        row.description,
        TaskKind(row.task_kind),
        row.estimated_minutes,
        row.actual_minutes,
        row.first_completed_at,
        Necessity(row.necessity),
        row.due_date,
        row.order_key,
        TaskStatus(row.status),
        row.version,
        row.created_at,
        row.updated_at,
    )


class SqlTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_event(
        self,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        command: TaskEventCommand,
        received_at: datetime,
    ) -> TaskEventView:
        existing = await self._event_by_key(user_id, idempotency_key)
        if existing:
            return self._validate_replay(existing, task_id, command)
        refs = (
            await self._session.execute(
                select(
                    TaskModel.user_id,
                    TaskModel.project_id,
                    TaskModel.week_plan_id,
                    WeekPlanModel.allocation_id,
                    UserWeekAllocationModel.allocation_set_id,
                    UserWeekAllocationModel.user_week_capacity_id,
                )
                .join(WeekPlanModel, WeekPlanModel.id == TaskModel.week_plan_id)
                .join(
                    UserWeekAllocationModel,
                    UserWeekAllocationModel.id == WeekPlanModel.allocation_id,
                )
                .where(TaskModel.id == task_id, TaskModel.user_id == user_id)
            )
        ).one_or_none()
        if refs is None:
            raise AppError("TASK_NOT_FOUND", "Task not found.", status_code=404)

        async with transaction_scope(self._session):
            capacity = await self._session.scalar(
                select(UserWeekCapacityModel)
                .where(
                    UserWeekCapacityModel.id == refs.user_week_capacity_id,
                    UserWeekCapacityModel.user_id == user_id,
                )
                .with_for_update()
            )
            allocation_set = await self._session.scalar(
                select(UserWeekAllocationSetModel)
                .where(
                    UserWeekAllocationSetModel.id == refs.allocation_set_id,
                    UserWeekAllocationSetModel.user_id == user_id,
                )
                .with_for_update()
            )
            allocation = await self._session.scalar(
                select(UserWeekAllocationModel)
                .where(
                    UserWeekAllocationModel.id == refs.allocation_id,
                    UserWeekAllocationModel.user_id == user_id,
                    UserWeekAllocationModel.project_id == refs.project_id,
                )
                .with_for_update()
            )
            project = await self._session.scalar(
                select(ProjectModel)
                .where(ProjectModel.id == refs.project_id, ProjectModel.user_id == user_id)
                .with_for_update()
            )
            week_plan = await self._session.scalar(
                select(WeekPlanModel)
                .where(
                    WeekPlanModel.id == refs.week_plan_id,
                    WeekPlanModel.user_id == user_id,
                    WeekPlanModel.project_id == refs.project_id,
                )
                .with_for_update()
            )
            task_row = await self._session.scalar(
                select(TaskModel)
                .where(
                    TaskModel.id == task_id,
                    TaskModel.user_id == user_id,
                    TaskModel.project_id == refs.project_id,
                )
                .with_for_update()
            )
            if any(
                value is None
                for value in (capacity, allocation_set, allocation, project, week_plan, task_row)
            ):
                raise AppError(
                    "TASK_OWNERSHIP_CHANGED",
                    "Task ownership changed; reload and try again.",
                    status_code=409,
                )
            assert capacity is not None
            assert allocation_set is not None
            assert allocation is not None
            assert project is not None
            assert week_plan is not None
            assert task_row is not None
            if (
                allocation.user_week_capacity_id != capacity.id
                or allocation.allocation_set_id != allocation_set.id
                or week_plan.allocation_id != allocation.id
                or task_row.week_plan_id != week_plan.id
            ):
                raise AppError(
                    "TASK_OWNERSHIP_CHANGED",
                    "Task ownership changed; reload and try again.",
                    status_code=409,
                )
            existing = await self._event_by_key(user_id, idempotency_key)
            if existing:
                return self._validate_replay(existing, task_id, command)
            if (
                week_plan.status == "settled"
                and command.event_type is not TaskEventType.DURATION_RECORDED
            ):
                raise AppError(
                    "WEEK_PLAN_SETTLED",
                    "Settled week tasks only accept cumulative duration corrections.",
                    status_code=409,
                )
            if (
                project.status
                in {
                    ProjectStatus.COMPLETED.value,
                    ProjectStatus.CLOSED.value,
                    ProjectStatus.ARCHIVED.value,
                }
                and command.event_type is not TaskEventType.DURATION_RECORDED
            ):
                raise AppError(
                    "PROJECT_TERMINAL",
                    "Terminal project tasks only accept cumulative duration corrections.",
                    status_code=409,
                )
            aggregate = _task(task_row)
            result = apply_task_event(aggregate, command, received_at)
            delta = result.after_consumed - result.before_consumed
            if allocation.actual_minutes + delta < 0 or capacity.actual_minutes + delta < 0:
                raise AppError(
                    "TASK_SUMMARY_INVALID", "Actual-minute summary cannot become negative."
                )
            next_revision = project.task_event_revision + 1
            event = TaskEventModel(
                id=uuid4(),
                task_id=task_id,
                user_id=user_id,
                project_id=project.id,
                project_event_revision=next_revision,
                event_type=command.event_type.value,
                previous_status=result.previous_status.value,
                new_status=result.new_status.value,
                actual_minutes=command.actual_minutes,
                reason_code=command.reason_code,
                note=command.note,
                idempotency_key=idempotency_key,
                occurred_at=command.occurred_at,
                created_at=received_at,
            )
            self._session.add(event)
            task_row.status = aggregate.status.value
            task_row.actual_minutes = aggregate.actual_minutes
            task_row.first_completed_at = aggregate.first_completed_at
            task_row.version = aggregate.version
            task_row.updated_at = aggregate.updated_at
            project.task_event_revision = next_revision
            project.updated_at = received_at
            allocation.actual_minutes += delta
            allocation.updated_at = received_at
            capacity.actual_minutes += delta
            capacity.updated_at = received_at
            await self._session.flush()
            return self._event_view(event, aggregate.version)

    async def get(self, user_id: UUID, task_id: UUID) -> TaskQueryItem | None:
        items = await self._query_rows(user_id, task_ids=(task_id,))
        return items[0] if items else None

    async def query(
        self,
        user_id: UUID,
        *,
        week_start: date | None,
        project_id: UUID | None,
        statuses: tuple[TaskStatus, ...],
        necessity: Necessity | None,
        due_before: date | None,
    ) -> list[TaskQueryItem]:
        statement = (
            select(TaskModel)
            .join(WeekPlanModel, WeekPlanModel.id == TaskModel.week_plan_id)
            .where(TaskModel.user_id == user_id)
        )
        if week_start is not None:
            statement = statement.where(WeekPlanModel.week_start == week_start)
        if project_id is not None:
            statement = statement.where(TaskModel.project_id == project_id)
        if statuses:
            statement = statement.where(TaskModel.status.in_([status.value for status in statuses]))
        if necessity is not None:
            statement = statement.where(TaskModel.necessity == necessity.value)
        if due_before is not None:
            statement = statement.where(TaskModel.due_date <= due_before)
        statement = statement.order_by(
            case((TaskModel.necessity == Necessity.REQUIRED.value, 0), else_=1),
            TaskModel.order_key,
            TaskModel.id,
        )
        rows = list((await self._session.scalars(statement)).all())
        return await self._decorate(rows)

    async def add_dependencies(
        self,
        user_id: UUID,
        project_id: UUID,
        edges: list[tuple[UUID, UUID]],
        now: datetime,
    ) -> None:
        async with transaction_scope(self._session):
            rows = (
                await self._session.execute(
                    select(
                        TaskDependencyModel.prerequisite_task_id,
                        TaskDependencyModel.dependent_task_id,
                    ).where(
                        TaskDependencyModel.user_id == user_id,
                        TaskDependencyModel.project_id == project_id,
                    )
                )
            ).all()
            existing = [(row.prerequisite_task_id, row.dependent_task_id) for row in rows]
            assert_acyclic_dependencies(existing + edges)
            task_ids = {value for edge in edges for value in edge}
            owned = set(
                (
                    await self._session.scalars(
                        select(TaskModel.id).where(
                            TaskModel.id.in_(task_ids),
                            TaskModel.user_id == user_id,
                            TaskModel.project_id == project_id,
                        )
                    )
                ).all()
            )
            if owned != task_ids:
                raise AppError(
                    "TASK_DEPENDENCY_INVALID",
                    "Dependency tasks must belong to the same user and project.",
                    status_code=409,
                )
            known = set(existing)
            for prerequisite, dependent in edges:
                if (prerequisite, dependent) not in known:
                    self._session.add(
                        TaskDependencyModel(
                            id=uuid4(),
                            user_id=user_id,
                            project_id=project_id,
                            prerequisite_task_id=prerequisite,
                            dependent_task_id=dependent,
                            created_at=now,
                        )
                    )

    async def _query_rows(
        self, user_id: UUID, *, task_ids: tuple[UUID, ...]
    ) -> list[TaskQueryItem]:
        rows = list(
            (
                await self._session.scalars(
                    select(TaskModel).where(
                        TaskModel.user_id == user_id, TaskModel.id.in_(task_ids)
                    )
                )
            ).all()
        )
        return await self._decorate(rows)

    async def _decorate(self, rows: list[TaskModel]) -> list[TaskQueryItem]:
        if not rows:
            return []
        ids = {row.id for row in rows}
        prerequisite = aliased(TaskModel)
        dependencies = (
            await self._session.execute(
                select(
                    TaskDependencyModel.prerequisite_task_id,
                    TaskDependencyModel.dependent_task_id,
                    prerequisite.status,
                )
                .join(prerequisite, prerequisite.id == TaskDependencyModel.prerequisite_task_id)
                .where(
                    or_(
                        TaskDependencyModel.prerequisite_task_id.in_(ids),
                        TaskDependencyModel.dependent_task_id.in_(ids),
                    )
                )
            )
        ).all()
        outgoing = {edge.prerequisite_task_id for edge in dependencies}
        unmet: dict[UUID, list[UUID]] = {}
        for edge in dependencies:
            if edge.status != TaskStatus.COMPLETED.value:
                unmet.setdefault(edge.dependent_task_id, []).append(edge.prerequisite_task_id)
        return [
            TaskQueryItem(
                task=_task(row),
                is_blocking=row.id in outgoing,
                is_blocked=bool(unmet.get(row.id)),
                unmet_prerequisites=tuple(sorted(unmet.get(row.id, []), key=str)),
            )
            for row in rows
        ]

    async def _event_by_key(self, user_id: UUID, idempotency_key: str) -> TaskEventModel | None:
        event: TaskEventModel | None = await self._session.scalar(
            select(TaskEventModel).where(
                TaskEventModel.user_id == user_id,
                TaskEventModel.idempotency_key == idempotency_key,
            )
        )
        return event

    def _validate_replay(
        self, event: TaskEventModel, task_id: UUID, command: TaskEventCommand
    ) -> TaskEventView:
        if (
            event.task_id != task_id
            or event.event_type != command.event_type.value
            or event.actual_minutes != command.actual_minutes
            or event.reason_code != command.reason_code
            or event.note != command.note
            or event.occurred_at != command.occurred_at
        ):
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "The task-event key was used for a different request.",
                status_code=409,
            )
        return self._event_view(event, command.expected_task_version + 1)

    @staticmethod
    def _event_view(event: TaskEventModel, task_version: int) -> TaskEventView:
        return TaskEventView(
            event.id,
            event.task_id,
            event.project_id,
            event.project_event_revision,
            TaskEventType(event.event_type),
            TaskStatus(event.previous_status),
            TaskStatus(event.new_status),
            event.actual_minutes,
            event.reason_code,
            event.note,
            event.occurred_at,
            event.created_at,
            task_version,
        )
