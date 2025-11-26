import multiprocessing

# Calcula cuántos núcleos tiene el servidor y crea workers óptimos
# Fórmula estándar: (2 x Número de CPUs) + 1
workers = multiprocessing.cpu_count() * 2 + 1

# Usamos Uvicorn para que sea asíncrono y rápido
worker_class = "uvicorn.workers.UvicornWorker"

# Dónde va a escuchar
bind = "0.0.0.0:8000"

# Tiempo de espera antes de matar un proceso pegado (120 segundos)
timeout = 120
keepalive = 5

# Logs (para ver errores en producción)
loglevel = "info"