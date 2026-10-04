from fastapi import APIRouter

from app.schemas.v2.user import LegalCurrent
from app.services import user_service

router = APIRouter()


@router.get("/current", response_model=LegalCurrent)
def legal_current():
    return user_service.legal_current()
