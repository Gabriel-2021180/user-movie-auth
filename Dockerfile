# 1. Usamos una imagen base oficial de Python (ligera)
FROM python:3.10-slim

# 2. Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# 3. Evita que Python genere archivos .pyc y que bufferée la salida (logs instantáneos)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. Copiamos el archivo de requerimientos primero (para aprovechar la caché de Docker)
COPY requirements.txt .

# 5. Instalamos las dependencias
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# 6. Copiamos el resto del código de la aplicación
COPY . .

# 7. Exponemos el puerto donde corre la API (Render usa la variable PORT, por defecto 8000 está bien internamente)
EXPOSE 8000

# 8. Comando de inicio para PRODUCCIÓN (usando Gunicorn)
# Asegúrate de que gunicorn_conf.py exista, si no, usa el comando directo abajo.
CMD ["gunicorn", "-c", "gunicorn_conf.py", "app.main:app"]