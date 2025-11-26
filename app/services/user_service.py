from fastapi import HTTPException, status
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.models.user import User
from app.core.security import get_password_hash

class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repo = user_repository

    def register_new_user(self, user_in: UserCreate) -> User:
        """
        Lógica completa de registro:
        1. Valida duplicados.
        2. Valida longitud de password.
        3. Encripta password.
        4. Crea usuario.
        """
        
        # 1. Validaciones de Negocio
        if len(user_in.password) > 72:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña es demasiado larga (máx 72 caracteres)."
            )

        if self.user_repo.get_by_email(user_in.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está registrado."
            )
        
        if self.user_repo.get_by_username(user_in.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de usuario ya está en uso."
            )

        # 2. Preparación de Datos (Seguridad)
        hashed_password = get_password_hash(user_in.password)
        
        # Creamos la instancia del Modelo (SQL) a partir del Esquema (Pydantic)
        # Usamos model_dump() para convertir el esquema a diccionario y excluimos el password plano
        user_data = user_in.model_dump(exclude={"password"})
        
        new_user = User(
            **user_data,
            hashed_password=hashed_password,
            status=True
        )

        # 3. Persistencia
        return self.user_repo.create(new_user)