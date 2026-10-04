from slowapi import Limiter

from app.core.client_ip import get_client_ip

# Identifica al cliente por su IP real (detrás del BFF usa X-Client-IP verificado).
# Nota: el almacenamiento es en memoria por proceso; con varios workers o serverless
# conviene apuntar storage_uri a Redis.
limiter = Limiter(key_func=get_client_ip)
