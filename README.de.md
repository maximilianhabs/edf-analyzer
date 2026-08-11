# EDF-Analyzer

**[English](README.md) · Deutsch**

**Ein browserbasiertes Forschungs- und Lehrwerkzeug zur quantitativen Auswertung von EEG- und EKG-Aufzeichnungen im European Data Format (EDF).** Es leitet aus Routine-Aufnahmen quantitative neurophysiologische und autonome (HRV-)Kennwerte ab — mit strikter Trennung zwischen bewährten Standard-Methoden und literatur-validierten Zusatzverfahren.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.9-blue)
![Status](https://img.shields.io/badge/status-aktiv%20·%20research%20prototype-orange)

> ⚠️ **Kein Medizinprodukt, keine Diagnosesoftware.** Der EDF-Analyzer ist ein Werkzeug für Forschung, methodische Exploration und Lehre. Alle ausgegebenen Werte sind **Orientierung**, keine Diagnosekriterien, und ersetzen keine ärztliche Befundung.

---

## Was es macht

Man lädt eine EDF-Datei hoch; die App erkennt automatisch die Kanaltypen (EEG/EKG/EOG/…), berechnet quantitative Marker (EEG-Spektralanalyse, HRV-Zeit- und Frequenzdomäne, Aperiodik, Komplexität) und erlaubt eine artefaktbereinigte Gegenauswertung sowie tabellarische und visuelle Reports.

## Warum es existiert

Kommerzielle EEG/EKG-Systeme geben quantitative Kennwerte oft als Blackbox aus — die zugrundeliegende Methodik ist selten transparent, herstellerabhängig und schwer nachzuvollziehen. Der EDF-Analyzer macht die Rechenwege **explizit und nachvollziehbar**: für jedes Verfahren ist dokumentiert, ob es einem publizierten Goldstandard folgt oder eine bewusste Vereinfachung ist (siehe [Wissenschaftliche Transparenz](#wissenschaftliche-transparenz)).

## Schnellstart

**Mit Docker (empfohlen):**

```bash
git clone https://github.com/maximilianhabs/edf-analyzer.git
cd edf-analyzer
docker build -t edf-analyzer .
docker run -p 8501:8501 -e EDF_PASSWORD=deinPasswort edf-analyzer
```

**Lokal (Python 3.9):**

```bash
pip install -r requirements.txt
EDF_PASSWORD=deinPasswort streamlit run app.py
```

`EDF_PASSWORD` ist eine Pflicht-Umgebungsvariable — ohne sie startet die App aus
Sicherheitsgründen nicht (kein Default-Passwort im Quellcode).

Danach [http://localhost:8501](http://localhost:8501) öffnen. Der Upload erwartet eine EDF-Datei (max. 200 MB).

## Funktionen

- **Kanal-Identifikation** — signalbasierter Classifier (EEG/EKG/EOG/EMG/Referenz/Vital) mit Konfidenz und manueller Korrektur.
- **EEG-Spektralanalyse** — Welch/Multitaper-PSD, absolute/relative Bandpower, Alpha-Grundrhythmus, A/P-Gradient, hemisphärische Asymmetrie.
- **Aperiodik (1/f)** — eigener Log-Log-Fit plus validierter FOOOF/specparam-Fit.
- **Rhythmus-Screening** — vorgeschaltetes AFib-/Ektopie-Screening vor der HRV-Analyse: Artefakt-Filterung (Orphanidou 2015), Vorhofflimmern-Erkennung via CosEn (Lake & Moorman 2011) mit gestufter Sicherheit, P-Wellen-Nachweis via Schlag-Summation, Ektopie-Erkennung (Kompensationspause/QRS-Breite), Detektor-Umschaltung (eigen/Hamilton/Christov/Pan-Tompkins/…), automatische Polaritätskorrektur mit In-App-Diagnose.
- **EKG & HRV** — QRS-Detektion, RR-Bereinigung, Zeitdomäne (SDNN/RMSSD/pNN50/CV/Poincaré), Frequenzdomäne (Welch + Burg, Lomb-Scargle), DFA α₁/α₂, autonome Gesamtaktivitäts-Warnung bei "starrer Herzfrequenz".
- **Komplexität** — Sample Entropy, Lempel-Ziv, Permutationsentropie.
- **Artefaktkorrektur** — regelbasierte Auto-Maske plus klickbares Editing; Gesamt- und bereinigte Auswertung laufen parallel.
- **Reports** — tabellarischer PDF/Excel-Export (Gesamt vs. korrigiert) und ein visueller PDF-Abstract.

## Wissenschaftliche Transparenz

Der Anspruch ist methodische Ehrlichkeit statt Feature-Marketing. Eine zentrale Registry (`analysis/methods.py`) klassifiziert **alle 22 eingesetzten Verfahren**:

| Status | Anzahl | Bedeutung |
|---|---|---|
| ✅ validiert | 15 | folgt einem publizierten Standard (z. B. Task Force 1996 für HRV, Pan & Tompkins 1985, FOOOF/Donoghue 2020, Nuwer für Asymmetrie) |
| 🟡 vereinfacht | 6 | funktionsfähige, bewusst vereinfachte Variante — als solche gekennzeichnet |
| 🔬 Proxy | 1 | explorativer Ersatzmarker, nicht klinisch etabliert |

Nach dem **Add-on-Prinzip** bleiben die bewährten Standard-Methoden unverändert; für jede vereinfachte Default-Methode existiert ein validiertes Pendant zum direkten Vergleich in der Rubrik „Erweiterte Analysen". Es wird nichts stillschweigend umgestellt.

## Limitationen

- **Nicht klinisch validiert.** Es existiert (noch) keine prospektive Validierung gegen etablierte Referenzsysteme oder annotierte Datensätze (z. B. MIT-BIH). Ergebnisse sind explorativ.
- **Artefakterkennung** ist regelbasiert und konservativ, bislang an wenigen Aufnahmen erprobt — keine ICA/autoreject-basierte Korrektur.
- **HRV-Frequenzdomäne** benötigt ausreichend lange, stationäre Abschnitte (Task Force: ≥ 5 min); kurze Aufnahmen liefern hier bewusst keine Werte.
- **Keine Normdatenbank** — angezeigte Normbereiche sind Literatur-Orientierungswerte, keine alters-/geschlechtsadjustierten Referenzkohorten.

## Datenschutz

- EDF-Dateien sind **im Repository nicht enthalten** und werden per `.gitignore` ausgeschlossen — es sind keinerlei Patientendaten Teil des Projekts.
- Beim Upload prüft die App den EDF-Header auf identifizierende Angaben; ein Standalone-Skript (`anonymize.py`) kann Header anonymisieren.
- Hochgeladene Dateien liegen in einem sitzungseigenen Temp-Ordner und werden durch einen Cleanup-Daemon nach spätestens ~4 h automatisch gelöscht.
- **Keine externen Verbindungen zur Laufzeit.** Schriften werden lokal aus `static/fonts/`
  ausgeliefert (vorher von einem CDN, wodurch bei jedem Aufruf die IP-Adresse des Nutzers an
  einen Dritten ging), und Streamlits Nutzungs-Telemetrie ist abgeschaltet
  (`gatherUsageStats = false`). Am 2026-08-11 über sechs Seiten geprüft: null Requests an
  externe Hosts. Selbst nachmessen lässt sich das in der Browser-Konsole mit:
  `performance.getEntriesByType('resource').map(r => r.name).filter(n => !n.includes(location.host))`
  — das Ergebnis sollte ein leeres Array sein. Das betrifft **die Anwendung selbst**;
  Streamlit ist Fremdsoftware, eine künftige Version könnte ihr Verhalten ändern — deshalb
  ist hier die Prüfmethode dokumentiert statt einer pauschalen Garantie.
- Wer EDF-Dateien schon *vor* dem Upload lokal anonymisieren möchte, kann dafür das eigenständige Begleit-Tool [edf-anonymizer](https://github.com/maximilianhabs/edf-anonymizer) nutzen — dependency-freies CLI plus optionale Web-Oberfläche, läuft komplett offline auf dem eigenen Rechner.

## Sicherheit

Der App-Zugang ist per Passwort geschützt (`EDF_PASSWORD`, Pflicht-Umgebungsvariable, siehe
Schnellstart). Bis 2026-08-10 hatte der Quellcode ein Default-Passwort als Fallback hinterlegt,
falls die Variable fehlte — das war insofern ein Fehler, als das Repo damals (noch privat) für
eine öffentliche Veröffentlichung vorbereitet wurde und dieser Fallback dann für jeden
einsehbar gewesen wäre. Behoben, bevor das Repo öffentlich ging: kein Fallback mehr, die App
startet ohne gesetzte Variable nicht. Details siehe [CHANGELOG.md](CHANGELOG.md). Sollte dir
ein sicherheitsrelevantes Problem auffallen, bitte über ein
[GitHub Security Advisory](https://github.com/maximilianhabs/edf-analyzer/security/advisories/new)
statt über ein öffentliches Issue melden.

## Tech-Stack

Python 3.9 · Streamlit · MNE · SciPy/NumPy/pandas · pyedflib · FOOOF · py-ecg-detectors · reportlab/openpyxl. Vollständige Liste in [`requirements.txt`](requirements.txt).

## Projektstatus & Verantwortung

Aktiv entwickeltes Forschungsprojekt eines einzelnen Autors und Maintainers. Die **inhaltliche und wissenschaftliche Verantwortung** — Methodenauswahl, Bewertung, Testung — liegt bei **Maximilian Habs** (Facharzt für Neurologie). Teile des Codes wurden mit KI-Unterstützung erstellt; die fachliche Prüfung und Freigabe erfolgt manuell durch den Autor.

Fehler und Vorschläge bitte über die [Issues](https://github.com/maximilianhabs/edf-analyzer/issues).

## Lizenz

[Apache License 2.0](LICENSE) © 2026 Maximilian Habs.

## Weiteres

[Changelog](CHANGELOG.md) · [Sicherheitsrichtlinie](SECURITY.md)

## Eigenes Hosting

Die App ist eine gewöhnliche Streamlit-Anwendung und läuft überall dort, wo Docker verfügbar
ist. Hinter einem Reverse Proxy (nginx, Caddy, Traefik) sind zwei Dinge zu beachten:

- **WebSocket-Upgrade durchreichen** — Streamlit braucht es, sonst bleibt die Seite beim
  Laden hängen.
- **`EDF_PASSWORD` als Umgebungsvariable setzen** (siehe [Schnellstart](#schnellstart)); ohne
  sie startet die App nicht.

Wird die App öffentlich erreichbar gemacht, gehört zusätzlich TLS davor und — je nach
Einsatzzweck — eine Zugangsbeschränkung auf Netzwerkebene. Für die Verarbeitung
personenbezogener Aufnahmen ist der Betreiber selbst verantwortlich; siehe
[Datenschutz](#datenschutz).
