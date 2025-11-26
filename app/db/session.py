from sqlmodel import create_engine, SQLModel, Session
from app.core.config import settings

# Argumento especial solo necesario para SQLite
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

# Creamos el motor de la base de datos
engine = create_engine(
    settings.DATABASE_URL, 
    echo=True, # echo=True imprime las consultas SQL en consola (útil para depurar)
    connect_args=connect_args
)

# Función para crear las tablas en la DB
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Dependencia para obtener la sesión en cada petición (Endpoint)
def get_session():
    with Session(engine) as session:
        yield session