# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [0.2.0] — 2026-08-12

Diese Fassung fügt keine einzige neue Analysemethode hinzu. Sie beantwortet stattdessen für
die vorhandenen 22 Verfahren die Frage, die ein externes Review zu Recht gestellt hat:
**worauf stützt sich eigentlich die Behauptung, dass sie richtig rechnen?**

Vier Dinge sind daraus geworden: ehrliche Etiketten mit hinterlegtem Nachweis, Tests gegen
bekannte Sollwerte, nachvollziehbare Herkunft in jedem Report und eine Spezifikation der
Vorverarbeitung. Dazu eine Reihe von Befunden, die dabei aufgefallen sind — darunter zwei,
die still falsche Ergebnisse erzeugen konnten.

Die Version 0.1.0 (2026-08-11) war der Stand der ersten öffentlichen Schaltung; ein getaggtes
Release gab es dafür nicht.

### Geändert — Methoden-Registry: „validiert" heißt jetzt, was es sagt

- **Das Etikett „✅ validiert" ist ersatzlos verschwunden.** Es stand über 15 Verfahren,
  während die Definition im selben Modul „publizierter/akzeptierter Standard-Algorithmus"
  lautete — das ist *literaturbasiert*. Das Etikett behauptete damit eine geprüfte
  Implementierung, die es nicht gab. Ein externes Review hat den Widerspruch beanstandet; er
  saß ausgerechnet in dem Teil des Projekts, der methodische Ehrlichkeit verspricht.
- **Zwei getrennte Achsen statt einer.** In dem einen alten Feld steckten zwei verschiedene
  Aussagen. Jetzt: **Umsetzungstreue** (vollständig · 🟡 vereinfacht · 🔬 Proxy — 15/6/1,
  inhaltlich unverändert) und **Belegstufe** (📖 literaturbasiert · ✅ implementierungs-
  validiert · 🏥 klinisch validiert).
- **Ausgangsstand bewusst ehrlich: 22 literaturbasiert, 0 implementierungsvalidiert.** Das
  war unbequemer als vorher und war der tatsächliche Stand. Die Belege sind unmittelbar
  danach entstanden (siehe nächster Abschnitt) — aber erst, nachdem die Etiketten stimmten.
- **Ein Etikett ist ohne Nachweis technisch nicht mehr setzbar.** Die Registry ist von einem
  namenlosen 5-Tupel auf ein `Method`-Datenmodell umgestellt; jede Stufe oberhalb von
  literaturbasiert braucht ein `Evidence`-Objekt (Datensatz, geprüfte Größe, Sollwert,
  Toleranz, Test), sonst wirft die Konstruktion einen Fehler. Zusätzliches Feld
  `limitations` für Einschränkungen, die vorher nur in Prosa in der Referenzspalte standen.
- **`tools/check_methods.py`** (neu, abhängigkeitsfrei, im schnellen CI-Job): prüft, dass
  Belege vollständig sind und auf existierende Testdateien zeigen, dass die Zahlen in
  **beiden** READMEs zur Registry passen und dass das alte Etikett nicht zurückkehrt.
  Absichtlich gegen drei Fehlerfälle getestet. Dazu `tests/test_methods_registry.py`, damit
  auch ein lokales `pytest` den Widerspruch findet — die alte Fehlklassifikation überlebte
  so lange, weil sie an keiner einzigen Stelle geprüft wurde.
- **README (beide Sprachen):** neue Doppel-Tabelle samt Erklärung, warum umgestellt wurde.
  Ausserdem sagte das englische README „atrial fibrillation **detection** via CosEn" — die
  App selbst formuliert durchgehend „AFib-**Verdacht**, Screening, keine Diagnose". Die
  Überspitzung stand also nur in der Doku und ist dort jetzt korrigiert (im Deutschen
  ebenso), genauso wie „literatur-validierte Zusatzverfahren" im Vorspann.

### Hinzugefügt — Sollwerte in die Tests, und was dabei herauskam

- **`tests/test_eeg_groundtruth.py`** (neu): die EEG-Sollwerte der synthetischen Fixture
  standen seit ihrer Erzeugung im Manifest, geprüft wurde davon aber nur die EKG-Seite.
  Jetzt geprüft: Alpha-Peak 10,0 Hz auf **allen 19 Kanälen** (±0,3 Hz), Multitaper gegen
  Welch, 1/f-Exponent 2,2 kanalweise, Asymmetrie O1/O2 und die zeitliche Lage des
  Artefakt-Bursts bei 240–245 s.
- **`tests/test_analytic_groundtruth.py`** (neu): Verfahren gegen ihre analytisch bekannte
  Wahrheit — Permutationsentropie von weissem Rauschen = 1,0, DFA-Exponent = 0,5 bzw. 1,0,
  SDNN einer sinusförmigen RR-Reihe = A/√2, SEF95 eines flachen Spektrums, die
  Poincaré-Identität SD1²+SD2² = 2·SDNN². Solche Prüfungen sind schärfer als jede Messung an
  einer Aufnahme, weil der Sollwert nicht selbst geschätzt ist.
- **Registry-Stand danach: 18 implementierungsvalidiert, 4 literaturbasiert.** Jeder der 18
  Einträge trägt Datensatz, Sollwert, Toleranz und den Test, der es prüft — in der App
  sichtbar in derselben Tabellenzeile wie das Etikett, zusammen mit den Einschränkungen.

**Dabei gefunden — die Vergleichsdetektoren brechen still ab.** Die Fixture enthält bei
400–410 s ein Fenster mit siebenfacher EKG-Amplitude. **Hamilton und Pan-Tompkins** aus
`py-ecg-detectors` detektieren bis dorthin sauber und hören dann vollständig auf: letzter
Schlag bei 409 s, **462 statt 702 Schlägen**, 190 s Aufnahme ohne einen einzigen Treffer.
Dabei melden sie keinen Fehler — eine HRV-Auswertung darauf wäre falsch, ohne dass es
auffiele. Der **eigene** Detektor der App übersteht denselben Sprung (685 Schläge, bis
599,9 s), Christov und Two-Average ebenfalls. Folge: der Eintrag „R-Zacken (validierte
Option)" bleibt **literaturbasiert** — ein Verfahren, das im Test durchfällt, bekommt kein
Etikett. Als offener Punkt notiert: eine Abdeckungs-Plausibilisierung, die meldet, wenn ein
Detektor über einen längeren Abschnitt gar nichts findet.

**Weitere Befunde, jeweils als Test festgehalten statt als Toleranz versteckt:**

- **FOOOF unterschätzt den 1/f-Exponenten bei schmalbandigen Linien** — auf der Fixture 1,74
  statt 2,2 bei R² = 0,80, während der eigene, als „vereinfacht" gekennzeichnete Fit 2,20
  trifft. Ursache ist nicht die Einbindung (ohne Gipfel trifft FOOOF alle Testexponenten auf
  ±0,02), sondern die untere Grenze von `peak_width_limits`: eine reine Sinus-Linie lässt
  sich nicht als Gaußgipfel modellieren und landet im aperiodischen Anteil. Der eigene
  Sigma-Clip wirft sie heraus. Bei realistisch breiten EEG-Gipfeln tritt der Effekt nicht auf.
- **DFA α₁ liegt auf dem klinischen Fenster (Skalen 4–16) bei 0,584 statt 0,5** für
  unkorreliertes Rauschen — der bekannte Kleinskalen-Versatz, kein Rechenfehler: derselbe
  Code trifft auf Skalen 16–256 die Theorie (0,511 / 0,493). α₁-Werte sind untereinander
  vergleichbar, dürfen aber nicht gegen 0,5 als Normwert gelesen werden.
- **Engzee ist polaritätskritisch** — 7 Schläge auf dem Rohsignal, 678 nach der
  Polaritätskorrektur. Die Reihenfolge Korrektur → Detektion ist damit zwingend.
- **Die Fixture trägt oberhalb ~25 Hz keine 1/f-Wahrheit mehr**: bei physikalischem Bereich
  ±500 µV und 16 Bit liegt die Quantisierungsstufe bei 0,0153 µV, deren weisses Rauschen
  überdeckt das zu hohen Frequenzen hin verschwindende Signal (gemessene Steigung 40–60 Hz:
  1,72 statt 2,2; eine Kontrollreihe ohne EDF-Umweg bleibt flach bei 2,2). Der Fixture-Fit
  läuft deshalb über 1–20 Hz — kein aufgeweichter Toleranzbereich, sondern der Bereich, in
  dem die Datei die behauptete Wahrheit überhaupt trägt.
- **Die Poincaré-Identität lässt sich nur bei großer Variabilität scharf prüfen**, weil
  `compute_hrv_time_domain` auf 0,1 ms gerundete Werte zurückgibt. Die Toleranz ist aus
  dieser Rundung hergeleitet statt gegriffen; nachgemessen fällt ein um 3 % falsches SD1 bei
  den verwendeten Amplituden auf, bei 25 ms Amplitude täte es das nicht — ein solcher Fall
  ist deshalb absichtlich nicht im Test.


### Hinzugefügt — Herkunft in den Reports

Ein exportierter Report zeigte bisher Werte, aber nichts darüber, **womit** sie entstanden
sind. Es gab überhaupt keine Versionsnummer im Code — nur `CITATION.cff` nannte eine. Wer
zwei Reports derselben Aufnahme aus verschiedenen Wochen nebeneinander legte, konnte nicht
entscheiden, ob ein Unterschied aus der Aufnahme oder aus einer Codeänderung stammt.

- **`core/version.py`** (neu) — eine einzige Versionsquelle: die Nummer wird aus
  `CITATION.cff` gelesen, nicht zusätzlich im Code gepflegt. Ein Test verhindert, dass
  später doch eine zweite Konstante dazukommt.
- **Git-Commit**, mit `+dirty`, wenn beim Erzeugen uncommittete Änderungen vorlagen — dann
  ist das Ergebnis eben *nicht* allein über den Commit reproduzierbar, und genau das soll man
  sehen. `.dockerignore` schließt `.git/` aus, im Image gibt es also kein Repository; der
  Commit wird deshalb beim Bauen hereingereicht
  (`--build-arg EDF_BUILD_COMMIT=$(git rev-parse --short HEAD)`). Fehlt er, steht
  „unbekannt" da statt einer erfundenen Angabe.
- **Python- und Paketversionen der laufenden Umgebung** (aus `importlib.metadata`, nicht aus
  `requirements.txt`: was installiert ist, entscheidet über das Ergebnis).
- **SHA-256 der EDF-Datei und ein Analyse-Fingerabdruck** aus Datei + Version + Commit +
  Analyseparametern. Gleicher Fingerabdruck heißt: gleiche Datei, gleicher Code, gleiche
  Einstellungen — ein Unterschied in den Werten wäre dann erklärungsbedürftig. Der Hash
  identifiziert die Aufnahme, ohne etwas über sie preiszugeben.
- Sichtbar in **allen drei** Ausgaben: als eigene Sektion im Tabellen-Report (PDF und Excel),
  als Block im HRV-Report und als Fußzeile auf **jeder Seite** des visuellen Reports — aus
  dem werden einzelne Seiten ausgedruckt und weitergereicht, und eine Seite ohne ihre
  Herkunft verliert sie genau dann, wenn es darauf ankommt.

**Beim Ansehen der erzeugten PDFs gefunden und behoben:** ReportLab bricht rohe Zellentexte
nicht um — die neue Paketliste lief rechts aus dem Satzspiegel und „Parameter: pädiatrische
Normwerte" überdruckte seinen eigenen Wert. `build_pdf` kann jetzt Sektionen umbrechen
lassen (`wrap`) und eigene Spaltenbreiten mitgeben. Der Fehler war nur sichtbar, weil die
Reports tatsächlich geöffnet und nicht nur erzeugt wurden.


### Hinzugefügt — `docs/PREPROCESSING.md`

Zwischen der EDF-Datei und einem ausgegebenen Kennwert liegen Filter, Fensterwahl,
Artefaktbehandlung und Umtastung. Sie standen nirgends zusammenhängend — über ein Dutzend
Filteraufrufe verteilt über `analysis/` und `views/`, jeder für sich kommentiert, ohne
Gesamtbild. Wer einen Wert nachrechnen wollte, musste den Code lesen.

Die Spezifikation ist **aus dem Code abgeleitet, nicht aus der Absicht**, und
`tests/test_preprocessing_doc.py` bindet sie daran: Bandgrenzen, Artefaktschwellen,
HRV-Frequenzparameter und die Filterordnungen werden aus den Modulen gelesen und gegen das
Dokument geprüft. Eine aus dem Code abgeleitete Doku veraltet sonst leise — und ist dann
schlimmer als keine, weil sie einen Rechenweg behauptet, den es nicht mehr gibt.

Der wichtigste Satz darin klärt die häufigste Fehlannahme: **die Filtereinstellungen im
EEG-Viewer beeinflussen keinen berechneten Wert.** Sie ändern nur die dargestellte Kurve;
die Kennwerte beruhen unverändert auf dem 1-Hz-hochpassgefilterten Signal.

**Beim Ableiten gefunden:**

- **Eine tote, abweichende EKG-Pipeline.** `analysis/ecg.py` enthält `run_ecg_analysis()`,
  das `preprocess_ecg()` (Bandpass 0,5–40 Hz) vor der R-Zacken-Suche anwendet und den
  Frequenzbereich über `compute_hrv_frequency_domain()` rechnet. **Diese Funktion ruft
  niemand auf**, und die beiden anderen ausschließlich sie. Der tatsächliche Pfad filtert
  *nicht* 0,5–40 Hz vor und nutzt eine andere Frequenzbereichsfunktion. Wer die Datei von
  oben liest, muss den Eindruck gewinnen, die EKG-Kette beginne mit diesem Filter. Ein Test
  hält den Zustand fest, bis die Leiche entfernt ist.
- **Delta beginnt bei 1 Hz, nicht bei 0,5 Hz** — ergibt sich zwingend aus dem 1-Hz-Hochpass
  und dem Ausgabeband, stand aber an keiner für Anwender sichtbaren Stelle. Für
  Enzephalopathie und Vigilanzminderung ist gerade der Bereich darunter relevant. Als
  offener Prüfpunkt notiert; nicht nebenbei geändert, weil es jeden Delta-abgeleiteten
  Quotienten verschieben würde.
- **Zwei Welch-Implementierungen, nachgemessen gleichwertig.** `_compute_psd` nutzt das
  symmetrische `np.hanning`, `scipy.signal.welch` das periodische Hann-Fenster (Energie
  299,6 gegen 300,0). Der Unterschied kürzt sich in der Normierung heraus: Alpha-Power,
  Alpha-Schwerpunkt und SEF95 stimmen auf sechs Stellen überein. Festgehalten, damit die
  Frage nicht ein zweites Mal untersucht wird.


### Hinzugefügt — Betriebshärtung

**Upload-Prüfung (`core/edf_validation.py`).** Bisher prüfte der Upload nur Dateiendung und
Größe; alles andere fiel erst beim Laden auf — als Stacktrace. Ein Fall fiel **gar nicht**
auf: eine abgeschnitten übertragene Datei lädt MNE klaglos als kürzere Aufnahme
(nachgemessen: eine halbierte 600-s-Datei wird zu 299 s), und die Analyse rechnet auf dem
Bruchstück weiter, ohne dass es jemandem auffällt. Geprüft wird jetzt allein anhand der
Header, in Millisekunden und ohne die Datei zu laden: ist es überhaupt eine EDF (umbenannte
Fremddatei, BDF), ist der Header in sich schlüssig, passt die Dateigröße zu den
angekündigten Datenblöcken, ist die Aufnahme lang genug.

Abgelehnt wird nur, was nicht analysierbar ist. Kurze Aufnahmen (< 5 min, HRV-Frequenzdomäne)
und niedrige Abtastraten (< 100 Hz) erzeugen eine **Warnung** — die App ist ein
Forschungswerkzeug, kein Torwächter; ungewöhnlich ist nicht unbrauchbar. Jede Meldung sagt,
was nicht stimmt und was zu tun ist, statt „ungültige Datei", und liegt **zweisprachig** vor:
eine abgelehnte Datei ist genau die Stelle, an der ein anderssprachiger Nutzer sonst ohne
Erklärung stehen bliebe. `tools/check_i18n.py` prüft diesen zweiten Übersetzungsort mit
(fehlende Fassung, unübersetzt gebliebener Text, abweichende Platzhalter — letztere würden
zur Laufzeit in `.format()` scheitern).

**Container.** Läuft nicht mehr als root, sondern als eigener Nutzer (`uid 10001`) — der
Container verarbeitet hochgeladene Fremddateien mit einem umfangreichen Parser-Stack, es gibt
keinen Grund für root-Rechte. Ressourcengrenzen gehören an den Start und stehen als
Betriebshinweis im Dockerfile; eine 200-MB-EDF wird von MNE vollständig als float64 in den
Speicher geladen, und ohne Grenze zieht eine einzelne große Aufnahme den Host in den Swap.
Das ist der realistische Fall — nicht ein Angreifer, sondern eine lange Aufnahme.

Nachgeprüft statt angenommen: das Image wurde gebaut und mit `--read-only --memory=2g
--cpus=2` plus tmpfs gestartet, und darin die **komplette Kette** durchlaufen —
Validierung, Laden, alle 15 Report-Sektionen, Tabellen-PDF, Excel und visueller Report. Alles
grün als Nicht-root auf einem schreibgeschützten Dateisystem.

**Abhängigkeiten.** Ober- **und** Untergrenzen statt nur `>=`. Exakte Pins wären für eine
Anwendung das Naheliegende — gerade weil die Reports jetzt die Paketversionen mitschreiben —
gehen hier aber nicht: das Image läuft auf Python 3.9 (wegen MNE), CI und Entwicklung
zusätzlich auf 3.12, und für mehrere Pakete gibt es keine auf beiden installierbare Version
(numpy 2.0.2 ist die letzte mit 3.9-Rädern). Die Obergrenzen schließen den nächsten
Major-Sprung aus; welche Versionen ein konkretes Ergebnis erzeugt haben, steht ohnehin im
Report. Dazu `.github/dependabot.yml`: monatlich, die wissenschaftlichen Pakete als **eine**
Gruppe, weil numpy/scipy/pandas/matplotlib einzeln aktualisiert entweder nicht installieren
oder eine Kombination ergeben, die niemand zusammen getestet hat.


## [0.1.0] — 2026-08-11 — erste öffentliche Fassung

Der Stand, mit dem das Repository von privat auf öffentlich geschaltet wurde: Sicherheits-
Fix am Passwort-Gate, Zweisprachigkeit, Lizenz- und Datenschutz-Bereinigung, lauffähige
Test-Suite und CI. Ein getaggtes Release gab es dafür nicht.

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
