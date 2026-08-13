"""Chunk 1: Wird die Datenbank überhaupt richtig gelesen?

Diese Prüfung steht bewusst VOR jeder Auswertung. Der Annotationsfilter entscheidet über
jede spätere Kennzahl: zählt er eine Rhythmusmarke als Schlag mit, sinkt der positive
Vorhersagewert aller Detektoren gleichermassen — und niemand merkt es, weil die Zahlen
plausibel bleiben und alle Detektoren gleich betroffen sind.

Geprüft wird deshalb gegen die in der Datenbank-Dokumentation veröffentlichten Schlagzahlen.

Läuft nur, wenn die Daten lokal liegen (`python3 benchmarks/fetch_mitdb.py 100 108`);
sonst übersprungen — die CI lädt keine 500 MB.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: Aufnahme → Zahl der Schlag-Annotationen nach der WFDB-Definition (`ann_label_table`).
#:
#: Bei 108 weicht der Wert um 11 von manchen veröffentlichten Tabellen ab: die zählen `x`
#: (nicht übergeleitete P-Welle) mit. Dort gibt es keinen QRS-Komplex — für einen
#: QRS-Benchmark wäre das Mitzählen falsch, siehe mitdb.BEAT_SYMBOLS.
ERWARTET = {100: 2273, 108: 1763, 203: 2980, 222: 2483, 207: 2332}


def _record(nr):
    from mitdb import DATA, lade
    if not (DATA / f"{nr}.dat").exists():
        pytest.skip(f"Aufnahme {nr} nicht geladen — python3 benchmarks/fetch_mitdb.py {nr}")
    return lade(nr)


@pytest.mark.parametrize("nr", sorted(ERWARTET))
def test_schlagzahl_stimmt_mit_der_datenbankdoku(nr):
    r = _record(nr)
    assert r.n_beats_total == ERWARTET[nr], (
        f"Aufnahme {nr}: {r.n_beats_total} Schlag-Annotationen gelesen, dokumentiert sind "
        f"{ERWARTET[nr]}. Der Annotationsfilter (BEAT_SYMBOLS) stimmt nicht — das würde "
        f"jede nachfolgende Kennzahl verschieben.")


def test_signal_und_zeitachse_sind_plausibel():
    r = _record(100)
    assert r.fs == 360.0, f"Abtastrate {r.fs} Hz — MIT-BIH ist 360 Hz"
    assert 29 < r.duration_s / 60 < 31, f"Dauer {r.duration_s/60:.1f} min, erwartet ~30"
    assert r.channel == "MLII"
    # Die Signalwerte sind in mV; ein EKG bewegt sich im Bereich weniger mV.
    assert 0.5 < float(abs(r.signal).max()) < 10.0, "Amplitude nicht im mV-Bereich"


def test_anfang_wird_verworfen_und_zwar_bei_beiden():
    """Die ersten 5 s fallen weg. Entscheidend ist, dass das für Annotationen UND
    Detektionen gilt — sonst zählt man Schläge als verpasst, die man gar nicht suchen
    durfte."""
    from mitdb import SKIP_START_S
    r = _record(100)
    assert r.beats.min() >= SKIP_START_S * r.fs
    assert r.beats.size < r.n_beats_total, "es wurde gar nichts verworfen"
    # Bei ~72 bpm sind 5 s rund 6 Schläge — grob plausibel, nicht die halbe Aufnahme.
    assert r.n_beats_total - r.beats.size < 20


def test_nichtschlag_symbole_zaehlen_nicht_mit():
    """Die Abgrenzung, an der die erste Fassung gescheitert ist — in beide Richtungen.

    `!` (Kammerflatterwelle) MUSS zählen: in Aufnahme 207 sind das 472 von 2332 Schlägen.
    `x` (nicht übergeleitete P-Welle) darf NICHT zählen: dort ist kein QRS-Komplex, ein
    Detektor kann ihn nicht finden und bekäme sonst falsch-negative für Schläge, die es
    nicht gibt.
    """
    from mitdb import BEAT_SYMBOLS
    assert "!" in BEAT_SYMBOLS, "Kammerflatterwellen fehlen — 207 sähe 20 % zu schlecht aus"
    for kein_schlag in ("x", "+", "~", "|", "[", "]", '"', "="):
        assert kein_schlag not in BEAT_SYMBOLS, f"{kein_schlag!r} markiert keinen Schlag"


def test_symbolliste_deckt_sich_mit_der_wfdb_tabelle():
    """Jedes Symbol unserer Liste muss in der WFDB-Tabelle vorkommen. Ein Tippfehler in der
    Zeichenkette fiele sonst nur dadurch auf, dass irgendwo ein paar Schläge fehlen."""
    import wfdb.io.annotation as A
    from mitdb import BEAT_SYMBOLS
    bekannt = set(A.ann_label_table["symbol"])
    unbekannt = BEAT_SYMBOLS - bekannt
    assert not unbekannt, f"unbekannte Symbole in BEAT_SYMBOLS: {sorted(unbekannt)}"
