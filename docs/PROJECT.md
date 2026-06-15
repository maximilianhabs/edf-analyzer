# EDF Analyzer — Projektdokumentation

## Vision

Klinisches EEG-Analyse-Tool für Routineaufnahmen aus NeuroFax/Neoncodesystem/Polaris.
Ziel: Mehr aus Standard-EEGs herausholen als die bloße visuelle Befundung.
Perspektivisch: Webbasiertes Tool für Kollegen.

## Kontext

- **Gerät**: NeuroFax / Neoncode (Polaris-Datenbank)
- **Format**: EDF+D (European Data Format, discontinuous)
- **Patienten**: Erwachsene, typisch ältere Epilepsiepatienten
- **Aufnahmedauer**: 10–20 Minuten Routine-EEG
- **Kanäle**: 19 EEG (10-20-System) + Polygraphie (SpO2, EtCO2, Puls, CO2) + EKG ($A1/$A2)
- **Sampling**: 200 Hz

## Datenschutz-Prinzipien

1. EDF-Dateien enthalten Patientendaten im Header (Name, Geburtsdatum, Fallnummer)
2. **Keine EDF-Dateien in Git** — `.gitignore` schützt `data/` und `*.edf`
3. Alle Analysen lokal, kein Cloud-Upload ohne explizite Pseudonymisierung
4. Vor Weitergabe: Header-Pseudonymisierung mit `core/anonymize.py`

## Technologie-Stack

| Schicht | Technologie | Zweck |
|---|---|---|
| EDF I/O | mne-python | Lesen, Kanal-Extraktion |
| EKG-Analyse | neurokit2 | R-Peaks, HRV, autonome Parameter |
| EEG-Analyse | scipy + mne | Spektralanalyse, Bandpower |
| UI Phase 1 | Streamlit | Lokale interaktive App |
| UI Phase 2 | FastAPI + React | Skalierbare Webapp für Kollegen |
| Export | pandas + reportlab | CSV, PDF-Berichte |

---

# Meilensteine

## ✅ M0 — Projekt-Setup (aktuell)
- [x] Projektstruktur angelegt
- [x] Git + GitHub initialisiert
- [x] EDF-Datei analysiert (Kanalstruktur, Annotations verstanden)
- [x] Datenschutz-Konzept definiert

## 🔲 M1 — EKG-Basis-Analyse (Prio 1)
**Ziel**: Aus dem EKG-Kanal ($A1/$A2) zuverlässig Herzrate, RR-Intervalle und HRV extrahieren.

- [ ] EDF laden, EKG-Kanal isolieren, DC-Offset korrigieren
- [ ] R-Peak-Detektion (neurokit2)
- [ ] RR-Intervalle berechnen und plotten
- [ ] HRV-Basismetriken: SDNN, RMSSD, pNN50
- [ ] Tachogramm-Plot (RR über Zeit)
- [ ] Puls-Validierung gegen `POL Pulse`-Kanal
- [ ] Export: CSV mit RR-Zeitreihe + HRV-Tabelle

## 🔲 M2 — Streamlit Viewer (Prio 2)
**Ziel**: Interaktive lokale App — EDF laden, EKG + EEG visuell prüfen.

- [ ] EDF-Upload / Pfad-Eingabe (mit Datenschutz-Warnung)
- [ ] EKG-Plot mit R-Peak-Markierung
- [ ] EEG-Übersicht (alle 19 Kanäle, scrollbar)
- [ ] Annotations eingeblendet (Augen auf/zu, Montagen)
- [ ] HRV-Metriken als Sidebar-Panel

## 🔲 M3 — EEG-Spektralanalyse (Prio 3)
**Ziel**: Frequenzspektrum und Bandpower pro Kanal.

- [ ] Welch-Spektrum pro EEG-Kanal
- [ ] Bandpower: Delta (0.5–4 Hz), Theta (4–8 Hz), Alpha (8–13 Hz), Beta (13–30 Hz)
- [ ] Topographische Heatmap (Bandpower-Verteilung über 10-20-System)
- [ ] Alpha-Reaktivität: Augen auf vs. Augen zu (aus Annotations)

## 🔲 M4 — Epilepsie-spezifische Module (Prio 4)
**Ziel**: Klinisch relevante Zusatzanalysen.

- [ ] SUDEP-relevante HRV-Parameter: LF/HF-Ratio, Poincaré-Plot, DFA
- [ ] Periiktale EKG-Analyse (falls iktale EEGs vorliegen)
- [ ] Synchronizitäts-Index EEG↔EKG (kardiozerebrale Kopplung)
- [ ] Automatischer Befundbericht (PDF)

## 🔲 M5 — Pseudonymisierungs-Pipeline (Prio 5, vor Kollegen-Rollout)
**Ziel**: Datenschutz-konforme Weiterverarbeitung.

- [ ] CLI-Tool: EDF-Header anonymisieren (Name → Pseudonym, Datum → optional löschen)
- [ ] Audit-Log: Was wurde wann mit welcher Datei gemacht
- [ ] DSGVO-Checkliste für Klinik-Betrieb

## 🔲 M6 — Webapp für Kollegen (Prio 6, Zukunft)
**Ziel**: Skalierbare Lösung für die Abteilung.

- [ ] FastAPI Backend
- [ ] Benutzer-Authentifizierung
- [ ] Datei-Upload mit automatischer Pseudonymisierung
- [ ] Befundberichte speichern + abrufbar

---

# Troubleshooting-Log

| Datum | Problem | Lösung |
|---|---|---|
| 2026-06-15 | EDF mit `utf-8` nicht lesbar | `encoding='latin1'` nötig (NeuroFax schreibt latin1) |
| 2026-06-15 | Samples-per-record = 0 im manuellen Parser | EDF+D format — immer mne verwenden, nicht manuell parsen |
| 2026-06-15 | EKG-Kanäle heißen `$A1`/`$A2`, nicht `EKG` | NeuroFax-spezifische Bezeichnung, Kanal-Mapping dokumentiert |
| 2026-06-15 | EKG-Amplituden ~-12000 mV | DC-Offset aus Kalibrierung — `signal - signal.mean()` vor Analyse |
| 2026-06-15 | R-Peak-Detektion: HR ~48bpm, pNN50=92% unrealistisch | scipy `find_peaks` mit adaptivem Threshold suboptimal — nächster Schritt: Pan-Tompkins-Algorithmus oder Python-3.10 + neurokit2 |
| 2026-06-15 | EKG-Kanal $A1/$A2 zeigt nur Nadelspitzen, kein EKG | $A1/$A2 sind gesättigte Kalibrierkanäle (nur 2 Digitalwerte, digital stuck at min). Echtes EKG in **POL X1** (794 unique Werte, ~0.7 mV, plausible HR). Dynamische Kanal-Erkennung via unique-value-count + HR-Plausibilität eingebaut. |
| 2026-06-15 | POL Pulse/SpO2/EtCO2 alle Null | In dieser EDF-Datei nicht angeschlossen — Vitalparameter-Channels leer. Gerät hat diese Option, war in dieser Aufnahme nicht verwendet. |

---

# Kanal-Mapping (NeuroFax / Neoncode)

| Kanal-Name im EDF | Inhalt | Einheit | Verwendung |
|---|---|---|---|
| `EEG Fp1/2-Ref` bis `EEG Pz-Ref` | Standard 10-20 EEG | µV | EEG-Analyse |
| `EEG A1/A2-Ref` | Ohrelektroden | µV | Referenz |
| `POL $A1`, `POL $A2` | **EKG** (Extremitäten) | mV | Herzanalyse |
| `POL SpO2` | Sauerstoffsättigung | % | Vitalparameter |
| `POL EtCO2` | endtidales CO2 | mmHg | Vitalparameter |
| `POL Pulse` | Puls (Referenz) | bpm | HF-Validierung |
| `POL CO2Wave` | CO2-Kurve | — | Atemrhythmus |
| `POL X1–X7` | Konfigurierbar | — | Gerätespezifisch |
| `POL E` | Erdung/Referenz | — | Technik |
| `POL PG1/2`, `T1/2` | Polygraphie-Zusatz | — | Erweiterung |
