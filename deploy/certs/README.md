# Eigene TLS-Zertifikate (optional)

Dieser Ordner ist für ein **eigenes/hinterlegtes** TLS-Zertifikat gedacht – als Alternative zum
automatischen Let's-Encrypt-Zertifikat, das der Reverse Proxy (Caddy) standardmäßig ohne
weitere Einrichtung selbst beschafft.

## Verwendung

1. Zertifikat (PEM, ggf. inkl. Zwischenzertifikaten) und privaten Schlüssel (PEM, unverschlüsselt)
   hier ablegen, z. B. `verein.crt` und `verein.key`.
2. In der `.env` (im Projektwurzelverzeichnis) die Dateinamen eintragen:
   ```
   VEREIN_TLS_CERT=verein.crt
   VEREIN_TLS_KEY=verein.key
   # entsprechend für OpenSlides:
   OPENSLIDES_TLS_CERT=versammlung.crt
   OPENSLIDES_TLS_KEY=versammlung.key
   ```
3. Reverse Proxy neu starten: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`.

Bleiben die Variablen leer, holt Caddy weiterhin automatisch ein Let's-Encrypt-Zertifikat (Standard,
keine Einrichtung nötig).

**Wichtig:** Dateien in diesem Ordner (außer dieser README) werden von Git ignoriert – private
Schlüssel dürfen nicht ins Repository gelangen. Sicherung erfolgt separat (z. B. zusammen mit `.env`).
