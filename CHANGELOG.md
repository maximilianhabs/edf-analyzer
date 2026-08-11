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
