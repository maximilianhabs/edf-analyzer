# EDF-Analyzer

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
streamlit run app.py
```

Danach [http://localhost:8501](http://localhost:8501) öffnen. Der Upload erwartet eine EDF-Datei (max. 200 MB).

## Funktionen

- **Kanal-Identifikation** — signalbasierter Classifier (EEG/EKG/EOG/EMG/Referenz/Vital) mit Konfidenz und manueller Korrektur.
- **EEG-Spektralanalyse** — Welch/Multitaper-PSD, absolute/relative Bandpower, Alpha-Grundrhythmus, A/P-Gradient, hemisphärische Asymmetrie.
- **Aperiodik (1/f)** — eigener Log-Log-Fit plus validierter FOOOF/specparam-Fit.
- **EKG & HRV** — QRS-Detektion, RR-Bereinigung, Zeitdomäne (SDNN/RMSSD/pNN50/CV/Poincaré), Frequenzdomäne (Welch + Burg, Lomb-Scargle), DFA α₁/α₂.
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

## Tech-Stack

Python 3.9 · Streamlit · MNE · SciPy/NumPy/pandas · pyedflib · FOOOF · py-ecg-detectors · reportlab/openpyxl. Vollständige Liste in [`requirements.txt`](requirements.txt).

## Projektstatus & Verantwortung

Aktiv entwickeltes Forschungsprojekt eines einzelnen Autors und Maintainers. Die **inhaltliche und wissenschaftliche Verantwortung** — Methodenauswahl, Bewertung, Testung — liegt bei **Maximilian Habs** (Facharzt für Neurologie). Teile des Codes wurden mit KI-Unterstützung erstellt; die fachliche Prüfung und Freigabe erfolgt manuell durch den Autor.

Fehler und Vorschläge bitte über die [Issues](https://github.com/maximilianhabs/edf-analyzer/issues).

## Lizenz

[Apache License 2.0](LICENSE) © 2026 Maximilian Habs.
