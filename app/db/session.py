from sqlmodel import create_engine, SQLModel, Session
from app.core.config import settings

# --- OPTIMIZACIÓN DE PRODUCCIÓN ---
# pool_size=20: Mantiene 20 conexiones listas para usar (como taxis esperando).
# max_overflow=10: Si se llenan los 20 taxis, llama a 10 más de refuerzo.
# pool_pre_ping=True: Verifica que la conexión a Neon siga viva antes de usarla (vital para la nube).
# echo=False: Apagamos los logs de SQL porque imprimir texto en consola hace lenta la app.

engine = create_engine(
    settings.DATABASE_URL,
    echo=False, 
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)

def get_session():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)