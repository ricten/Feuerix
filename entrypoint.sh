#!/bin/sh
set -e
if [ "$1" = "gunicorn" ]; then
  # Erststart: falls noch keine Migrationen im Projekt liegen, werden sie erzeugt.
  # Empfohlen: einmalig erzeugen und ins Projekt uebernehmen (siehe README).
  NEED=0
  for a in core members honors finance inventory donations allowances events documents openslides accounting; do
    ls apps/$a/migrations/0001_*.py >/dev/null 2>&1 || NEED=1
  done
  if [ "$NEED" = "1" ]; then
    echo ">>> Keine Migrationen gefunden - erzeuge Erst-Migrationen"
    python manage.py makemigrations --noinput
  fi
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  python manage.py ersteinrichtung
fi
exec "$@"
