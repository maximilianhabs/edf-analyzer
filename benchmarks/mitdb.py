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


def _kanal_wie_die_app(rec) -> int:
    """Index des Kanals, den die Anwendung selbst wählen würde.

    Ruft denselben Klassifizierer und dieselbe Rangfolge auf wie `core/shared.py` für
    `ecg_channels[0]` — Konfidenz zuerst, bei Gleichstand die amplituden-abgeschmolzene
    QRS-Formkonsistenz. Nicht nachgebaut, sondern importiert: eine zweite Fassung dieser
    Regel würde irgendwann von der echten abweichen, ohne dass es jemand merkt.
    """
    from core.channel_classifier import ECG, classify_channels

    daten = np.asarray(rec.p_signal, dtype=float).T / 1000.0   # mV → Volt wie in der App
    res = classify_channels(daten, list(rec.sig_name), float(rec.fs))

    def rang(name):
        r = res[name]
        p2p = r.features.get("p2p_mv", 0.0)
        tmpl = r.features.get("qrs_template_corr", 0.0)
        return (-r.confidence, -(tmpl * min(1.0, p2p / 0.3)))

    kandidaten = [c for c in rec.sig_name
                  if res[c].channel_type == ECG and res[c].confidence >= 60.0]
    if not kandidaten:                      # kein Kanal als EKG erkannt → Regel greift nicht
        return 0
    return list(rec.sig_name).index(min(kandidaten, key=rang))


def lade(record: int | str, data_dir: Path = DATA, kanal: str = "erster") -> Record:
    """Liest eine Aufnahme nach den Regeln aus docs/BENCHMARK_QRS.md.

    `kanal="erster"` (Vorgabe): **erster Kanal** der Aufnahme. Nicht der beste, nicht der mit
    den schönsten Zahlen — der erste. Das ist die Regel, unter der die veröffentlichten
    MIT-BIH-Zahlen zustande kommen, und sie schliesst nachträgliche Rosinenpickerei aus.

    `kanal="app"`: der Kanal, den die **Anwendung selbst** wählen würde. Das weicht bei
    **19 der 44 Aufnahmen** vom ersten Kanal ab — deutlich mehr als die eine Aufnahme, bei der
    MLII gar nicht an erster Stelle steht. Beide Betriebsarten werden berichtet: die erste ist
    mit der Literatur vergleichbar, die zweite beschreibt, was Anwender tatsächlich bekommen.
    Die Ergebnisse stehen in docs/BENCHMARK_QRS.md.
    """
    import wfdb

    pfad = str(Path(data_dir) / str(record))
    rec = wfdb.rdrecord(pfad)
    ann = wfdb.rdann(pfad, "atr")

    if kanal not in ("erster", "app"):
        raise ValueError(f"kanal muss 'erster' oder 'app' sein, nicht {kanal!r}")
    idx = 0 if kanal == "erster" else _kanal_wie_die_app(rec)

    signal = np.asarray(rec.p_signal[:, idx], dtype=float)
    fs = float(rec.fs)

    ist_schlag = np.array([s in BEAT_SYMBOLS for s in ann.symbol], dtype=bool)
    beats_alle = np.asarray(ann.sample, dtype=np.int64)[ist_schlag]

    ab = int(SKIP_START_S * fs)
    beats = beats_alle[beats_alle >= ab]

    return Record(name=str(record), signal=signal, fs=fs, beats=beats,
                  channel=rec.sig_name[idx], n_beats_total=int(beats_alle.size))
