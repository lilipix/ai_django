FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy \
    UV_NO_MANAGED_PYTHON=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade uv

# Copiés séparément pour profiter du cache Docker
COPY pyproject.toml uv.lock README.md ./

# Création de l'environnement virtuel avec Python 3.13 du conteneur
RUN uv sync --frozen --no-dev --python /usr/local/bin/python

# Copie du code après l'installation des dépendances
COPY . .

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /home/app app \
    && mkdir -p /home/app/.cache/uv \
    && chown -R app:app /app /home/app

USER app

EXPOSE 8000

CMD ["sh", "-c", "/app/.venv/bin/python manage.py migrate && /app/.venv/bin/python manage.py collectstatic --noinput && exec /app/.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000"]