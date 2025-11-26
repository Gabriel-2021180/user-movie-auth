from slowapi import Limiter
from slowapi.util import get_remote_address

# Creamos el limitador.
# get_remote_address usa la IP del usuario para identificarlo.
limiter = Limiter(key_func=get_remote_address)