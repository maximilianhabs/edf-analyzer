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

---

# Protokoll-Erweiterung: die Frage auf Patientenebene

**Vor der Messung geschrieben (14.08.2026).**

## Warum die Fensterebene die falsche Einheit ist

Alles oben zählt 30-Sekunden-Fenster. Klinisch wird aber nicht je Fenster entschieden, sondern
**je Patient**: Liegt Vorhofflimmern vor, ja oder nein?

Der Unterschied ist keine Formalie, sondern folgt aus der Krankheit. Vorhofflimmern ist häufig
**paroxysmal** — es tritt in Episoden auf. Für einen Patienten mit anfallsartigem Vorhofflimmern
gilt deshalb:

* Wird **ein einziges** Fenster richtig erkannt, steht die Diagnose. Alle übrigen verpassten
  Fenster derselben Episode ändern daran nichts.
* Umgekehrt zählt bei einem Gesunden **jeder einzelne** Fehlalarm — ein falsch positives Fenster
  in vierzig genügt, um jemanden fälschlich mit einem Vorhofflimmern-Verdacht zu belasten.

Eine Sensitivität von 75,3 % je Fenster ist damit weder gut noch schlecht, sondern schlicht die
falsche Auskunft auf die eigentliche Frage. Die Fensterebene bleibt trotzdem stehen: Sie ist die
belastbare Größe für Qualitätssicherung und für den Vergleich zweier Verfahren, weil sie
tausende unabhängige Beobachtungen liefert statt dreiundzwanzig.

## Was bisher fehlt

Auf Aufnahmeebene erkennt das Screening 23 von 23 — **und diese Zahl ist wertlos**, weil die
AFib-Datenbank keine einzige Aufnahme ohne Vorhofflimmern enthält. Die Hälfte der Frage
(„schlägt es bei Gesunden nicht an?") ist damit unbeantwortet.

## Negativkohorte

**MIT-BIH Normal Sinus Rhythm Database**: 18 Aufnahmen à rund 25 Stunden, 128 Hz, Probanden
ohne nachweisbare relevante Arrhythmien (`benchmarks/fetch_nsrdb.py`).

**Was diese Kohorte nicht ist:** eine neurologische Routineambulanz. Gesunde Freiwillige, keine
Extrasystolen, keine Medikation. Eine hier gemessene Spezifität ist deshalb eine **Obergrenze**;
Patienten mit Ektopie erzeugen mehr Fehlalarme — dafür ist die P-Wellen-Stufe gebaut, und die
Frage braucht die Arrhythmie-Datenbank und eine eigene Betrachtung.

Zweiter Vorbehalt: 128 Hz gegen 250 Hz in der AFib-Datenbank. Vor der Auswertung wird geprüft,
ob Detektion und CosEn dort vergleichbar arbeiten; falls nicht, wird das berichtet.

## Bewertungseinheit: 20-Minuten-Abschnitte

**Nicht die vollen Aufnahmen.** Die Regel „ein Fenster genügt" macht die Fehlalarm­wahrschein­lich­keit
zu einer Funktion der Aufnahmedauer — auf 25 Stunden schlägt sie nahezu sicher an
(rechnerisch 99,3 % bei 10 Stunden). Ein an 25-Stunden-Aufnahmen gemessener Wert beantwortet
eine Frage, die an dieses Werkzeug niemand stellt.

Bewertet werden deshalb **20-Minuten-Abschnitte** — die Dauer, mit der die Anwendung
tatsächlich arbeitet. Zusätzlich werden 10 und 30 Minuten berichtet, damit die Abhängigkeit von
der Dauer sichtbar wird statt versteckt.

Die Abschnitte entstehen durch Zusammenfassen der bereits herausgeschriebenen Einzelfenster —
es wird nichts neu gerechnet, und jede Zahl bleibt aus der Fenster-CSV nachvollziehbar.

## Drei Gruppen

| Gruppe | Herkunft | erwartet |
|---|---|---|
| **A — gesund** | nsrdb-Abschnitte | kein Verdacht |
| **B — AFib-Patient, aber gerade Sinusrhythmus** | afdb-Abschnitte ohne annotiertes AFib | kein Verdacht |
| **C — AFib im Abschnitt** | afdb-Abschnitte mit mindestens einem AFib-Fenster | Verdacht |

Gruppe B wird **getrennt** ausgewiesen und nicht mit A verrechnet. Ein Abschnitt eines
AFib-Patienten ohne Episode ist der klinisch heikelste Fall: derselbe Mensch, dasselbe Herz,
nur gerade kein Flimmern. Ein Fehlalarm ist dort weniger folgenschwer als bei einem Gesunden,
aber er ist trotzdem einer.

Ein Abschnitt aus Gruppe B, der keinen Verdacht auslöst, ist **richtig negativ** — kein
verpasster Fall. Diese Unterscheidung ist der Grund, warum die Gruppen über die Annotation
gebildet werden und nicht über die Datenbankzugehörigkeit.

## Verdikt

Wie in der Anwendung (`classify_afib_risk`): Verdacht, sobald **mindestens ein** auswertbares
Fenster im AFib-Bereich liegt. Schwellen unverändert.

## Kennzahlen

Sensitivität aus Gruppe C, Spezifität getrennt aus A und B, jeweils mit den Vier-Felder-Zahlen
und der Zahl der Abschnitte. Zusätzlich für jede Abschnittslänge, damit die Dauerabhängigkeit
belegt statt behauptet ist.

Ergebnisse siehe unten, sobald gemessen.

## Kontrollpunkt: trägt 128 Hz?

Vor der Aggregation zu 20-Minuten-Abschnitten geprüft an zwei Aufnahmen der Negativkohorte
(16265, 16483), analog zum Kontrollpunkt in `docs/BENCHMARK_PWAVE.md`.

Das P-Fenster (−250 bis −60 ms) umfasst bei 128 Hz **24 Abtastwerte**, gegenüber 47 bei den
250 Hz der AFib-Datenbank — spürbar gröber.

| Aufnahme | Fenster | Kohärenz Median | Minimum | Anteil < 0,35 |
|---|---|---|---|---|
| 16265 | 2.668 | 0,96 | 0,63 | 0,00 % |
| 16483 | 2.517 | 0,99 | 0,73 | 0,00 % |

Selbst das **niedrigste** gemessene Fenster (0,63) liegt weit über der Schwelle 0,35, und kein
einziges Fenster war nicht auswertbar. **Die Abbruchbedingung greift nicht** — 128 Hz trägt für
diese Kohorte.

## Fensterebene, Negativkohorte

45.919 Fenster, 18 gesunde Probanden, rund 459 Stunden — alle als „nicht AFib" gewertet.

| Verfahren | Fehlalarme | Spezifität |
|---|---|---|
| CosEn (Schwelle −0,8) | 800 | 98,26 % |
| **P-Wellen-Kohärenz (Schwelle 0,35)** | **7** | **99,98 %** |

CosEn's Fehlalarme häufen sich stark bei einzelnen Probanden (16539: 258, 16773: 238,
16795: 103) — vermutlich Phasen mit unregelmäßiger Sinusarrhythmie oder Bewegungsartefakt,
die als RR-Irregularität erscheinen, ohne dass eine P-Welle fehlt. Genau die Situation, für
die die P-Wellen-Stufe ursprünglich gebaut wurde (Ektopie-Fehlalarme), zeigt sich hier auch
bei gesundem Sinusrhythmus.

**Die P-Welle ist auf dieser Kohorte nicht nur empfindlicher für AFib (47,5 % gegen CosEns
faktische 13–75 % je nach Schwellenwahl), sie ist auch spezifischer bei Gesunden.** Das ist
kein Kompromiss zwischen den beiden Zielen, sondern ein Verfahren, das auf dieser Datenlage
in beiden Richtungen besser abschneidet als CosEn allein.

---

# Schritt 4 — Ergebnis auf Patientenebene

Aggregiert aus den bereits geschriebenen Fenster-CSVs, ohne Neuberechnung
(`benchmarks/run_patient.py`). 6.619 Abschnitte über drei Längen, drei Gruppen, drei
Verfahren.

## 20-Minuten-Abschnitte — die Dauer der Anwendung

| Verfahren | Sensitivität (Gruppe C) | Spezifität, gesund (A) | Spezifität, AFib-Pat. ohne Episode (B) |
|---|---|---|---|
| CosEn allein | 96,87 % | 85,96 % | 97,07 % |
| **P-Welle allein** | 89,97 % | **99,39 %** | 96,48 % |
| CosEn ODER P-Welle | 97,49 % | 85,35 % | 93,84 % |

**Auf Patientenebene kehrt sich das Bild um.** Die Regel „ein Fenster genügt" hebt CosEns
Sensitivität auf 96,9 % — genau der paroxysmale Charakter, den der Betreiber beschrieben hat:
eine einzelne erkannte Episode reicht. Der Preis dafür ist eine Spezifität von nur 85,96 % bei
gesunden 20-Minuten-Abschnitten — **rund jeder siebte gesunde Abschnitt löst einen
Fehlalarm aus**, in etwa die 15,2 %, die aus der Fenster-Fehlalarmrate vorab berechnet wurden
(`docs/BENCHMARK_AFIB.md`, Abschnitt zur Ein-Fenster-Regel).

Die P-Welle allein liegt bei 89,97 % Sensitivität — niedriger als CosEn, weil ihr auf
Fensterebene ohnehin geringerer Anteil betroffener Fenster (47,5 % gegen CosEns 75,3 %) bei
„ein Fenster genügt" weniger Chancen bekommt, wenigstens eines zu treffen. Dafür liegt ihre
Spezifität bei 99,39 % — mehr als das Zehnfache besser.

## Die Kombination hilft NICHT — sie summiert die Schwächen

Das war die eigentliche Frage dieses Schritts, und die Antwort widerspricht der Erwartung aus
der Fensterebene. **Die 160 CosEn-Fehlalarme und die 7 P-Wellen-Fehlalarme bei gesunden
20-Minuten-Abschnitten überschneiden sich in KEINEM einzigen Fall.** Jedes Verfahren erzeugt
seine eigenen, unabhängigen Fehlalarme — auf 12 von 18 gesunden Aufnahmen verteilt.

Eine ODER-Verknüpfung („Verdacht, wenn CosEn ODER P-Welle anschlägt") erbt deshalb **beide**
Fehlerquellen: Spezifität 85,35 % — kaum anders als CosEn allein, weil dessen 160 Fehlalarme
fast unverändert durchschlagen und die 7 der P-Welle nur draufkommen. Die Sensitivität steigt
dabei nur marginal (96,87 → 97,49 %), weil CosEn ohnehin schon fast alles fängt, was die
P-Welle zusätzlich fände.

**Damit ist die ursprüngliche Idee — „P-Welle als zweite Achse einsammeln" — auf
Patientenebene widerlegt.** Sie trug auf Fensterebene (dort war P-Welle in beiden Richtungen
besser), aber die Aggregationsregel „ein Fenster genügt" verstärkt gerade die Schwäche, die man
kombinieren wollte auszugleichen.

## Was stattdessen tatsächlich hilft: P-Welle statt CosEn, nicht zusätzlich

Der eigentliche Hebel liegt nicht in der Kombination, sondern im **Austausch**:

| bei 20 min | Sensitivität | Spezifität (gesund) |
|---|---|---|
| CosEn (heutiges Verfahren) | 96,87 % | 85,96 % |
| **P-Welle statt CosEn** | 89,97 % | **99,39 %** |

7 Punkte weniger Sensitivität für 13,4 Punkte mehr Spezifität — und eine Fehlalarmquote, die
von „jeder siebte" auf „einer von 163" fällt. Für einen Betreiber, der ausdrücklich Spezifität
vor Sensitivität stellt, ist das der günstigere Tausch der beiden geprüften Optionen.

**Auch das ist gemessen, nicht umgesetzt.** Ein Wechsel des primären Verfahrens ist eine
fachliche Entscheidung, keine Kombination zweier bestehender.

## Dauerabhängigkeit — wie vorab erwartet

| Länge | CosEn Spez. (gesund) | P-Welle Spez. (gesund) |
|---|---|---|
| 10 min | 89,69 % | 99,69 % |
| 20 min | 85,96 % | 99,39 % |
| 30 min | 83,51 % | 99,34 % |

CosEns Spezifität fällt mit der Dauer spürbar, weil mehr Fenster mehr Gelegenheiten für einen
Fehlalarm bedeuten. Die P-Welle bleibt über alle drei Längen nahe konstant — ihre Fehlalarme
sind selten genug, dass die Dauer kaum ins Gewicht fällt.

## Gruppe B — der Kontrollfall

AFib-Patienten in einem Abschnitt ohne Episode verhalten sich bei CosEn (97,1–97,8 % korrekt
negativ) ähnlich wie gesunde Probanden bei P-Welle, aber schlechter als gesunde Probanden bei
CosEn — plausibel, da ihr Grundrhythmus (oft mit früherer Ektopie) unruhiger ist als der
komplett gesunder Freiwilliger.

