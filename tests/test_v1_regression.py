"""v1 debe seguir funcionando sobre el esquema migrado hasta que se retire."""
import uuid

import pytest
from sqlmodel import Session

from app.core.security import get_password_hash
from app.db.session import engine
from app.models.user import User

pytestmark = pytest.mark.usefixtures("db_ready")


def test_v1_user_insert_login_and_favorites(client):
    email = f"v1_{uuid.uuid4().hex[:8]}@example.com"
    with Session(engine) as s:
        s.add(User(email=email, username=f"v1_{uuid.uuid4().hex[:6]}", first_name="V", last_name="Uno",
                   hashed_password=get_password_hash("Clave123"), status=True))
        s.commit()
    r = client.post("/api/v1/auth/login", data={"username": email, "password": "Clave123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/v1/favorites/", headers=h, json={"movie_id": "550", "title": "Fight Club"})
    assert r.status_code == 201, r.text
    assert [f["movie_id"] for f in client.get("/api/v1/favorites/", headers=h).json()] == ["550"]
