import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import RowMapping

from app.api.v2.deps import client_ip, get_current_user_id, get_current_user_row
from app.core.limiter import limiter
from app.schemas.v2.user import ConsentIn, DeleteMeIn, UserMe
from app.services import user_service

router = APIRouter()


@router.get("/me", response_model=UserMe)
def read_me(row: RowMapping = Depends(get_current_user_row)):
    # get_current_user_row ya trae el perfil completo: no hace falta otra consulta
    return user_service.to_user_me(row)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/hour")
def deactivate_me(request: Request, data: DeleteMeIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    user_service.deactivate(user_id, data.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/consents", status_code=status.HTTP_204_NO_CONTENT)
def accept_consents(
    data: ConsentIn, user_id: uuid.UUID = Depends(get_current_user_id), ip: str = Depends(client_ip),
):
    user_service.record_consent(user_id, data.terms_version, data.privacy_version, ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
