from fastapi import APIRouter, Depends

from app.api.v2.deps import require_bff
from app.api.v2.endpoints import auth, favorites, legal, lists, movies, onboarding, reviews, users

# Todas las rutas de v2 exigen el secreto del BFF
api_router = APIRouter(dependencies=[Depends(require_bff)])
api_router.include_router(auth.router, prefix="/auth", tags=["v2 Auth"])
api_router.include_router(users.router, prefix="/users", tags=["v2 Users"])
api_router.include_router(legal.router, prefix="/legal", tags=["v2 Legal"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["v2 Onboarding"])
api_router.include_router(favorites.router, prefix="/favorites", tags=["v2 Favorites"])
api_router.include_router(lists.router, prefix="/lists", tags=["v2 Lists"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["v2 Reviews"])
api_router.include_router(movies.router, prefix="/movies", tags=["v2 Movies"])
