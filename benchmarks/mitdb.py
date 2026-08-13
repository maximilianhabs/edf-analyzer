"""Zugriff auf MIT-BIH-Aufnahmen — Signal, Annotationen, Kanalwahl.

Bewusst getrennt vom Auswertungscode: Was gelesen wird, entscheidet über jede spätere
Kennzahl, und diese Entscheidungen sollen an einer Stelle stehen und einzeln prüfbar sein.
Die Regeln stammen aus `docs/BENCHMARK_QRS.md`, die vor der ersten Messung geschrieben wurde.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data"

#: Schlag-Symbole nach `wfdb.io.annotation.ann_label_table` — jedes davon beschreibt einen
#: tatsächlichen Herzschlag mit QRS-Komplex.
#:
#: Zwei Fälle, die beim Aufbau des Benchmarks Zahlen verschoben haben und deshalb ausdrücklich
#: begründet sind:
#:
#:   * **`!` gehört DAZU** — „Ventricular flutter wave". Bei Kammerflattern markiert sie die
#:     einzelnen Ausschläge; ein QRS-Detektor soll sie finden. In Aufnahme 207 sind das 472
#:     von 2332 Schlägen, also ein Fünftel. Ohne sie sähe jeder Detektor dort um 20 % zu
#:     schlecht aus (erste Fassung dieser Liste hatte sie vergessen, der Test hat es gefunden).
#:   * **`x` gehört NICHT dazu** — „Non-conducted P-wave (blocked APB)". Dort ist eine
#:     P-Welle ohne nachfolgenden QRS-Komplex; es gibt nichts zu detektieren. Manche
#:     veröffentlichten Schlagtabellen zählen sie mit, weshalb deren Gesamtzahlen um wenige
#:     Schläge höher liegen (Aufnahme 108: 1774 statt 1763). Für einen QRS-Benchmark wäre das
#:     falsch — jeder Detektor bekäme falsch-negative für Schläge, die es nicht gibt.
#:
#: Ebenfalls nicht gezählt: `+` (Rhythmuswechsel), `~` (Signalqualität), `|` (isolierter
#: Artefakt), `[`/`]` (Beginn/Ende Kammerflattern), `"` (Kommentar).
BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ?!")

#: Anfangsstück, das verworfen wird: adaptive Schwellen brauchen Einlaufzeit, und ein Detektor
#: dafür zu bestrafen misst die Einschwingphase statt der Detektion.
SKIP_START_S = 5.0


@dataclass(frozen=True)
class Record:
    name: str
    signal: np.ndarray      # gewählter Kanal, in mV
    fs: float
    beats: np.ndarray       # Sample-Indizes der annotierten Schläge
    channel: str            # Name des gewählten Kanals
    n_beats_total: int      # vor dem Verwerfen des Anfangs

    @property
    def duration_s(self) -> float:
        return len(self.signal) / self.fs


def lade(record: int | str, data_dir: Path = DATA) -> Record:
    """Liest eine Aufnahme nach den Regeln aus docs/BENCHMARK_QRS.md.

    Kanalwahl: **erster Kanal** der Aufnahme. Nicht der beste, nicht der mit den schönsten
    Zahlen — der erste. Bei den meisten MIT-BIH-Aufnahmen ist das MLII; wo nicht, gibt
    `Record.channel` es aus und die Auswertung protokolliert es mit.
    """
    import wfdb

    pfad = str(Path(data_dir) / str(record))
    rec = wfdb.rdrecord(pfad)
    ann = wfdb.rdann(pfad, "atr")

    signal = np.asarray(rec.p_signal[:, 0], dtype=float)
    fs = float(rec.fs)

    ist_schlag = np.array([s in BEAT_SYMBOLS for s in ann.symbol], dtype=bool)
    beats_alle = np.asarray(ann.sample, dtype=np.int64)[ist_schlag]

    ab = int(SKIP_START_S * fs)
    beats = beats_alle[beats_alle >= ab]

    return Record(name=str(record), signal=signal, fs=fs, beats=beats,
                  channel=rec.sig_name[0], n_beats_total=int(beats_alle.size))
