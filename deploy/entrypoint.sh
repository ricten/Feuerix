#!/bin/sh
# Erzeugt aus der Caddyfile-Vorlage die tatsächliche Caddyfile: mit einer "tls"-Zeile fuer ein
# eigenes hinterlegtes Zertifikat (VEREIN_TLS_CERT/_KEY, OPENSLIDES_TLS_CERT/_KEY bzw.
# PAPERLESS_TLS_CERT/_KEY, Dateien unter deploy/certs/), oder ohne diese Zeile - dann holt Caddy
# automatisch ein Let's-Encrypt-Zertifikat (Standardverhalten, keine Aenderung noetig).
# Die optionalen Bloecke (OpenSlides, Paperless - zwischen ihren Markierungen) werden komplett
# entfernt, wenn die jeweilige *_DOMAIN leer ist - eine leere Caddyfile-Site-Adresse waere sonst
# ein ungueltiger/globaler Catch-all.
set -e

tls_zeile() {
  cert="$1"; schluessel="$2"
  if [ -n "$cert" ] && [ -n "$schluessel" ]; then
    echo "tls /certs/$cert /certs/$schluessel"
  fi
}

block_filter() {
  marker="$1"; domain="$2"
  if [ -n "$domain" ]; then
    echo "/# ${marker}_START/d;/# ${marker}_END/d"
  else
    echo "/# ${marker}_START/,/# ${marker}_END/d"
  fi
}

sed -e "s#@@VEREIN_TLS@@#$(tls_zeile "$VEREIN_TLS_CERT" "$VEREIN_TLS_KEY")#" \
    -e "s#@@OPENSLIDES_TLS@@#$(tls_zeile "$OPENSLIDES_TLS_CERT" "$OPENSLIDES_TLS_KEY")#" \
    -e "s#@@PAPERLESS_TLS@@#$(tls_zeile "$PAPERLESS_TLS_CERT" "$PAPERLESS_TLS_KEY")#" \
    -e "$(block_filter OPENSLIDES "$OPENSLIDES_DOMAIN")" \
    -e "$(block_filter PAPERLESS "$PAPERLESS_DOMAIN")" \
    /etc/caddy/Caddyfile.tmpl > /etc/caddy/Caddyfile

exec "$@"
