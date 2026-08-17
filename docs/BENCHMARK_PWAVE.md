# Trägt der P-Wellen-Nachweis, und hilft er dort, wo CosEn aufgibt?

**Dieses Protokoll wurde vor der ersten Messung geschrieben.**

## Die Frage

`docs/BENCHMARK_AFIB.md` hat gezeigt: Das CosEn-Screening ist auf Fensterebene sehr spezifisch
(99,70 %) und mittelmäßig sensitiv (75,26 %). Eine niedrigere Schwelle würde Sensitivität
kaufen und Spezifität kosten — dieselbe Kurve entlanggeschoben. Der Betreiber hat sich
ausdrücklich für die Spezifität entschieden: Das Werkzeug soll anschlagen, wenn wirklich etwas
ist.

Der P-Wellen-Nachweis (`analysis/p_wave_analysis.py`) ist eine **zweite, von CosEn unabhängige**
Evidenzquelle. CosEn misst die Unregelmäßigkeit der RR-Abstände; die P-Wellen-Kohärenz misst,
ob vor den QRS-Komplexen eine zeitlich feste Vorhofaktivität steht. Bei zwei unabhängigen
Merkmalen gilt der Zielkonflikt nicht zwingend: Man fügt eine Achse hinzu, statt auf einer zu
verschieben.

Zwei Fragen also:

1. **Trägt das Verfahren für sich?** Bisher ist es an **drei** echten Fällen belegt
   (Kohärenz 0,99 Sinusrhythmus / 0,83 Ektopie / 0,41 Vorhofflimmern) — dieselbe dünne
   Grundlage, auf der CosEn stand, bevor gemessen wurde.
2. **Hilft es genau dort, wo CosEn versagt?** Von den 2.259 AFib-Fenstern, die CosEn verpasst
   hat: Wie viele haben eine niedrige Kohärenz — und was kostet es an Spezifität, sie
   einzusammeln?

## Daten und Wahrheit

Dieselben wie in `docs/BENCHMARK_AFIB.md`: MIT-BIH Atrial Fibrillation Database, 23 Aufnahmen
mit Signal, rund 234 Stunden, Rhythmus-Annotationen der Datenbankautoren als Wahrheit.

Dieselbe Wahrheit und dieselben Fenster zu benutzen ist hier nicht Bequemlichkeit, sondern
Voraussetzung: Nur so lassen sich beide Verfahren **fensterweise gegeneinander** stellen und
die Frage nach der Kombination überhaupt beantworten.

## Bewertungseinheit

**Dieselben 30-Sekunden-Fenster**, die `sliding_cosen()` liefert — inklusive Artefaktausschluss.
Für jedes Fenster wird zusätzlich `p_wave_analysis.analyze_window()` gerechnet, also genau der
Weg, den auch die Anwendung geht (`views/rhythm_screening.py`, Stufe ②b).

Fensterlabel, Ausschluss von Vorhofflattern und junktionalem Rhythmus, Umgang mit gemischten
Fenstern: unverändert wie in `docs/BENCHMARK_AFIB.md`.

## Schwellen

**0,6 („sichtbar") und 0,35 („nicht abgrenzbar"), unverändert aus dem Bestand.** Als AFib-Hinweis
gilt eine Kohärenz **unter 0,35**.

Sie werden für diesen Benchmark **nicht** angepasst. Eine an diesen Daten gewählte Schwelle
würde auf denselben Daten glänzen und über ihre Güte nichts aussagen — dieselbe Regel wie bei
der CosEn-Schwelle.

## Was gemessen wird

**Teil A — P-Welle allein.** Sensitivität, Spezifität und Vorhersagewert der Kohärenz je
Fenster, gegen dieselbe Wahrheit. Zusätzlich die Verteilung der Kohärenz in AFib- und
Nicht-AFib-Fenstern (Median und Quartile), damit sichtbar wird, *wie* getrennt die Klassen
sind und nicht nur, wo die Schwelle zufällig liegt.

**Teil B — die Kombination.** Für die Regel „AFib-Hinweis, wenn CosEn ≥ −0,8 **oder** Kohärenz
< 0,35":

* Wie viele der von CosEn verpassten Fenster kommen dazu?
* Was kostet es an Spezifität, und wie ändert sich die Fehlalarm-Wahrscheinlichkeit einer
  20-Minuten-Ableitung (heute 15,2 %)?

Berichtet werden beide Zahlen immer zusammen. Eine Sensitivitätssteigerung ohne den zugehörigen
Preis wäre genau die Halbwahrheit, gegen die dieser Benchmark gebaut ist.

**Gemessen, nicht umgesetzt.** Ob die Anwendung die Kombination übernimmt, ist eine fachliche
Entscheidung des Betreibers — wie bei der CosEn-Schwelle, der HRV-Normgrenze und dem
Delta-Band.

## Abbruchbedingung

Wenn der Kontrollpunkt an einer einzelnen Aufnahme zeigt, dass die Kohärenz auf diesen Daten
nicht trennt (etwa weil 250 Hz Abtastrate oder die Signalqualität der Langzeitableitungen die
Ensemble-Mittelung nicht tragen), wird **abgebrochen und das berichtet** — statt Zahlen zu
erzeugen, die nichts bedeuten.

## Was dieser Benchmark nicht zeigt

* **Keine klinische Gültigkeit** — gemessen wird Übereinstimmung mit einer Rhythmus-Annotation.
* **Keine Aussage über Ektopie-Fälle.** Der eigentliche Zweck der P-Wellen-Stufe im Bestand ist,
  Fehlalarme durch Extrasystolen zu vermeiden (unregelmäßige RR **mit** P-Welle). Diese
  Datenbank annotiert Ektopie nicht getrennt; die Frage braucht die Arrhythmie-Datenbank und
  eine eigene Betrachtung.
* **Langzeit-EKG bei 250 Hz**, nicht 20-Minuten-Routine bei höherer Abtastrate. Für ein
  Verfahren, das auf einem Zeitfenster von −250 bis −60 ms vor der R-Zacke arbeitet, ist die
  Abtastrate keine Nebensache: 250 Hz bedeuten 4 ms je Abtastwert und damit rund 48 Werte im
  P-Fenster.

## Durchführung

    python3 benchmarks/run_pwave.py 04015                 # Kontrollpunkt
    python3 benchmarks/run_pwave.py --all --csv benchmarks/results/pwave_alle23.csv

Setzt die AFib-Datenbank voraus (`benchmarks/fetch_afdb.py --all`, ~640 MB — Downloadzeit
siehe docs/BENCHMARK_AFIB.md). Für die Patientenebene (Schritt 4) kommt die Normal-Sinus-
Datenbank dazu (`benchmarks/fetch_nsrdb.py --all`, ~630 MB, bei uns 20–30 min).

Ergebnisse siehe unten.

---

# Schritt 2 — Kontrollpunkt (nicht abgebrochen)

Zweck: Läuft das Verfahren auf diesen Daten, wie lange dauert es, und **trennt** die Kohärenz
überhaupt? Erst wenn das steht, lohnt sich ein Lauf über 234 Stunden.

Geprüft an zwei bewusst gegensätzlich zusammengesetzten Aufnahmen, damit ein Ergebnis nicht
an der Eigenart einer einzelnen hängt:

| Aufnahme | Fenster | davon AFib |
|---|---|---|
| 04746 | 1.220 | 647 (53 %) |
| 04015 | 1.176 | 7 (0,6 %) |
| 06426 | 918 | 877 (96 %) |

Aufnahme 04015 allein wäre als Kontrollpunkt untauglich gewesen — sieben AFib-Fenster tragen
keine Aussage über eine Trennung. Die Auswahl richtet sich nach der Klassenbesetzung, nicht
nach dem Ergebnis.

## Das Verfahren trennt

| | Median | Quartile |
|---|---|---|
| **AFib-Fenster** | **0,53–0,58** | 0,43–0,69 |
| **Nicht-AFib-Fenster** | **0,95–0,97** | 0,94–0,98 |

Abstand der Mediane rund **0,4**, und die Quartilsbereiche überschneiden sich kaum: Das obere
Quartil der AFib-Fenster liegt bei 0,61–0,69, das untere der unauffälligen bei 0,94.
**Kein einziges Fenster war nicht auswertbar** — die Sorge, 250 Hz könnten die
Ensemble-Mittelung nicht tragen, hat sich nicht bestätigt.

Die Werte passen zu den drei Referenzfällen aus dem Bestand (Sinusrhythmus 0,99, Ektopie 0,83,
Vorhofflimmern 0,41) und bestätigen sie erstmals an großer Zahl.

**Die Abbruchbedingung greift nicht.**

## Die bestehende Schwelle steht weit unterhalb der Trennung

An der unveränderten Schwelle (Kohärenz < 0,35):

| Aufnahmen | Sensitivität | Spezifität | Vorhersagewert |
|---|---|---|---|
| 04746 | 12,98 % | 100,00 % | 100,00 % |
| 04015 + 06426 | 12,90 % | 99,92 % | 99,13 % |

Beide Male rund **13 %** — der Schnitt bei 0,35 liegt unterhalb fast aller AFib-Fenster, deren
Masse zwischen 0,43 und 0,69 sitzt. Er ist damit extrem konservativ: Was er meldet, stimmt
praktisch immer, aber er meldet sehr wenig.

Das erklärt sich aus seiner Herkunft: Der einzige AFib-Referenzfall im Bestand hatte eine
Kohärenz von 0,41, und die Schwelle wurde darunter gesetzt. An 2.094 annotierten Fenstern
zeigt sich, dass 0,41 am **unteren Rand** der AFib-Verteilung liegt und nicht in ihrer Mitte.

**Die Schwelle wird hier nicht angepasst** — das bleibt Regel dieses Benchmarks. Der Befund
wird berichtet, die Entscheidung liegt beim Betreiber.

## Laufzeit

Rund 15 Sekunden je Aufnahme, also etwa **6 Minuten** für alle 23. Der volle Lauf ist
unproblematisch.

