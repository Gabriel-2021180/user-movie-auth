from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.db.session import get_session
from app.models.user import User
from app.schemas.user import UserUpdate, UserRead
from app.api.v1.endpoints.auth import router as auth_router # Solo para referencia de imports
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from app.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Dependencia para obtener usuario actual (Reutilizable)
def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@router.put("/me", response_model=UserRead)
def update_user_me(
    user_update: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    now = datetime.utcnow()

    # =================================================================
    # 1. LÓGICA DE COLOR (Máximo 3 veces al día)
    # =================================================================
    if user_update.banner_color and user_update.banner_color != current_user.banner_color:
        
        # Si la última vez fue ayer (o nunca), reiniciamos el contador a 0
        if not current_user.last_color_change_at or current_user.last_color_change_at.date() < now.date():
            current_user.daily_color_changes = 0
        
        # Si ya gastó sus 3 vidas de hoy -> ERROR
        if current_user.daily_color_changes >= 3:
             raise HTTPException(
                status_code=429, # Too Many Requests
                detail="Has alcanzado el límite de 3 cambios de color por día."
            )
        
        # Aplicamos el cambio y sumamos 1
        current_user.banner_color = user_update.banner_color
        current_user.daily_color_changes += 1
        current_user.last_color_change_at = now


    # =================================================================
    # 2. LÓGICA DE DATOS SENSIBLES (Restricción 14 días)
    # =================================================================
    # TRUCO: Solo nos preocupamos si el valor enviado es DISTINTO al actual.
    # Si el frontend manda el mismo nombre de siempre, 'has_sensitive_changes' será False.
    
    has_sensitive_changes = False

    if user_update.username and user_update.username != current_user.username:
        has_sensitive_changes = True
        # Chequeo extra de duplicados
        existing = session.exec(select(User).where(User.username == user_update.username)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Ese usuario ya existe.")
        current_user.username = user_update.username

    if user_update.first_name and user_update.first_name != current_user.first_name:
        has_sensitive_changes = True
        current_user.first_name = user_update.first_name

    if user_update.last_name and user_update.last_name != current_user.last_name:
        has_sensitive_changes = True
        current_user.last_name = user_update.last_name

    # Si REALMENTE cambió algo sensible, verificamos los 14 días
    if has_sensitive_changes:
        if current_user.last_profile_update:
            days_passed = (now - current_user.last_profile_update).days
            if days_passed < 14:
                days_left = 14 - days_passed
                raise HTTPException(
                    status_code=400, 
                    detail=f"No puedes cambiar tu nombre/usuario tan pronto. Espera {days_left} días."
                )
        
        # Marcamos que hoy cambió datos sensibles (inicia cuenta regresiva de 14 días)
        current_user.last_profile_update = now

    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    return current_user