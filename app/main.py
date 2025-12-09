from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.session import create_db_and_tables
from app.api.v1.endpoints import auth, favorites
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
from app.api.v1.endpoints import auth, favorites, users
from app.api.v1.endpoints import auth, favorites, users, reviews
from app.models.review import Review
@asynccontextmanager
async def lifespan(app: FastAPI):
    #create_db_and_tables() # Descomentar si necesitas inicializar tablas
    print("------> ¡SERVIDOR LISTO! <------")
    yield

app = FastAPI(
    title="Movie Identity Service",
    version="1.0.0",
    lifespan=lifespan
)

# Conectar limitador de velocidad
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(favorites.router, prefix="/api/v1/favorites", tags=["Favorites"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["Reviews"])

@app.get("/")
def read_root():
    return {"status": "online", "message": "API Funcionando 🚀"}