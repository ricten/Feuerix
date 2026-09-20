#!/bin/sh
# Erzeugt aus der Caddyfile-Vorlage die tatsächliche Caddyfile: mit einer "tls"-Zeile fuer ein
# eigenes hinterlegtes Zertifikat (VEREIN_TLS_CERT/_KEY bzw. OPENSLIDES_TLS_CERT/_KEY, Dateien
# unter deploy/certs/), oder ohne diese Zeile - dann holt Caddy automatisch ein Let's-Encrypt-
# Zertifikat (Standardverhalten, keine Aenderung noetig).
set -e

tls_zeile() {
  cert="$1"; schluessel="$2"
  if [ -n "$cert" ] && [ -n "$schluessel" ]; then
    echo "tls /certs/$cert /certs/$schluessel"
  fi
}

sed -e "s#@@VEREIN_TLS@@#$(tls_zeile "$VEREIN_TLS_CERT" "$VEREIN_TLS_KEY")#" \
    -e "s#@@OPENSLIDES_TLS@@#$(tls_zeile "$OPENSLIDES_TLS_CERT" "$OPENSLIDES_TLS_KEY")#" \
    /etc/caddy/Caddyfile.tmpl > /etc/caddy/Caddyfile

exec "$@"
