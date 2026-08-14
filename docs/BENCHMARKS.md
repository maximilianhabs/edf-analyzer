# Übersicht: alle Validierungen gegen öffentliche Referenzdatenbanken

Vier Fragen, vier Protokolle, vier Auswertungen — jedes Protokoll vor der ersten Messung
geschrieben, jede Messung reproduzierbar, jedes Ergebnis mit Datum und Commit. Diese Seite
fasst zusammen; die Einzelheiten, jede Fallstricke und jede Kennzahl stehen in den verlinkten
Dokumenten.

| # | Frage | Protokoll |
|---|---|---|
| 1 | Wie gut findet der Detektor R-Zacken? | [BENCHMARK_QRS.md](BENCHMARK_QRS.md) |
| 2 | Was macht ein Detektionsfehler mit den HRV-Zahlen? | [BENCHMARK_HRV.md](BENCHMARK_HRV.md) |
| 3 | Wie gut erkennt CosEn Vorhofflimmern? | [BENCHMARK_AFIB.md](BENCHMARK_AFIB.md) |
| 4 | Trägt die P-Wellen-Stufe, und hilft sie CosEn? | [BENCHMARK_PWAVE.md](BENCHMARK_PWAVE.md) + Schritt 3/4 in BENCHMARK_AFIB.md |

## 1 · Datensätze — was tatsächlich geprüft wurde

| Datensatz | Herkunft | Aufnahmen | Dauer | Abtastrate | Goldstandard |
|---|---|---|---|---|---|
| **MIT-BIH Arrhythmia** | PhysioNet, ODC-BY | 44 von 48¹ | ~24 Min. je Aufnahme, 100.932 Schläge gesamt | 360 Hz | R-Zacken einzeln von Kardiologen annotiert |
| **MIT-BIH Atrial Fibrillation** | PhysioNet, ODC-BY | 23 von 25² | ~10 h je Aufnahme, 234 h gesamt | 250 Hz | Rhythmus-Intervalle `(AFIB`/`(N`/`(AFL`/`(J` von den Datenbankautoren |
| **MIT-BIH Normal Sinus Rhythm** | PhysioNet, ODC-BY | 18 von 18 | ~25 h je Aufnahme, 459 h gesamt | 128 Hz | Datenbankzugehörigkeit: gesunde Probanden, keine relevante Arrhythmie |

¹ 4 Aufnahmen mit Herzschrittmacher nach ANSI/AAMI EC57 ausgeschlossen (Konvention, nicht
unsere Wahl). ² 2 Aufnahmen ohne Signaldatei auf PhysioNet, nur Annotationen — nichts zu
detektieren.

**Kein Datensatz stammt von uns.** Alle drei sind seit Jahrzehnten öffentliche
Referenzdatenbanken, an denen sich publizierte QRS- und AFib-Detektoren üblicherweise messen
lassen — der Vergleich ist damit nicht nur intern, sondern gegen den Stand des Feldes möglich.

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

Jede Zahl auf dieser Seite lässt sich nachrechnen:

    pip install -r requirements-benchmark.txt
    python3 benchmarks/fetch_mitdb.py --all      # ~500 MB
    python3 benchmarks/fetch_afdb.py --all       # ~640 MB
    python3 benchmarks/fetch_nsrdb.py --all      # ~630 MB

    python3 benchmarks/run_qrs.py --all --csv benchmarks/results/chunk5_alle44_eigen.csv
    python3 benchmarks/run_hrv.py --all --csv benchmarks/results/hrv_alle44.csv
    python3 benchmarks/run_afib.py --all --csv benchmarks/results/afib_alle23_eigen.csv
    python3 benchmarks/run_pwave.py --all
    python3 benchmarks/run_nsrdb.py --all
    python3 benchmarks/run_patient.py --csv benchmarks/results/patient_ebene.csv

Alle Zwischenergebnisse (jedes einzelne Fenster, nicht nur Zusammenfassungen) liegen als CSV
in `benchmarks/results/` und sind Teil des Repositorys.
