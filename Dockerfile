FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Bootstrap und HTMX werden lokal ausgeliefert (kein CDN -> DSGVO-freundlich)
RUN mkdir -p static/vendor \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css -o static/vendor/bootstrap.min.css \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js -o static/vendor/bootstrap.bundle.min.js \
 && curl -fsSL https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js -o static/vendor/htmx.min.js
RUN useradd -m app && mkdir -p /data/media /data/backups && chown -R app /app /data \
 && chmod +x /app/entrypoint.sh /app/scripts/*.sh
USER app
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
