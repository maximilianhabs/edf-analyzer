# EDF Analyzer — Projektdokumentation

> **Achtung: Dieses Projekt ist NICHT der EEG-Navigator.**
> Der EEG-Navigator (github.com/maximilianhabs/eeg-navigator) ist ein interaktives
> Lern-Tool mit 94 EEG-Wellen und 26 Artefakten.
> Dieses Projekt hier (EDF Analyzer) ist ein klinisches Analyse-Tool für
> echte EDF-Aufnahmen aus NeuroFax — mit HRV-Analyse, EEG-Spektrum, qEEG.

---

## Vision

Klinisches EEG/EKG-Analyse-Tool für Routineaufnahmen aus NeuroFax/Neoncodesystem/Polaris.
Ziel: Mehr aus Standard-EEGs herausholen als die bloße visuelle Befundung.
Perspektivisch: Webbasiertes Tool für Kollegen.

---

## Architektur & Tech-Stack

### Überblick

```
edf-analyzer/
├── app.py                     # Einstiegspunkt — Streamlit Multi-Page-App
├── requirements.txt           # Python-Abhängigkeiten
├── anonymize.py               # CLI-Tool: EDF-Header de-identifizieren
├── anonymization_log.json     # Audit-Log (lokal, nicht in Git)
│
├── .streamlit/
│   └── config.toml            # maxUploadSize = 1024 MB, Port 8501
│
├── core/
│   ├── loader.py              # EDF laden, Kanal-Erkennung, MNE-Wrapper
│   └── shared.py              # Session-State-Helfer, CSS, Pfeiltasten-JS
│
├── analysis/
│   ├── ecg.py                 # R-Peak-Detektion, RR-Intervalle, HRV-Zeitdomäne
│   ├── hrv_freq.py            # HRV-Frequenzdomäne (Welch/Burg, LF/HF, PSD)
│   ├── hrv_reference.py       # Normwert-Tabellen (Altersgruppen, Pediatrie)
│   ├── hv_segmentation.py     # Hyperventilations-Segmenterkennung (Annotations)
│   └── pdf_report.py          # PDF-Befundbericht (ReportLab)
│
├── views/
│   ├── file_patient.py        # Seite 1: EDF-Upload, Patientendaten, Vorschau
│   ├── eeg_viewer.py          # Seite 2: EEG-Kurven, Montagen, Epochen-Nav
│   ├── ecg_hrv.py             # Seite 3: EKG-Spur, HRV-Analyse, Blocks 1–3
│   ├── eeg_spectrum.py        # Seite 4: qEEG — Spektrum, Bandpower, Asymmetrie
│   └── report.py              # Seite 5: PDF-Export, Zusammenfassung
│
├── tests/
│   └── test_ecg_pipeline.py   # Unit-Tests ECG-Pipeline
│
└── docs/
    └── PROJECT.md             # Dieses Dokument
```

### Schichten im Detail

| Schicht | Technologie | Zweck |
|---|---|---|
| **UI / Frontend** | Streamlit (Python) | Multi-Page-App, lokale interaktive Analyse |
| **EDF I/O** | MNE-Python | EDF+D laden, Kanal-Extraktion, Metadaten |
| **EKG-Analyse** | SciPy (find_peaks) | R-Peak-Detektion, RR-Intervalle, HRV |
| **EEG-Spektrum** | SciPy (Welch + DPSS) | PSD, Bandpower, Multitaper (Thomson 1982) |
| **Visualisierung** | Plotly (via Streamlit) | Interaktive Charts, Zoom, Hover |
| **Daten-Export** | Pandas + ReportLab | Excel (HRV), PDF-Befundbericht |
| **De-Identifikation** | MNE + hashlib | EDF-Header anonymisieren, SHA-256-Audit |

### Datenhaltung

| Art | Ort | Persistenz | Inhalt |
|---|---|---|---|
| **Temporär (Sitzung)** | `st.session_state` | nur Sitzung | geladene EDF-Daten, Analyse-Ergebnisse, UI-Zustand |
| **Temporär (Datei)** | `/tmp/edf_analyzer_uploads/` | bis Neustart | hochgeladene EDF-Datei (UUID-Prefix) |
| **Dauerhaft (lokal)** | `anonymization_log.json` | persistent | Audit-Log de-identifizierter Dateien |
| **Keine** | — | — | keine Datenbank, kein Server, kein Cloud-Upload |

**→ Es gibt keine persistente Datenbank.** Die App ist rein lokal und zustandslos zwischen Sitzungen. EDF-Dateien werden nie in Git committed.

### Wie Daten fließen

```
EDF-Datei (lokal)
    ↓ st.file_uploader (Finder-Dialog)
/tmp/edf_analyzer_uploads/<uuid>.edf
    ↓ core/loader.py → MNE
session_state: raw_data, ch_names, eeg_map, annotations, ...
    ↓ views/ rendern auf Anfrage
analysis/ berechnet HRV / Spektrum / Bandpower
    ↓ Ergebnisse in session_state gecacht
Plotly-Charts + Metriken → Browser
    ↓ auf Wunsch
PDF (reportlab) / Excel (pandas) → Download
```

---

## Datenschutz-Prinzipien

1. EDF-Dateien enthalten Patientendaten im Header (Name, Geburtsdatum, Fallnummer)
2. **Keine EDF-Dateien in Git** — `.gitignore` schützt `data/` und `*.edf`
3. Alle Analysen lokal, kein Cloud-Upload ohne explizite Pseudonymisierung
4. Vor Weitergabe: Header-De-Identifikation mit `anonymize.py`
5. Aus dem Header wird **nur Geburtsjahr** ausgelesen (für Altersgruppen) — nie der vollständige Name

---

## Kontext

- **Gerät**: NeuroFax / Neoncode (Polaris-Datenbank)
- **Format**: EDF+D (European Data Format, discontinuous)
- **Patienten**: Erwachsene, typisch ältere Epilepsiepatienten
- **Aufnahmedauer**: 10–20 Minuten Routine-EEG
- **Kanäle**: 19 EEG (10-20-System) + Polygraphie (SpO2, EtCO2, Puls, CO2) + EKG
- **Sampling**: 200 Hz

---

# Meilensteine & Status

## ✅ M0 — Projekt-Setup
- [x] Projektstruktur angelegt
- [x] Git + GitHub initialisiert (github.com/maximilianhabs/edf-analyzer)
- [x] EDF-Datei analysiert (Kanalstruktur, Annotations verstanden)
- [x] Datenschutz-Konzept definiert

## ✅ M1 — EKG-Basis-Analyse
- [x] EDF laden, EKG-Kanal isolieren, DC-Offset korrigieren
- [x] R-Peak-Detektion (SciPy, adaptiver Threshold, |Signal|-Normierung)
- [x] 3-stufiger Outlier-Filter für RR-Intervalle
- [x] HRV-Basismetriken: SDNN, RMSSD, pNN50
- [x] Tachogramm-Plot (RR über Zeit)
- [x] Poincaré-Plot
- [x] HRV-Frequenzanalyse: Welch/Burg-PSD, LF/HF, LF/HF-Ratio

## ✅ M2 — Streamlit Viewer
- [x] EDF-Upload via Finder-Dialog (`st.file_uploader`)
- [x] EKG-Plot mit R-Peak-Markierung
- [x] EEG-Übersicht (alle Kanäle, scrollbar, Epochen-Navigation)
- [x] Annotations eingeblendet (Augen auf/zu, Montagen)
- [x] HRV-Metriken als Analyse-Panel
- [x] Multi-Page-App mit linker Navigation (`st.navigation`/`st.Page`)
- [x] Tastatur-Navigation (Pfeiltasten ← →)

## ✅ M3 — EEG-Spektralanalyse (qEEG-Seite)
- [x] Welch-Spektrum pro EEG-Kanal
- [x] Multitaper-Methode (Thomson 1982, DPSS NW=3, K=5)
- [x] Bandpower: Delta (0.5–4 Hz), Theta (4–8 Hz), Alpha (8–13 Hz), Beta (13–30 Hz), Gamma
- [x] Konsensus-Panel: Spektrogramme + Bandpower + klinische Ratios über alle EEG-Kanäle
- [x] Klinische Ratios: Delta/Alpha, Theta/Alpha, Alpha/Theta, Theta/Beta, DTAB
- [x] Referenz-Epoch (10s, Slider-Navigation, Positions-Balken, Roh-EEG + normiertes FFT)
- [x] Alpha-Peak-Konsistenz-Check (Gesamt vs. Referenz-Epoch)
- [x] Hemisphärische Asymmetrie (AI = L-R/L+R × 100%, nach Frequenzbändern, Nuwer 1997)
- [x] Extremartefakt-Filter (optional, ≥150 µV Schwelle)
- [x] 1 Hz Hochpassfilter (DC-Drift-Kompensation)
- [x] Appendix mit Parameter-Erklärungen

## ✅ M4.1 — Autonome Analyse / HRV-Normwerte
- [x] Altersgruppen-spezifische Normwerte (Pädiatrie: Gąsior 2018; Erwachsene)
- [x] Klinische Lab-Panel-Darstellung (farbige Zonen, Pfeil-Indicator)
- [x] HRV unter Hyperventilation — Block 2 (HV-Segmenterkennung via Annotations)
- [x] HRV post-HV — Block 3 (Vergleich Ruhe vs. HV vs. Post-HV)
- [x] HV-False-Positive-Fix: ohne HV-Annotations kein Block 2 angezeigt
- [x] HR-Klassifikation: 5-Zonen-System (<40 rot, 40-60 orange, 60-100 grün, 100-140 orange, >140 rot)

## ✅ M5 — De-Identifikations-Pipeline
- [x] CLI-Tool `anonymize.py`: EDF-Header vollständig de-identifizieren
- [x] Audit-Log (JSON): Timestamp, Anon-ID, SHA-256 des Originals, beibehaltene Felder
- [x] Einzel- und Batch-Modus (`--batch`)
- [x] Verifikations-Modus (`--verify-only`)
- [x] Optionale Erhalt von Geschlecht + Alters-Dekade für EEG-Normwerte

## 🔲 Offen / Backlog

### Kurzfristig
- [ ] Kopfdiagramm (10-20) klickbar machen (Montage direkt am Kopf wählen)
- [ ] EEG-Bedienpanel weiter verfeinern (Niveau der EKG-Seite anstreben)
- [ ] HV-Block: explizite UI-Abfrage "Hyperventilation: ja/nein" (nicht nur Annotation)
- [ ] HRV-Analyse für HV-Abschnitte getrennt vs. Ruhe (segmentierter Vergleich)

### Mittelfristig
- [ ] Alpha-Reaktivität: Augen-auf vs. Augen-zu (aus Annotations automatisch extrahieren)
- [ ] Topographische Heatmap (Bandpower-Verteilung über 10-20-System)
- [ ] Automatisierte Spike/IED-Detection (konzeptionell geplant, hoher Aufwand)
- [ ] Tragbarer Viewer (USB-Stick, ohne Installation) — technisch zu klären

### Langfristig (M6)
- [ ] FastAPI + React/Next.js Webapp für Kollegen
- [ ] Benutzer-Authentifizierung + Rollen
- [ ] Datei-Upload mit automatischer Pseudonymisierung
- [ ] Befundberichte speichern + abrufbar

---

# Kanal-Mapping (NeuroFax / Neoncode)

| Kanal-Name im EDF | Inhalt | Einheit | Verwendung |
|---|---|---|---|
| `EEG Fp1/2-Ref` bis `EEG Pz-Ref` | Standard 10-20 EEG | µV | EEG-Analyse |
| `EEG A1/A2-Ref` | Ohrelektroden | µV | Referenz |
| `POL $A1`, `POL $A2` | Kalibrierkanal (gesättigt, tot) | mV | NICHT verwenden |
| `POL SpO2` | Sauerstoffsättigung | % | Vitalparameter |
| `POL EtCO2` | endtidales CO2 | mmHg | Vitalparameter |
| `POL Pulse` | Puls (Referenz) | bpm | HF-Validierung |
| `POL X1–X7` | Konfigurierbar | — | Gerätespezifisch |

---

# Troubleshooting-Log

| Datum | Problem | Lösung |
|---|---|---|
| 2026-06-15 | EDF mit `utf-8` nicht lesbar | `encoding='latin1'` nötig (NeuroFax schreibt latin1) |
| 2026-06-15 | EKG-Kanäle heißen `$A1`/`$A2`, nicht `EKG` | NeuroFax-spezifische Bezeichnung, Kanal-Mapping dokumentiert |
| 2026-06-15 | EKG-Amplituden ~-12000 mV | DC-Offset aus Kalibrierung — `signal - signal.mean()` vor Analyse |
| 2026-06-15 | $A1/$A2 zeigt nur Nadelspitzen, kein EKG | Gesättigte Kalibrierkanäle — echtes EKG in POL X1 (dynamische Kanal-Erkennung via unique-value-count) |
| 2026-06-16 | Datei/Patient-Werte gingen bei Seitenwechsel verloren | Werte in eigenen Session-State-Keys (nicht Widget-Keys) |
| 2026-06-16 | Alpha-Peak nicht detektierbar | DC-Drift von Elektroden überwältigt Spektrum — 1 Hz HPF als Pflicht eingeführt |
| 2026-06-17 | HR zeigt "5. Perz.: 60.0 bpm" | p5_threshold=None gesetzt, 5-Zonen-HR-Chart eingeführt |
| 2026-06-17 | HV False Positive: Block 2 auch ohne HV-Annotations | Early-return + optionaler "HV manuell"-Button eingeführt |
