from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.db.session import get_session
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.core.security import get_password_hash

router = APIRouter()

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, session: Session = Depends(get_session)):
    """
    Registra un nuevo usuario con Nombre, Apellido y Username.
    """
    # 1. Validar Email único
    if session.exec(select(User).where(User.email == user_in.email)).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado.")

    # 2. Validar Username único
    if session.exec(select(User).where(User.username == user_in.username)).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso.")

    # 3. Crear Usuario (Encriptando password)
    user = User(
        email=user_in.email,
        username=user_in.username,
        first_name=user_in.first_name, # Guardamos nombre
        last_name=user_in.last_name,   # Guardamos apellido
        hashed_password=get_password_hash(user_in.password),
        status=True
    )

    # 4. Guardar en DB
    session.add(user)
    session.commit()
    session.refresh(user)

    return user