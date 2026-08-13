# Wie gut erkennt das Screening Vorhofflimmern?

**Dieses Protokoll wurde vor der ersten Messung geschrieben.**

## Die Frage

Das Rhythmus-Screening (`analysis/rhythm_screening.py`) stuft 30-Sekunden-Fenster über CosEn
(Coefficient of Sample Entropy, Lake & Moorman 2011) als AFib-verdächtig ein. Die Schwelle
−0,8 stammt aus veröffentlichten Referenzbereichen (Sarkar et al. 2015).

Belegt ist bisher: die Formel, zwei Sekundärquellen, und **zwei echte Fälle** aus dem eigenen
Bestand. Damit lässt sich sagen, dass die Umsetzung plausibel rechnet — aber nicht, wie oft
sie richtig liegt. Publizierte Sensitivitäts- und Spezifitätswerte gehören der Publikation,
nicht dieser Umsetzung.

Dieser Benchmark beziffert es für **unsere** Umsetzung.

## Daten

**MIT-BIH Atrial Fibrillation Database** (PhysioNet, ODC-BY):
25 Langzeit-EKGs à rund 10 Stunden, 250 Hz, zwei Kanäle.

Moody GB, Mark RG. *A new method for detecting atrial fibrillation using R-R intervals.*
Computers in Cardiology 10:227-230 (1983).

**Ausgewertet werden 23 Aufnahmen.** Zu `00735` und `03665` gibt es auf PhysioNet keine
Signaldatei, nur Annotationen (geprüft 13.08.2026) — ein Detektor kann darauf nichts finden.
Der Ausschluss ist Datenlage, nicht unsere Wahl.

## Wahrheit

Die Rhythmus-Annotationen der `.atr`-Dateien: Intervallmarken mit `(AFIB`, `(N`, `(AFL`
(Vorhofflattern), `(J` (junktional). Sie stammen von den Autoren der Datenbank und sind die
Referenz, gegen die diese Datenbank üblicherweise ausgewertet wird.

## Bewertungseinheit

**30-Sekunden-Fenster**, nicht überlappend — dieselbe Fensterlänge, mit der die Anwendung
rechnet, und die klinische Mindestdauer, ab der Vorhofflimmern als solches gilt.

Ein Fenster gilt als **AFib**, wenn mindestens die Hälfte seiner Dauer als `(AFIB` annotiert
ist, sonst als **kein AFib**. Zusätzlich wird eine zweite Auswertung berichtet, die alle
**gemischten** Fenster (Rhythmuswechsel innerhalb des Fensters) verwirft — an einem Übergang
kann kein Verfahren richtig liegen, und wie groß dieser Anteil ist, gehört ausgewiesen statt
stillschweigend eingerechnet.

**`(AFL` und `(J` werden aus der Bewertung ausgeschlossen**, nicht als „kein AFib" gezählt.
Vorhofflattern als unauffällig zu verbuchen wäre irreführend, es als Vorhofflimmern zu zählen
wäre falsch. Der Anteil wird berichtet.

## Zwei Durchläufe, um die Ursache trennen zu können

| Durchlauf | Schläge aus | beantwortet |
|---|---|---|
| **A — wie im Betrieb** | eigener Detektor | Was bekommen Anwender? |
| **B — CosEn allein** | `.qrs` der Datenbank | Wie gut ist das Verfahren ohne Detektionsfehler? |

Die HRV-Messung (`docs/BENCHMARK_HRV.md`) hat gezeigt, dass Detektionsfehler sich sehr
unterschiedlich auf RR-basierte Kennwerte auswirken. Ohne diese Trennung wäre ein schlechtes
Ergebnis nicht zuzuordnen.

**Die `.qrs`-Dateien sind maschinell erzeugt und NICHT von Hand geprüft** — anders als die
Schlag-Annotationen der Arrhythmie-Datenbank. Durchlauf B ist deshalb kein Goldstandard,
sondern eine sauberere Schlagreihe als die eigene. Das begrenzt, was B aussagt, und wird
beim Ergebnis wiederholt.

## Schwelle

**−0,8, unverändert aus der Literatur.** Sie wird für diesen Benchmark **nicht** angepasst.

Eine an diesen Daten optimierte Schwelle würde auf denselben Daten glänzen und über ihre
Güte nichts aussagen. Falls die Messung nahelegt, dass eine andere Schwelle besser wäre, wird
das als **Befund** berichtet — die Entscheidung darüber ist fachlich und liegt beim Betreiber,
wie bei der HRV-Normgrenze und der Delta-Frage.

## Kanalwahl

**Erster Kanal** (`ECG1`). Beide Kanäle sind echte EKG-Ableitungen; die Kanalidentifikation
ist nach Festlegung des Betreibers Aufgabe des Anwenders und nicht Gegenstand dieses
Benchmarks.

## Artefaktausschluss

Die Anwendung schließt Segmente aus, die `analysis/ecg_quality.py` als Artefakt einstuft.
Dieser Schritt **bleibt aktiv** — er gehört zur Kette, die Anwender benutzen. Der Anteil
verworfener Fenster wird berichtet; verschwiegen wäre er eine stille Beschönigung.

## Kennzahlen

Je Aufnahme und über alle Aufnahmen zusammen: **Sensitivität, Spezifität, positiver und
negativer Vorhersagewert**, dazu die Vier-Felder-Zahlen.

Der positive Vorhersagewert hängt stark von der Häufigkeit ab, und die schwankt zwischen den
Aufnahmen extrem (Aufnahme 04015: 0,6 % AFib-Zeit). Er wird deshalb **nur zusammen mit der
Häufigkeit** berichtet, nie allein.

Zusammengefasst wird über die **aufsummierten Fensterzahlen**, nicht als Mittel der
Einzelwerte — sonst zählte eine Aufnahme mit wenigen bewertbaren Fenstern so viel wie eine
mit tausenden.

## Was dieser Benchmark nicht zeigt

* **Keine klinische Gültigkeit.** Gemessen wird die Übereinstimmung mit einer
  Rhythmus-Annotation, nicht der Nutzen einer Screening-Aussage am Patienten.
* **Langzeit-EKG, nicht Routine-EEG.** 10 Stunden ambulant gegen 20 Minuten im Liegen.
* **Angereicherte Häufigkeit.** Die Datenbank wurde für AFib-Forschung zusammengestellt; der
  AFib-Anteil liegt weit über dem einer neurologischen Routineambulanz. Auf die Wirkung auf
  den Vorhersagewert wird beim Ergebnis eingegangen.
* **Ektopie- und P-Wellen-Stufe bleiben außen vor.** Sie sind eigene Verfahren und brauchen
  eine eigene Wahrheit.

## Durchführung

    pip install -r requirements-benchmark.txt
    python3 benchmarks/fetch_afdb.py --all          # rund 640 MB
    python3 benchmarks/run_afib.py --all --csv benchmarks/results/afib_alle23.csv

Ergebnisse siehe unten, sobald gemessen.
