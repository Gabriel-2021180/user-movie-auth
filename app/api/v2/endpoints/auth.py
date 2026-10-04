import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.v2.deps import client_ip, get_current_user_id, user_agent
from app.core.limiter import limiter
from app.schemas.v2.auth import (
    AuthOut, ForgotPasswordIn, LoginIn, MessageOut, ReactivateIn, RefreshIn, ResetPasswordIn,
    SignupIn, Tokens, VerifyIn,
)
from app.services import auth_service

router = APIRouter()


@router.post("/signup", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
async def signup(request: Request, data: SignupIn):
    return MessageOut(message=await auth_service.signup(data))


@router.post("/verify", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/10minutes")
def verify(
    request: Request, data: VerifyIn,
    ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent),
):
    return auth_service.verify(data, ua, ip)


@router.post("/login", response_model=AuthOut)
@limiter.limit("10/minute")
def login(
    request: Request, data: LoginIn,
    ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent),
):
    return auth_service.login(data, ua, ip)


@router.post("/refresh", response_model=Tokens)
@limiter.limit("30/minute")
def refresh(
    request: Request, data: RefreshIn,
    ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent),
):
    return auth_service.refresh(data.refresh_token, ua, ip)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def logout(request: Request, data: RefreshIn):
    auth_service.logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user_id: uuid.UUID = Depends(get_current_user_id)):
    auth_service.logout_all(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/forgot-password", response_model=MessageOut)
@limiter.limit("5/hour")
async def forgot_password(request: Request, data: ForgotPasswordIn):
    return MessageOut(message=await auth_service.forgot_password(data))


@router.post("/reset-password", response_model=MessageOut)
@limiter.limit("10/10minutes")
def reset_password(request: Request, data: ResetPasswordIn):
    return MessageOut(message=auth_service.reset_password(data))


@router.post("/reactivate", response_model=AuthOut)
@limiter.limit("10/minute")
def reactivate(
    request: Request, data: ReactivateIn,
    ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent),
):
    return auth_service.reactivate(data, ua, ip)
