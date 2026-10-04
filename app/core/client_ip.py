import hmac
import ipaddress

from fastapi import Request

from app.core.config import settings


def is_trusted_bff(request: Request) -> bool:
    """True si la petición trae el secreto compartido del BFF (comparación en tiempo constante)."""
    secret = settings.BFF_SHARED_SECRET
    sent = request.headers.get("x-bff-secret")
    return bool(secret and sent and hmac.compare_digest(sent.encode(), secret.encode()))


def get_client_ip(request: Request) -> str:
    """IP real del cliente. Solo se confía en X-Client-IP cuando lo manda el BFF."""
    if is_trusted_bff(request):
        candidate = request.headers.get("x-client-ip", "").strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"
