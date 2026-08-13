"""Abgleich zwischen detektierten und annotierten R-Zacken.

Das Herzstück des Benchmarks — und die zweite Stelle, an der ein Fehler schöne Zahlen
erzeugt, die nichts bedeuten. Ein zu großzügiger Abgleich lässt jeden Detektor gut aussehen,
ein falsch zugeordneter macht alle gleich schlecht; beides fällt an den Kennzahlen selbst
nicht auf, weil sie plausibel bleiben.

Deshalb wird dieser Code **gegen konstruierte Fälle** geprüft, deren Ergebnis vorher feststeht
(`test_matching.py`), nicht gegen echte Aufnahmen. Bei echten Daten kennt man die richtige
Antwort ja gerade nicht.

Regeln aus `docs/BENCHMARK_QRS.md`:

* Toleranzfenster ±150 ms (ANSI/AAMI EC57), Grenze eingeschlossen
* **eindeutige** Zuordnung: jede Annotation höchstens ein Treffer, jede Detektion höchstens
  einer Annotation
* bei mehreren Kandidaten gewinnt der zeitlich nächste
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Toleranz nach ANSI/AAMI EC57. Bei sehr hohen Frequenzen (Kammerflattern in Aufnahme 207,
#: RR teils unter 250 ms) überlappen sich die Fenster benachbarter Schläge — deshalb ist die
#: Eindeutigkeit der Zuordnung keine Feinheit, sondern notwendig.
TOLERANZ_MS = 150.0


@dataclass(frozen=True)
class MatchResult:
    tp: int
    fp: int
    fn: int
    #: Zeitfehler der Treffer in ms (Detektion − Annotation), positiv = Detektion später.
    offsets_ms: np.ndarray

    @property
    def sensitivity(self) -> float:
        nenner = self.tp + self.fn
        return self.tp / nenner if nenner else float("nan")

    @property
    def ppv(self) -> float:
        """Positiver Vorhersagewert. Ohne jede Detektion nicht definiert — dann NaN, nicht 0:
        ein Detektor, der nichts findet, hat keinen schlechten PPV, sondern gar keinen."""
        nenner = self.tp + self.fp
        return self.tp / nenner if nenner else float("nan")

    @property
    def f1(self) -> float:
        se, pp = self.sensitivity, self.ppv
        if not np.isfinite(se) or not np.isfinite(pp) or (se + pp) == 0:
            return float("nan")
        return 2 * se * pp / (se + pp)

    @property
    def der(self) -> float:
        """Detektionsfehlerrate (FP + FN) / Anzahl Annotationen."""
        nenner = self.tp + self.fn
        return (self.fp + self.fn) / nenner if nenner else float("nan")

    @property
    def offset_mean_ms(self) -> float:
        return float(np.mean(self.offsets_ms)) if self.offsets_ms.size else float("nan")

    @property
    def offset_sd_ms(self) -> float:
        return float(np.std(self.offsets_ms, ddof=1)) if self.offsets_ms.size > 1 else float("nan")

    @property
    def offset_abs_mean_ms(self) -> float:
        """Mittlerer BETRAG des Zeitfehlers. Der vorzeichenbehaftete Mittelwert kann nahe null
        liegen, obwohl jede einzelne Detektion weit danebenliegt — für die HRV zählt der
        Betrag, denn Streuung erzeugt künstliche RMSSD."""
        return float(np.mean(np.abs(self.offsets_ms))) if self.offsets_ms.size else float("nan")


def match(annotations: np.ndarray, detections: np.ndarray, fs: float,
          toleranz_ms: float = TOLERANZ_MS) -> MatchResult:
    """Ordnet Detektionen den Annotationen zu und zählt TP/FP/FN.

    Beide Eingaben sind Sample-Indizes und müssen aufsteigend sortiert sein. Ein etwaiges
    Verwerfen des Aufnahmeanfangs muss VORHER geschehen sein, und zwar für beide Reihen —
    sonst zählt man Schläge als verpasst, die man gar nicht suchen durfte.

    **Zuordnungsverfahren:** alle Paare innerhalb der Toleranz werden nach Abstand aufsteigend
    abgearbeitet; das nächstliegende freie Paar gewinnt. Das ist deterministisch und behandelt
    den Fall überlappender Fenster korrekt — eine einfache Reihenfolge-nach-Zeit-Zuordnung
    würde bei zwei eng benachbarten Annotationen die falsche bedienen.
    """
    ann = np.asarray(annotations, dtype=np.int64)
    det = np.asarray(detections, dtype=np.int64)
    if ann.size and np.any(np.diff(ann) < 0):
        raise ValueError("Annotationen sind nicht aufsteigend sortiert")
    if det.size and np.any(np.diff(det) < 0):
        raise ValueError("Detektionen sind nicht aufsteigend sortiert")

    tol = toleranz_ms / 1000.0 * fs

    if ann.size == 0 or det.size == 0:
        return MatchResult(tp=0, fp=int(det.size), fn=int(ann.size),
                           offsets_ms=np.empty(0, dtype=float))

    # Kandidatenpaare einsammeln: je Annotation nur die Detektionen im Fenster. searchsorted
    # statt einer doppelten Schleife — bei 110.000 Schlägen ist das der Unterschied zwischen
    # Sekunden und Minuten.
    links = np.searchsorted(det, ann - tol, side="left")
    rechts = np.searchsorted(det, ann + tol, side="right")

    paare = []
    for i in range(ann.size):
        for j in range(links[i], rechts[i]):
            paare.append((abs(int(det[j]) - int(ann[i])), i, j))

    # Nach Abstand sortieren; bei Gleichstand entscheiden die Indizes, damit das Ergebnis
    # reproduzierbar ist und nicht von der Sortierstabilität abhängt.
    paare.sort()

    ann_belegt = np.zeros(ann.size, dtype=bool)
    det_belegt = np.zeros(det.size, dtype=bool)
    offsets = []
    for _, i, j in paare:
        if ann_belegt[i] or det_belegt[j]:
            continue
        ann_belegt[i] = det_belegt[j] = True
        offsets.append((int(det[j]) - int(ann[i])) / fs * 1000.0)

    tp = int(ann_belegt.sum())
    return MatchResult(tp=tp,
                       fp=int(det.size - tp),
                       fn=int(ann.size - tp),
                       offsets_ms=np.asarray(offsets, dtype=float))
