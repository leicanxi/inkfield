from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.errors import AppError
from app.modules.planning.domain.projects import (
    Project,
    ProjectStatus,
    TerminalReason,
)

ALLOWED_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.DRAFT: frozenset({ProjectStatus.PLANNING}),
    ProjectStatus.PLANNING: frozenset(
        {ProjectStatus.ACTIVE, ProjectStatus.DRAFT, ProjectStatus.CLOSED}
    ),
    ProjectStatus.ACTIVE: frozenset(
        {
            ProjectStatus.PAUSED,
            ProjectStatus.COMPLETED,
            ProjectStatus.CLOSED,
            ProjectStatus.ARCHIVED,
        }
    ),
    ProjectStatus.PAUSED: frozenset(
        {ProjectStatus.ACTIVE, ProjectStatus.CLOSED, ProjectStatus.ARCHIVED}
    ),
    ProjectStatus.COMPLETED: frozenset({ProjectStatus.ARCHIVED}),
    ProjectStatus.CLOSED: frozenset({ProjectStatus.ARCHIVED}),
    ProjectStatus.ARCHIVED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class TransitionResult:
    previous: ProjectStatus
    current: ProjectStatus
    project_revision: int


def transition_project(
    project: Project,
    target: ProjectStatus,
    now: datetime,
    *,
    terminal_reason: TerminalReason | None = None,
) -> TransitionResult:
    previous = project.status
    if target not in ALLOWED_TRANSITIONS[previous]:
        raise AppError(
            "STATE_TRANSITION_NOT_ALLOWED",
            "The requested project state transition is not allowed.",
            status_code=409,
            details={"from": previous.value, "to": target.value},
        )

    if target is ProjectStatus.COMPLETED:
        if terminal_reason is not TerminalReason.USER_COMPLETED:
            raise AppError(
                "STATE_TRANSITION_NOT_ALLOWED",
                "Only an explicit user completion can complete a project.",
                status_code=409,
            )
        project.terminal_reason = TerminalReason.USER_COMPLETED
        project.ended_at = now
    elif target is ProjectStatus.CLOSED:
        if terminal_reason is not TerminalReason.DEADLINE_REACHED:
            raise AppError(
                "STATE_TRANSITION_NOT_ALLOWED",
                "A project can only be closed by deterministic deadline settlement.",
                status_code=409,
            )
        project.terminal_reason = TerminalReason.DEADLINE_REACHED
        project.ended_at = now
    elif target is not ProjectStatus.ARCHIVED:
        project.terminal_reason = None
        project.ended_at = None

    project.status = target
    project.project_revision += 1
    project.updated_at = now
    return TransitionResult(previous, target, project.project_revision)
