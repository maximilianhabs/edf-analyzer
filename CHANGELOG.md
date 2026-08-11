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

### Behoben
- **Test-Suite lief nur auf dem Rechner des Autors.** `tests/test_ecg_pipeline.py` und
  `tests/test_artifacts.py` verwiesen fest auf eine echte Patientenaufnahme unter
  `~/Downloads/`; für alle anderen war die Suite nicht ausführbar, und die Fallnummer stand
  im Repository. Ausserdem **schlug ein Test fehl** (erwartete 2 EKG-Kanäle, der
  nachgeschärfte Klassifizierer findet 1) — unbemerkt, weil die Tests nie automatisch liefen.
  Jetzt gegen die synthetischen Ground-Truth-Fixtures mit belegten Sollwerten aus deren
  Manifest; der optionale Lauf gegen eine echte Aufnahme geht über `EDF_TEST_FILE=…`.
  Ergebnis: 13 grün ohne jede echte Datei.
- **Echte Aufnahme-Kennungen aus dem Code entfernt.** An 30 Stellen dokumentierten
  Fallnummern aus dem Kliniksystem, an welchem Fall ein Schwellenwert kalibriert wurde —
  fachlich wertvoll, in einem öffentlichen Repo aber unnötig. Ersetzt durch stabile
  Pseudonyme (`Referenzfall A`–`F`); die fachliche Aussage bleibt vollständig erhalten, die
  Zuordnung liegt ausserhalb des Repositories.

### Hinzugefügt (Fortsetzung)
- **CI** (`.github/workflows/test.yml`): pytest auf Python 3.9 und 3.12 plus die drei
  Konsistenz-Prüfer. Die schnellen, abhängigkeitsfreien Prüfer laufen als eigener Job und
  liefern in Sekunden ein Ergebnis. Zuvor gab es Tests, aber niemand führte sie aus.
- `requirements-dev.txt` (nur pytest) — vom Lizenz-Prüfer angemahnt, weil die Tests `pytest`
  importieren, es aber nirgends deklariert war.

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
- `NOTICE` ergänzt und faktenbasiert überarbeitet: Schriftlizenz (SIL OFL), alle direkten
  Abhängigkeiten mit Lizenz, optionale Copyleft-Abhängigkeit getrennt ausgewiesen. Alle
  Angaben aus den Paket-Metadaten der installierten Version ausgelesen
  (`importlib.metadata`), nicht aus dem Gedächtnis. Dabei zwei eigene Fehler korrigiert:
  **matplotlib** steht unter einer PSF-artigen Eigenlizenz, nicht unter BSD, und **MNE** lässt
  sich aus den Metadaten gar nicht belegen (dort nur „OSI Approved") — beides steht jetzt so
  da, statt eine plausible Lizenz zu behaupten. `matplotlib` fehlte zuvor ganz.
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
