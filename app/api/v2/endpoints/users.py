import uuid

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import RowMapping

from app.api.v2.deps import client_ip, get_current_user_id, get_current_user_row
from app.core import rate_limit
from app.core.limiter import limiter
from app.schemas.v2.user import ConsentIn, DeleteMeIn, ProfilePatch, PublicProfile, UserMe
from app.repositories import maintenance_repository
from app.services import user_service

router = APIRouter()


@router.get("/me", response_model=UserMe)
def read_me(row: RowMapping = Depends(get_current_user_row)):
    # get_current_user_row ya trae el perfil completo: no hace falta otra consulta
    return user_service.to_user_me(row)


@router.patch("/me", response_model=UserMe)
@limiter.limit("30/minute")
def update_me(request: Request, data: ProfilePatch, user_id: uuid.UUID = Depends(get_current_user_id)):
    return user_service.update_profile(user_id, data)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_me(data: DeleteMeIn, row: RowMapping = Depends(get_current_user_row)):
    rate_limit.enforce("delete_me", user=str(row["id"]))
    user_service.deactivate(row["id"], row["email"], data.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/consents", status_code=status.HTTP_204_NO_CONTENT)
def accept_consents(
    data: ConsentIn, user_id: uuid.UUID = Depends(get_current_user_id), ip: str = Depends(client_ip),
):
    user_service.record_consent(user_id, data.terms_version, data.privacy_version, ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/export")
def export_me(user_id: uuid.UUID = Depends(get_current_user_id)):
    """Todos mis datos en JSON (derecho de acceso y portabilidad)."""
    rate_limit.enforce("export", user=str(user_id))
    data = maintenance_repository.export_user(user_id) or {}
    data["exported_at"] = datetime.now(timezone.utc).isoformat()
    filename = f"filmstack-mis-datos-{datetime.now(timezone.utc):%Y%m%d}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# Va al final para que /me tenga prioridad sobre /{username}
@router.get("/{username}", response_model=PublicProfile)
def public_profile(username: str = Path(pattern=r"^[A-Za-z0-9_.]{3,30}$")):
    return user_service.public_profile(username)
