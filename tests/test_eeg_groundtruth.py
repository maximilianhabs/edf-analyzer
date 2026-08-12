"""EEG-Sollwerte der synthetischen Fixture — die Gegenprobe zur Methoden-Registry.

Die Fixture `tests/fixtures/test_edf_datei.edf` trägt seit ihrer Erzeugung dokumentierte
Sollwerte im Manifest: Alpha bei 10 Hz mit kanalweise festgelegten Amplituden, 1/f-Exponent
2,2, ein Artefakt-Burst bei 240–245 s. Geprüft wurde davon bisher **nur die EKG-Seite** —
Alpha, Aperiodik, Asymmetrie und Artefakt standen dokumentiert da und wurden von keinem Test
angefasst. Sie waren einmal manuell verifiziert worden; seither hätte jede Regression
unbemerkt bleiben können.

Jeder Test hier ist zugleich der Beleg für einen Eintrag in `analysis/methods.py`. Wo ein
Test steht, darf die Methode `implementation-validated` heißen — und nur dort.

Geprüft wird über die Funktionen, die die App tatsächlich aufruft (`views/eeg_spectrum.py`),
nicht über nachgebaute Formeln. Ein Test gegen eine Zweitimplementierung würde beweisen, dass
zwei Rechnungen übereinstimmen, nicht dass die ausgelieferte richtig ist.
"""
import json
import os
import sys
import warnings

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")
MANIFEST = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei_manifest.json")

# Oberhalb von ~25 Hz ist die Fixture NICHT mehr als 1/f-Wahrheit brauchbar: die Datei wird mit
# physikalischem Bereich ±500 µV und 16 Bit geschrieben, die Quantisierungsstufe liegt also bei
# 1000/65536 ≈ 0,0153 µV. Deren weisses Rauschen ist frequenzunabhängig, während das
# 1/f^2,2-Signal zu hohen Frequenzen hin praktisch verschwindet — ab etwa 40 Hz dominiert der
# Quantisierungsboden und flacht die gemessene Steigung auf ~1,3 ab (nachgemessen: 3–20 Hz
# 2,81 mit Alpha-Gipfel, 40–60 Hz 1,72, 60–90 Hz 1,26; eine rein rechnerisch erzeugte
# Kontrollreihe ohne EDF-Umweg liegt über denselben Bereiche flach bei 2,18–2,25).
# Deshalb wird der Fixture-Fit bewusst über 1–20 Hz geführt. Das ist KEINE aufgeweichte
# Toleranz, sondern der Bereich, in dem die Datei die behauptete Wahrheit überhaupt trägt.
APERIODIC_FIT_RANGE = (1.0, 20.0)


@pytest.fixture(scope="module")
def edf():
    from core.shared import load_and_prepare
    return load_and_prepare(FIXTURE)


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


def _psd(edf, ch, multitaper=False):
    from views.eeg_spectrum import _compute_psd, _highpass
    sig = edf["data"][edf["ch_idx"][ch]].astype(float)
    return _compute_psd(_highpass(sig, edf["sfreq"]), edf["sfreq"], multitaper=multitaper)


# ── Alpha-Peak ───────────────────────────────────────────────────────────────────────────

def test_alpha_peak_cog_auf_allen_kanaelen(edf, manifest):
    """Beleg für: „Alpha-Peak (CoG, Default)". Der Schwerpunkt muss den eingebauten
    10-Hz-Rhythmus auf JEDEM der 19 Kanäle finden — auch auf den frontalen mit nur 3 µV
    Amplitude, wo der Gipfel kaum aus dem 1/f-Untergrund ragt."""
    from views.eeg_spectrum import _peak_freq_cog
    soll = manifest["alpha"]["freq_hz"]
    abweichungen = {}
    for ch in edf["eeg_map"]:
        f, p = _psd(edf, ch)
        cog = _peak_freq_cog(f, p, 8.0, 13.0)
        abweichungen[ch] = abs(cog - soll)
    schlimmster = max(abweichungen, key=abweichungen.get)
    assert abweichungen[schlimmster] < 0.3, (
        f"Alpha-CoG weicht auf '{schlimmster}' um {abweichungen[schlimmster]:.3f} Hz vom "
        f"Sollwert {soll} Hz ab (alle: {abweichungen})")


def test_alpha_peak_multitaper_stimmt_mit_welch_ueberein(edf, manifest):
    """Beleg für: „Multitaper-Vergleich (Add-on, G7)". Der Vergleich ist nur dann etwas wert,
    wenn beide Schätzer auf einem Signal mit bekanntem Gipfel dieselbe Frequenz liefern —
    sonst misst die Seite nur den Unterschied zwischen zwei Fehlern."""
    from views.eeg_spectrum import _peak_freq_cog
    soll = manifest["alpha"]["freq_hz"]
    f_w, p_w = _psd(edf, "O1")
    f_m, p_m = _psd(edf, "O1", multitaper=True)
    welch = _peak_freq_cog(f_w, p_w, 8.0, 13.0)
    multi = _peak_freq_cog(f_m, p_m, 8.0, 13.0)
    assert abs(welch - soll) < 0.3, f"Welch: {welch:.3f} Hz statt {soll}"
    assert abs(multi - soll) < 0.3, f"Multitaper: {multi:.3f} Hz statt {soll}"
    assert abs(welch - multi) < 0.1, f"Welch {welch:.3f} und Multitaper {multi:.3f} uneins"


# ── Bandpower und Asymmetrie ─────────────────────────────────────────────────────────────

def test_alpha_dominiert_die_bandpower_posterior(edf):
    """Beleg für: „Bandpower / rel. Power". Auf O1 sitzt mit 33 µV der stärkste Rhythmus der
    Datei; das Alpha-Band muss dort deutlich mehr Leistung tragen als Theta oder Beta."""
    from views.eeg_spectrum import _band_power
    f, p = _psd(edf, "O1")
    alpha = _band_power(f, p, 8.0, 13.0)
    theta = _band_power(f, p, 4.0, 8.0)
    beta = _band_power(f, p, 13.0, 30.0)
    assert alpha > 3 * theta, f"Alpha {alpha:.3g} nicht klar über Theta {theta:.3g}"
    assert alpha > 3 * beta, f"Alpha {alpha:.3g} nicht klar über Beta {beta:.3g}"


def test_asymmetrie_index_trifft_den_eingebauten_wert(edf, manifest):
    """Beleg für: „Asymmetrie-Index (Default)".

    Der Sollwert ist hier nicht geschätzt, sondern rechnerisch festgelegt: O1 trägt 33,0 µV
    Alpha, O2 27,5 µV. Der AI arbeitet auf der LEISTUNG, also auf dem Quadrat der Amplitude:

        AI = (33,0² − 27,5²) / (33,0² + 27,5²) × 100 = 18,03 %

    Genau diese Zahl muss aus der Pipeline herauskommen — Filter, Welch-Schätzer,
    Bandintegral und Indexformel zusammengenommen.
    """
    from views.eeg_spectrum import _band_power
    amps = manifest["alpha"]["amplitude_uv_per_channel"]
    l, r = amps["O1"], amps["O2"]
    soll = (l ** 2 - r ** 2) / (l ** 2 + r ** 2) * 100

    f1, p1 = _psd(edf, "O1")
    f2, p2 = _psd(edf, "O2")
    pl, pr = _band_power(f1, p1, 8.0, 13.0), _band_power(f2, p2, 8.0, 13.0)
    ai = (pl - pr) / (pl + pr) * 100
    assert abs(ai - soll) < 1.0, f"AI {ai:.2f} %, erwartet {soll:.2f} % aus den Amplituden"


def test_anterior_posterior_gradient_zeigt_in_die_richtige_richtung(edf):
    """Für den PAR bleibt es bewusst bei einer RICHTUNGS-Prüfung, und die Methode bleibt
    literaturbasiert: die Fixture legt nur „posterior ≫ anterior" fest, kein Zahlenniveau.
    Ein erfundener Zahlensollwert wäre genau die Scheinvalidierung, die hier abgestellt
    werden soll. Der Test schützt trotzdem vor einem Vorzeichen-/Zuordnungsfehler."""
    from views.eeg_spectrum import _band_power
    def alpha_power(ch):
        f, p = _psd(edf, ch)
        return _band_power(f, p, 8.0, 13.0)
    post = np.exp(np.mean([np.log(alpha_power(c)) for c in ("O1", "O2", "Pz")]))
    ant = np.exp(np.mean([np.log(alpha_power(c)) for c in ("Fp1", "Fp2", "F3", "F4")]))
    assert post / ant > 5.0, f"PAR {post / ant:.2f} — posteriores Alpha nicht klar überlegen"


# ── Aperiodik ────────────────────────────────────────────────────────────────────────────

def test_aperiodischer_exponent_auf_allen_kanaelen(edf, manifest):
    """Beleg für: „1/f-Exponent (eigener Fit)". Der Generator skaliert das Hintergrund-
    rauschen mit exakt 2,2 — und zwar für jeden Kanal identisch, unabhängig davon, wie viel
    Alpha darüber liegt. Der Sigma-Clip-Fit muss die aufgesetzten Sinus-Linien also
    aussortieren; täte er das nicht, würden die Kanäle je nach Alpha-Amplitude auseinander-
    laufen."""
    from analysis.aperiodic import welch_psd, fit_aperiodic
    soll = manifest["aperiodic"]["exponent_all_channels"]
    werte = {}
    for ch in edf["eeg_map"]:
        sig = edf["data"][edf["ch_idx"][ch]].astype(float)
        f, p = welch_psd(sig, edf["sfreq"])
        werte[ch] = fit_aperiodic(f, p, *APERIODIC_FIT_RANGE)["exponent"]
    schlimmster = max(werte, key=lambda c: abs(werte[c] - soll))
    assert abs(werte[schlimmster] - soll) < 0.15, (
        f"Exponent auf '{schlimmster}': {werte[schlimmster]:.3f} statt {soll} "
        f"(Spanne {min(werte.values()):.3f}–{max(werte.values()):.3f})")

    # Der schärfere Nachweis ist der KANALMITTELWERT: Fit-Rauschen streut symmetrisch und
    # mittelt sich über 19 Kanäle weg, eine systematische Verzerrung durch die aufgesetzten
    # Sinus-Linien täte das nicht. Toleranz ±0,05 statt ±0,15 — hier ist mehr zu verlangen.
    mittel = float(np.mean(list(werte.values())))
    assert abs(mittel - soll) < 0.05, (
        f"Kanalmittel {mittel:.3f} statt {soll} — das wäre eine systematische Verzerrung, "
        f"kein Fit-Rauschen")

    # Bewusst KEINE Zusatzprüfung auf die Streuung zwischen den Kanälen. Nachgemessen
    # (2026-08-12): sie beträgt hier SD 0,038, während 19 rein rechnerisch erzeugte
    # 1/f^2,2-Reihen ohne jedes Alpha unter demselben Fit auf SD 0,017 kommen. Der
    # Sigma-Clip-Fit lässt also einen Rest der Sinus-Linien durch — schwach negativ mit der
    # Alpha-Amplitude korreliert (r = −0,37), ohne den Mittelwert zu verschieben. Das ist
    # eine echte Eigenschaft des Verfahrens und steht als solche in `analysis/methods.py`
    # unter `limitations`. Sie hier hinter einer großzügig gewählten Schwelle zu verstecken
    # wäre genau die Scheinvalidierung, um die es bei diesem Umbau geht.


# ── Artefakt ─────────────────────────────────────────────────────────────────────────────

def test_artefakt_burst_wird_zeitlich_getroffen(edf, manifest):
    """Beleg für: „Artefakt-Markierung". Der Burst liegt bei 240–245 s auf sechs frontalen/
    temporalen Kanälen, 300 µV — das ist ein Vielfaches der Baseline und muss als
    Multikanal-Konsens erkannt werden. Geprüft wird beides: dass er getroffen wird UND dass
    der Detektor nicht großflächig sonst noch anschlägt (eine Maske, die alles markiert,
    fände den Burst auch)."""
    from analysis.artifacts import mask_from_edf
    a = manifest["artifact_burst"]
    onset, ende = a["onset_s"], a["onset_s"] + a["duration_s"]

    res = mask_from_edf(edf)
    treffer = [s for s in res.segments if s["end_s"] > onset - 2 and s["start_s"] < ende + 2]
    assert treffer, (f"Burst bei {onset}–{ende} s nicht erkannt; gefundene Segmente: "
                     f"{[(round(s['start_s'], 1), round(s['end_s'], 1)) for s in res.segments]}")
    # Der Rest der Datei ist artefaktfrei konstruiert — höchstens ein kleiner Teil darf
    # markiert sein, sonst ist der Treffer oben nichts wert.
    assert res.clean_frac > 0.9, (
        f"nur {res.clean_frac:.1%} der Aufnahme gilt als sauber — die Maske schlägt zu breit "
        f"an, dann ist der Burst-Treffer kein Nachweis")
