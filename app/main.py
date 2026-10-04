from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import auth, favorites, reviews, users
from app.api import internal
from app.api.v2.router import api_router as api_v2_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.limiter import limiter
from app.models.review import Review  # noqa: F401  (registra el modelo para las relaciones de v1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("------> ¡SERVIDOR LISTO! <------")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    lifespan=lifespan,
    # La documentación solo se publica en desarrollo
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# Limitador de velocidad y formato de errores
app.state.limiter = limiter
register_error_handlers(app)

# CORS restringido al origen del front (v2 lo llama el BFF desde el servidor)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith(settings.API_V2_STR):
        # Respuestas con tokens o datos personales: nunca en caché
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Rutas v1 (se retiran cuando el front termine de migrar a v2)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(favorites.router, prefix="/api/v1/favorites", tags=["Favorites"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["Reviews"])

# Rutas v2
app.include_router(api_v2_router, prefix=settings.API_V2_STR)

# Tareas internas (Vercel Cron)
app.include_router(internal.router, prefix="/api/internal")


@app.get("/")
def read_root():
    return {"status": "online"}
