"""Chunk 2: Der Abgleich wird gegen konstruierte Fälle geprüft, nicht gegen echte Daten.

Bei einer echten Aufnahme kennt man die richtige Antwort nicht — deshalb kann man an ihr auch
nicht prüfen, ob der Abgleich stimmt. Hier stehen die Eingaben und das erwartete Ergebnis
vorher fest, jeweils so gebaut, dass genau ein Fehlermuster auffällt.

Diese Datei ist die Grundlage jeder späteren Kennzahl. Wenn sie grün ist, misst der Benchmark
das, was er zu messen behauptet.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from matching import TOLERANZ_MS, match  # noqa: E402

FS = 360.0  # wie MIT-BIH


def schlaege(n=100, rr_ms=800.0, start_s=1.0):
    """Gleichmässige Schlagfolge als Sample-Indizes."""
    return np.round((start_s + np.arange(n) * rr_ms / 1000.0) * FS).astype(np.int64)


def ms(x):
    return int(round(x / 1000.0 * FS))


def test_identische_reihen_sind_perfekt():
    a = schlaege()
    r = match(a, a, FS)
    assert (r.tp, r.fp, r.fn) == (100, 0, 0)
    assert r.sensitivity == 1.0 and r.ppv == 1.0 and r.f1 == 1.0
    assert r.der == 0.0
    assert abs(r.offset_mean_ms) < 1e-9


def test_kleine_verschiebung_bleibt_ein_treffer():
    """50 ms liegen klar innerhalb der Toleranz — und der Zeitfehler muss sie ausweisen."""
    a = schlaege()
    r = match(a, a + ms(50), FS)
    assert (r.tp, r.fp, r.fn) == (100, 0, 0)
    assert abs(r.offset_mean_ms - 50) < 1.0, f"Zeitfehler {r.offset_mean_ms:.1f} ms statt 50"
    assert abs(r.offset_abs_mean_ms - 50) < 1.0


def test_grosse_verschiebung_trifft_nichts():
    """200 ms liegen ausserhalb — jede Detektion ist dann falsch-positiv UND jede Annotation
    verpasst. Ein Abgleich, der hier noch Treffer meldet, ist zu großzügig."""
    a = schlaege()
    r = match(a, a + ms(200), FS)
    assert (r.tp, r.fp, r.fn) == (0, 100, 100)
    assert r.sensitivity == 0.0 and r.ppv == 0.0


def test_die_toleranzgrenze_selbst():
    """Die Grenze ist eingeschlossen: genau 150 ms zählt noch, 151 ms nicht mehr. Ohne diesen
    Test bleibt unklar, ob am Rand < oder <= gilt — ein Unterschied, der bei Zehntausenden
    Schlägen sichtbar wird."""
    a = schlaege(10)
    assert match(a, a + ms(TOLERANZ_MS), FS).tp == 10
    assert match(a, a + ms(TOLERANZ_MS + 5), FS).tp == 0


def test_jeder_zweite_schlag_fehlt():
    a = schlaege(100)
    r = match(a, a[::2], FS)
    assert (r.tp, r.fp, r.fn) == (50, 0, 50)
    assert r.sensitivity == 0.5
    assert r.ppv == 1.0, "wer nichts erfindet, hat einen perfekten Vorhersagewert"


def test_doppelt_so_viele_detektionen():
    """Zwischen jeden echten Schlag eine erfundene Detektion — weit genug weg, um nicht
    zufällig zu treffen."""
    a = schlaege(100, rr_ms=800.0)
    erfunden = a[:-1] + ms(400)
    det = np.sort(np.concatenate([a, erfunden]))
    r = match(a, det, FS)
    assert r.tp == 100 and r.fn == 0
    assert r.fp == 99
    assert abs(r.ppv - 100 / 199) < 1e-9


def test_eine_r_zacke_zweimal_detektiert_zaehlt_einmal():
    """Der klassische Fehler. Ohne Eindeutigkeitszwang bekäme diese Annotation zwei Treffer,
    und der Detektor sähe besser aus, als er ist: aus einer Doppeldetektion würde ein
    zusätzlicher TP statt eines FP."""
    a = schlaege(10)
    det = np.sort(np.concatenate([a, a[3:4] + ms(30)]))
    r = match(a, det, FS)
    assert r.tp == 10, "mehr Treffer als Annotationen — Eindeutigkeit verletzt"
    assert r.fp == 1, "die zweite Detektion derselben Zacke muss falsch-positiv sein"
    assert r.fn == 0
    # Die Zeitfehlerliste muss genauso lang sein wie die Trefferzahl. Ohne diese Prüfung
    # bliebe eine verletzte Eindeutigkeit verborgen, weil TP über die belegten Annotationen
    # gezählt wird und dadurch ohnehin gedeckelt ist — die Offsets aber nicht.
    assert r.offsets_ms.size == r.tp, (
        f"{r.offsets_ms.size} Zeitfehler bei {r.tp} Treffern — eine Annotation wurde mehrfach "
        f"zugeordnet")


def test_bei_zwei_kandidaten_gewinnt_der_naehere():
    """Zwei Detektionen im Fenster derselben Annotation: die nähere wird Treffer, die weitere
    falsch-positiv. Und der Zeitfehler muss den der NÄHEREN ausweisen.

    Der Fall ist bewusst so gebaut, dass die nähere Detektion die ZWEITE in der Zeitreihe ist
    (−120 ms vs. +20 ms). Eine erste Fassung dieses Tests nahm +20/+120 ms — dort war die
    nähere zufällig auch die erste, und eine Zuordnung nach blosser Reihenfolge statt nach
    Nähe wäre unentdeckt geblieben (per Mutationsprobe festgestellt)."""
    a = np.array([ms(10000)], dtype=np.int64)
    det = np.array([a[0] - ms(120), a[0] + ms(20)], dtype=np.int64)
    r = match(a, det, FS)
    assert (r.tp, r.fp, r.fn) == (1, 1, 0)
    assert abs(r.offset_mean_ms - 20) < 1.0, (
        f"Zeitfehler {r.offset_mean_ms:.0f} ms — es wurde der weiter entfernte Kandidat "
        f"(−120 ms) zugeordnet statt des näheren (+20 ms)")


def test_eng_benachbarte_annotationen_konkurrieren_sauber():
    """Bei Kammerflattern (Aufnahme 207) liegen Schläge unter 250 ms auseinander, die
    ±150-ms-Fenster benachbarter Annotationen überlappen sich also. Genau dann muss die
    Eindeutigkeit greifen: zwei Annotationen dürfen sich nicht dieselbe Detektion teilen."""
    a = np.array([ms(10000), ms(10200)], dtype=np.int64)   # 200 ms Abstand
    det = np.array([ms(10100)], dtype=np.int64)            # 100 ms zu beiden
    r = match(a, det, FS)
    assert r.tp == 1, "eine Detektion kann nur einen Schlag belegen"
    assert r.fn == 1 and r.fp == 0


def test_leere_reihen():
    a = schlaege(10)
    leer = np.empty(0, dtype=np.int64)
    r = match(a, leer, FS)
    assert (r.tp, r.fp, r.fn) == (0, 0, 10)
    assert r.sensitivity == 0.0
    assert np.isnan(r.ppv), "ohne jede Detektion ist der Vorhersagewert nicht definiert"
    r2 = match(leer, a, FS)
    assert (r2.tp, r2.fp, r2.fn) == (0, 10, 0)


def test_unsortierte_eingabe_wird_abgelehnt():
    """Lieber ein Fehler als ein stilles Falschergebnis: `searchsorted` liefert bei
    unsortierter Eingabe Unsinn, ohne sich zu beschweren."""
    a = np.array([100, 50, 200], dtype=np.int64)
    with pytest.raises(ValueError, match="sortiert"):
        match(a, a, FS)


def test_zeitfehler_streuung_wird_berichtet():
    """Ein Detektor kann im Mittel exakt liegen und trotzdem stark streuen — für die HRV ist
    die Streuung das Problem, nicht der Mittelwert."""
    rng = np.random.default_rng(0)
    a = schlaege(200)
    jitter = np.round(rng.normal(0, ms(20), a.size)).astype(np.int64)
    r = match(a, np.sort(a + jitter), FS)
    assert r.tp == 200
    assert abs(r.offset_mean_ms) < 5, "Mittelwert sollte nahe null sein"
    assert 15 < r.offset_sd_ms < 25, f"Streuung {r.offset_sd_ms:.1f} ms, erwartet ~20"
    assert r.offset_abs_mean_ms > 10, "der Betrag darf sich nicht wegmitteln"
