from sqlmodel import Session, select
from app.models.user import User
from app.schemas.user import UserCreate

class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        """Busca un usuario por su email de forma optimizada."""
        statement = select(User).where(User.email == email)
        return self.session.exec(statement).first()

    def get_by_username(self, username: str) -> User | None:
        """Busca un usuario por su username."""
        statement = select(User).where(User.username == username)
        return self.session.exec(statement).first()

    def create(self, user_data: User) -> User:
        """Guarda un nuevo usuario en la BD."""
        self.session.add(user_data)
        self.session.commit()
        self.session.refresh(user_data)
        return user