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

Ergebnisse siehe unten.

---

# Ergebnisse

Gemessen am 13./14.08.2026 über alle 23 Aufnahmen, rund 234 Stunden EKG.

## Fensterebene

| Durchlauf | Fenster | AFib-Anteil | Sensitivität | Spezifität | Vorhersagewert |
|---|---|---|---|---|---|
| **A — eigener Detektor** | 26.652 | 39,3 % | **75,26 %** | **99,70 %** | 99,38 % |
| **B — `.qrs`-Referenzschläge** | 25.562 | 37,4 % | 76,17 % | 99,59 % | 99,10 % |
| A, nur reine Fenster | 26.182 | 39,2 % | 75,97 % | 99,74 % | 99,46 % |

Verworfen: 222 Fenster wegen Vorhofflattern/junktionalem Rhythmus, 470 gemischte,
1.230 durch den Artefaktausschluss.

**Der Detektor ist nicht die Grenze.** Die beiden Durchläufe liegen 0,9 Punkte auseinander —
mit einer sauberen Schlagreihe wird das Ergebnis nicht besser. Das war der Zweck der Trennung,
und die Antwort ist eindeutig: Was hier begrenzt, ist CosEn beziehungsweise seine Schwelle.

Der hohe Vorhersagewert von 99,38 % ist eine Folge der Häufigkeit von 39 % in dieser
Datenbank und **nicht auf eine Routineambulanz übertragbar**. Die Zahl steht hier nur der
Vollständigkeit halber.

## Die verpassten Fenster liegen dicht unter der Schwelle

| | Anzahl | CosEn (Median) |
|---|---|---|
| AFib erkannt | 7.279 | −0,37 |
| **AFib verpasst** | **2.259** | **−1,00** (25./75. Perzentil −1,21 / −0,89) |
| kein AFib | 16.006 | −2,31 |

Die beiden Verteilungen sind gut getrennt — der Abstand zwischen −0,37 und −2,31 ist groß.
Die Schwelle −0,8 liegt aber **am Rand der AFib-Verteilung statt zwischen beiden**, und
schneidet damit ein Viertel der echten AFib-Fenster ab.

Die gemessenen Werte bestätigen die Literatur, an der die Schwelle hängt (Sarkar 2015: AFib
−0,5, Sinusrhythmus −2,1): unsere −0,37 und −2,31 liegen nahe dran. Nicht bestätigt wird die
Wahl des Schnitts.

Was eine andere Schwelle brächte — **gemessen, nicht umgesetzt**:

| Schwelle | Sensitivität | Spezifität |
|---|---|---|
| **−0,8 (heute)** | **75,3 %** | **99,70 %** |
| −0,9 | 82,7 % | 99,49 % |
| **−1,0** | **88,2 %** | **99,28 %** |
| −1,1 | 91,8 % | 98,96 % |
| −1,3 | 95,5 % | 97,73 % |
| −1,8 | 99,3 % | 89,12 % |

Bei −1,0 stiege die Sensitivität um 13 Punkte und kostete 0,4 Punkte Spezifität. Bis etwa
−1,1 bleibt der Handel günstig, danach kippt er.

**Bewusst nicht umgesetzt.** Die Schwelle stammt aus der Literatur; sie an dieser Datenbank
zu wählen hieße, sie an denselben Daten zu prüfen, an denen sie gefunden wurde. Und sie
verändert jede Rhythmusaussage der Anwendung — eine fachliche Entscheidung, wie bei der
HRV-Normgrenze und dem Delta-Band. Die Messung liegt vor, die Entscheidung nicht.

## Die Regel „ein Fenster genügt" ist der eigentliche Befund

Die Anwendung stuft eine Aufnahme als verdächtig ein, sobald **ein einziges** Fenster
anschlägt (`classify_afib_risk`) — bewusst konservativ, weil Vorhofflimmern oft anfallsartig
auftritt. Auf Aufnahmeebene erkennt sie damit **23 von 23** Aufnahmen.

Diese 100 % sind allerdings wenig wert: **die Datenbank enthält keine einzige Aufnahme ohne
Vorhofflimmern.** Die Spezifität auf Aufnahmeebene ist hier nicht messbar.

Sie lässt sich aber ausrechnen. Die Falsch-positiv-Rate je Fenster beträgt **0,412 %**:

| Aufnahmedauer | Fenster | Wahrscheinlichkeit für mindestens einen Fehlalarm |
|---|---|---|
| **20 min (Routine-EEG)** | 40 | **15,2 %** |
| 30 min | 60 | 22,0 % |
| 10 h (Langzeit-EKG) | 1.200 | 99,3 % |

**Etwa jede siebte unauffällige 20-Minuten-Ableitung erhielte einen AFib-Verdacht.** Für ein
Langzeit-EKG wäre die Regel unbrauchbar; für die Dauer, mit der diese Anwendung arbeitet, ist
sie vertretbar — aber die Größenordnung sollte bekannt sein und gehört in die Oberfläche.

Zwischen Schwelle und Regel besteht ein Zusammenhang: Eine Schwelle von −1,0 würde die
Fehlalarmrate je Fenster auf 0,72 % heben und damit die 20-Minuten-Wahrscheinlichkeit auf
rund 25 %. Beide Entscheidungen gehören zusammen getroffen.

## Eine Vermutung, die nicht standhielt

CosEn enthält den Term −ln(mittleres RR). Daraus folgte die Erwartung, dass Vorhofflimmern
mit langsamer Kammerfrequenz systematisch übersehen wird. **Widerlegt:** die Korrelation
zwischen mittlerer Herzfrequenz und Sensitivität je Aufnahme beträgt r = −0,06, die zum
AFib-Anteil r = −0,04.

Anders als bei der Amplitude im QRS-Benchmark und der Zeitstreuung im HRV-Benchmark ist die
Ursache der Streuung zwischen den Aufnahmen (27,6 % bis 100 % Sensitivität) hier **nicht
geklärt**. Das bleibt offen und wird nicht durch eine nachträglich passende Erklärung ersetzt.

## Was das für die Registry bedeutet

Das Rhythmus-Screening steht bisher in **keinem** Registry-Eintrag. Mit diesen Zahlen lässt
sich es erstmals belegt aufnehmen — als Screening-Marker mit hoher Spezifität und
eingeschränkter Sensitivität auf Fensterebene, gemessen an 234 Stunden annotiertem EKG.

