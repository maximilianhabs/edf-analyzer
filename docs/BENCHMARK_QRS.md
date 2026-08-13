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
