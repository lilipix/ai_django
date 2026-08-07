FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/home/app/.cache/uv \
    UV_LINK_MODE=copy \
    UV_NO_MANAGED_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/home/app/.venv

WORKDIR /app

RUN pip install --no-cache-dir --upgrade uv

# Création de l'utilisateur système app
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /home/app app \
    && mkdir -p /home/app/.cache/uv /home/app/.venv \
    && chown -R app:app /home/app

# Fichiers de dépendances pour le cache Docker
COPY pyproject.toml uv.lock README.md ./

# Installation des dépendances dans /home/app/.venv
RUN uv sync --frozen --no-dev --python /usr/local/bin/python

# Copie du code source
COPY . .

# Transmission des droits d'accès
RUN chown -R app:app /app /home/app

USER app

EXPOSE 8000

CMD ["sh", "-c", "/home/app/.venv/bin/python manage.py migrate && /home/app/.venv/bin/python manage.py collectstatic --noinput && exec /home/app/.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000"]