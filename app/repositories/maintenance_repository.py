import uuid
from typing import Optional

from sqlalchemy import RowMapping

from app.db import procedures


def export_user(user_id: uuid.UUID) -> Optional[dict]:
    return procedures.call_scalar("api.user_export", p_user_id=user_id)


def purge(grace_days: int, session_retention_days: int) -> RowMapping:
    return procedures.call_one(
        "api.purge_run", p_grace_days=grace_days, p_session_retention_days=session_retention_days
    )
