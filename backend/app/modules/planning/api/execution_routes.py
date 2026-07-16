from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.core.clock import shanghai_week_start
from app.core.observability import get_correlation_id
from app.core.schemas import SuccessEnvelope
from app.modules.identity.api.dependencies import current_claims
from app.modules.identity.application.idempotency import (
    ClaimStatus,
    IdempotencyRequest,
    IdempotencyService,
)
from app.modules.identity.domain.entities import AccessClaims
from app.modules.planning.api.dependencies import get_idempotency_service
from app.modules.planning.api.execution_dependencies import (
    get_capacity_service,
    get_task_service,
    get_week_plan_service,
)
from app.modules.planning.api.execution_schemas import (
    AllocationResponse,
    UserWeekResponse,
    WeekPlanResponse,
)
from app.modules.planning.application.capacity import CapacityService
from app.modules.planning.application.week_plans import WeekPlanService
from app.modules.planning.domain.capacity import UserWeekSummary
from app.modules.tasks.api.schemas import TaskEventRequest, TaskEventResponse, TaskResponse
from app.modules.tasks.application.service import TaskQueryItem, TaskService
from app.modules.tasks.domain.task_events import Necessity, TaskEventCommand, TaskStatus

router = APIRouter(prefix="/api/v1", tags=["execution"])


def _user_week(summary: UserWeekSummary) -> UserWeekResponse:
    return UserWeekResponse(
        capacity_id=summary.capacity_id,
        week_start=summary.week_start,
        total_minutes=summary.total_minutes,
        allocatable_minutes=summary.allocatable_minutes,
        buffer_minutes=summary.buffer_minutes,
        allocated_minutes=summary.allocated_minutes,
        planned_minutes=summary.planned_minutes,
        actual_minutes=summary.actual_minutes,
        status=summary.status,
        active_allocation_revision=summary.active_allocation_revision,
        allocations=[
            AllocationResponse.model_validate(item, from_attributes=True)
            for item in summary.allocations
        ],
        updated_at=summary.updated_at,
    )


def _task(item: TaskQueryItem) -> TaskResponse:
    task = item.task
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        week_plan_id=task.week_plan_id,
        source_milestone_id=task.source_milestone_id,
        origin_task_id=task.origin_task_id,
        title=task.title,
        description=task.description,
        task_kind=task.task_kind,
        estimated_minutes=task.estimated_minutes,
        actual_minutes=task.actual_minutes,
        first_completed_at=task.first_completed_at,
        necessity=task.necessity,
        due_date=task.due_date,
        order_key=task.order_key,
        status=task.status,
        version=task.version,
        is_blocking=item.is_blocking,
        is_blocked=item.is_blocked,
        unmet_prerequisites=list(item.unmet_prerequisites),
    )


@router.get("/user-weeks/current", response_model=SuccessEnvelope[UserWeekResponse])
async def current_user_week(
    request: Request,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    capacity: Annotated[CapacityService, Depends(get_capacity_service)],
) -> SuccessEnvelope[UserWeekResponse]:
    week_start = shanghai_week_start(request.app.state.clock)
    return SuccessEnvelope(
        data=_user_week(await capacity.get(claims.user_id, week_start)),
        correlation_id=get_correlation_id(),
    )


@router.get("/user-weeks/{week_start}", response_model=SuccessEnvelope[UserWeekResponse])
async def user_week(
    week_start: date,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    capacity: Annotated[CapacityService, Depends(get_capacity_service)],
) -> SuccessEnvelope[UserWeekResponse]:
    return SuccessEnvelope(
        data=_user_week(await capacity.get(claims.user_id, week_start)),
        correlation_id=get_correlation_id(),
    )


@router.get(
    "/projects/{project_id}/weeks/current",
    response_model=SuccessEnvelope[list[WeekPlanResponse]],
)
async def current_project_weeks(
    project_id: UUID,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    weeks: Annotated[WeekPlanService, Depends(get_week_plan_service)],
) -> SuccessEnvelope[list[WeekPlanResponse]]:
    rows = await weeks.get_project_weeks(claims.user_id, project_id)
    return SuccessEnvelope(
        data=[WeekPlanResponse.model_validate(row, from_attributes=True) for row in rows],
        correlation_id=get_correlation_id(),
    )


@router.get(
    "/projects/{project_id}/weeks/{week_start}",
    response_model=SuccessEnvelope[list[WeekPlanResponse]],
)
async def project_week(
    project_id: UUID,
    week_start: date,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    weeks: Annotated[WeekPlanService, Depends(get_week_plan_service)],
) -> SuccessEnvelope[list[WeekPlanResponse]]:
    rows = await weeks.get_project_weeks(claims.user_id, project_id, week_start)
    return SuccessEnvelope(
        data=[WeekPlanResponse.model_validate(row, from_attributes=True) for row in rows],
        correlation_id=get_correlation_id(),
    )


@router.get("/tasks/current-week", response_model=SuccessEnvelope[list[TaskResponse]])
async def current_week_tasks(
    request: Request,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    tasks: Annotated[TaskService, Depends(get_task_service)],
) -> SuccessEnvelope[list[TaskResponse]]:
    rows = await tasks.query(
        claims.user_id, week_start=shanghai_week_start(request.app.state.clock)
    )
    return SuccessEnvelope(data=[_task(item) for item in rows], correlation_id=get_correlation_id())


@router.get("/tasks", response_model=SuccessEnvelope[list[TaskResponse]])
async def query_tasks(
    claims: Annotated[AccessClaims, Depends(current_claims)],
    tasks: Annotated[TaskService, Depends(get_task_service)],
    week_start: date | None = None,
    project_id: UUID | None = None,
    statuses: Annotated[list[TaskStatus] | None, Query()] = None,
    necessity: Necessity | None = None,
    due_before: date | None = None,
) -> SuccessEnvelope[list[TaskResponse]]:
    rows = await tasks.query(
        claims.user_id,
        week_start=week_start,
        project_id=project_id,
        statuses=tuple(statuses or []),
        necessity=necessity,
        due_before=due_before,
    )
    return SuccessEnvelope(data=[_task(item) for item in rows], correlation_id=get_correlation_id())


@router.get("/tasks/{task_id}", response_model=SuccessEnvelope[TaskResponse])
async def get_task(
    task_id: UUID,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    tasks: Annotated[TaskService, Depends(get_task_service)],
) -> SuccessEnvelope[TaskResponse]:
    return SuccessEnvelope(
        data=_task(await tasks.get(claims.user_id, task_id)),
        correlation_id=get_correlation_id(),
    )


@router.post("/tasks/{task_id}/events", response_model=SuccessEnvelope[TaskEventResponse])
async def append_task_event(
    request: Request,
    task_id: UUID,
    body: TaskEventRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    claims: Annotated[AccessClaims, Depends(current_claims)],
    tasks: Annotated[TaskService, Depends(get_task_service)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> SuccessEnvelope[TaskEventResponse]:
    claim = await idempotency.claim(
        IdempotencyRequest.create(
            user_id=claims.user_id,
            key=idempotency_key,
            method=request.method,
            path=request.url.path,
            body=body.model_dump(mode="json"),
        )
    )
    if claim.status is ClaimStatus.REPLAY:
        if claim.response_body is None:
            raise RuntimeError("completed task-event idempotency record has no response")
        response = TaskEventResponse.model_validate(claim.response_body)
    else:
        result = await tasks.append_event(
            claims.user_id,
            task_id,
            idempotency_key,
            TaskEventCommand(
                body.event_type,
                body.expected_task_version,
                body.actual_minutes,
                body.reason_code,
                body.note,
                body.occurred_at,
            ),
        )
        response = TaskEventResponse.model_validate(result, from_attributes=True)
        await idempotency.complete(
            claim,
            200,
            response.model_dump(mode="json"),
            resource_type="task_event",
            resource_id=response.id,
        )
    return SuccessEnvelope(data=response, correlation_id=get_correlation_id())
