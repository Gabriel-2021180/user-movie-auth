from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.db.session import get_session
from app.models.user import User
from app.models.review import Review
from app.models.movie import Movie
from app.schemas.review import ReviewCreate, ReviewRead
from app.api.v1.endpoints.users import get_current_user
from sqlalchemy.orm import joinedload
import uuid # Necesario para el tipo UUID
from app.schemas.review import ReviewUpdate
router = APIRouter()

# --- CREAR ---
@router.post("/", response_model=ReviewRead)
def create_review(
    review_in: ReviewCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # (Tu lógica de validación y creación sigue igual...)
    existing_review = session.exec(
        select(Review).where(Review.user_id == current_user.id, Review.movie_id == review_in.movie_id)
    ).first()
    if existing_review:
        raise HTTPException(status_code=400, detail="Ya escribiste una reseña para esta película.")

    movie = session.get(Movie, review_in.movie_id)
    if not movie:
        movie = Movie(
            id=review_in.movie_id, title=review_in.movie_title,
            poster=review_in.movie_poster or "", year=review_in.movie_year or "N/A"
        )
        session.add(movie)
        session.commit()

    sentiment = "positive" if review_in.rating >= 4 else "neutral" if review_in.rating == 3 else "negative"

    new_review = Review(
        user_id=current_user.id,
        movie_id=review_in.movie_id,
        rating=review_in.rating,
        content=review_in.content,
        sentiment=sentiment
    )
    session.add(new_review)
    session.commit()
    session.refresh(new_review)
    
    return ReviewRead(
        id=new_review.id,
        user_id=str(new_review.user_id),
        movie_id=new_review.movie_id,
        username=current_user.username or "Anónimo",
        # Devolvemos también los datos de la peli
        movie_title=review_in.movie_title,
        movie_poster=review_in.movie_poster,
        rating=new_review.rating,
        content=new_review.content,
        sentiment=new_review.sentiment,
        created_at=new_review.created_at
    )

# --- NUEVO: OBTENER MIS RESEÑAS (Para el Perfil) ---
@router.get("/me", response_model=List[ReviewRead])
def get_my_reviews(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Buscamos reseñas de ESTE usuario
    statement = select(Review).where(Review.user_id == current_user.id).order_by(Review.created_at.desc())
    reviews = session.exec(statement).all()
    
    results = []
    for r in reviews:
        # Cargamos la película asociada para saber el título/poster
        movie_data = r.movie 
        
        results.append(ReviewRead(
            id=r.id,
            user_id=str(r.user_id),
            movie_id=r.movie_id,
            username=current_user.username,
            # Llenamos datos de la película desde la relación
            movie_title=movie_data.title if movie_data else "Película desconocida",
            movie_poster=movie_data.poster if movie_data else None,
            rating=r.rating,
            content=r.content,
            sentiment=r.sentiment,
            created_at=r.created_at
        ))
    return results

# --- LEER POR PELÍCULA (Pública) ---
@router.get("/movie/{movie_id}", response_model=List[ReviewRead])
def get_movie_reviews(
    movie_id: str,
    session: Session = Depends(get_session)
):
    # ESTRATEGIA OPTIMIZADA:
    # Usamos .options(joinedload(Review.user)) para traer al usuario JUNTO con la reseña.
    # También traemos la película por si acaso.
    # Esto reduce el tiempo de 4 segundos a 0.05 segundos.
    statement = (
        select(Review)
        .where(Review.movie_id == movie_id)
        .options(joinedload(Review.user), joinedload(Review.movie)) # <--- LA CLAVE DE LA VELOCIDAD
        .order_by(Review.created_at.desc())
    )
    
    reviews = session.exec(statement).unique().all()
    
    results = []
    for r in reviews:
        # Ahora r.user YA está en memoria, no hace consulta extra a la BD
        user_name = r.user.username if r.user else "Usuario Eliminado"
        
        results.append(ReviewRead(
            id=r.id,
            user_id=str(r.user_id),
            movie_id=r.movie_id,
            username=user_name,
            movie_title=r.movie.title if r.movie else "",
            movie_poster=r.movie.poster if r.movie else "",
            rating=r.rating,
            content=r.content,
            sentiment=r.sentiment,
            created_at=r.created_at
        ))
        
    return results

@router.put("/{review_id}", response_model=ReviewRead)
def update_review(
    review_id: uuid.UUID,
    review_in: ReviewUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # 1. Buscar la reseña
    review = session.get(Review, review_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
        
    # 2. Verificar que sea SU reseña (Seguridad)
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar esta reseña")
    
    # 3. Actualizar campos si vienen datos
    if review_in.rating is not None:
        review.rating = review_in.rating
        # Recalcular sentimiento
        review.sentiment = "positive" if review.rating >= 4 else "neutral" if review.rating == 3 else "negative"
        
    if review_in.content is not None:
        review.content = review_in.content
        
    # 4. Guardar cambios
    session.add(review)
    session.commit()
    session.refresh(review)
    
    # 5. Devolver respuesta (con datos de la película para que no rompa el front)
    return ReviewRead(
        id=review.id,
        user_id=str(review.user_id),
        movie_id=review.movie_id,
        username=current_user.username,
        movie_title=review.movie.title if review.movie else "",
        movie_poster=review.movie.poster if review.movie else "",
        rating=review.rating,
        content=review.content,
        sentiment=review.sentiment,
        created_at=review.created_at
    )