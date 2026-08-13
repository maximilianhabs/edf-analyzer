# Wie stark verfälscht die R-Zacken-Detektion die HRV-Werte?

**Dieses Protokoll wurde vor der ersten Messung geschrieben.** Es legt fest, was verglichen
wird, mit welcher Wahrheit und unter welchen Regeln. Wer die Regeln erst nach den Zahlen
festlegt, findet immer welche, die passen.

## Die Frage

`docs/BENCHMARK_QRS.md` beziffert, wie gut die R-Zacken gefunden werden: 95,53 % der Schläge
bei korrekt gewähltem Kanal. Die HRV-Formeln selbst sind gegen analytische Sollwerte geprüft
(SDNN = A/√2 und weitere, siehe `analysis/methods.py`).

Zwischen beidem klafft eine Lücke. Die Formeln sind auf **perfekten** RR-Reihen bewiesen; die
Anwendung rechnet auf **detektierten**. Ein verpasster Schlag verschmilzt zwei RR-Intervalle
zu einem doppelt so langen — das trifft RMSSD, das aufeinanderfolgende Differenzen misst,
härter als SDNN, das um den Mittelwert streut.

Bisher ist unbekannt, wie groß dieser Fehler in den Zahlen ist, die Anwender ablesen. Genau
das misst dieser Benchmark: **nicht, ob richtig gerechnet wird, sondern ob das Ergebnis
stimmt.**

## Wahrheit

Die Schlag-Annotationen der MIT-BIH Arrhythmia Database — von Kardiologen geprüft, dieselbe
Quelle wie im QRS-Benchmark. Aus ihnen wird eine RR-Reihe gebildet und daraus die HRV.

Das ist der bestmögliche Vergleich: dieselbe Aufnahme, dasselbe Signal, derselbe
Auswertungsweg — der einzige Unterschied ist, **woher die Schläge kommen**.

## Verglichen wird die vollständige Kette der Anwendung

Auf beide Schlagreihen — annotierte wie detektierte — wird **dieselbe** Verarbeitung
angewandt, die auch die Anwendung benutzt:

    build_rr_series()          # Artefaktmaske: <300/>2000 ms, >20 % vom lokalen Median, Dropout
    .clean_rr                  # nur die unauffälligen Intervalle
    compute_hrv_time_domain()  # SDNN, RMSSD, pNN50, mittlere HF …

Ein Benchmark, der die Rohreihe nähme, misst etwas, das niemand angezeigt bekommt.

**Der Ausreißerfilter läuft auf beiden Seiten mit — bewusst.** Er entfernt Abweichungen über
20 % vom lokalen Median und trifft damit genau die Intervalle, die ein verpasster Schlag
erzeugt. Er könnte den Detektionsfehler also weitgehend auffangen. Ob er das tut, ist eine
der Fragen dieser Messung; ihn nur auf einer Seite laufen zu lassen, würde die Antwort
vorwegnehmen.

## Kennwerte

Verglichen werden die Werte, die in Oberfläche und Report stehen: **mittlere Herzfrequenz,
SDNN, RMSSD, pNN50**. Je Aufnahme wird die Abweichung `detektiert − annotiert` berichtet,
absolut und relativ; über alle Aufnahmen Median und Spannweite.

Der **Median** ist die Hauptgröße, nicht der Mittelwert: einzelne Aufnahmen mit schwerer
Arrhythmie erzeugen Ausreißer, die einen Mittelwert dominieren würden, ohne den typischen
Fall zu beschreiben. Die Ausreißer werden trotzdem einzeln ausgewiesen.

## Schichtung — vor der Messung festgelegt

Die vorige Schichtung nach der Auswahlmethode der Datenbank hat sich als wirkungslos
erwiesen (`docs/BENCHMARK_QRS.md`, Chunk 5). Diesmal wird nach einer Eigenschaft geschichtet,
die für die Fragestellung nachweislich zählt: **dem Anteil nicht-normaler Schläge** in den
Annotationen (Symbol ≠ `N`).

| Gruppe | Kriterium | Warum |
|---|---|---|
| **sinusnah** | ≤ 5 % nicht-normale Schläge | entspricht dem Einsatzfeld: EKG neben einem Routine-EEG |
| **arrhythmisch** | > 5 % | HRV ist hier ohnehin eingeschränkt deutbar |

Die 5-%-Grenze ist gesetzt, bevor die Verteilung bekannt ist. Sie ist eine Konvention, keine
Optimierung — falls sie die Gruppen sehr ungleich teilt, wird das berichtet und die Grenze
**nicht** nachträglich verschoben.

Berichtet werden beide Gruppen und die Gesamtheit.

## Kanalwahl

**MLII, wo vorhanden** (43 von 44 Aufnahmen; bei Aufnahme 114 steht MLII an zweiter Stelle).
Das entspricht der Annahme „der EKG-Kanal ist korrekt gewählt" — die Kanalidentifikation ist
nach Festlegung des Betreibers Aufgabe des Anwenders und nicht Gegenstand dieses Benchmarks.

## Was dieser Benchmark nicht zeigt

* **Keine klinische Gültigkeit.** Gemessen wird die Übereinstimmung mit einer perfekten
  Schlagreihe, nicht, ob ein HRV-Wert eine Aussage über den Patienten trägt.
* **Keine Aussage über Frequenzdomäne und nichtlineare Maße.** LF/HF, DFA und Sample Entropy
  bleiben zunächst außen vor; sie hängen zusätzlich von Interpolation und Fensterung ab und
  verdienen eine eigene Betrachtung.
* **MIT-BIH ist nicht repräsentativ zusammengestellt** (siehe `docs/BENCHMARK_QRS.md`).
  Deshalb die Schichtung oben.
* **30-Minuten-Ableitungen im Liegen.** Routine-EEGs dauern 20 Minuten und enthalten
  Wachheitswechsel und Hyperventilation.

## Durchführung

    pip install -r requirements-benchmark.txt
    python3 benchmarks/fetch_mitdb.py --all
    python3 benchmarks/run_hrv.py --all --csv benchmarks/results/hrv_alle44.csv

Ergebnisse siehe unten.

---

# Ergebnisse

Gemessen am 13.08.2026 über alle 44 bewerteten Aufnahmen.

## Für den typischen Fall ist der Fehler nicht messbar

Median der Abweichung `detektiert − annotiert`:

| Gruppe | Aufnahmen | ΔHF (min⁻¹) | ΔSDNN (ms) | ΔRMSSD (ms) | ΔpNN50 (%) |
|---|---|---|---|---|---|
| **sinusnah** (≤ 5 % nicht-normale Schläge) | 20 | **0,0** | **−0,05** | **0,1** | **0,0** |
| arrhythmisch (> 5 %) | 24 | −0,2 | 3,7 | 0,85 | 0,1 |
| gesamt | 44 | 0,0 | 0,05 | 0,1 | 0,05 |

Die 5-%-Grenze teilt die Datenbank fast hälftig (20 zu 24) — sie musste nicht verschoben
werden.

Das ist das wichtigste Ergebnis: **Obwohl 4,5 % der Schläge nicht gefunden werden, erreichen
die HRV-Werte für sinusnahe Aufnahmen praktisch exakt die Wahrheit.** Der Grund steht schon im
Protokoll oben: Der Ausreißerfilter verwirft Abweichungen über 20 % vom lokalen Median und
trifft damit genau die überlangen Intervalle, die ein verpasster Schlag erzeugt. Die
Detektionslücke erreicht die angezeigten Zahlen also gar nicht.

Der Median verdeckt allerdings Einzelfälle, und die sind erheblich.

## Die entscheidende Größe ist nicht die Trefferquote, sondern die Zeitgenauigkeit

Aufnahme 121 ist der Schlüsselfall. Sie ist **sinusnah** (0,1 % nicht-normale Schläge), und
die Trefferquote ist nahezu perfekt: **99,89 % Sensitivität, 100 % Vorhersagewert, zwei
verpasste Schläge von 1858.** Trotzdem:

| | annotiert | detektiert |
|---|---|---|
| RMSSD | 20,1 ms | **93,2 ms** |
| größte aufeinanderfolgende Differenz | 91 ms | 219 ms |
| verworfene Intervalle | 0,7 % | 0,4 % |

Nicht die Anzahl weicht ab, sondern die **Lage** der Schläge: Die Standardabweichung des
Zeitfehlers beträgt hier 39,1 ms. Da RMSSD aufeinanderfolgende Differenzen misst, erzeugt
zitternde Lokalisierung unmittelbar künstliche Variabilität — aus 20 ms werden 93.

Über alle 44 Aufnahmen:

| Zusammenhang | r |
|---|---|
| \|ΔRMSSD\| ~ **Streuung des Zeitfehlers** | **+0,57** |
| \|ΔRMSSD\| ~ Sensitivität | −0,42 |
| \|ΔSDNN\| ~ Streuung des Zeitfehlers | +0,13 |

Und der Zusammenhang ist an den Rändern eindeutig:

| | SD(Δt) | Sensitivität | \|ΔRMSSD\| |
|---|---|---|---|
| 6 Aufnahmen mit **kleinster** Streuung | 1,1–1,3 ms | 98,8–100 % | **0,0–1,4 ms** |
| 6 Aufnahmen mit **größter** Streuung | 15,7–39,1 ms | 76,8–99,9 % | 6,8–92,8 ms |

**Sensitivität ist für die HRV das falsche Gütemaß.** Aufnahme 121 hat eine hervorragende
Trefferquote und einen um das Viereinhalbfache verfälschten RMSSD; Aufnahme 108 hat eine
schlechte Trefferquote (85 %) und einen um 10,6 ms abweichenden RMSSD. Wer einen
QRS-Detektor für HRV auswählt, sollte nach der Zeitgenauigkeit fragen, nicht nach Se/+P.

## Wo die Werte stark abweichen

| Aufnahme | ΔSDNN | ΔRMSSD | Ursache |
|---|---|---|---|
| 228 | +258,4 | +23,3 | Sensitivität 45 % — hier bricht die Detektion ein |
| 208 | +74,6 | +69,4 | 46 % nicht-normale Schläge, Se 87 % |
| 222 | +56,2 | +96,0 | Vorhofflimmern, Se 86 % |
| 207 | −14,8 | −92,8 | Kammerflattern, RR teils unter 300 ms |
| 121 | +15,4 | **+73,1** | **sinusnah, Se 99,9 % — reine Zeitstreuung** |

Vier davon sind Aufnahmen mit schwerer Arrhythmie, bei denen HRV ohnehin eingeschränkt
deutbar ist. Aufnahme 121 ist die Ausnahme und die Warnung: Eine unauffällige Aufnahme mit
tadelloser Trefferquote kann einen grob falschen RMSSD liefern, ohne dass irgendetwas darauf
hinweist.

## Was daraus folgt

1. **Für die Zeitdomäne auf sinusnahen Aufnahmen ist die Kette belastbar.** Der Median-Fehler
   liegt unter der Anzeigegenauigkeit.
2. **RMSSD und pNN50 sind die empfindlichen Kennwerte**, SDNN und mittlere Herzfrequenz die
   robusten. Die mittlere Herzfrequenz weicht in 30 von 44 Aufnahmen um exakt 0,0 min⁻¹ ab.
3. **Offen:** Die Anwendung weist die Zeitstreuung nirgends aus. Sie ist ohne Annotationen
   nicht direkt messbar, aber es gibt Näherungen (etwa die Streuung der Lage des
   Maximums im Verfeinerungsfenster). Solange das fehlt, kann ein Fall wie 121 unbemerkt
   bleiben — dieselbe Klasse von stillem Fehler, gegen die die Abdeckungsprüfung eingeführt
   wurde.
4. **Nicht gemessen:** Frequenzdomäne (LF/HF), DFA, Sample Entropy. Sie hängen zusätzlich von
   Interpolation und Fensterung ab.

