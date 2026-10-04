import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response, status

from app.api.v2.deps import client_ip, get_current_user_id, user_agent
from app.core import rate_limit
from app.schemas.v2.auth import (
    AuthOut, ForgotPasswordIn, LoginIn, MessageOut, ReactivateIn, RefreshIn, ResetPasswordIn,
    SignupIn, Tokens, VerifyIn,
)
from app.services import auth_service

# Los límites de estas rutas se guardan en la BD (app/core/rate_limit.py), no en memoria:
# así se respetan aunque Vercel levante varias instancias.

router = APIRouter()


@router.post("/signup", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
async def signup(data: SignupIn, ip: str = Depends(client_ip)):
    await asyncio.to_thread(rate_limit.enforce, "signup", ip=ip, email=data.email)
    return MessageOut(message=await auth_service.signup(data))


@router.post("/verify", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def verify(data: VerifyIn, ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent)):
    rate_limit.enforce("verify", ip=ip, email=data.email)
    return auth_service.verify(data, ua, ip)


@router.post("/login", response_model=AuthOut)
def login(data: LoginIn, ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent)):
    rate_limit.enforce("login", ip=ip, email=data.email)
    return auth_service.login(data, ua, ip)


@router.post("/refresh", response_model=Tokens)
def refresh(data: RefreshIn, ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent)):
    rate_limit.enforce("refresh", ip=ip)
    return auth_service.refresh(data.refresh_token, ua, ip)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshIn, ip: str = Depends(client_ip)):
    rate_limit.enforce("logout", ip=ip)
    auth_service.logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user_id: uuid.UUID = Depends(get_current_user_id)):
    auth_service.logout_all(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(data: ForgotPasswordIn, ip: str = Depends(client_ip)):
    await asyncio.to_thread(rate_limit.enforce, "forgot", ip=ip, email=data.email)
    return MessageOut(message=await auth_service.forgot_password(data))


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(data: ResetPasswordIn, ip: str = Depends(client_ip)):
    await asyncio.to_thread(rate_limit.enforce, "reset", ip=ip, email=data.email)
    return MessageOut(message=await auth_service.reset_password(data))


@router.post("/reactivate", response_model=AuthOut)
def reactivate(data: ReactivateIn, ip: str = Depends(client_ip), ua: Optional[str] = Depends(user_agent)):
    rate_limit.enforce("reactivate", ip=ip, email=data.email)
    return auth_service.reactivate(data, ua, ip)
