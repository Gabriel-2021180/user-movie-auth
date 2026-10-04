from fastapi import APIRouter, Depends

from app.api.v2.deps import require_bff
from app.api.v2.endpoints import auth, legal, users

# Todas las rutas de v2 exigen el secreto del BFF
api_router = APIRouter(dependencies=[Depends(require_bff)])
api_router.include_router(auth.router, prefix="/auth", tags=["v2 Auth"])
api_router.include_router(users.router, prefix="/users", tags=["v2 Users"])
api_router.include_router(legal.router, prefix="/legal", tags=["v2 Legal"])
