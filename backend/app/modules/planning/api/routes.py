from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status

from app.core.observability import get_correlation_id
from app.core.schemas import SuccessEnvelope
from app.modules.identity.api.dependencies import current_claims
from app.modules.identity.application.idempotency import (
    ClaimStatus,
    IdempotencyRequest,
    IdempotencyService,
)
from app.modules.identity.domain.entities import AccessClaims
from app.modules.planning.api.dependencies import get_idempotency_service, get_project_service
from app.modules.planning.api.schemas import (
    ClosureResponse,
    CompleteProjectRequest,
    CreateProjectRequest,
    CurrentMilestoneResponse,
    CurrentRouteResponse,
    CurrentStageResponse,
    FutureMilestoneResponse,
    HistoryMilestoneResponse,
    ProjectCommandRequest,
    ProjectResponse,
    RenameProjectRequest,
    RouteResponse,
)
from app.modules.planning.application.projects import CreateProject, ProjectService
from app.modules.planning.domain.projects import Project, RouteView

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse.model_validate(project, from_attributes=True)


def _route_response(route: RouteView) -> RouteResponse:
    current = None
    if route.current:
        current = CurrentRouteResponse(
            stage=CurrentStageResponse(id=route.current.stage_id, title=route.current.stage_title),
            milestone=CurrentMilestoneResponse(
                id=route.current.milestone_id,
                title=route.current.milestone_title,
                status=route.current.milestone_status,
            ),
        )
    return RouteResponse(
        project_id=route.project_id,
        route_revision=route.route_revision,
        current=current,
        history_milestones=[
            HistoryMilestoneResponse.model_validate(item, from_attributes=True)
            for item in route.history_milestones
        ],
        future_milestones=[
            FutureMilestoneResponse.model_validate(item, from_attributes=True)
            for item in route.future_milestones
        ],
    )


async def _idempotent_project_command(
    *,
    request: Request,
    claims: AccessClaims,
    key: str,
    body: dict[str, Any],
    idempotency: IdempotencyService,
    operation: Callable[[], Awaitable[Project]],
    success_status: int = 200,
) -> ProjectResponse:
    claim = await idempotency.claim(
        IdempotencyRequest.create(
            user_id=claims.user_id,
            key=key,
            method=request.method,
            path=request.url.path,
            body=body,
        )
    )
    if claim.status is ClaimStatus.REPLAY:
        if claim.response_body is None:
            raise RuntimeError("completed idempotency record has no response body")
        return ProjectResponse.model_validate(claim.response_body)
    response = _project_response(await operation())
    await idempotency.complete(
        claim,
        success_status,
        response.model_dump(mode="json"),
        resource_type="project",
        resource_id=response.id,
    )
    return response


@router.post(
    "", response_model=SuccessEnvelope[ProjectResponse], status_code=status.HTTP_201_CREATED
)
async def create_project(
    request: Request,
    body: CreateProjectRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> SuccessEnvelope[ProjectResponse]:
    data = await _idempotent_project_command(
        request=request,
        claims=claims,
        key=idempotency_key,
        body=body.model_dump(mode="json"),
        idempotency=idempotency,
        success_status=201,
        operation=lambda: projects.create(
            claims.user_id,
            CreateProject(
                name=body.name,
                description=body.description,
                goal_type=body.goal_type,
                target_date=body.target_date,
                deadline_day_policy=body.deadline_day_policy,
                priority=body.priority,
                minimum_weekly_minutes=body.minimum_weekly_minutes,
                predecessor_project_id=body.predecessor_project_id,
            ),
        ),
    )
    return SuccessEnvelope(data=data, correlation_id=get_correlation_id())


@router.get("", response_model=SuccessEnvelope[list[ProjectResponse]])
async def list_projects(
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
) -> SuccessEnvelope[list[ProjectResponse]]:
    rows = await projects.list(claims.user_id)
    return SuccessEnvelope(
        data=[_project_response(row) for row in rows], correlation_id=get_correlation_id()
    )


@router.get("/{project_id}", response_model=SuccessEnvelope[ProjectResponse])
async def get_project(
    project_id: UUID,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
) -> SuccessEnvelope[ProjectResponse]:
    return SuccessEnvelope(
        data=_project_response(await projects.get(claims.user_id, project_id)),
        correlation_id=get_correlation_id(),
    )


@router.patch("/{project_id}", response_model=SuccessEnvelope[ProjectResponse])
async def rename_project(
    project_id: UUID,
    body: RenameProjectRequest,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
) -> SuccessEnvelope[ProjectResponse]:
    project = await projects.rename(
        claims.user_id, project_id, body.expected_project_revision, body.name
    )
    return SuccessEnvelope(data=_project_response(project), correlation_id=get_correlation_id())


@router.get("/{project_id}/route", response_model=SuccessEnvelope[RouteResponse])
async def route(
    project_id: UUID,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
) -> SuccessEnvelope[RouteResponse]:
    return SuccessEnvelope(
        data=_route_response(await projects.route(claims.user_id, project_id)),
        correlation_id=get_correlation_id(),
    )


@router.get("/{project_id}/closure", response_model=SuccessEnvelope[ClosureResponse])
async def closure(
    project_id: UUID,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
) -> SuccessEnvelope[ClosureResponse]:
    snapshot = await projects.closure(claims.user_id, project_id)
    return SuccessEnvelope(
        data=ClosureResponse.model_validate(snapshot, from_attributes=True),
        correlation_id=get_correlation_id(),
    )


async def _run_transition(
    *,
    request: Request,
    project_id: UUID,
    body: ProjectCommandRequest,
    idempotency_key: str,
    claims: AccessClaims,
    projects: ProjectService,
    idempotency: IdempotencyService,
    operation: Callable[[UUID, UUID, int], Awaitable[Project]],
) -> SuccessEnvelope[ProjectResponse]:
    data = await _idempotent_project_command(
        request=request,
        claims=claims,
        key=idempotency_key,
        body=body.model_dump(mode="json"),
        idempotency=idempotency,
        operation=lambda: operation(claims.user_id, project_id, body.expected_project_revision),
    )
    return SuccessEnvelope(data=data, correlation_id=get_correlation_id())


@router.post("/{project_id}/pause", response_model=SuccessEnvelope[ProjectResponse])
async def pause_project(
    request: Request,
    project_id: UUID,
    body: ProjectCommandRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> SuccessEnvelope[ProjectResponse]:
    return await _run_transition(
        request=request,
        project_id=project_id,
        body=body,
        idempotency_key=idempotency_key,
        claims=claims,
        projects=projects,
        idempotency=idempotency,
        operation=projects.pause,
    )


@router.post("/{project_id}/resume", response_model=SuccessEnvelope[ProjectResponse])
async def resume_project(
    request: Request,
    project_id: UUID,
    body: ProjectCommandRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> SuccessEnvelope[ProjectResponse]:
    return await _run_transition(
        request=request,
        project_id=project_id,
        body=body,
        idempotency_key=idempotency_key,
        claims=claims,
        projects=projects,
        idempotency=idempotency,
        operation=projects.resume,
    )


@router.post("/{project_id}/complete", response_model=SuccessEnvelope[ProjectResponse])
async def complete_project(
    request: Request,
    project_id: UUID,
    body: CompleteProjectRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> SuccessEnvelope[ProjectResponse]:
    return await _run_transition(
        request=request,
        project_id=project_id,
        body=body,
        idempotency_key=idempotency_key,
        claims=claims,
        projects=projects,
        idempotency=idempotency,
        operation=projects.complete,
    )


@router.post("/{project_id}/archive", response_model=SuccessEnvelope[ProjectResponse])
async def archive_project(
    request: Request,
    project_id: UUID,
    body: ProjectCommandRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    claims: Annotated[AccessClaims, Depends(current_claims)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> SuccessEnvelope[ProjectResponse]:
    return await _run_transition(
        request=request,
        project_id=project_id,
        body=body,
        idempotency_key=idempotency_key,
        claims=claims,
        projects=projects,
        idempotency=idempotency,
        operation=projects.archive,
    )
