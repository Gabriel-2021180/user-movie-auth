from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.db.session import get_session
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.models.user import User
from app.models.pending_user import PendingRegistration
from app.schemas.user import UserCreate, UserRead, UserVerify
from app.schemas.token import Token
from app.services.email_service import EmailService

router = APIRouter()

# --- PASO 1: SOLICITAR REGISTRO (No crea usuario, solo manda código) ---
@router.post("/signup", status_code=status.HTTP_200_OK)
async def signup_user(
    user_in: UserCreate, 
    session: Session = Depends(get_session)
):
    # 1. Validaciones
    if len(user_in.password) > 72:
        raise HTTPException(status_code=400, detail="Contraseña muy larga")

    # Verificar si ya existe en la tabla REAL (Usuarios ya verificados)
    existing_user = session.exec(
        select(User).where((User.email == user_in.email) | (User.username == user_in.username))
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email o usuario ya registrado")

    # 2. Limpieza (Borrar intentos fallidos previos de este email)
    existing_pending = session.exec(
        select(PendingRegistration).where(PendingRegistration.email == user_in.email)
    ).all()
    for pending in existing_pending:
        session.delete(pending)

    # 3. Generar Código y Expiración (10 mins)
    code = EmailService.generate_code()
    expires = datetime.utcnow() + timedelta(minutes=10)

    # 4. Guardar en Tabla TEMPORAL (PendingRegistration)
    temp_user = PendingRegistration(
        email=user_in.email,
        username=user_in.username,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        hashed_password=get_password_hash(user_in.password),
        verification_code=code,
        expires_at=expires
    )
    session.add(temp_user)
    session.commit()

    # 5. Enviar Email Real
    sent = await EmailService.send_verification_email(user_in.email, code)
    if not sent:
        raise HTTPException(status_code=500, detail="Error enviando el correo. Intenta de nuevo.")

    return {"message": "Código de verificación enviado. Revisa tu correo."}


# --- PASO 2: VERIFICAR CÓDIGO (Aquí se crea el usuario real) ---
@router.post("/verify", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def verify_user(verify_in: UserVerify, session: Session = Depends(get_session)):
    pending_user = session.exec(select(PendingRegistration).where(PendingRegistration.email == verify_in.email)).first()
    if not pending_user:
        raise HTTPException(status_code=400, detail="No hay registro pendiente.")
    if pending_user.verification_code != verify_in.code:
        raise HTTPException(status_code=400, detail="Código incorrecto.")
    if datetime.utcnow() > pending_user.expires_at:
        session.delete(pending_user)
        session.commit()
        raise HTTPException(status_code=400, detail="Código expirado.")

    new_user = User(
        email=pending_user.email,
        username=pending_user.username,
        first_name=pending_user.first_name,
        last_name=pending_user.last_name,
        hashed_password=pending_user.hashed_password,
        status=True,
        last_profile_update=None # Inicializamos esto vacío
    )
    
    session.add(new_user)
    session.delete(pending_user)
    session.commit()
    session.refresh(new_user)
    return new_user


# --- LOGIN ---
@router.post("/login")
def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    # Buscamos por email (el form_data.username trae el email en este caso)
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.status:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # RESPUESTA ENRIQUECIDA:
    # Devolvemos el token Y los datos del usuario para que el Front los guarde
    return {
        "access_token": create_access_token(data={"sub": str(user.id)}, expires_delta=access_token_expires),
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "banner_color": user.banner_color,
            "photo": None # Si agregas foto en el futuro, ponla aquí
        }
    }