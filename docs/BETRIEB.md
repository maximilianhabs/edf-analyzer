# Betrieb auf dem Server neuro-vibe (Stand 16.11.2026)

Hinweis: Dieses Repo ist öffentlich. Hier stehen keine Zugangsdaten und keine Serverdetails über das Nötige hinaus. Die Demo läuft auf `edf.neuro-vibe.de` auf einem gemeinsamen, am 16.11.2026 gehärteten Server. Zentrales Betriebsdokument (lokal beim Betreiber, nicht im Repo): `/Users/maximilianhabs/Code/Programme Claude Code/ki-in-der-medizin/docs/12_SERVER_NEURO_VIBE_BETRIEB.md`.

Was sich für dieses Projekt ändert:
- **Geteilter Caddy ist ein Eigenbau** (`local/caddy-ratelimit:2.11.9-5625512`); kein `docker compose pull caddy`. Caddyfile-Änderungen: laufende Datei gegen Datei vergleichen, mit dem Eigenbau-Image validieren, Container neu erstellen (nicht reload). Das Caddyfile liegt unter `~/nz-dienstplan/` auf dem Server.
- **Netz:** der Container `edf-analyzer` bleibt im Docker-Netz `nz-dienstplan_app` (Aufruf bisher manuell mit `docker run --network nz-dienstplan_app`, laut älterer Übergabe). Header und Rate-Limit des Caddy gelten nur für `edu.neuro-vibe.de`, nicht für `edf.`.
- **Nächtlicher Auto-Neustart 04:30:** Der Server startet bei Bedarf neu. Der Container muss mit `--restart unless-stopped` laufen, sonst kommt er nach dem Neustart nicht zurück. Nach dem Neustart-Fenster prüfen (`docker ps`, `https://edf.neuro-vibe.de/_stcore/health` mit Status 200). Die Restart-Policy des laufenden Containers wurde bei dieser Doku-Änderung nicht geprüft.
- **SSH:** nur Schlüssel, erlaubte Benutzer `deploy` und `kursdeploy` (`AllowUsers`); neue SSH-Benutzer müssen ergänzt werden.
- **Routine-Check** (monatlich und bei Projektarbeit): Kernel, `/var/run/reboot-required`, Image-Alter und Digests, Zertifikate, `curl -sI`, `docker ps` health (Abschnitt 5 des zentralen Dokuments).
- Offen: Die ältere Übergabe nennt als Basis `python:3.9-slim-bookworm` (Python 3.9 ist am Ende der Lebensdauer). Beim nächsten Rebuild Basis-Image prüfen (Stand der Dockerfile hier nicht verifiziert).
