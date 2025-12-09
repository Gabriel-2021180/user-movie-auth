from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from jose import jwt, JWTError

from app.db.session import get_session
from app.core.config import settings
from app.models.favorite import Favorite
from app.models.user import User
from app.schemas.favorite import FavoriteCreate, FavoriteRead
from fastapi import Request # <--- Importar Request
from app.core.limiter import limiter # <--- Importar el limitador
from app.models.favorite_person import FavoritePerson
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# --- DEPENDENCIA DE SEGURIDAD ---
# Esto valida el Token y nos dice quién es el usuario actual
def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="No se pudo validar las credenciales")
    
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user

# --- ENDPOINTS ---

# 1. Agregar a Favoritos
@router.post("/", response_model=FavoriteRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute") # <--- AQUÍ ESTÁ LA MAGIA (10 peticiones por minuto)
def add_favorite(
    request: Request, # <--- Necesario para que slowapi lea la IP
    fav_in: FavoriteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # ... (El resto de tu lógica sigue IGUAL) ...
    existing_fav = session.exec(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.movie_id == fav_in.movie_id
        )
    ).first()
    
    if existing_fav:
        raise HTTPException(status_code=400, detail="Esta película ya está en favoritos")

    new_fav = Favorite(
        user_id=current_user.id,
        movie_id=fav_in.movie_id,
        title=fav_in.title,
        poster=fav_in.poster,
        year=fav_in.year
    )
    
    session.add(new_fav)
    session.commit()
    session.refresh(new_fav)
    return new_fav

# 2. Listar Favoritos del Usuario
@router.get("/", response_model=List[FavoriteRead])
def read_favorites(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Buscamos SOLO los favoritos de ESTE usuario
    statement = select(Favorite).where(Favorite.user_id == current_user.id)
    results = session.exec(statement).all()
    return results

# 3. Eliminar de Favoritos
@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute") # <--- Límite para borrar
def delete_favorite(
    request: Request, # <--- No olvides esto
    movie_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # ... (tu lógica igual) ...
    fav = session.exec(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.movie_id == movie_id
        )
    ).first()
    
    if not fav:
        raise HTTPException(status_code=404, detail="Favorito no encontrado")
        
    session.delete(fav)
    session.commit()
    return None

@router.get("/people", response_model=List[FavoritePerson])
def read_favorite_people(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    return current_user.favorite_people


# --- 2. AGREGAR PERSONA FAVORITA ---
@router.post("/people", response_model=FavoritePerson)
def add_favorite_person(
    person_in: FavoritePerson, # Recibimos los datos del front
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Verificar si ya existe
    existing = session.exec(
        select(FavoritePerson)
        .where(FavoritePerson.user_id == current_user.id)
        .where(FavoritePerson.person_id == person_in.person_id)
    ).first()
    
    if existing:
        return existing # Si ya está, no hacemos nada (idempotente)

    # Crear nueva relación
    # Forzamos el user_id del token (seguridad)
    person_in.user_id = current_user.id
    # Re-generamos ID interno por si el front mandó basura
    person_in.id = None 
    
    session.add(person_in)
    session.commit()
    session.refresh(person_in)
    return person_in


# --- 3. ELIMINAR PERSONA FAVORITA ---
@router.delete("/people/{person_id}")
def remove_favorite_person(
    person_id: str, # El ID de TMDB
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    fav = session.exec(
        select(FavoritePerson)
        .where(FavoritePerson.user_id == current_user.id)
        .where(FavoritePerson.person_id == person_id)
    ).first()
    
    if not fav:
        raise HTTPException(status_code=404, detail="Persona no encontrada en favoritos")
        
    session.delete(fav)
    session.commit()
    return {"ok": True}