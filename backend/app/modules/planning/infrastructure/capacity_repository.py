from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.database.session import transaction_scope
from app.modules.planning.application.capacity import (
    CapacityInput,
    ReallocationCommand,
    UserWeekRunView,
)
from app.modules.planning.domain.capacity import (
    AllocationReason,
    AllocationSetStatus,
    AllocationStatus,
    BudgetDecision,
    CapacityStatus,
    DeadlineRisk,
    ProjectDemand,
    UserWeekRunStatus,
    UserWeekRunType,
    UserWeekSummary,
    allocate_project_budgets,
)
from app.modules.planning.domain.projects import ProjectStatus
from app.modules.planning.infrastructure.execution_models import (
    UserWeekAllocationModel,
    UserWeekAllocationSetModel,
    UserWeekCapacityModel,
    UserWeekRunModel,
    WeekPlanModel,
)
from app.modules.planning.infrastructure.models import ProjectModel


class SqlCapacityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_capacity(
        self, user_id: UUID, value: CapacityInput, now: datetime
    ) -> UserWeekSummary:
        async with transaction_scope(self._session):
            row = await self._session.scalar(
                select(UserWeekCapacityModel)
                .where(
                    UserWeekCapacityModel.user_id == user_id,
                    UserWeekCapacityModel.week_start == value.week_start,
                )
                .with_for_update()
            )
            if row is None:
                row = UserWeekCapacityModel(
                    id=uuid4(),
                    user_id=user_id,
                    week_start=value.week_start,
                    total_minutes=value.total_minutes,
                    allocatable_minutes=value.allocatable_minutes,
                    buffer_minutes=value.buffer_minutes,
                    allocated_minutes=0,
                    planned_minutes=0,
                    actual_minutes=0,
                    status=CapacityStatus.DRAFT.value,
                    preference_revision=value.preference_revision,
                    active_allocation_revision=0,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(row)
                await self._session.flush()
            elif row.status == CapacityStatus.DRAFT.value:
                row.total_minutes = value.total_minutes
                row.allocatable_minutes = value.allocatable_minutes
                row.buffer_minutes = value.buffer_minutes
                row.preference_revision = value.preference_revision
                row.updated_at = now
            elif (
                row.total_minutes != value.total_minutes
                or row.allocatable_minutes != value.allocatable_minutes
                or row.buffer_minutes != value.buffer_minutes
                or row.preference_revision != value.preference_revision
            ):
                raise AppError(
                    "CAPACITY_ALREADY_ALLOCATED",
                    "Allocated capacity cannot be overwritten; "
                    "create a capacity-change allocation.",
                    status_code=409,
                )
            return await self._summary(row)

    async def create_run(
        self,
        user_id: UUID,
        week_start: date,
        run_type: UserWeekRunType,
        trigger_ref: str | None,
        idempotency_key: str,
        now: datetime,
    ) -> UserWeekRunView:
        async with transaction_scope(self._session):
            advisory_key = f"user-week-run:{user_id}:{week_start.isoformat()}:{run_type.value}"
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": advisory_key},
            )
            existing = await self._session.scalar(
                select(UserWeekRunModel).where(UserWeekRunModel.idempotency_key == idempotency_key)
            )
            if existing:
                if (
                    existing.user_id != user_id
                    or existing.week_start != week_start
                    or existing.run_type != run_type.value
                    or existing.trigger_ref != trigger_ref
                ):
                    raise AppError(
                        "IDEMPOTENCY_KEY_REUSED",
                        "The user-week run key was used for another request.",
                        status_code=409,
                    )
                return self._run(existing)
            if run_type is UserWeekRunType.ROLLOVER:
                rollover = await self._session.scalar(
                    select(UserWeekRunModel).where(
                        UserWeekRunModel.user_id == user_id,
                        UserWeekRunModel.week_start == week_start,
                        UserWeekRunModel.run_type == UserWeekRunType.ROLLOVER.value,
                    )
                )
                if rollover:
                    return self._run(rollover)
            row = UserWeekRunModel(
                id=uuid4(),
                user_id=user_id,
                week_start=week_start,
                run_type=run_type.value,
                trigger_ref=trigger_ref,
                status=UserWeekRunStatus.PENDING.value,
                expected_projects=0,
                succeeded_projects=0,
                failed_projects=0,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
            await self._session.flush()
            return self._run(row)

    async def reallocate(
        self, user_id: UUID, command: ReallocationCommand, now: datetime
    ) -> UserWeekSummary:
        async with transaction_scope(self._session):
            capacity = await self._session.scalar(
                select(UserWeekCapacityModel)
                .where(
                    UserWeekCapacityModel.user_id == user_id,
                    UserWeekCapacityModel.week_start == command.week_start,
                )
                .with_for_update()
            )
            if capacity is None:
                raise AppError("USER_WEEK_NOT_FOUND", "User week not found.", status_code=404)
            if capacity.status == CapacityStatus.SETTLED.value:
                raise AppError(
                    "CAPACITY_SETTLED",
                    "A settled user week cannot be reallocated.",
                    status_code=409,
                )
            old_set = await self._session.scalar(
                select(UserWeekAllocationSetModel)
                .where(
                    UserWeekAllocationSetModel.user_week_capacity_id == capacity.id,
                    UserWeekAllocationSetModel.status == AllocationSetStatus.ACTIVE.value,
                )
                .with_for_update()
            )
            old_allocations: list[UserWeekAllocationModel] = []
            if old_set:
                old_allocations = list(
                    (
                        await self._session.scalars(
                            select(UserWeekAllocationModel)
                            .where(UserWeekAllocationModel.allocation_set_id == old_set.id)
                            .order_by(UserWeekAllocationModel.project_id)
                            .with_for_update()
                        )
                    ).all()
                )
            old_by_project = {item.project_id: item for item in old_allocations}
            projects = list(
                (
                    await self._session.scalars(
                        select(ProjectModel)
                        .where(
                            ProjectModel.user_id == user_id,
                            ProjectModel.status == ProjectStatus.ACTIVE.value,
                            ProjectModel.deleted_at.is_(None),
                        )
                        .order_by(ProjectModel.id)
                        .with_for_update()
                    )
                ).all()
            )
            demands = []
            for project in projects:
                previous = old_by_project.get(project.id)
                planned = previous.planned_minutes if previous else 0
                actual = previous.actual_minutes if previous else 0
                desired = command.desired_minutes.get(
                    project.id,
                    previous.budget_minutes if previous else project.minimum_weekly_minutes,
                )
                demands.append(
                    ProjectDemand(
                        project.id,
                        ProjectStatus.ACTIVE,
                        project.priority,
                        project.minimum_weekly_minutes,
                        desired,
                        planned,
                        actual,
                        project.project_revision,
                        DeadlineRisk(previous.deadline_risk) if previous else DeadlineRisk.NONE,
                    )
                )
            unknown = set(command.desired_minutes) - {project.id for project in projects}
            if unknown:
                raise AppError(
                    "ALLOCATION_PROJECT_INELIGIBLE",
                    "Desired allocation contains a paused, terminal, missing, or foreign project.",
                    status_code=409,
                    details={"project_ids": sorted(str(value) for value in unknown)},
                )
            decisions = allocate_project_budgets(
                capacity.allocatable_minutes, demands, prepared=command.prepared
            )
            next_revision = capacity.active_allocation_revision + 1
            new_set = UserWeekAllocationSetModel(
                id=uuid4(),
                user_id=user_id,
                user_week_capacity_id=capacity.id,
                allocation_revision=next_revision,
                status=AllocationSetStatus.DRAFT.value,
                allocated_minutes=sum(item.budget_minutes for item in decisions),
                reason=command.reason.value,
                source_user_week_run_id=command.source_run_id,
                created_at=now,
            )
            self._session.add(new_set)
            await self._session.flush()
            new_by_project: dict[UUID, UserWeekAllocationModel] = {}
            for decision in decisions:
                item = UserWeekAllocationModel(
                    id=uuid4(),
                    user_id=user_id,
                    user_week_capacity_id=capacity.id,
                    allocation_set_id=new_set.id,
                    project_id=decision.project_id,
                    budget_minutes=decision.budget_minutes,
                    minimum_minutes=decision.minimum_minutes,
                    priority_snapshot=decision.priority_snapshot,
                    project_revision_snapshot=decision.project_revision_snapshot,
                    deadline_risk=decision.deadline_risk.value,
                    allocation_reason=decision.allocation_reason.value,
                    status=decision.status.value,
                    planned_minutes=decision.planned_minutes,
                    actual_minutes=decision.actual_minutes,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(item)
                new_by_project[item.project_id] = item
            await self._session.flush()

            if old_allocations:
                live_plans = list(
                    (
                        await self._session.scalars(
                            select(WeekPlanModel)
                            .where(
                                WeekPlanModel.allocation_id.in_(
                                    [allocation.id for allocation in old_allocations]
                                ),
                                WeekPlanModel.status.in_(["prepared", "active"]),
                            )
                            .order_by(WeekPlanModel.project_id)
                            .with_for_update()
                        )
                    ).all()
                )
                for plan in live_plans:
                    replacement = new_by_project.get(plan.project_id)
                    if replacement is None or replacement.budget_minutes < plan.planned_minutes:
                        raise AppError(
                            "ALLOCATION_BELOW_LOCKED_WORK",
                            "New allocation cannot fund the current week plan.",
                            status_code=409,
                        )
                    plan.allocation_id = replacement.id
                    plan.budget_minutes = replacement.budget_minutes
                    plan.version += 1
                    plan.updated_at = now
                    replacement.status = (
                        AllocationStatus.ACTIVE.value
                        if plan.status == "active"
                        else AllocationStatus.RESERVED.value
                    )
                for old in old_allocations:
                    if old.status != AllocationStatus.SETTLED.value:
                        old.status = AllocationStatus.RELEASED.value
                        old.updated_at = now
                if old_set:
                    old_set.status = AllocationSetStatus.SUPERSEDED.value

            new_set.status = AllocationSetStatus.ACTIVE.value
            new_set.activated_at = now
            capacity.active_allocation_revision = next_revision
            capacity.allocated_minutes = new_set.allocated_minutes
            capacity.status = (
                CapacityStatus.ALLOCATED.value if command.prepared else CapacityStatus.ACTIVE.value
            )
            capacity.updated_at = now
            if command.source_run_id:
                await self._session.execute(
                    update(UserWeekRunModel)
                    .where(
                        UserWeekRunModel.id == command.source_run_id,
                        UserWeekRunModel.user_id == user_id,
                    )
                    .values(
                        allocation_set_id=new_set.id,
                        status=UserWeekRunStatus.DISPATCHING_PROJECTS.value,
                        expected_projects=len(decisions),
                        updated_at=now,
                    )
                )
            await self._session.flush()
            return await self._summary(capacity, decisions)

    async def get_summary(self, user_id: UUID, week_start: date) -> UserWeekSummary | None:
        row = await self._session.scalar(
            select(UserWeekCapacityModel).where(
                UserWeekCapacityModel.user_id == user_id,
                UserWeekCapacityModel.week_start == week_start,
            )
        )
        return await self._summary(row) if row else None

    async def _summary(
        self,
        capacity: UserWeekCapacityModel,
        decisions: tuple[BudgetDecision, ...] | None = None,
    ) -> UserWeekSummary:
        if decisions is None:
            rows = (
                await self._session.scalars(
                    select(UserWeekAllocationModel)
                    .join(
                        UserWeekAllocationSetModel,
                        UserWeekAllocationSetModel.id == UserWeekAllocationModel.allocation_set_id,
                    )
                    .where(
                        UserWeekAllocationModel.user_week_capacity_id == capacity.id,
                        UserWeekAllocationSetModel.status == AllocationSetStatus.ACTIVE.value,
                    )
                    .order_by(
                        UserWeekAllocationModel.priority_snapshot.desc(),
                        UserWeekAllocationModel.project_id,
                    )
                )
            ).all()
            decisions = tuple(
                BudgetDecision(
                    row.project_id,
                    row.budget_minutes,
                    row.minimum_minutes,
                    row.priority_snapshot,
                    row.project_revision_snapshot,
                    DeadlineRisk(row.deadline_risk),
                    AllocationReason(row.allocation_reason),
                    AllocationStatus(row.status),
                    row.planned_minutes,
                    row.actual_minutes,
                )
                for row in rows
            )
        return UserWeekSummary(
            capacity.id,
            capacity.user_id,
            capacity.week_start,
            capacity.total_minutes,
            capacity.allocatable_minutes,
            capacity.buffer_minutes,
            capacity.allocated_minutes,
            capacity.planned_minutes,
            capacity.actual_minutes,
            CapacityStatus(capacity.status),
            capacity.active_allocation_revision,
            decisions,
            capacity.updated_at,
        )

    @staticmethod
    def _run(row: UserWeekRunModel) -> UserWeekRunView:
        return UserWeekRunView(
            row.id,
            row.user_id,
            row.week_start,
            UserWeekRunType(row.run_type),
            UserWeekRunStatus(row.status),
            row.idempotency_key,
        )
