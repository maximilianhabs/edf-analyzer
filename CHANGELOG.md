# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [Unreleased] — Vorbereitung der öffentlichen Veröffentlichung

### Hinzugefügt
- **DE/EN-Sprachumschalter** in der Oberfläche (`core/i18n.py`), Wahl per Cookie gespeichert.
  Übersetzt ist alles, was zum Bedienen nötig ist (Navigation, Buttons, Auswahlfelder,
  Hilfe- und Hinweistexte); klinische Parameternamen, Einheiten und Referenzwerte in Tabellen
  bleiben in ihrer etablierten Form. `tools/check_i18n.py` prüft die Vollständigkeit.
- `SECURITY.md` — wie Sicherheitsprobleme zu melden sind, plus Betriebshinweis zur Reichweite
  des Passwort-Gates.
- README zweisprachig: `README.md` (Englisch) und `README.de.md` (Deutsch).

### Geändert
- **Keine externen Verbindungen mehr zur Laufzeit** (gemessen, nicht angenommen):
  - Streamlits Nutzungs-Telemetrie jetzt auch in `.streamlit/config.toml` abgeschaltet
    (`gatherUsageStats = false`). Im **lokalen** Lauf gingen vorher pro Sitzung fünf Aufrufe
    an `webhooks.fivetran.com`; das Docker-Image setzte den entsprechenden Schalter bereits
    als CLI-Flag, dort war die Telemetrie also schon aus. Die Einstellung liegt nun an beiden
    Stellen, damit lokale Entwicklung und Container sich gleich verhalten.
  - Schrift **Inter** wird lokal aus `static/fonts/` ausgeliefert statt vom Google-Fonts-CDN
    (drei Teilzeichensätze latin/latin-ext/greek, zusammen 152 KB, variable Achse
    `wght 100–900` vor dem Einchecken mit `fontTools` verifiziert). Erfordert
    `server.enableStaticServing = true`.
  - **Material Symbols** wird gar nicht mehr geladen: die Variante „Rounded" liefert
    Streamlit bereits lokal mit, die eigene CSS-Klasse referenziert jetzt diese. Dadurch
    keine zweite Schriftdatei im Repo — und die eigenen HTML-Icons sehen nun genauso aus wie
    Streamlits native `:material/...:`-Icons. Klasse dabei von `.material-symbols-outlined`
    zu `.material-symbol` umbenannt, damit der Name nicht die falsche Variante suggeriert.
  - Ergebnis über sechs Seiten + Login-Bildschirm nachgemessen: **null externe Requests**.
- **`py-ecg-detectors` (GPL-3.0) ist keine Standard-Abhängigkeit mehr.** Das Projekt steht
  unter Apache-2.0; eine normale Installation soll keine Copyleft-Bibliothek mitbringen. Das
  Paket liegt jetzt allein in `requirements-validated.txt`, das Docker-Image nimmt es nur mit
  `--build-arg WITH_VALIDATED_DETECTORS=1` auf. **Kein Funktionsverlust im Standardfall:** die
  App läuft vollständig, der eigene Detektor war ohnehin der Default; es entfallen nur die
  Vergleichsdetektoren — und die Oberfläche bietet sie dann gar nicht erst an bzw. erklärt,
  wie man sie nachrüstet, statt sie anzubieten und still etwas anderes zu rechnen.
- **`neurokit2` aus den Abhängigkeiten entfernt** — stand in `requirements.txt`, wurde aber
  in der gesamten Projekt-Historie nie importiert. Weniger Installationsgewicht, eine
  Lizenz weniger zu führen, kleinere Angriffsfläche. Gegengeprüft: alle im Code
  vorkommenden externen Imports sind weiterhin deklariert (Abgleich des Import-Baums gegen
  `requirements*.txt`).
- `NOTICE` ergänzt (Schriftlizenz SIL OFL, Drittbibliotheken). Lizenzangaben gegen die
  installierten Paket-Metadaten geprüft, nicht aus dem Gedächtnis übernommen.
- README: internes Betriebskapitel zu einem konkreten Server durch eine allgemeine
  Selbst-Hosting-Anleitung ersetzt.

### Sicherheit
- **Hartcodiertes Default-Passwort entfernt** (`core/auth.py`): Der Login-Schutz nutzte bisher
  `os.environ.get("EDF_PASSWORD", "<Default>")` — ein im Quellcode sichtbarer Fallback-Wert,
  falls die Umgebungsvariable fehlte. Da dieser Fallback dem tatsächlich produktiv genutzten
  Passwort entsprach, wäre er in einem öffentlichen Repo für jeden lesbar gewesen.
  `EDF_PASSWORD` ist jetzt eine **Pflicht-Umgebungsvariable**; die App startet ohne sie mit
  einer klaren Fehlermeldung statt eines unsicheren Defaults. Der Produktivserver hatte die
  Variable bereits explizit gesetzt — **kein Passwortwechsel nötig, kein Ausfall**.
- Die Commit-Historie wurde vor der Veröffentlichung mit `git filter-repo` bereinigt, um den
  alten Default-Wert auch aus vergangenen Commits zu entfernen (nicht nur aus dem aktuellen
  Stand). Dadurch haben sich Commit-Hashes ab dem betroffenen Commit geändert.

## Älter

Frühere Änderungen wurden nicht fortlaufend in diesem Format dokumentiert — siehe `git log`
für die vollständige Entwicklungshistorie.
