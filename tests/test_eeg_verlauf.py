"""Repräsentativer Verlauf neben dem „besten Grundrhythmus" (Review R7, 02.10.2026).

Konstruiertes Signal mit bekannter Antwort: 5 min reines Alpha (10 Hz), dann 5 min reines
Theta (6 Hz). Das Bestwert-Fenster muss im Alpha-Teil liegen und dort ~100 % Alpha zeigen.
Der Verlauf muss die Verlangsamung sichtbar machen: Median der Alpha-Anteile um 50 %.
"""
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

FS = 200


def _signal():
    t = np.arange(FS * 300) / FS
    rng = np.random.default_rng(0)
    alpha = 30 * np.sin(2 * np.pi * 10 * t)
    theta = 30 * np.sin(2 * np.pi * 6 * t)
    return np.concatenate([alpha, theta]) + rng.normal(0, 0.5, FS * 600)


def test_bestwert_fenster_liegt_im_alpha_teil():
    from analysis.glory_report import _best_alpha_window
    bt, wl = _best_alpha_window(_signal(), FS, 600.0, [])
    assert bt is not None and bt + wl <= 300.0


def test_verlauf_zeigt_die_verlangsamung():
    from analysis.eeg_course import representative_course
    v = representative_course(_signal(), FS, [])
    assert v["n_abschnitte"] == 10 and v["n_sauber"] == 10
    alpha = v["zusammenfassung"]["Alpha relativ"]
    assert alpha["max"] > 95 and alpha["min"] < 5
    assert 5 < alpha["median"] < 95, "Median verdeckt die Verlangsamung nicht"
    assert alpha["q25"] < 10 and alpha["q75"] > 90


def test_artefaktabschnitte_fallen_heraus():
    from analysis.eeg_course import representative_course
    v = representative_course(_signal(), FS, [{"start_s": 300.0, "end_s": 600.0}])
    assert v["n_sauber"] == 5
    assert v["zusammenfassung"]["Alpha relativ"]["median"] > 95


def test_zu_wenige_saubere_abschnitte_ergeben_keine_aussage():
    from analysis.eeg_course import representative_course
    v = representative_course(_signal(), FS, [{"start_s": 0.0, "end_s": 480.0}])
    assert v["n_sauber"] == 2 and v["zusammenfassung"] == {}


def test_standardreport_zeigt_hauptfenster_und_verlauf():
    import core.shared as sh
    from analysis.report_export import collect_sections
    pfad = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")
    secs = collect_sections(sh.load_and_prepare(pfad), pfad, age=52)
    sec = next(s for s in secs if s["name"].startswith("EEG — Hauptfenster und Verlauf"))
    namen = [r[0] for r in sec["rows"]]
    assert "Hauptfenster" in namen and "Alpha relativ" in namen
    assert "bester Grundrhythmus" in sec["rows"][0][4]


def test_report_schreibt_keine_erwarteten_faelle_als_fehler_ins_log(caplog):
    """Ein normaler Report darf das Log nicht mit Tracebacks füllen: Dass es für manche
    HRV-Werte keine Normwerte gibt, ist kein Fehler. Gefunden am 03.10.2026, zehn Meldungen
    je Report."""
    import logging

    import core.shared as sh
    from analysis.report_export import collect_sections
    pfad = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")
    with caplog.at_level(logging.WARNING):
        collect_sections(sh.load_and_prepare(pfad), pfad, age=52)
    meldungen = [r.getMessage() for r in caplog.records if r.name.startswith(("analysis", "views", "core"))]
    assert not meldungen, meldungen
