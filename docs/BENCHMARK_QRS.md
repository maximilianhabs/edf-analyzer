# R-Zacken-Erkennung gegen MIT-BIH — Auswertungsvorschrift

**Diese Datei ist entstanden, bevor die erste Zahl gemessen wurde** (2026-08-12). Das ist
Absicht: Wer die Auswertungsregeln erst festlegt, nachdem er die Ergebnisse gesehen hat, kann
sich selbst nicht mehr trauen — jede Entscheidung über Toleranzen, Ausschlüsse und Kanalwahl
lässt sich dann unbewusst so treffen, dass das Ergebnis besser aussieht. Die Regeln stehen
deshalb hier fest, mit Datum, und Abweichungen davon werden ausdrücklich vermerkt.

Ziel ist die einzige Aussage, die bisher in `analysis/methods.py` bei allen Verfahren auf
null steht: **klinisch validiert**. Sie ist hier erreichbar, weil die MIT-BIH-Datenbank eine
schlagweise Annotation durch Kardiologen mitbringt — es braucht keine eigene Kohorte.

---

## Was genau geprüft wird

Ausschliesslich die **Detektion von R-Zacken**: findet der Algorithmus die Herzschläge, die
dort sind, und erfindet er keine? Das ist **nicht** dasselbe wie die Gültigkeit der darauf
aufbauenden HRV-Kennwerte. Ein Detektor kann jede R-Zacke finden und trotzdem so ungenau
liegen, dass RMSSD unbrauchbar wird — deshalb wird der Zeitfehler mitgemessen (siehe unten)
und die HRV-Kennwerte behalten in der Registry ihren eigenen, separaten Eintrag.

## Datensatz

**MIT-BIH Arrhythmia Database** (PhysioNet, `mitdb`), 48 Aufnahmen à 30 Minuten, 360 Hz,
zwei Kanäle, rund 110.000 annotierte Schläge. Lizenz: Open Data Commons Attribution.

**Ausgeschlossen: 102, 104, 107, 217** — die vier Aufnahmen mit Herzschrittmacher. Der
Ausschluss folgt ANSI/AAMI EC57, das paced beats aus der QRS-Detektions-Bewertung
herausnimmt; er ist damit Konvention und nicht unsere Wahl. **44 Aufnahmen** bleiben.

Der Ausschluss wird im Ergebnis ausgewiesen. Eine Kennzahl ohne die Angabe, worüber sie
gebildet wurde, ist wertlos.

## Kanalwahl

**Erster Kanal der Aufnahme.** Das ist bei den meisten MLII; bei 102 und 104 wäre es V5, aber
beide sind ohnehin ausgeschlossen. Wo der erste Kanal nicht MLII ist, wird das je Aufnahme
protokolliert — nicht stillschweigend ein anderer gewählt, weil der bessere Zahlen liefert.

## Welche Annotationen als Schlag zählen

Nur Symbole, die nach `wfdb.io.annotation.ann_label_table` einen tatsächlichen Herzschlag
beschreiben:

```
N L R B A a J S V r F e j n E / f Q ? !
```

**Nicht** gezählt werden Rhythmus- und Qualitätsmarken (`+`, `~`, `|`, `[`, `]`, `"`, `=`) und
insbesondere **`x`** — die nicht übergeleitete P-Welle. Dort gibt es keinen QRS-Komplex; ein
Detektor kann ihn nicht finden und dürfte dafür nicht bestraft werden. Manche veröffentlichten
Schlagtabellen zählen `x` mit, deren Gesamtzahlen liegen deshalb um wenige Schläge höher
(Aufnahme 108: 1774 statt 1763).

**Beim Aufbau ist genau hier ein Fehler passiert**, und er ist lehrreich genug, um ihn
festzuhalten: Die erste Fassung der Liste enthielt `!` nicht — „Ventricular flutter wave",
die Markierung der Einzelausschläge bei Kammerflattern. In Aufnahme 207 sind das 472 von 2332
Schlägen. Jeder Detektor hätte dort rund 20 % zu schlecht ausgesehen, und die Zahl wäre
plausibel genug gewesen, um sie zu glauben — 207 gilt ohnehin als schwierige Aufnahme. Der
Prüfpunkt aus Chunk 1 (Schlagzahl gegen dokumentierten Wert) hat es gefunden, bevor eine
einzige Kennzahl berechnet wurde. Ohne diesen Zwischenschritt wäre der Fehler in jedes
Ergebnis eingegangen.

## Zuordnung von Detektion zu Annotation

* **Toleranzfenster ±150 ms** (EC57-Standard).
* Die Zuordnung ist **eindeutig**: jede Annotation kann höchstens einen Treffer erhalten,
  jede Detektion höchstens einer Annotation zugeordnet werden. Ohne diesen Zwang zählt eine
  doppelt detektierte R-Zacke als zwei Treffer, und der Detektor sieht besser aus, als er ist.
* Bei mehreren Kandidaten im Fenster gewinnt der **zeitlich nächste**.
* **Die ersten 5 Sekunden** jeder Aufnahme werden verworfen (Einschwingen adaptiver
  Schwellen); dieselbe Regel gilt für Annotationen und Detektionen.

Umgesetzt in `benchmarks/matching.py`. Alle Paare innerhalb der Toleranz werden nach Abstand
aufsteigend abgearbeitet, das nächstliegende freie Paar gewinnt. Eine Zuordnung in blosser
Zeitreihenfolge wäre einfacher, würde aber bei zwei eng benachbarten Annotationen die falsche
bedienen — bei Kammerflattern (Aufnahme 207, RR teils unter 250 ms) überlappen sich die
±150-ms-Fenster benachbarter Schläge tatsächlich.

**Der Abgleich wird gegen konstruierte Fälle geprüft, nicht gegen echte Aufnahmen**
(`benchmarks/test_matching.py`, 12 Fälle): identische Reihen, Verschiebung innerhalb und
ausserhalb der Toleranz, die Toleranzgrenze selbst, jeder zweite Schlag fehlend, doppelt so
viele Detektionen, eine zweimal detektierte R-Zacke, zwei konkurrierende Kandidaten, leere
Reihen, unsortierte Eingabe, Zeitfehler-Streuung. Bei einer echten Aufnahme kennt man die
richtige Antwort nicht und kann deshalb auch nicht prüfen, ob der Abgleich stimmt.

Zusätzlich wurde der Abgleich **absichtlich beschädigt**, um zu sehen, ob die Prüfungen das
merken: Eindeutigkeit entfernt, Toleranzgrenze exklusiv statt inklusiv, Zuordnung nach
Reihenfolge statt nach Nähe. Die dritte Mutation blieb zunächst **unentdeckt** — der
zugehörige Test war so gebaut, dass die nähere Detektion zufällig auch die erste war. Er ist
daraufhin umgebaut worden (nähere Detektion liegt jetzt hinten); seither schlagen alle drei
Mutationen fehl.

## Kennzahlen

| Kennzahl | Definition |
|---|---|
| Sensitivität (Se) | TP / (TP + FN) — wie viele echte Schläge gefunden wurden |
| Positiver Vorhersagewert (+P) | TP / (TP + FP) — wie viele Detektionen echt waren |
| F1 | harmonisches Mittel aus Se und +P |
| Detektionsfehlerrate (DER) | (FP + FN) / Anzahl Annotationen |
| **Zeitfehler** | Mittelwert und Standardabweichung von (Detektion − Annotation) in ms, nur über die Treffer |

Der Zeitfehler wird berichtet, weil die gesamte HRV daran hängt: ein Jitter von 8 ms erzeugt
bereits eine künstliche RMSSD in der Größenordnung, die klinisch unterschieden wird. Eine
Sensitivität von 99,9 % bei 20 ms Streuung wäre für die Detektion exzellent und für die HRV
ein Problem.

**Berichtet wird je Aufnahme UND als Gesamtwert.** Der Gesamtwert wird über die aufsummierten
TP/FP/FN gebildet, nicht als Mittel der Einzelwerte — sonst zählen kurze Aufnahmen gleich
schwer wie lange.

## Was das Ergebnis NICHT bedeutet

* Keine Aussage über die HRV-Kennwerte (eigener Registry-Eintrag).
* Keine Aussage über EEG-Aufnahmen: MIT-BIH sind Langzeit-EKG-Ableitungen mit anderer
  Elektrodenlage und anderem Rauschprofil als ein EKG-Kanal, der in einem Routine-EEG
  mitläuft. Der Benchmark zeigt die Detektionsgüte unter Standardbedingungen, nicht unter
  unseren.
* Keine Aussage über Aufnahmen mit Schrittmacher (ausgeschlossen).

## Reproduzierbarkeit

Die Daten liegen **nicht** im Repository (rund 500 MB). `benchmarks/fetch_mitdb.py` lädt sie
nach `benchmarks/data/` (in `.gitignore`). Im Repository liegen das Auswertungsskript und die
**Ergebnisse als CSV** — diffbar, damit eine Veränderung zwischen zwei Ständen sichtbar wird.

Das Benchmark-Werkzeug (`wfdb`) steht in `requirements-benchmark.txt` und ist **keine**
Laufzeitabhängigkeit der Anwendung.

---

## Ergebnisse

### Chunk 3 — Aufnahme 100, eigener Detektor (2026-08-12)

| Aufnahme | Schläge | TP | FP | FN | Se | +P | F1 | Zeitfehler |
|---|---|---|---|---|---|---|---|---|
| 100 (MLII) | 2267 | 2267 | 0 | 0 | **100,00 %** | **100,00 %** | **100,00 %** | +1,4 ms, SD 2,5 ms |

Rohdaten: `benchmarks/results/chunk3_record100_eigen.csv`.

2267 statt 2273 Schläge, weil die ersten fünf Sekunden verworfen werden — sechs Schläge
liegen darin.

**Ein fehlerfreies Ergebnis ist verdächtig, deshalb geprüft.** Aufnahme 100 ist die leichteste
der Datenbank (Sinusrhythmus, sauberes Signal, 33 supraventrikuläre Extrasystolen), und
publizierte Detektoren erreichen dort ebenfalls nahezu 100 %. Trotzdem wurde die Kette
absichtlich gestört, um auszuschliessen, dass der Abgleich einfach alles durchwinkt:

| Störung | Erwartung | Gemessen |
|---|---|---|
| jede zehnte Detektion entfernt | Se ≈ 90 % | 89,99 % |
| 200 Detektionen erfunden | +P ≈ 91,9 % | 91,89 % |
| alle Detektionen um 200 ms verschoben | Se ≈ 0 % | 0,04 % |

Die letzten 0,04 % sind **ein** Schlag von 2267 und kein Fehler: Aufnahme 100 enthält
supraventrikuläre Extrasystolen mit kurzem Kopplungsintervall; eine um 200 ms verschobene
Detektion kann dort in das Fenster des *nächsten* Schlags fallen. Genau so soll sich der
Abgleich verhalten.

**Der Zeitfehler ist die für uns wichtigere Zahl.** Mittelwert +1,4 ms bei einer Streuung von
2,5 ms — die Detektion liegt also systematisch minimal nach der Annotation und streut kaum.
Für die HRV heisst das: der Detektor erzeugt keine nennenswerte künstliche RMSSD. Ein einzelner
Ausreisser bei −94 ms zeigt, dass es Einzelfälle gibt, aber der Median liegt bei +2,8 ms.

**Was das noch nicht bedeutet:** eine einzige, leichte Aufnahme. Aussagekraft bekommt der
Benchmark erst über alle 44 — insbesondere über die schwierigen (108, 203, 207, 222).

### Chunk 4 — vier schwierige Aufnahmen (2026-08-12)

Nicht die nächsten vier, sondern gezielt die schweren: 108 (Grundlinienrauschen), 203
(Rauschen und Ektopie), 207 (Kammerflattern), 222 (Vorhofflimmern mit Übergängen).

| Aufnahme | Schläge | eigen Se | eigen +P | Hamilton Se | Hamilton +P |
|---|---|---|---|---|---|
| 100 | 2267 | 100,00 % | 100,00 % | 99,91 % | 100,00 % |
| 108 | 1758 | 85,04 % | **100,00 %** | 70,76 % | **60,71 %** |
| 203 | 2972 | 84,83 % | 99,64 % | **98,08 %** | 99,59 % |
| 207 | 2327 | 76,84 % | 99,83 % | **85,69 %** | 99,30 % |
| 222 | 2476 | 86,19 % | 100,00 % | **99,92 %** | 99,68 % |
| **gesamt** | **11800** | **86,48 %** | **99,88 %** | 92,31 % | 92,85 % |

Rohdaten: `benchmarks/results/chunk4_schwierige_eigen.csv` und `…_hamilton.csv`.

**Die Gesamt-F1-Werte sind fast gleich (92,70 gegen 92,58) — und das ist irreführend.** Die
beiden Detektoren scheitern völlig verschieden:

* **Der eigene ist konservativ.** Der Vorhersagewert liegt bei 99,88 %: er erfindet praktisch
  nie einen Schlag. Dafür übersieht er auf schwierigen Aufnahmen jeden siebten bis vierten.
* **Hamilton ist aggressiv.** Auf drei der vier schweren Aufnahmen findet er deutlich mehr
  Schläge, produziert aber auf Aufnahme 108 **805 falsch-positive** bei 1758 echten Schlägen —
  der Vorhersagewert bricht auf 60,7 % ein. Eine HRV-Auswertung darauf wäre wertlos.

Für ein Werkzeug, dessen Ergebnis eine Variabilitätsanalyse ist, ist die konservative
Auslegung die richtige: ein übersehener Schlag verlängert ein RR-Intervall, ein erfundener
zerreisst zwei. Trotzdem sind 86,5 % Sensitivität deutlich unter dem Stand der Technik
(publizierte Detektoren erreichen über 99 %).

#### Warum der eigene Detektor Schläge übersieht — zwei belegte Ursachen

**1. Die Schwelle ist global, nicht adaptiv.** `detect_r_peaks()` berechnet sie einmal über
die *gesamte* Aufnahme (98. Perzentil × 0,25); der Docstring nennt sie „adaptive Threshold",
was sie nicht ist. Gemessen am 98. Perzentil je Minute schwankt die Amplitude innerhalb einer
Aufnahme erheblich:

| Aufnahme | Schwankung | Sensitivität |
|---|---|---|
| 100 | 1,2× | 100,0 % |
| 222 | 2,2× | 86,2 % |
| 108 | 3,2× | 85,0 % |

Der Zusammenhang ist eindeutig: Wo die Amplitude über die Aufnahme konstant bleibt, ist die
Erkennung perfekt. Wo sie schwankt, liegt die global bestimmte Schwelle in den leisen
Abschnitten zu hoch.

**2. Der Mindestabstand von 300 ms schliesst schnelle Rhythmen aus.** In Aufnahme 207 liegen
**265 von 2326 RR-Intervallen unter 300 ms** — diese Schläge kann der Detektor bauartbedingt
nicht finden, unabhängig von Signalqualität oder Schwelle. Das erklärt einen erheblichen Teil
der dortigen 539 Fehlschläge.

#### Was eine Korrektur brächte (gemessen, nicht geschätzt)

Blockweise Schwelle über 10-Sekunden-Fenster statt global, sonst unverändert:

| Aufnahme | heute | mit 10-s-Fenster |
|---|---|---|
| 100 | 100,0 / 100,0 | 100,0 / 100,0 |
| 108 | 85,0 / 100,0 | **99,1** / 99,7 |
| 203 | 84,9 / 99,7 | 87,3 / 99,7 |
| 207 | 76,9 / 99,9 | **87,6** / 99,7 |
| 222 | 86,2 / 100,0 | **93,3** / 100,0 |
| **gesamt** | **86,50 / 99,90** | **92,82 / 99,81** |

Sensitivität +6,3 Prozentpunkte, Vorhersagewert praktisch unverändert (−0,09). Der Gewinn
kostet also nichts.

Ein zusätzlich auf 200 ms verkürzter Mindestabstand brächte auf 207 weitere 2,6 Punkte,
kostet aber auf 108 den Vorhersagewert (99,7 → 92,2 %). Diese Änderung ist deshalb **nicht**
zu empfehlen; die Fensterung allein ist der klare Gewinn.

**Bewusst nicht umgesetzt.** Eine Änderung am Detektor verändert jede HRV-Ausgabe der
Anwendung — das ist eine fachliche Entscheidung und keine Aufräumarbeit. Die Messung liegt
vor, die Entscheidung nicht.

---

## Chunk 5 — alle 44 Aufnahmen

    python3 benchmarks/fetch_mitdb.py --all
    python3 benchmarks/run_qrs.py --all --csv benchmarks/results/chunk5_alle44_eigen.csv

**Ergebnis über 100.932 Schläge: Sensitivität 94,55 %, positiver Vorhersagewert 99,93 %.**

Damit war die Auswahl der fünf Aufnahmen aus Chunk 4 unbeabsichtigt pessimistisch — der
Gesamtwert liegt acht Punkte über dem, was die schwierige Stichprobe nahelegte.

### Die vorab gebildete Schichtung erklärt nichts

Vor der Messung war die Erwartung, dass die 20 zufällig gezogenen Aufnahmen (100–124)
deutlich besser abschneiden als die 24 gezielt nach seltenen Arrhythmien ausgewählten
(200–234), weil das Einsatzfeld der Anwendung — EKG neben einem Routine-EEG — der
Zufallsgruppe näher liegt.

| Gruppe | Aufnahmen | Schläge | Se % | +P % |
|---|---|---|---|---|
| Zufallsauswahl | 20 | 40.983 | 94,73 | 99,87 |
| gezielt selektiert | 24 | 59.949 | 94,43 | 99,97 |
| **gesamt** | **44** | **100.932** | **94,55** | **99,93** |

**Der Unterschied beträgt 0,3 Punkte — die Hypothese ist widerlegt.** Sie wird hier stehen
gelassen, weil eine vorab formulierte und dann verworfene Erwartung mehr wert ist als eine
nachträglich passende Erzählung. Wer nicht Arrhythmie, sondern Signalqualität als Ursache
vermutet, liegt richtig, und die Datenbank trennt danach nicht.

### Was tatsächlich trennt

Die Verteilung ist zweigipflig, nicht breit gestreut: **27 der 44 Aufnahmen liegen bei 99 %
oder darüber**, 34 über 95 %. Der Ausfall konzentriert sich auf zehn Aufnahmen, und **zwei
davon — 228 (45,4 %) und 114 (47,4 %) — stellen allein 2.104 der 5.501 verpassten Schläge.**

Geprüfte Erklärungsgrössen (Korrelation über alle 44):

| Grösse | r zur Sensitivität |
|---|---|
| Amplitudenschwankung über die Aufnahme (90./10. Perzentil der 10-s-Blöcke) | −0,40 |
| Anteil RR-Intervalle unter 300 ms | −0,22 |

Beides wirkt, keines allein erklärt den Befund: Aufnahme 208 schwankt kaum (1,25×) und liegt
dennoch bei 87 %. Aufnahme 114 ist die **einzige, bei der die Anwendung nicht MLII, sondern
V5 wählt** — dort ist die R-Zacke klein und die Wahl selbst könnte der Fehler sein. Das ist
noch nicht geklärt.

### Gemessener Nutzen einer blockweisen Schwelle (nicht umgesetzt)

Dieselbe Verarbeitungskette, nur die Schwelle je 10-s-Block statt einmal über die ganze
Aufnahme — offline gerechnet, ohne die Anwendung anzufassen:

| | Se % | +P % |
|---|---|---|
| heute (globale Schwelle) | 94,55 | 99,93 |
| blockweise Schwelle | **97,41** | 99,84 |

**+2,9 Punkte Sensitivität, 0,09 Punkte Vorhersagewert dafür.** Der Gewinn entsteht fast
vollständig bei den schwachen Aufnahmen: 106 +15,6, 116 +16,3, 108 +14,3, 228 +27,7,
114 +35,0 Punkte. Bei den bereits guten Aufnahmen ändert sich nichts.

**Eine Verschlechterung gibt es**: Aufnahme 215 fällt von 99,76 auf 95,71 %. Sie ist nicht
verstanden und wäre vor einer Umsetzung zu klären — genau die Art Nebenwirkung, die ein
Einzelfall-Test nicht gefunden hätte.

**Weiterhin bewusst nicht umgesetzt.** Die Entscheidung berührt jede HRV-Ausgabe der
Anwendung und liegt beim Betreiber, nicht beim Benchmark.

---

## Chunk 6 — die Kanalwahl der Anwendung

Aufnahme 114 fiel in Chunk 5 mit 47,4 % auf. Die Ursache war **nicht der Detektor**: 114 ist
die einzige Aufnahme, deren erster Kanal nicht MLII ist, sondern V5. Derselbe Detektor auf
demselben Signalabschnitt liefert

| Kanal | QRS-Amplitude | Se % |
|---|---|---|
| V5 (erster Kanal) | 0,77 mV | 47,36 |
| MLII (zweiter Kanal) | 2,23 mV | **99,89** |

Ein Kanalproblem, kein Detektorproblem. Und die Anwendung entscheidet hier **richtig**: ihr
Klassifizierer gibt beiden Kanälen 97 % Konfidenz, der Gleichstand wird über die
amplituden-abgeschmolzene QRS-Formkonsistenz gelöst, und die spricht für MLII (0,982 gegen
0,918). Der schlechte Wert entstand allein durch die Benchmark-Regel „erster Kanal".

Damit der Benchmark nicht länger etwas misst, das kein Anwender bekommt, ruft
`mitdb.lade(..., kanal="app")` jetzt denselben Klassifizierer und dieselbe Rangfolge auf wie
`core/shared.py` für `ecg_channels[0]` — importiert, nicht nachgebaut.

    python3 benchmarks/run_qrs.py --all --kanal app --csv benchmarks/results/chunk6_alle44_eigen_appkanal.csv

### Das Ergebnis war nicht das erwartete

| Kanalwahl | Se % | +P % |
|---|---|---|
| erster Kanal | 94,55 | 99,93 |
| wie die Anwendung | 94,75 | 99,78 |

**Zwei Zehntel Unterschied — und darunter verbergen sich 19 abweichende Kanalwahlen mit
Ausschlägen in beide Richtungen:**

| gewinnt | | verliert | |
|---|---|---|---|
| 228 | +53,8 | 208 | −40,1 |
| 114 | +52,5 | 212 | −33,6 |
| 116 | +16,7 | 105 | −19,5 |
| 222 | +13,4 | 233 | −4,1 |
| 223 | +4,4 | 214 | −3,2 |

**Der Befund:** Die QRS-Formkonsistenz, die den Gleichstand entscheidet, trägt **keine
Information über die Detektionsgüte**. Sie wählt die für die Detektion bessere Ableitung
ungefähr so oft wie die schlechtere; im Mittel hebt sich das auf.

Das ist kein Versagen des Klassifizierers in seiner eigentlichen Aufgabe. Die besteht darin,
den EKG-Kanal unter EEG-, EOG- und Artefaktkanälen zu **finden** — und das tut er hier
fehlerfrei, beide Ableitungen bekommen 97 %. Zwischen zwei echten EKG-Ableitungen nach
Detektionsgüte zu **entscheiden** ist eine andere Aufgabe, für die das Kriterium 2026-08-08 nie
gedacht war (es entstand, um hochamplitudige Crosstalk-Kanäle von der echten Ableitung zu
trennen — dort funktioniert es nachweislich).

Praktisch relevant wird das nur bei Aufnahmen mit **zwei gleichwertigen EKG-Ableitungen**
(z. B. NeuroFax X + T). Dort entscheidet heute ein Kriterium, das für diese Frage nachweislich
blind ist. Ob sich ein besseres lohnt, ist offen — es müsste erst gefunden und gemessen
werden, und der Nutzen im Mittel wäre gering.

**Berichtet wird weiterhin die Zahl aus Chunk 5** (erster Kanal, 94,55 %), weil nur sie mit
veröffentlichten Ergebnissen vergleichbar ist. Die App-Zahl steht daneben, nicht an ihrer
Stelle.

