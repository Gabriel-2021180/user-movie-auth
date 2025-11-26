from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.session import create_db_and_tables
from app.api.v1.endpoints import auth

@asynccontextmanager
async def lifespan(app: FastAPI):
    # COMENTAMOS ESTO PARA QUE NO INTENTE CREAR TABLAS CADA VEZ
    # Si necesitas crear tablas nuevas en el futuro, descoméntalo una vez.
    # create_db_and_tables()
    print("------> ¡SERVIDOR LISTO PARA RECIBIR PETICIONES! <------")
    yield

app = FastAPI(
    title="Movie Identity Service",
    lifespan=lifespan
)

origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])

@app.get("/")
def read_root():
    return {"message": "¡API de Usuarios Funcionando!"}