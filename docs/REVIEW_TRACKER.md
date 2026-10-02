# Review-Tracker und To-do-Liste

Eine Stelle für alle Reviews, ihre Befunde und den Stand jedes Punkts. Details stehen im
`CHANGELOG.md`, hier nur Status und Verweis. Jeder Befund wurde vor der Übernahme im Code
nachgeprüft; was sich nicht bestätigte, steht unter „Nicht übernommen".

Status: ✅ erledigt · 🔧 in Arbeit · ⬜ offen · ⏸ bewusst zurückgestellt · ✖ abgelehnt

## 1. Reviews

| Kürzel | Datum | Art | Schwerpunkt |
|---|---|---|---|
| R1 | 11.08.2026 | extern | Gesamtbewertung, Weg zu „klinisch validiert" |
| R2 | 12.08.2026 | extern | Code. Teilweise auf einem veralteten Stand, nur Bestätigtes übernommen |
| R3 | 12.08.2026 | extern | Architektur: Engine/UI trennen, Provenance je Wert |
| R4 | 01.10.2026 | extern | Performance und Pitfalls (P0 Cache-Verwechslung) |
| R5 | 01.10.2026 | extern | Zweites Performance-Review, bestätigt R4 |
| R6 | 01.10.2026 | extern | Drittes Review: veraltete Exporte, Fehler als „100 % sauber" |
| R7 | 02.10.2026 | extern | EEG-Spektralanalyse: Multitaper, Artefakt-Fallback, Fensterwahl |
| P1 | 02.10.2026 | Literatur | Helfrich et al., PNAS 2026, „Spectral mapping…": Übertragbarkeit |
| U | laufend | Nutzer | Funde beim Testen |

## 2. Offen — nach Priorität

### Priorität 1: Rechenfehler und stille Falschergebnisse

| # | Punkt | Quelle | Status |
|---|---|---|---|
| 1.1 | Multitaper liefert die halbe absolute Leistung (Faktor 2 beim einseitigen Spektrum fehlt). Relative Werte sind nicht betroffen. | R7 | ✅ |
| 1.2 | Keine sauberen Epochen → es wird trotzdem alles verwendet (`spectral._compute_psd`). Richtig wäre „nicht auswertbar". | R7 | ✅ |
| 1.3 | Dasselbe im visuellen Report: `glory_report._clean_concat` nimmt das ganze Signal, wenn alles Artefakt ist. | R7 (eigener Zusatzfund) | ✅ |
| 1.7 | Versteckter Absturz im visuellen Report ohne Alpha-Peak (`None == None`). | eigener Fund 02.10. | ✅ |
| 1.4 | Epochenlänge ist auf 1024 Punkte begrenzt: bei 500 Hz 2,05 s statt der dokumentierten 4 s. Ausweisen oder angleichen. | R7 | ✅ |
| 1.5 | Die Zeitstreuung der R-Zacken-Detektion wird nicht ausgewiesen. MIT-BIH 121: Se 99,9 %, aber RMSSD 20 → 93 ms. | Benchmark HRV | ⬜ |
| 1.6 | Unterscheidbare Ergebniszustände (erfolgreich / zu wenig Daten / nicht verfügbar / fehlgeschlagen) fehlen allgemein. Die Werte werden protokolliert, die Oberfläche zeigt aber keinen Grund. | R4, R6 | ⬜ |
| 1.8 | Visueller Report: Findet sich kein 60-s-Alpha-Fenster, rechnet der A/P-Gradient über die ganze Aufnahme ohne Artefaktmaske, das Spektrum dagegen nur auf den sauberen Abschnitten. | eigener Fund 02.10. | ⬜ |

### Priorität 2: Methodische Aussagekraft

| # | Punkt | Quelle | Status |
|---|---|---|---|
| 2.1 | Zwei Auswertungsziele trennen: „bester Grundrhythmus" (alphastarkes Fenster, wie bisher) und „repräsentativer Verlauf" (mehrere saubere Abschnitte, Schwankung). Im Report kennzeichnen. | R7 | ⬜ |
| 2.2 | Langsames Delta < 1 Hz: eigener, optionaler Pfad. Bandgrenzen nicht einfach verschieben. | R7 | ⬜ |
| 2.3 | Zusätzlicher FOOOF-Fit 25–45 Hz neben dem Breitbandfit. Nicht austauschbar, beide anzeigen. | R7, P1 | ⬜ |
| 2.4 | Interpretation: Exponent nicht als direktes E/I-Maß darstellen; Alpha-Schwerpunkt und Peakfrequenz unterscheiden. | R7 | ⬜ |
| 2.5 | `fooof` ist abgekündigt → `specparam`. Erst die Kennwerte einfrieren und das Vergleichsskript um FOOOF erweitern. | eigener Fund 30.08. | ⬜ |
| 2.6 | Ein gemeinsamer Ergebnisschlüssel für alle Seiten (Datei, Kanalkorrekturen, Parameter). | R4 | ⬜ |
| 2.7 | Herkunftsangaben: Grenzen der Artefaktsegmente und Kanalkorrekturen fehlen im Fingerabdruck. | R4 | ⬜ |
| 2.8 | Provenance je Einzelwert (`AnalysisResult`). | R3 | ⬜ |

### Priorität 3: Performance und Betrieb

| # | Punkt | Quelle | Status |
|---|---|---|---|
| 3.1 | Kanalprüfung langsam: alle Vorschauen werden gebaut, auch zugeklappt. Vorschau erst auf Klick. | U 01.10. | ⬜ |
| 3.2 | RAM ≈ 10× Dateigröße (float64, Kopien). float32 und weniger Kopien, mit Kennwertvergleich. | eigene Messung 01.10. | ⬜ |
| 3.3 | Viewer filtert bei jeder Filteränderung die ganze Aufnahme. | R4 | ⬜ |
| 3.4 | Mehrere Seiten laden die EDF erneut vollständig. | R4 | ⬜ |
| 3.5 | Lock-Datei für Abhängigkeiten. Braucht Freigabe. | R4 | ⬜ |
| 3.6 | Server-Neustart für Kernel-Updates. Termin abstimmen. | R4 | ⬜ |
| 3.7 | Alte Rollback-Images aufräumen. | eigener Fund | ⬜ |

### Priorität 4: Bedienung und Erweiterungen

| # | Punkt | Quelle | Status |
|---|---|---|---|
| 4.1 | EKG & HRV: die vier Analyse-Tabs stehen erst in Zeile ~1500 und werden übersehen. | U 30.08. | ⬜ |
| 4.2 | Ausprobieren ohne eigene EDF: synthetische Fixture mitliefern. | R1 | ⬜ |
| 4.3 | `core/shared.py` schrittweise aufteilen. | R3 | ⬜ |
| 4.4 | Forschungsmodul „Spektrale Zustandsmuster": 19-Kanal-Karten, 10-s-Verlauf, Referenzvergleich, Orthogonalisierung. Klar als Forschung gekennzeichnet, keine Klassifikation. Vorher die Multitaper-Konfiguration des Papers klären (neun Fenster passen zu 5 s, nicht zu 10 s). | P1 | ⬜ |
| 4.5 | `compute_hrv_time_domain` rundet auf 0,1 ms. | eigener Fund 12.08. | ⬜ |

### Zurückgestellt

| # | Punkt | Grund | Status |
|---|---|---|---|
| Z1 | iPhone: Navigation hängt seit Streamlit 1.57 (tornado → uvicorn). Lösung wäre ein Pin auf 1.56. | Erst wenn die Web-Version stabil ist | ⏸ |
| Z2 | `use_container_width` ersetzen | Nur zusammen mit einem gewollten Streamlit-Versionssprung | ⏸ |
| Z3 | Artefaktdetektor gegen echte Pathologie prüfen | Braucht eine echte Aufnahme mit bekanntem Befund | ⏸ |
| Z4 | Manuelle QRS-Korrektur | Mehrere Tage, ganz hinten | ⏸ |

## 3. Erledigt (Auswahl seit 01.10.2026, Details im CHANGELOG)

| Punkt | Quelle | Commit |
|---|---|---|
| Cache-Verwechslung zwischen Patienten (Viewer, Reports) | R4, R5 | c4bfb6f |
| Performance: SampEn/LZC zwischengespeichert, alle Caches begrenzt | R4 | 8817581 |
| Veraltete Exporte, Fehler als „100 % sauber", versteckte Cache-Eingaben | R6 | a7e7d87 |
| Report-HRV nach Kanalkorrektur, 30 stille Fehler protokolliert, README-Validierungsstand | R4, R6 | 90343d7 |
| Ressourcengrenzen des Containers, Upload-Grenze nach Messwerten | R4, eigene Messung | be55b90 |
| Multitaper-Skalierung, Artefakt-Rückfall (2×), Epochenlänge, Absturz ohne Alpha-Peak | R7 | lokal, noch nicht committet |
| Absturz bei sehr kurzen Aufnahmen (EKG & HRV) | U 29.09. | c01ee69 |
| MIT-BIH-Benchmarks (R-Zacken, CosEn, P-Wellen) veröffentlicht | R1 | siehe docs/BENCHMARKS.md |

## 4. Nicht übernommen (mit Begründung, nicht erneut aufwerfen)

- `mypy`/strikte Typisierung: hoher Aufwand, wenig Ertrag; `ruff` deckt das Praktische ab.
- Pydantic für Konfiguration: die Objekte sind bereits Dataclasses.
- BIDS-Support: Format für Studiendatensätze, hier kommen Einzelaufnahmen.
- Deep-Learning-Klassifikatoren: nie geplant.
- Digest-Pin des Basis-Images: friert auch Sicherheitsupdates ein.
- Tieferer Healthcheck: Docker startet einen „unhealthy" Container ohne Orchestrator nicht neu.
- Automatische Schlaf-/Koma-Klassifikation aus P1: ohne unabhängige Validierung nicht vertretbar.
