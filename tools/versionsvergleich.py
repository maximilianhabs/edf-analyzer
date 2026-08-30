"""Kennwerte der Fixture-Aufnahmen als JSON — zum Vergleich zweier Umgebungen.

Anlass: Der Wechsel des Basis-Images von Python 3.9 auf 3.12 (August 2026). Nicht die
Python-Version selbst ist dabei das Risiko, sondern was sie nach sich zieht: Auf 3.9
installiert pip `numpy 2.0.2` — die letzte Version mit 3.9-Rädern —, auf 3.12 dagegen 2.1
oder neuer. Damit ändern sich möglicherweise BLAS-Pfade und FFT-Implementierungen, und
Kennwerte wandern in den hinteren Stellen.

Die Ground-Truth-Tests fangen grobe Fehler, arbeiten aber mit Toleranzen. Eine
systematische Verschiebung um wenige Promille rutscht durch und fällt erst auf, wenn zwei
Befunde derselben Aufnahme aus verschiedenen Monaten nebeneinanderliegen. Dieses Skript
macht solche Verschiebungen sichtbar, bevor sie in einen Report geraten.

    # in der alten Umgebung (Referenz einfrieren)
    python tools/versionsvergleich.py > /tmp/kennwerte-py39.json

    # in der neuen Umgebung
    python tools/versionsvergleich.py > /tmp/kennwerte-py312.json

    # vergleichen
    python tools/versionsvergleich.py --diff /tmp/kennwerte-py39.json /tmp/kennwerte-py312.json

Alles läuft deterministisch: feste Seeds, feste Fixture-Dateien, keine Zufallsauswahl.
Zwei Läufe in derselben Umgebung müssen Zeichen für Zeichen dasselbe ergeben — sonst ist
das Skript kaputt und nicht die Umgebung.

Bewusst 3.9-tauglich geschrieben (keine moderne Syntax), damit es in beiden Umgebungen
läuft.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "fixtures")
DATEIEN = ("test_edf_datei.edf", "test_edf_afib.edf")

# SIGNIFIKANTE Stellen, nicht Nachkommastellen. Der Unterschied ist hier
# entscheidend: MNE liefert Daten in Volt, EEG-Amplituden liegen bei ~5e-5 V und
# Bandleistungen entsprechend bei ~1e-11. Eine Rundung auf 9 NACHKOMMAstellen
# macht daraus glatt 0.0 -- der gesamte EEG-Teil des Vergleichs waere blind
# gewesen (beim ersten Messlauf genau so passiert). Mit 9 signifikanten Stellen
# bleibt die Aufloesung unabhaengig von der Groessenordnung erhalten.
STELLEN = 9


def _z(wert):
    """Zahl auf feste Stellen runden; alles Nicht-Endliche wird benannt statt verschluckt."""
    try:
        f = float(wert)
    except (TypeError, ValueError):
        return None
    if np.isnan(f):
        return "nan"
    if np.isinf(f):
        return "inf" if f > 0 else "-inf"
    if f == 0.0:
        return 0.0
    return float("%.*g" % (STELLEN, f))


def umgebung():
    """Womit gerechnet wurde — die Erklärung für jede spätere Abweichung."""
    aus = {"python": platform.python_version()}
    for name in ("numpy", "scipy", "mne", "pyedflib", "pandas"):
        try:
            modul = __import__(name)
            aus[name] = getattr(modul, "__version__", "?")
        except ImportError:
            aus[name] = "fehlt"
    return aus


def eeg_kennwerte(sig, sfreq):
    """Spektrum, aperiodischer Anteil und Komplexität eines Kanals."""
    aus = {}
    from analysis.aperiodic import fit_aperiodic, welch_psd
    from analysis.spectral import _band_power

    f, p = welch_psd(sig, sfreq)
    aus["psd_summe"] = _z(np.sum(p))
    aus["psd_stuetzstellen"] = int(len(f))
    for name, lo, hi in (("delta", 0.5, 4.0), ("theta", 4.0, 8.0),
                         ("alpha", 8.0, 13.0), ("beta", 13.0, 30.0)):
        aus["band_" + name] = _z(_band_power(f, p, lo, hi))

    try:
        # fit_aperiodic gibt ein dict zurueck (offset, exponent, r2, ...) oder
        # None, wenn zu wenige Stuetzstellen im Fit-Bereich liegen.
        fit = fit_aperiodic(f, p)
        if not fit:
            aus["aperiodisch"] = "kein Fit"
        else:
            for schluessel in ("exponent", "offset", "r2"):
                aus["aperiodisch_" + schluessel] = _z(fit.get(schluessel))
    except Exception as fehler:                                    # noqa: BLE001
        aus["aperiodisch"] = "FEHLER: " + type(fehler).__name__

    from analysis.complexity import permutation_entropy, sample_entropy

    # Auf einen festen Ausschnitt begrenzt: sample_entropy ist quadratisch in der
    # Länge, der volle Kanal würde den Vergleich unnötig lange laufen lassen.
    kurz = np.asarray(sig[: int(30 * sfreq)], dtype=float)
    aus["permutationsentropie"] = _z(permutation_entropy(kurz))
    aus["sample_entropie"] = _z(sample_entropy(kurz))
    return aus


def ekg_kennwerte(sig, sfreq):
    """R-Zacken, RR-Reihe und HRV in Zeit- und Frequenzdomäne."""
    aus = {}
    from analysis.ecg import build_rr_series, compute_hrv_time_domain, detect_r_peaks

    peaks = detect_r_peaks(np.asarray(sig, dtype=float), sfreq)
    aus["r_zacken_anzahl"] = int(len(peaks))
    aus["r_zacken_erste"] = int(peaks[0]) if len(peaks) else None
    aus["r_zacken_letzte"] = int(peaks[-1]) if len(peaks) else None

    reihe = build_rr_series(peaks, sfreq)
    if reihe is None:
        aus["rr_reihe"] = "keine"
        return aus

    rr = np.asarray(getattr(reihe, "rr_ms", []), dtype=float)
    aus["rr_anzahl"] = int(len(rr))
    aus["rr_mittel"] = _z(np.mean(rr)) if len(rr) else None

    for schluessel, wert in sorted(compute_hrv_time_domain(rr).items()):
        aus["hrv_" + schluessel] = _z(wert)

    try:
        from analysis.hrv_freq import band_power, psd_welch, resample_rr

        t_s = np.cumsum(rr) / 1000.0
        gerade = resample_rr(rr, t_s)
        even = gerade[0] if isinstance(gerade, tuple) else gerade
        fr, ps = psd_welch(np.asarray(even, dtype=float))
        aus["hrv_lf"] = _z(band_power(fr, ps, (0.04, 0.15)))
        aus["hrv_hf"] = _z(band_power(fr, ps, (0.15, 0.40)))
    except Exception as fehler:                                    # noqa: BLE001
        aus["hrv_frequenz"] = "FEHLER: " + type(fehler).__name__
    return aus


def datei_kennwerte(pfad):
    """Alle Kennwerte einer Aufnahme. Kanalauswahl fest, damit der Vergleich trägt."""
    from core.loader import load_edf

    raw = load_edf(pfad)
    sfreq = float(raw.info["sfreq"])
    namen = list(raw.ch_names)
    aus = {
        "sfreq": _z(sfreq),
        "kanaele": len(namen),
        "dauer_s": _z(raw.n_times / sfreq),
        "kanalnamen": namen[:8],
    }

    daten = raw.get_data()
    aus["signal_pruefsumme"] = _z(float(np.sum(np.abs(daten))))

    # Erster Kanal als EEG-Vertreter — die Auswahl muss fest sein, sonst
    # vergleicht man zwei verschiedene Signale statt zweier Umgebungen.
    aus["eeg_kanal"] = namen[0]
    aus["eeg"] = eeg_kennwerte(daten[0], sfreq)

    ekg_index = next(
        (i for i, n in enumerate(namen) if any(s in n.upper() for s in ("ECG", "EKG", "POL X1"))),
        None,
    )
    if ekg_index is None:
        aus["ekg"] = "kein EKG-Kanal erkannt"
    else:
        aus["ekg_kanal"] = namen[ekg_index]
        aus["ekg"] = ekg_kennwerte(daten[ekg_index], sfreq)
    return aus


def erheben():
    ergebnis = {"umgebung": umgebung(), "dateien": {}}
    for name in DATEIEN:
        pfad = os.path.join(FIXTURES, name)
        if not os.path.exists(pfad):
            ergebnis["dateien"][name] = "FEHLT"
            continue
        try:
            ergebnis["dateien"][name] = datei_kennwerte(pfad)
        except Exception as fehler:                                # noqa: BLE001
            ergebnis["dateien"][name] = "FEHLER: %s: %s" % (type(fehler).__name__, fehler)
    return ergebnis


def flach(d, praefix=""):
    """Verschachteltes dict zu 'a.b.c' -> Wert, damit sich zwei Läufe zeilenweise vergleichen lassen."""
    aus = {}
    for schluessel in sorted(d):
        wert = d[schluessel]
        pfad = praefix + "." + str(schluessel) if praefix else str(schluessel)
        if isinstance(wert, dict):
            aus.update(flach(wert, pfad))
        else:
            aus[pfad] = wert
    return aus


def vergleichen(pfad_alt, pfad_neu):
    with open(pfad_alt) as f:
        alt = flach(json.load(f))
    with open(pfad_neu) as f:
        neu = flach(json.load(f))

    print("=== Umgebungen ===")
    for schluessel in sorted(k for k in set(alt) | set(neu) if k.startswith("umgebung.")):
        print("  %-22s %-12s -> %s" % (schluessel[9:], alt.get(schluessel, "-"), neu.get(schluessel, "-")))

    print("\n=== Kennwerte ===")
    identisch = 0
    abweichungen = []
    for schluessel in sorted(k for k in set(alt) | set(neu) if not k.startswith("umgebung.")):
        a, n = alt.get(schluessel), neu.get(schluessel)
        if a == n:
            identisch += 1
            continue
        rel = None
        if isinstance(a, (int, float)) and isinstance(n, (int, float)) and a not in (0, None):
            rel = abs(n - a) / abs(a)
        abweichungen.append((schluessel, a, n, rel))

    print("  %d Kennwerte identisch" % identisch)
    if not abweichungen:
        print("\nKeine Abweichung. Die Umgebungen rechnen identisch.")
        return 0

    print("  %d Kennwerte abweichend:\n" % len(abweichungen))
    ernst = 0
    for schluessel, a, n, rel in abweichungen:
        if rel is None:
            einordnung = "nicht numerisch"
        elif rel < 1e-9:
            einordnung = "Rundungsrauschen"
        elif rel < 1e-6:
            einordnung = "unkritisch (< 1 ppm)"
        elif rel < 1e-3:
            einordnung = "PRUEFEN (< 0,1 %)"
            ernst += 1
        else:
            einordnung = "RELEVANT (>= 0,1 %)"
            ernst += 1
        print("  %s" % schluessel)
        print("    alt: %s" % a)
        print("    neu: %s" % n)
        if rel is not None:
            print("    rel. Abweichung: %.2e  -> %s" % (rel, einordnung))
        else:
            print("    -> %s" % einordnung)
        print()

    if ernst:
        print("%d Abweichung(en) ueber 1 ppm. Ursache klaeren, bevor deployed wird." % ernst)
        return 1
    print("Alle Abweichungen im Bereich des Fliesskomma-Rauschens.")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diff", nargs=2, metavar=("ALT", "NEU"), help="zwei Ergebnisdateien vergleichen")
    args = p.parse_args()
    if args.diff:
        sys.exit(vergleichen(args.diff[0], args.diff[1]))
    json.dump(erheben(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
