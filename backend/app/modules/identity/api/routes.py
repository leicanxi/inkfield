from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.observability import get_correlation_id
from app.core.schemas import SuccessEnvelope
from app.modules.identity.api.dependencies import (
    current_claims,
    get_auth_service,
    get_preference_service,
)
from app.modules.identity.api.schemas import (
    MeResponse,
    PreferenceResponse,
    PreferenceUpdateRequest,
    RefreshRequest,
    SessionResponse,
    TokenPairResponse,
    WeChatLoginRequest,
)
from app.modules.identity.application.preferences import PreferenceService, PreferenceUpdate
from app.modules.identity.application.service import AuthService, TokenPair
from app.modules.identity.domain.entities import AccessClaims

router = APIRouter(prefix="/api/v1", tags=["identity"])


def _token_response(pair: TokenPair) -> SuccessEnvelope[TokenPairResponse]:
    return SuccessEnvelope(
        data=TokenPairResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            access_expires_in=pair.access_expires_in,
            refresh_expires_in=pair.refresh_expires_in,
        ),
        correlation_id=get_correlation_id(),
    )


@router.post(
    "/auth/wechat/login",
    response_model=SuccessEnvelope[TokenPairResponse],
    status_code=status.HTTP_200_OK,
)
async def wechat_login(
    body: WeChatLoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessEnvelope[TokenPairResponse]:
    pair = await service.wechat_login(
        code=body.code,
        platform=body.platform,
        device_label=body.device_label,
        fingerprint_hash=body.fingerprint_hash,
    )
    return _token_response(pair)


@router.post("/auth/refresh", response_model=SuccessEnvelope[TokenPairResponse])
async def refresh(
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessEnvelope[TokenPairResponse]:
    return _token_response(await service.refresh(body.refresh_token))


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def logout(
    claims: Annotated[AccessClaims, Depends(current_claims)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.logout(claims)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/sessions", response_model=SuccessEnvelope[list[SessionResponse]])
async def sessions(
    claims: Annotated[AccessClaims, Depends(current_claims)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessEnvelope[list[SessionResponse]]:
    rows = await service.sessions(claims.user_id)
    return SuccessEnvelope(
        data=[SessionResponse.model_validate(row, from_attributes=True) for row in rows],
        correlation_id=get_correlation_id(),
    )


@router.delete(
    "/auth/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def revoke_session(
    session_id: UUID,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.revoke_session(claims, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def logout_all(
    claims: Annotated[AccessClaims, Depends(current_claims)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.logout_all(claims)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _preference_response(preference: object) -> PreferenceResponse:
    return PreferenceResponse.model_validate(preference, from_attributes=True)


@router.get("/me", response_model=SuccessEnvelope[MeResponse])
async def me(
    claims: Annotated[AccessClaims, Depends(current_claims)],
    preferences: Annotated[PreferenceService, Depends(get_preference_service)],
) -> SuccessEnvelope[MeResponse]:
    preference = await preferences.get(claims.user_id)
    return SuccessEnvelope(
        data=MeResponse(
            user_id=claims.user_id,
            preferences=_preference_response(preference),
        ),
        correlation_id=get_correlation_id(),
    )


@router.patch("/me/preferences", response_model=SuccessEnvelope[PreferenceResponse])
async def update_preferences(
    body: PreferenceUpdateRequest,
    claims: Annotated[AccessClaims, Depends(current_claims)],
    preferences: Annotated[PreferenceService, Depends(get_preference_service)],
) -> SuccessEnvelope[PreferenceResponse]:
    preference = await preferences.update(
        claims.user_id,
        body.expected_preference_revision,
        PreferenceUpdate(
            weekly_capacity_minutes=body.weekly_capacity_minutes,
            utilization_ratio=body.utilization_ratio,
            preferred_task_minutes=body.preferred_task_minutes,
            max_task_minutes=body.max_task_minutes,
            available_weekdays=body.available_weekdays,
            stable_preferences=body.stable_preferences,
        ),
    )
    return SuccessEnvelope(
        data=_preference_response(preference), correlation_id=get_correlation_id()
    )
