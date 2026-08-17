# Validierung: Referenzwerte und Benchmarks

Wie gut das EKG-seitige Screening dieser Anwendung tatsächlich arbeitet, gegen öffentliche,
von Fachleuten annotierte Referenzdatenbanken gemessen — nicht behauptet.

Vier Fragen, vier Protokolle, vier Auswertungen. **Jedes Protokoll wurde vor der ersten
Messung geschrieben** und legt Datenquelle, Goldstandard, Kennzahlen und Ausschlussregeln vorab
fest — so lässt sich eine Schwelle im Nachhinein nicht mehr passend zurechtbiegen. Diese Seite
fasst zusammen; jede Einzelheit, jeder Fallstrick und jede Kennzahl steht in den verlinkten
Protokollen, jedes Zwischenergebnis als CSV im Repository.

| # | Frage | Protokoll |
|---|---|---|
| 1 | Wie gut findet der Detektor R-Zacken? | [BENCHMARK_QRS.md](BENCHMARK_QRS.md) |
| 2 | Was macht ein Detektionsfehler mit den HRV-Zahlen? | [BENCHMARK_HRV.md](BENCHMARK_HRV.md) |
| 3 | Wie gut erkennt CosEn Vorhofflimmern? | [BENCHMARK_AFIB.md](BENCHMARK_AFIB.md) |
| 4 | Trägt die P-Wellen-Stufe, und hilft sie CosEn? | [BENCHMARK_PWAVE.md](BENCHMARK_PWAVE.md) + Schritt 3/4 in BENCHMARK_AFIB.md |

> **Bevor du startest: Umfang und Downloadzeit.** Zum Nachrechnen werden **rund 1,8 GB** von
> PhysioNet geladen (nicht Teil dieses Repos, siehe unten). Bei 20–50 MBit/s sind das grob
> 5–15 Minuten, bei 500 MBit/s+ unter zwei Minuten — **in der eigenen Erfahrung dauerte allein
> die 640-MB-AFib-Datenbank über eine halbe Stunde**, weil PhysioNets Server selbst oft der
> Flaschenhals sind, nicht die eigene Leitung. Wer nur die Ergebnisse lesen will, braucht
> nichts davon herunterzuladen — jedes einzelne Zwischenergebnis liegt bereits als CSV in
> [`benchmarks/results/`](../benchmarks/results/).

## 1 · Datensätze — was tatsächlich geprüft wurde

**Kein Datensatz stammt von uns.** Alle drei sind seit Jahrzehnten öffentliche
Referenzdatenbanken bei [PhysioNet](https://physionet.org), an denen sich publizierte QRS- und
AFib-Detektoren üblicherweise messen lassen — der Vergleich ist damit nicht nur intern, sondern
gegen den Stand des Feldes möglich. Alle drei stehen unter der
[Open Data Commons Attribution License v1.0](https://physionet.org/content/mitdb/view-license/1.0.0/)
(ODC-BY): frei nutzbar, mit Pflicht zur Namensnennung.

| Datensatz | Aufnahmen | Umfang | Abtastrate | Goldstandard |
|---|---|---|---|---|
| [**MIT-BIH Arrhythmia Database**](https://doi.org/10.13026/C2F305) | 44 von 48¹ | 100.932 Schläge | 360 Hz | R-Zacken einzeln kardiologisch annotiert |
| [**MIT-BIH Atrial Fibrillation Database**](https://doi.org/10.13026/C2MW2D) | 23 von 25² | 234 Stunden | 250 Hz | Rhythmus-Intervalle (`AFIB`/`N`/`AFL`/`J`) von den Datenbankautoren |
| [**MIT-BIH Normal Sinus Rhythm Database**](https://doi.org/10.13026/C2NK5R) | 18 von 18 | 459 Stunden | 128 Hz | gesunde Probanden, keine dokumentierte Arrhythmie |

¹ 4 Aufnahmen mit Herzschrittmacher nach ANSI/AAMI EC57 ausgeschlossen (Konvention, nicht
unsere Wahl). ² 2 Aufnahmen ohne Signaldatei auf PhysioNet, nur Annotationen — nichts zu
detektieren.

<details>
<summary><strong>Empfohlene Zitierweise</strong> (nach Angabe der jeweiligen PhysioNet-Seite)</summary>

Jede Datenbank nennt zwei Zitate: die Originalpublikation und die PhysioNet-Plattform selbst.

**MIT-BIH Arrhythmia Database**
> Moody GB, Mark RG. *The impact of the MIT-BIH Arrhythmia Database.* IEEE Eng in Med and Biol 20(3):45–50 (May–June 2001).

**MIT-BIH Atrial Fibrillation Database**
> Moody GB, Mark RG. *A new method for detecting atrial fibrillation using R-R intervals.* Computers in Cardiology 10:227–230 (1983).

**MIT-BIH Normal Sinus Rhythm Database**
> beitragende Autoren: Ary L. Goldberger, MIT Laboratory for Computational Physiology — kein eigener Zeitschriftenartikel, zitiert wird nur die PhysioNet-Plattform.

**Alle drei Datenbanken zusätzlich, wie von PhysioNet empfohlen:**
> Pollard T, Moody BE, Lehman L, Gow B, Fernandes C, Xie C, Johnson A, Mark RG, Heldt T. *PhysioNet as a global platform for biomedical research.* Nature Health (2026).

</details>

## 2 · Bewertungsebenen

Dieselben Daten wurden auf drei unterschiedlich feinen Ebenen ausgewertet, weil jede eine
andere Frage beantwortet:

| Ebene | Einheit | Beantwortet |
|---|---|---|
| **Sample/Zeitachse** | einzelne R-Zacke, ±150 ms Toleranz (ANSI/AAMI EC57) | Wird jeder Herzschlag an der richtigen Stelle gefunden? |
| **Fenster** | 30 Sekunden (HRV) oder 10 Minuten (QRS-Kennzahlen) | Wie gut ist ein Kennwert über einen klinisch sinnvollen Ausschnitt? |
| **Patient/Abschnitt** | 10/20/30 Minuten, ein Verdikt je Abschnitt | Was bekäme ein Anwender tatsächlich zu sehen? |

Die dritte Ebene wurde erst nachträglich ergänzt (Betreiber-Hinweis 14.08.2026): Vorhofflimmern
ist klinisch eine Patienten-, keine Fensterdiagnose, und die Anwendung meldet Verdacht bereits,
sobald ein einziges Fenster anschlägt. Ohne diese Ebene wäre die aussagekräftigste Zahl gar
nicht gemessen worden.

## 3 · Ergebnisse im Überblick

### R-Zacken-Detektion (Sample-Ebene, 44 Aufnahmen, 100.932 Schläge)

| Kennzahl | Wert |
|---|---|
| Sensitivität | 95,53 % |
| positiver Vorhersagewert | 99,93 % |
| mittlerer Zeitfehler (Aufnahmen mit engster Genauigkeit) | 1,1–1,3 ms |

**Bewertung:** Der Detektor ist konservativ — er erfindet praktisch nie einen Schlag
(99,93 % Vorhersagewert), übersieht aber in manchen Aufnahmen mehr, als aktuelle publizierte
Detektoren es täten (Chunk-4-Vergleich mit Hamilton: fast gleiches F1, entgegengesetztes
Fehlerprofil — Hamilton erfindet, unser Detektor übersieht). Für ein HRV-Werkzeug ist das die
richtige Seite des Fehlers: Ein übersehener Schlag verlängert ein Intervall, ein erfundener
zerreißt zwei. Eine gemessene, nicht umgesetzte Verbesserung (blockweise statt globaler
Schwelle) läge bei 97,4 % Sensitivität zu praktisch gleichem Vorhersagewert.

### HRV-Fehlerfortpflanzung (Fenster-Ebene, dieselben 44 Aufnahmen)

| Gruppe | Median-Fehler ΔSDNN | Median-Fehler ΔRMSSD |
|---|---|---|
| sinusnah (≤ 5 % nicht-normale Schläge) | −0,05 ms | 0,1 ms |
| arrhythmisch | 3,7 ms | 0,85 ms |

**Bewertung:** Für den Regelfall — unauffälliger Rhythmus, das Einsatzfeld dieser Anwendung —
ist der Fehler nicht von der Anzeigegenauigkeit zu unterscheiden. Der Ausreißerfilter der
Anwendung fängt den größten Teil der Detektionslücke ab. Eine Ausnahme wurde gefunden und ist
namentlich dokumentiert: Sensitivität ist das falsche Gütemaß für HRV, ausschlaggebend ist die
**Zeitgenauigkeit** der Detektion (r = +0,57 zu |ΔRMSSD|, gegenüber nur r = −0,42 für
Sensitivität). Die Anwendung weist diese Größe bisher nicht aus — offener Punkt.

### AFib-Screening, CosEn (Fenster-Ebene, 23 Aufnahmen, 26.652 Fenster)

| Kennzahl | Wert |
|---|---|
| Sensitivität | 75,26 % |
| Spezifität | 99,70 % |

**Bewertung:** Auf Fensterebene spezifisch, mittelmäßig sensitiv. Zwei Durchläufe (eigener
Detektor gegen Referenzschläge der Datenbank) zeigen: **nicht der Detektor begrenzt** —
CosEn bzw. seine Schwelle tut es. Die verpassten AFib-Fenster liegen dicht unter der Schwelle
(Median CosEn −1,00 bei Schwelle −0,8), nicht weit entfernt in einer anderen Verteilung.

### AFib-Screening, P-Wellen-Kohärenz (Fenster-Ebene, dieselben 23 Aufnahmen + 18 gesunde)

| Kennzahl | CosEn | P-Welle |
|---|---|---|
| Sensitivität (AFib-Fenster) | 75,26 % | 47,51 % |
| Spezifität (Nicht-AFib-Fenster, afdb) | 99,70 % | 99,72 % |
| Spezifität (459 h gesunde Probanden) | 98,26 % | **99,98 %** |

**Bewertung:** Auf reiner Fensterebene liegt CosEn bei der Sensitivität vorn — dieses Bild
kehrt sich auf Patientenebene um (siehe unten), weil die Aggregationsregel der Anwendung
("ein Fenster genügt") die beiden Verfahren unterschiedlich behandelt.

### AFib-Screening auf Patientenebene (20-Minuten-Abschnitte — die Dauer der Anwendung)

**Das ist die klinisch aussagekräftigste Tabelle dieser gesamten Validierung.**

| Verfahren | Sensitivität | Spezifität, gesund | Spezifität, AFib-Pat. ohne Episode |
|---|---|---|---|
| CosEn allein (heutiges Verfahren) | **96,87 %** | 85,96 % | 97,07 % |
| P-Welle allein | 89,97 % | 99,39 % | 96,48 % |
| CosEn ODER P-Welle | 97,49 % | 85,35 % | 93,84 % |
| **CosEn UND P-Welle (Screen-then-Confirm)** | 89,34 % | **100,00 %** | **99,71 %** |

**Bewertung:**

* **Das heutige Verfahren nutzt den paroxysmalen Charakter von Vorhofflimmern richtig aus** —
  „ein Fenster genügt" hebt die Sensitivität auf 96,9 %. Der Preis: rund **jeder siebte**
  gesunde 20-Minuten-Abschnitt löst einen Fehlalarm aus.
* **Die einfache Kombination (ODER) hilft nicht.** CosEns und der P-Welle Fehlalarme
  überschneiden sich in keinem einzigen der 167 geprüften Fälle — eine ODER-Verknüpfung erbt
  beide Fehlerquellen, statt sie auszugleichen.
* **Die Reihenfolge UND (Screen-then-Confirm) ist der einzige gemessene Weg, der beide Ziele
  gleichzeitig verbessert** gegenüber mindestens einem der Einzelverfahren: gegenüber CosEn
  gewinnt sie 14 Punkte Spezifität bei 7,5 Punkten weniger Sensitivität; gegenüber der P-Welle
  allein verliert sie fast nichts an Sensitivität und gewinnt zusätzlich Spezifität. Das ist
  genau das von Ihnen beschriebene Muster — sensitiver Test zuerst, spezifischer Test
  bestätigt — und es funktioniert hier, weil die beiden Verfahren an unterschiedlichen
  Stellen versagen.

## 4 · Zusammenfassende Einordnung

**Die Anwendung schneidet insgesamt solide ab, mit einer benannten Lücke und einer benannten
Verbesserungsmöglichkeit je Baustein:**

| Baustein | Status | offener Punkt |
|---|---|---|
| R-Zacken-Detektion | gut belegt, konservativ (richtige Fehlerrichtung für HRV) | globale statt blockweise Schwelle |
| HRV-Zeitdomäne | für den Regelfall verlässlich | Zeitgenauigkeit wird nicht ausgewiesen |
| AFib-Screening | spezifisch auf Fensterebene, aber die Patientenebene zeigt eine Fehlalarmquote, die der Betreiber so nicht kannte | Schwelle sitzt am Rand der AFib-Verteilung statt in der Mitte; Screen-then-Confirm ungenutzt |

Kein Baustein hat sich in dieser Validierung als grundlegend fehlerhaft erwiesen. Jede
gefundene Schwäche ist **beziffert**, jede geprüfte Abhilfe ist **gemessen**, und keine ist
**umgesetzt worden**, ohne dass der Betreiber es entschieden hat — Verfahrensänderungen
verändern jede Ausgabe der Anwendung und sind deshalb keine Aufräumarbeit, sondern fachliche
Entscheidungen.

## 5 · Was bewusst nicht geprüft wurde

* **Frequenzdomäne (LF/HF), DFA, Sample Entropy, Ektopie-Erkennung als eigenes Verfahren** —
  jeweils eigene Wahrheit nötig, nicht Teil dieser vier Protokolle.
* **Klinische Validität.** Alle Zahlen sind Übereinstimmung mit einer Referenzannotation, keine
  Aussage über den Nutzen am Patienten.
* **Repräsentativität für eine neurologische Routineambulanz.** Die Referenzdatenbanken sind
  Langzeit-EKG (10–25 h) bei Kardiologiepatienten bzw. gesunden Probanden, nicht 20-Minuten-EEG
  mit mitlaufendem EKG. Wo das die Übertragbarkeit einschränkt, steht es im jeweiligen
  Protokoll.

## Reproduzierbarkeit

Jede Zahl auf dieser Seite lässt sich nachrechnen — die Daten liegen bewusst nicht im
Repository, sondern werden von PhysioNet direkt bezogen:

| Datensatz | Größe | bei 20–50 MBit/s | eigene Erfahrung |
|---|---|---|---|
| MIT-BIH Arrhythmia | ~500 MB | ~2–4 min | — |
| MIT-BIH AFib | ~640 MB | ~2–5 min | **über 30 min** (PhysioNet-seitig gebremst) |
| MIT-BIH Normal Sinus | ~630 MB | ~2–5 min | ~20–30 min |
| **zusammen** | **~1,8 GB** | **~6–14 min** | **eher 45–90 min** |

    pip install -r requirements-benchmark.txt
    python3 benchmarks/fetch_mitdb.py --all      # MIT-BIH Arrhythmia,  ~500 MB, s. Tabelle oben
    python3 benchmarks/fetch_afdb.py --all       # MIT-BIH AFib,        ~640 MB, s. Tabelle oben
    python3 benchmarks/fetch_nsrdb.py --all      # MIT-BIH Normal Sinus,~630 MB, s. Tabelle oben

    python3 benchmarks/run_qrs.py --all --csv benchmarks/results/chunk5_alle44_eigen.csv
    python3 benchmarks/run_hrv.py --all --csv benchmarks/results/hrv_alle44.csv
    python3 benchmarks/run_afib.py --all --csv benchmarks/results/afib_alle23_eigen.csv
    python3 benchmarks/run_pwave.py --all
    python3 benchmarks/run_nsrdb.py --all
    python3 benchmarks/run_patient.py --csv benchmarks/results/patient_ebene.csv

Alle Zwischenergebnisse — jedes einzelne Fenster, nicht nur die Zusammenfassungen — liegen als
CSV in [`benchmarks/results/`](../benchmarks/results/) und sind Teil des Repositorys.
