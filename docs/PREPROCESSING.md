# Vorverarbeitung — was mit dem Signal geschieht, bevor eine Zahl entsteht

Zwischen der EDF-Datei und einem ausgegebenen Kennwert liegen mehrere Schritte: Filter,
Fensterwahl, Artefaktbehandlung, Umtastung. Sie standen bisher nirgends zusammenhängend —
über ein Dutzend Filteraufrufe verteilten sich über `analysis/` und `views/`, jeder für sich
kommentiert, aber ohne Gesamtbild. Wer einen Wert nachrechnen wollte, musste den Code lesen.

Dieses Dokument ist **aus dem Code abgeleitet**, nicht aus der Absicht. Wo Code und Erwartung
auseinandergingen, steht das ausdrücklich dabei (Abschnitt „Befunde beim Erstellen").

Stand: 2026-08-12 · Geprüft gegen Commit `d2a26f7`

---

## Der Grundsatz: Anzeige und Analyse sind getrennt

Das Wichtigste vorweg, weil es die häufigste Fehlannahme ist:

> **Die Filtereinstellungen im EEG-Viewer haben KEINEN Einfluss auf die berechneten
> Kennwerte.** Sie verändern ausschließlich die dargestellte Kurve.

Wer im Viewer auf 0,5–70 Hz stellt und danach das Spektrum betrachtet, sieht ein Spektrum,
das weiterhin auf dem 1-Hz-hochpassgefilterten Signal beruht. Das ist beabsichtigt —
Kennwerte sollen nicht davon abhängen, wie jemand gerade die Darstellung eingestellt hat —
aber es muss man wissen.

| Pfad | Funktion | Filter | Wirkt auf |
|---|---|---|---|
| **Anzeige** EEG | `core.shared.get_filtered_eeg` | Butterworth 4. Ordnung, Bandpass, **vom Nutzer wählbar** | nur die Viewer-Kurve |
| **Anzeige** EKG | `core.shared.load_and_prepare` → `ecg_filtered` | Butterworth 4. Ordnung, 0,5–40 Hz | nur die dargestellte EKG-Kurve |
| **Analyse** EEG | `analysis.spectral._highpass` | Butterworth 4. Ordnung, Hochpass 1 Hz | alle EEG-Kennwerte |
| **Analyse** EKG | `analysis.ecg.detect_r_peaks` | Butterworth 2. Ordnung, 5–15 Hz (nur intern) | R-Zacken → alles HRV |

Alle Filter laufen als **`filtfilt`**, also vorwärts und rückwärts. Das verdoppelt die
effektive Ordnung und ist **nullphasig**: es entsteht keine Zeitverschiebung, was für die
Lage der R-Zacken und die Zuordnung von Artefaktzeiten entscheidend ist.

---

## Vor allem anderen: Strukturprüfung der Datei

Bevor irgendetwas geladen wird, prüft `core/edf_validation.py` allein die Header — ohne die
Datei zu lesen. Abgelehnt wird, was nicht analysierbar ist: keine EDF (umbenannte Fremddatei,
BDF), beschädigter oder in sich widersprüchlicher Header, **weniger Daten als der Header
ankündigt** und Aufnahmen unter 10 s.

Der dritte Fall ist der wichtigste, weil er als einziger vorher gar nicht auffiel: eine
abgeschnitten übertragene Datei lädt MNE klaglos als kürzere Aufnahme (nachgemessen: eine
halbierte 600-s-Datei wird zu 299 s), und die Analyse rechnet auf dem Bruchstück weiter.

Nur gewarnt — nicht abgelehnt — wird bei Aufnahmen unter 5 Minuten (HRV-Frequenzdomäne bleibt
möglicherweise leer) und bei Abtastraten unter 100 Hz. Die App ist ein Forschungswerkzeug,
kein Torwächter: ungewöhnlich ist nicht unbrauchbar.

## EEG — der Weg zu einem Spektralwert

### 1. Laden und Kanalzuordnung

`core.shared.load_and_prepare` liest die Datei über MNE. **Die Signalmatrix `edf["data"]`
steht in Volt**, nicht in Mikrovolt; jede Analysestelle multipliziert selbst mit `1e6`. Es
findet **keine** Umtastung und **keine** Re-Referenzierung statt — gerechnet wird auf der
Referenz, mit der aufgezeichnet wurde.

Welcher Kanal EEG ist, entscheidet ein signalbasierter Klassifizierer
(`core.channel_classifier`), nicht der Kanalname. Er prüft dazu unter anderem
bandgefilterte Varianten des Signals (Butterworth 4. Ordnung) — diese Filterung dient
ausschließlich der Erkennung und wird nicht weitergereicht.

### 2. Hochpass 1 Hz

```
analysis/spectral.py::_highpass    butter(4, 1.0 Hz, "high") + filtfilt
```

Entfernt Grundlinienschwankungen (Schwitzen, Elektrodendrift, langsame Bewegung). Dieselbe
Vorschrift, an drei Stellen unabhängig implementiert, aber mit identischen Parametern:
`analysis/spectral.py`, `analysis/glory_report.py::_hp`, `analysis/artifacts.py::_highpass`
(dort über `ArtifactParams.hp_hz`, Default 1,0).

**Folge für die Auslegung:** Aktivität unter 1 Hz wird gedämpft. Delta wird ab 1 Hz
gerechnet, nicht ab 0,5 Hz — sehr langsame Delta-Aktivität (schwere Enzephalopathie, Koma)
liegt damit teilweise unterhalb des Analysebands. Einzige Ausnahme: die **Dominanzbestimmung**
in `_dominant_band_peak` setzt die Delta-Untergrenze bewusst auf 0,5 Hz, damit sich ein sehr
langsames Delta von einem 1,5–2-Hz-Delta unterscheiden lässt.

### 3. Wahl des Analysefensters

Nicht die ganze Aufnahme wird gemittelt. `analysis.glory_report._best_alpha_window` sucht
das **saubere 60-s-Fenster mit dem klarsten posterioren Alpha-Grundrhythmus** — also das,
was klinisch als Grundrhythmus beurteilt wird (entspannte Wachheit), statt über
Augen-auf-/Wachheitswechsel hinwegzumitteln.

Dasselbe Fenster nutzen Hauptseite, Tabellen-Report und visueller Report. Das war nicht
immer so: der Tabellen-Report verwendete früher ein blindes „Mitte 5 Minuten"-Fenster und
lieferte für dieselbe Aufnahme abweichende PAR-Werte — gefunden im Cross-Report-Abgleich
2026-08-09.

Findet sich kein sauberes Fenster, fällt die Wahl auf die mittleren 5 Minuten.

### 4. Leistungsspektrum

```
analysis/spectral.py::_compute_psd
  Epochen 4 s (nperseg = min(4·fs, len/2, 1024)), 50 % Überlapp
  Fenster Hann · Mittelwertabzug je Epoche (detrend constant)
  Skalierung Density (einseitig, ×2 außer DC und Nyquist)
  Ausgabeband 1–30 Hz (FREQ_MAX)
  optional: Multitaper (DPSS, NW=3, K=5) statt Welch
  optional: Epochen mit ptp > amp_thresh_uv werden VERWORFEN, nicht interpoliert
```

Die Verwerfen-statt-Interpolieren-Entscheidung ist bewusst: eine lineare Brücke über eine
Artefaktepoche erzeugt Steigungssprünge und damit spektrales Splatter. Bleibt keine saubere
Epoche übrig, wird ausnahmsweise über alle gemittelt — sonst gäbe es gar kein Spektrum.

Für den **aperiodischen Fit** wird ein zweites Spektrum gerechnet
(`analysis.aperiodic.welch_psd`, bis 45 Hz), weil der 1/f-Fit über die klinischen Bänder
hinausreichen muss.

### 5. Was daraus abgeleitet wird

| Kennwert | Rechenweg | Besonderheit |
|---|---|---|
| Bandpower | Trapezintegral über das Band | Delta ab **1 Hz** (s. o.) |
| relative Power | Band / Summe der vier Bänder | |
| Alpha-Peak (Default) | Schwerpunkt 8–13 Hz nach Abzug einer **linearen Baseline** zwischen den Bandrändern | verhindert, dass die Theta-Flanke den Schwerpunkt nach unten zieht |
| SEF95 / Medianfrequenz | kumulierte Leistung mit linearer Bin-Interpolation | über das Ausgabeband 1–30 Hz |
| 1/f-Exponent | Sigma-Clip-Log-Log-Fit, **kein Knee** | über 1–20 bzw. 1–40 Hz |
| Asymmetrie-Index | (L−R)/(L+R)·100 auf der **Leistung** | nicht auf der Amplitude |
| LZC | am Median binarisiert, **auf 128 Hz umgetastet**, ≤ 8 Segmente à 5 s, 20 Surrogate | Umtastung nur hier, aus Laufzeitgründen |
| Sample Entropy | m=2, r=0,2·SD, zentrales Segment ≤ 4000 Punkte | |

---

## EKG und HRV — der Weg zu einem Variabilitätswert

### 1. Polarität vor Detektion

Zuerst wird entschieden, ob der Kanal invertiert ist (`detect_polarity_flip`), **auf dem
ungefilterten Signal**, und zwar bevor die Peaks verfeinert werden. Die Reihenfolge ist
nicht beliebig: wird erst verfeinert und dann gespiegelt, springt die Verfeinerung bei
invertiertem Kanal auf einen Nebenpunkt statt auf die R-Zacke — das erzeugt *strukturierte*
Zeitfehler und damit sichtbare Streifen im Tachogramm.

Wie sehr das zählt, zeigt der Engzee-Detektor: auf dem rohen Signal findet er 7 Schläge,
nach der Polaritätskorrektur 678 (`tests/test_ecg_pipeline.py`).

### 2. R-Zacken-Erkennung

```
analysis/ecg.py::detect_r_peaks   (vereinfachtes Pan-Tompkins)
  Bandpass 5–15 Hz (butter Ordnung 2, filtfilt)
  → Differentiation → Quadrierung
  → gleitende Integration über 150 ms
  → adaptive Schwelle
  → Verfeinerung ±40 ms auf dem Originalsignal
```

**Kein 0,5–40-Hz-Vorfilter.** Der Bandpass 5–15 Hz innerhalb des Detektors ist die einzige
Filterung auf diesem Pfad (siehe „Befunde" unten).

### 3. RR-Reihe und Bereinigung

`analysis.ecg.build_rr_series`, dreistufig:

1. **physiologisch implausibel** — RR < 300 ms oder > 2000 ms
2. **ektope Schläge** — Abweichung > 20 % vom gleitenden Median (Fenster 5)
3. **Signalausfall** — drei identische aufeinanderfolgende RR-Werte

Markierte Intervalle werden **maskiert, nicht ersetzt** — es wird kein Wert interpoliert, der
dann wie eine Messung aussähe.

### 4. Zeit- und Frequenzbereich

Der Zeitbereich rechnet direkt auf der bereinigten RR-Reihe. **Alle Rückgabewerte sind auf
0,1 ms gerundet** — wer daraus weiterrechnet, erbt bei kleiner Variabilität einige Prozent
Fehler.

Der Frequenzbereich braucht ein gleichmäßiges Raster:

```
analysis/hrv_freq.py::resample_rr    PCHIP-Interpolation auf 4 Hz, Mittelwert abgezogen
  Bänder  VLF 0,0033–0,04 · LF 0,04–0,15 · HF 0,15–0,40 Hz   (Task Force 1996)
  Schätzer Welch und Burg (Ordnung 16)
```

PCHIP statt kubischem Spline, weil PCHIP **nicht überschwingt**: über entfernten Schlägen
und langen Lücken erfindet ein kubischer Spline Oszillationen, die genau im LF/HF-Bereich
liegen und das Ergebnis verfälschen.

Zusätzlich steht **Lomb-Scargle** zur Verfügung, das ganz ohne Umtastung direkt aus den
Schlagzeitpunkten rechnet — der sauberere Weg bei Lücken; beide Verfahren treffen auf der
Fixture dieselbe RSA-Frequenz.

### 5. Weitere EKG-Pfade mit eigenen Filtern

| Zweck | Filter | Modul |
|---|---|---|
| P-Wellen-Nachweis | 0,5–30 Hz, Ordnung 2 | `analysis/p_wave_analysis.py` |
| Ektopie (QRS-Breite) | 5–15 Hz, Ordnung 2 | `analysis/ectopy_detection.py` |
| Atmungssignal (EDR) | Atemband, Ordnung 2 | `analysis/ecg.py` |
| Darstellung | 0,5–40 Hz, Ordnung 4 | `core/shared.py`, `views/ecg_hrv.py` |

---

## Artefaktmarkierung

```
analysis/artifacts.py
  Hochpass 1 Hz → Fenster 1 s, 50 % Überlapp
  je Kanal Spitze-Tal gegen die EIGENE Baseline (Median über die Aufnahme)
  „heiß" ab 4× Baseline · regionsabhängig: Fp ×2,0 · F7/F8 ×1,4 · T3/T4 ×1,2 · sonst ×1,0
  Artefakt, wenn ≥ 3 Kanäle heiß UND ≥ 1 davon nicht-frontal
  Sicherheitsrand 0,5 s · saubere Inseln < 5 s werden absorbiert
  EKG bestätigt zusätzlich (Amplitude > 2,5× Baseline im Segment)
```

Zwei Entscheidungen sind erklärungsbedürftig:

**Eigene Baseline statt fester µV-Schwelle.** Ein Kind mit 120 µV Grundaktivität und ein
sedierter Patient mit 15 µV bekämen sonst völlig unterschiedliche Empfindlichkeiten.

**Die Nicht-frontal-Bedingung filtert Blinzeln heraus.** Ein Lidschlag ist frontal groß und
posterior praktisch nicht vorhanden — er ist ein *Signal*, kein Störer, und soll die
Analyse nicht verkleinern. Eine echte Bewegung erfasst auch nicht-frontale Kanäle.

Die Maske entfernt Zeit **sample-genau** aus der korrigierten Auswertung; Gesamt- und
korrigierte Rechnung laufen parallel nebeneinander, nichts wird stillschweigend ersetzt.

---

## Befunde beim Erstellen dieses Dokuments

Das Ableiten aus dem Code hat drei Dinge zutage gefördert, die vorher niemandem auffallen
konnten — genau deshalb entsteht so ein Dokument aus dem Code und nicht aus der Erinnerung.

### 1. Eine tote, abweichende EKG-Pipeline — ✅ entfernt

`analysis/ecg.py` enthielt `run_ecg_analysis()`, das `preprocess_ecg()` (Bandpass 0,5–40 Hz)
auf das Signal anwendete, **bevor** es die R-Zacken suchte, und den Frequenzbereich über
`compute_hrv_frequency_domain()` rechnete. **Diese Funktion rief niemand auf** — und die
anderen ausschließlich sie. Wer die Datei von oben las, musste schließen, die EKG-Kette
beginne mit einem 0,5–40-Hz-Filter. Sie tut es nicht.

Am 2026-08-12 gelöscht (74 Zeilen), mit einer Notiz an ihrer Stelle. Der Code zeigt jetzt nur
noch einen EKG-Weg — den oben beschriebenen.

### 2. Zwei Welch-Implementierungen — nachgemessen gleichwertig

Für das EEG-Spektrum existieren zwei getrennte Implementierungen: die eigene, epochenweise
in `views/eeg_spectrum._compute_psd` (mit `np.hanning`, also dem **symmetrischen** Fenster)
und `scipy.signal.welch` in `views/report._compute_bandpower` und
`analysis.aperiodic.welch_psd` (mit dem **periodischen** Hann-Fenster).

Der Fensterunterschied ist real (Energie 299,6 gegen 300,0), aber er kürzt sich in der
Normierung heraus: auf der Fixture stimmen Alpha-Power, Alpha-Schwerpunkt und SEF95 der
beiden Wege auf sechs Stellen überein. **Kein Handlungsbedarf** — festgehalten, damit die
Frage nicht ein zweites Mal untersucht werden muss.

Ein echter Unterschied bleibt: nur `_compute_psd` kann Artefaktepochen verwerfen. Bei
aktiver Amplitudenschwelle liefern die beiden Wege daher zu Recht verschiedene Werte.

### 3. Delta beginnt bei 1 Hz, nicht bei 0,5 Hz — bewusst

Die verbreitetste Delta-Definition in der Literatur ist 0,5–4 Hz, und klinische Hochpässe
liegen üblicherweise zwischen 0,5 und 1,0 Hz. Diese Anwendung nutzt bewusst die obere
Variante. **Entscheidung getroffen am 2026-08-12 nach Recherche und Messung — nicht offen.**

**Warum nicht 0,5 Hz:** Unterhalb 1 Hz liegt der spektrale Gipfel der langsamen Störungen,
die man in einem Routine-EEG nicht loswird — Schwitzartefakte, Elektrodendrift, langsame
Bewegung, Wackeln am Kabel. Sie kontaminieren genau Delta und Theta. Der 1-Hz-Hochpass hält
sie draußen. Das kostet echtes langsames Delta, und dieser Preis wird hier absichtlich
gezahlt: eine Verlangsamung, die nur aus Schweiß besteht, ist schlimmer als eine, die man
etwas zu schwach misst.

**Was es kostet (gemessen an einem simulierten 1/f^1,8-EEG mit Alpha):**

| | |
|---|---|
| Anteil von 0,5–1 Hz an der wahren Delta-Leistung | 47 % |
| heute erfasster Anteil des wahren 0,5–4-Hz-Bandes | 37 % |
| Delta bei Umstellung auf 0,5 Hz | +121 % |
| Delta/Alpha-Ratio bei Umstellung | +121 % |

Delta würde sich also mehr als verdoppeln — bei einem 1/f-Spektrum sitzt der Großteil der
Leistung unten, die halbe Oktave 0,5–1 Hz trägt fast so viel wie die zwei Oktaven darüber.

**Was eine Umstellung zusätzlich erfordern würde** (dokumentiert, damit niemand sie für einen
Einzeiler hält):

1. **Drei Codestellen, nicht eine**: die Hochpass-Grenzfrequenz, die Ausgabemaske in
   `_compute_psd` (`freqs >= 1.0`) und die `BANDS`-Definition. Nur das Band zu ändern ist
   exakt wirkungslos — nachgemessen: +0,0 %.
2. **Der Artefaktdetektor müsste mit**: er filtert selbst bei 1 Hz
   (`ArtifactParams.hp_hz`) und sähe die Drift gar nicht, die neu in Delta fiele. Die
   Spektralanalyse zählte sie dann als Verlangsamung, während der Detektor das Segment für
   sauber hielte.
3. **Alle Delta-abhängigen Normschwellen wären ungültig** (DAR, DTABR, „Verlangsamung") —
   sie wurden gegen die heutige Definition gesetzt und müssten neu abgeleitet werden.

**Was man dabei wissen sollte:** Auch im heutigen Zustand dämpft der Hochpass die untere
Delta-Flanke — bei 1,0 Hz kommen nur 50 % der Amplitude durch (Butterworth 4. Ordnung,
durch `filtfilt` effektiv 8.). Vom Band 1–4 Hz werden dadurch rund 82 % erfasst. Das ist bei
einem Vergleich mit Fremdsystemen zu bedenken, die anders filtern.

**Eine verbliebene Inkonsistenz, bewusst nicht angeglichen:** `core/channel_classifier.py`
nutzt für sein Merkmal `delta_rel` bereits 0,5–4 Hz. Das ist dort unkritisch — es dient der
KANALERKENNUNG (EEG oder nicht), nicht der klinischen Bandpower, und profitiert eher davon,
tiefe Frequenzen zu sehen. Eine Angleichung würde die Kanalerkennung ändern, ohne einen
Vorteil zu bringen.

---

## Was hier bewusst NICHT steht

Keine Empfehlungen, keine Normwerte, keine Deutung. Nur der Rechenweg. Was die Zahlen
bedeuten und wie gut sie belegt sind, steht in der Methoden-Registry
(`analysis/methods.py`, in der App unter „Erweiterte Analysen & Methodik") und in den
READMEs.
