from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.session import create_db_and_tables
from app.api.v1.endpoints import auth, favorites

# --- IMPORTS NUEVOS PARA RATE LIMIT ---
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    print("------> ¡SERVIDOR LISTO! <------")
    yield

app = FastAPI(
    title="Movie Identity Service",
    lifespan=lifespan
)

# --- CONECTAR LIMITADOR A LA APP ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(favorites.router, prefix="/api/v1/favorites", tags=["Favorites"])

@app.get("/")
def read_root():
    return {"message": "API Activa"}