FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar y instalar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn dj-database-url psycopg2-binary

# Copiar todo el proyecto
COPY . .

# Variables de entorno
ENV PYTHONPATH=/app
ENV DJANGO_SETTINGS_MODULE=citas_project.settings

# Comando para Render (producción)
CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 citas_project.wsgi:application"]