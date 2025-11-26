from sqlmodel import create_engine, SQLModel, Session
from app.core.config import settings

# 1. CREAR EL MOTOR (ENGINE)
# Usamos la URL que pusimos en config.py para conectar a Neon
# echo=True sirve para ver en la consola el SQL que se ejecuta (útil para desarrollar)
engine = create_engine(
    settings.DATABASE_URL, 
    echo=True
)

# 2. FUNCIÓN PARA OBTENER SESIÓN
# Esta función se inyecta en cada endpoint (ruta) para poder guardar/leer datos
def get_session():
    with Session(engine) as session:
        yield session

# 3. FUNCIÓN PARA CREAR TABLAS
# Esta se ejecuta al iniciar la app (en main.py) para crear las tablas si no existen
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)