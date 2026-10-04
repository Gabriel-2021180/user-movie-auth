import hmac
import logging

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.errors import APIError
from app.repositories import maintenance_repository

logger = logging.getLogger(__name__)

# Tareas programadas. Vercel Cron llama con GET y "Authorization: Bearer <CRON_SECRET>".
router = APIRouter(include_in_schema=False)


def _require_cron_secret(request: Request) -> None:
    secret = settings.CRON_SECRET
    sent = request.headers.get("authorization", "")
    if not secret or not hmac.compare_digest(sent.encode(), f"Bearer {secret}".encode()):
        raise APIError(404, "not_found", "Not Found")  # no revela que el endpoint existe


@router.get("/cron/purge")
def cron_purge(request: Request):
    _require_cron_secret(request)
    row = maintenance_repository.purge(settings.ACCOUNT_GRACE_DAYS, settings.SESSION_RETENTION_DAYS)
    result = dict(row)
    logger.info("Purga diaria: %s", result)
    return result
