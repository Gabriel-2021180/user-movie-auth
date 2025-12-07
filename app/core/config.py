from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Configuración general (no sensible)
    PROJECT_NAME: str = "Movie Identity Service"
    API_V1_STR: str = "/api/v1"
    
    # --- VARIABLES SENSIBLES (Se leen del .env) ---
    
    # Clave secreta para firmar tokens. 
    # Al no ponerle valor aquí, Pydantic la buscará obligatoriamente en el .env
    SECRET_KEY: str 
    
    # URL de conexión a la Base de Datos
    # También la buscará en el .env
    DATABASE_URL: str
    
# Nuevas variables para el Email
    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    # Configuración de JWT
    
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    class Config:
        # Archivo donde buscar las variables
        env_file = ".env"
        # Distingue mayúsculas de minúsculas
        case_sensitive = True

settings = Settings()