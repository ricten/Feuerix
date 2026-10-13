FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Bootstrap, Bootstrap Icons und HTMX werden lokal ausgeliefert (kein CDN -> DSGVO-freundlich)
RUN mkdir -p static/vendor/fonts \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css -o static/vendor/bootstrap.min.css \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js -o static/vendor/bootstrap.bundle.min.js \
 && curl -fsSL https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js -o static/vendor/htmx.min.js \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css -o static/vendor/bootstrap-icons.css \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2 -o static/vendor/fonts/bootstrap-icons.woff2 \
 && curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff -o static/vendor/fonts/bootstrap-icons.woff
# TinyMCE (GPL-2.0-or-later) fuer den formatierten Text in Vorlagen/Schriftstuecken - ebenfalls lokal ausgeliefert
RUN mkdir -p /tmp/tmce static/vendor/tinymce/langs \
 && curl -fsSL https://registry.npmjs.org/tinymce/-/tinymce-7.9.1.tgz | tar xz -C /tmp/tmce \
 && curl -fsSL https://registry.npmjs.org/tinymce-i18n/-/tinymce-i18n-24.12.9.tgz | tar xz -C /tmp/tmce --one-top-level=i18n \
 && T=/tmp/tmce/package && D=static/vendor/tinymce \
 && cp $T/tinymce.min.js $T/license.md $D/ \
 && mkdir -p $D/themes/silver $D/models/dom $D/icons/default $D/skins/ui/oxide $D/skins/content/default \
 && cp $T/themes/silver/theme.min.js $D/themes/silver/ && cp $T/models/dom/model.min.js $D/models/dom/ \
 && cp $T/icons/default/icons.min.js $D/icons/default/ \
 && cp $T/skins/ui/oxide/skin.min.css $T/skins/ui/oxide/content.min.css $D/skins/ui/oxide/ \
 && cp $T/skins/content/default/content.min.css $D/skins/content/default/ \
 && for p in lists table link autolink charmap; do mkdir -p $D/plugins/$p && cp $T/plugins/$p/plugin.min.js $D/plugins/$p/; done \
 && cp /tmp/tmce/i18n/package/langs7/de.js $D/langs/de.js \
 && rm -rf /tmp/tmce
RUN useradd -m app && mkdir -p /data/media /data/backups && chown -R app /app /data \
 && chmod +x /app/entrypoint.sh /app/scripts/*.sh
USER app
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
