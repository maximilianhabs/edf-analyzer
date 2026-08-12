"""Verfahren gegen ihre analytisch bekannte Wahrheit.

Für einen Teil der Kennwerte braucht es keine EEG-Datei: die Theorie legt den Wert exakt
fest. Die Permutationsentropie von weissem Rauschen ist 1,0, der DFA-Exponent unkorrelierten
Rauschens 0,5, die SDNN einer sinusförmigen RR-Reihe der Amplitude A ist A/√2. Solche
Prüfungen sind schärfer als jede Messung an einer Aufnahme, weil der Sollwert nicht selbst
geschätzt ist.

Was hier NICHT passiert: eine Formel neben der Implementierung nachbauen und beide
vergleichen. Das zeigte nur, dass zwei Rechnungen übereinstimmen. Geprüft wird gegen Werte,
die aus der Theorie oder aus der Konstruktion des Eingangssignals folgen.

Alle Zufallsreihen laufen über einen festen Seed — ein Test, der gelegentlich rot wird, wird
irgendwann ignoriert, und dann ist er schlimmer als keiner.
"""
import os
import sys
import warnings

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

FS = 200.0


def _powerlaw(n, fs, exponent, seed):
    """Reihe mit exakt bekanntem Spektralexponenten: weisses Rauschen im Frequenzbereich mit
    f^(−exponent/2) skalieren. Die Wahrheit steckt damit in der Konstruktion, nicht in einer
    zweiten Schätzung."""
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    freqs[0] = freqs[1]
    return np.fft.irfft(spec * freqs ** (-exponent / 2.0), n)


# ── Aperiodik: eigener Fit und FOOOF gegen drei bekannte Exponenten ──────────────────────

@pytest.mark.parametrize("soll", [1.0, 1.5, 2.2])
def test_eigener_aperiodik_fit_trifft_bekannten_exponenten(soll):
    """Beleg für: „1/f-Exponent (eigener Fit)"."""
    from analysis.aperiodic import welch_psd, fit_aperiodic
    f, p = welch_psd(_powerlaw(int(600 * FS), FS, soll, seed=11), FS)
    res = fit_aperiodic(f, p, 1.0, 40.0)
    assert abs(res["exponent"] - soll) < 0.05, f"Exponent {res['exponent']:.3f} statt {soll}"
    assert res["r2"] > 0.98, f"Fitgüte nur R²={res['r2']:.3f}"


@pytest.mark.parametrize("soll", [1.0, 1.5, 2.2])
def test_fooof_trifft_bekannten_exponenten(soll):
    """Beleg für: „FOOOF/specparam (Add-on, W2)". Die Referenz-Implementierung wird hier
    nicht auf Zuruf für validiert erklärt, sondern in der Einbindung geprüft, die diese App
    tatsächlich benutzt — Parametrisierung und Auslesen der Parameter eingeschlossen."""
    fooof = pytest.importorskip("fooof", reason="FOOOF nicht installiert")  # noqa: F841
    from analysis.aperiodic import welch_psd
    from analysis.aperiodic_fooof import fit_fooof
    f, p = welch_psd(_powerlaw(int(600 * FS), FS, soll, seed=11), FS)
    res = fit_fooof(f, p, 1.0, 40.0)
    assert res is not None
    assert abs(res["exponent"] - soll) < 0.05, f"FOOOF {res['exponent']:.3f} statt {soll}"


def test_schmalbandige_linie_stoert_fooof_staerker_als_den_eigenen_fit():
    """Kein Sollwert-Test, sondern ein festgehaltener Befund (2026-08-12).

    Auf der synthetischen Fixture liefert FOOOF für den 1/f-Exponenten 1,74 statt 2,2 bei
    R² = 0,80 — deutlich schlechter als der eigene Fit mit 2,20. Ursache ist nicht die
    Einbindung (siehe Test oben: ohne Gipfel trifft FOOOF alle drei Exponenten auf ±0,02),
    sondern die Beschaffenheit der Fixture: sie enthält **reine Sinus-Linien**, deren
    spektrale Breite weit unter dem `peak_width_limits`-Minimum von 1 Hz liegt. FOOOF kann
    sie nicht als Gipfel modellieren und verrechnet sie in den aperiodischen Anteil; der
    Sigma-Clip des eigenen Fits wirft sie schlicht heraus.

    Praktische Folge: der eigene, als „vereinfacht" gekennzeichnete Fit ist gegenüber
    schmalbandigen Störungen (Netzbrumm, Stimulationsartefakte) robuster als die Referenz-
    Implementierung. Das ist keine Kritik an FOOOF — reale EEG-Gipfel sind breit — aber es
    gehört dokumentiert, statt es als Widerspruch stehen zu lassen.
    """
    pytest.importorskip("fooof", reason="FOOOF nicht installiert")
    from analysis.aperiodic import welch_psd, fit_aperiodic
    from analysis.aperiodic_fooof import fit_fooof
    n = int(600 * FS)
    t = np.arange(n) / FS
    sig = _powerlaw(n, FS, 2.2, seed=11)
    sig = sig / np.std(sig) + 8.0 * np.sin(2 * np.pi * 10.0 * t)   # scharfe Linie bei 10 Hz
    f, p = welch_psd(sig, FS)
    eigen = fit_aperiodic(f, p, 1.0, 40.0)["exponent"]
    fooof_exp = fit_fooof(f, p, 1.0, 40.0)["exponent"]
    assert abs(eigen - 2.2) < 0.05, f"eigener Fit unerwartet gestört: {eigen:.3f}"
    assert abs(fooof_exp - 2.2) > abs(eigen - 2.2), (
        f"Befund nicht mehr reproduzierbar: FOOOF {fooof_exp:.3f}, eigen {eigen:.3f} — dann "
        f"gehört die Notiz in methods.py/limitations überprüft")


# ── Spektrale Edge-Frequenz ──────────────────────────────────────────────────────────────

def test_spektrale_edge_frequenz_auf_flachem_spektrum():
    """Beleg für: „SEF95 / Medianfrequenz". Bei konstanter Leistungsdichte über [1, 41) Hz
    liegt die Frequenz, unter der p % der Leistung liegen, exakt bei 1 + p·40."""
    from views.eeg_spectrum import _spectral_edge
    freqs = np.arange(1.0, 41.0, 0.1)
    psd = np.ones_like(freqs)
    for pct in (0.50, 0.95):
        soll = freqs[0] + pct * (freqs[-1] - freqs[0])
        got = _spectral_edge(freqs, psd, pct)
        assert abs(got - soll) < 0.15, f"pct={pct}: {got:.3f} Hz statt {soll:.3f} Hz"

    # Gegenprobe mit bekannter Verlangsamung: liegt alle Leistung unter 5 Hz, muss auch die
    # 95-%-Grenze dort liegen. Ein Verfahren, das immer ~die Bandmitte liefert, fiele hier auf.
    psd_slow = np.where(freqs < 5.0, 1.0, 0.0)
    assert _spectral_edge(freqs, psd_slow, 0.95) < 5.0


# ── Komplexität ──────────────────────────────────────────────────────────────────────────

def test_permutationsentropie_gegen_die_beiden_extremfaelle():
    """Beleg für: „Permutationsentropie (G3)". Für unkorreliertes Rauschen sind alle
    Ordinalmuster gleich wahrscheinlich → normalisierte PE = 1,0. Ein reiner Sinus
    durchläuft nur wenige Muster → deutlich darunter."""
    from analysis.complexity import permutation_entropy
    rng = np.random.default_rng(5)
    weiss = permutation_entropy(rng.standard_normal(20000))
    t = np.arange(20000) / FS
    sinus = permutation_entropy(np.sin(2 * np.pi * 10.0 * t))
    assert abs(weiss - 1.0) < 0.01, f"PE(weisses Rauschen) = {weiss:.4f}, erwartet 1,0"
    assert sinus < 0.7, f"PE(Sinus) = {sinus:.4f} — zu hoch für ein rein periodisches Signal"


def test_sample_entropy_gegen_publizierten_richtwert():
    """Beleg für: „Sample Entropy". Für gaußsches weisses Rauschen mit m=2 und r=0,2·SD
    liegt SampEn bei rund 2,2 (Richman & Moorman 2000); ein reiner Sinus ist nahezu
    vollständig vorhersagbar und muss weit darunter liegen."""
    from analysis.complexity import sample_entropy
    rng = np.random.default_rng(5)
    weiss = sample_entropy(rng.standard_normal(4000))
    t = np.arange(4000) / FS
    sinus = sample_entropy(np.sin(2 * np.pi * 10.0 * t))
    assert 2.0 < weiss < 2.4, f"SampEn(weisses Rauschen) = {weiss:.3f}, erwartet ≈2,2"
    assert sinus < 0.5, f"SampEn(Sinus) = {sinus:.3f} — zu hoch für ein periodisches Signal"


def test_lempel_ziv_komplexitaet_gegen_die_extremfaelle():
    """Beleg für: „LZC (shuffle)". Gegen die **shuffle**-Normierung geprüft: dort ist der
    Bezug eine Zufallsumordnung derselben Werte, für weisses Rauschen also das Signal selbst
    → Verhältnis ≈ 1. Ein Sinus muss klar darunter liegen.

    Die **phase**-Normierung wird bewusst nicht auf einen Zahlenwert festgelegt: bei einem
    schmalbandigen Signal ist das phasenrandomisierte Surrogat selbst fast periodisch, der
    Nenner wird klein und das Verhältnis kann 1 deutlich überschreiten (hier ≈ 3,8 für einen
    reinen Sinus). Das ist eine Eigenschaft der Normierung, kein Rechenfehler — sie steht in
    `analysis/methods.py` unter `limitations`.
    """
    from analysis.complexity import lziv_complexity
    rng = np.random.default_rng(5)
    weiss = lziv_complexity(rng.standard_normal(int(60 * FS)), FS)
    t = np.arange(int(60 * FS)) / FS
    sinus = lziv_complexity(np.sin(2 * np.pi * 10.0 * t), FS)
    assert abs(weiss["shuffle"] - 1.0) < 0.1, f"LZC(weiss) = {weiss['shuffle']:.3f}"
    assert sinus["shuffle"] < 0.6, f"LZC(Sinus) = {sinus['shuffle']:.3f} — zu hoch"


# ── DFA ──────────────────────────────────────────────────────────────────────────────────

def test_dfa_konvergiert_auf_grossen_skalen_gegen_die_theorie():
    """Beleg für: „DFA α₁+α₂ (Add-on, G6)". Unkorreliertes Rauschen hat α = 0,5,
    1/f-Rauschen α = 1,0 — aber erst asymptotisch, also auf hinreichend großen Fenstern.
    Dort wird hier geprüft, weil nur dort ein Sollwert existiert."""
    from analysis.ecg import dfa_alpha1
    rng = np.random.default_rng(7)
    weiss = 800.0 + 30.0 * rng.standard_normal(40000)
    for smin, smax in ((16, 64), (64, 256)):
        a = dfa_alpha1(weiss, smin, smax)["alpha1"]
        assert abs(a - 0.5) < 0.05, f"α auf Skalen {smin}–{smax}: {a:.3f} statt 0,5"

    rosa = _powerlaw(8192, 1.0, 1.0, seed=7)
    rosa = 800.0 + 30.0 * rosa / np.std(rosa)
    a = dfa_alpha1(rosa, 16, 256)["alpha1"]
    assert abs(a - 1.0) < 0.15, f"α für 1/f-Rauschen: {a:.3f} statt 1,0"


def test_dfa_alpha1_hat_auf_dem_klinischen_fenster_einen_bekannten_versatz():
    """Festgehaltener Befund, kein Sollwert-Test (2026-08-12).

    Auf dem klinisch üblichen α₁-Fenster (Skalen 4–16) liefert die Implementierung für
    unkorreliertes Rauschen nicht 0,5, sondern 0,584 ± 0,008 (20 Realisierungen). Das ist
    der bekannte Kleinskalen-Versatz der DFA und **kein Implementierungsfehler**: derselbe
    Code konvergiert auf größeren Fenstern sauber gegen 0,5 (Test oben, 16–64: 0,511;
    64–256: 0,493).

    Praktische Folge: α₁-Werte aus diesem Fenster sind untereinander vergleichbar, dürfen
    aber nicht gegen den theoretischen Wert 0,5 als „Normwert" gelesen werden. Der Test
    hält den Versatz fest, damit eine spätere Änderung am DFA-Code auffällt.
    """
    from analysis.ecg import dfa_alpha1
    werte = [dfa_alpha1(800.0 + 30.0 * np.random.default_rng(i).standard_normal(4000),
                        4, 16)["alpha1"] for i in range(10)]
    m = float(np.mean(werte))
    assert abs(m - 0.584) < 0.03, (
        f"α₁-Versatz jetzt {m:.3f} statt der dokumentierten 0,584 — DFA-Code geändert?")


# ── HRV-Zeitdomäne ───────────────────────────────────────────────────────────────────────

def _sinus_rr(mean_rr_ms=857.14, amp_ms=60.0, f_hz=0.25, n=600):
    """RR-Reihe mit sinusförmiger Modulation — dieselbe Konstruktion wie in der Fixture,
    hier aber ohne Detektionsschritt, damit die Zeitdomäne isoliert geprüft wird."""
    t = np.cumsum(np.full(n, mean_rr_ms / 1000.0))
    return mean_rr_ms + amp_ms * np.sin(2 * np.pi * f_hz * t)


def test_hrv_zeitdomaene_gegen_analytische_werte():
    """Beleg für: „SDNN, RMSSD, pNN50 …". Für eine sinusförmige RR-Reihe der Amplitude A
    ist die Standardabweichung exakt A/√2, und die mittlere Herzfrequenz folgt direkt aus
    dem mittleren RR-Intervall."""
    from analysis.ecg import compute_hrv_time_domain
    rr = _sinus_rr()
    td = compute_hrv_time_domain(rr)
    assert abs(td["sdnn_ms"] - 60.0 / np.sqrt(2)) < 1.0, f"SDNN {td['sdnn_ms']:.2f}"
    assert abs(td["mean_hr_bpm"] - 70.0) < 0.2, f"HR {td['mean_hr_bpm']:.2f}"
    assert abs(td["mean_rr_ms"] - 857.14) < 1.0
    assert abs(td["cv_pct"] - td["sdnn_ms"] / td["mean_rr_ms"] * 100) < 0.05


def test_poincare_erfuellt_die_definierende_identitaet():
    """Beleg für: „Poincaré SD1/SD2". Aus den Definitionen (Brennan 2001) folgt zwingend
    SD1² + SD2² = 2·SDNN². Diese Identität prüft die Implementierung schärfer als ein
    Zahlenvergleich: sie kann nur gelten, wenn beide Größen korrekt aus SDNN und SDSD
    gebildet werden.

    Die Toleranz ist nicht gegriffen, sondern **aus der Rundung hergeleitet**: die Funktion
    gibt alle Werte auf 0,1 ms gerundet zurück, jeder Wert trägt also bis zu ±0,05 ms
    Rundungsfehler. Nach der Fehlerfortpflanzung schlägt das auf ein Quadrat mit 2·x·0,05
    durch. Bei kleinen Amplituden dominiert dieser Anteil — ein erster Ansatz mit fester
    2-%-Toleranz scheiterte bei 5 ms Amplitude genau daran und hätte, pauschal aufgeweicht,
    einen echten Formelfehler bei großen Amplituden durchgelassen.

    Deshalb wird bewusst bei **großen** Amplituden geprüft, wo die Rundung gegenüber den
    Werten verschwindet. Nachgemessen: ein um 3 % falsches SD1 fällt bei allen drei hier
    verwendeten Amplituden auf. Bei 25 ms täte es das nicht — ein solcher Fall wäre also
    Testtheater und ist absichtlich nicht dabei.
    """
    from analysis.ecg import compute_hrv_time_domain
    for amp, f_hz in ((60.0, 0.25), (120.0, 0.10), (200.0, 0.30)):
        td = compute_hrv_time_domain(_sinus_rr(amp_ms=amp, f_hz=f_hz))
        sd1, sd2, sdnn = td["sd1_ms"], td["sd2_ms"], td["sdnn_ms"]
        links, rechts = sd1 ** 2 + sd2 ** 2, 2.0 * sdnn ** 2
        toleranz = 2 * 0.05 * (sd1 + sd2 + 2 * sdnn)      # Rundung, fortgepflanzt
        assert abs(links - rechts) <= toleranz, (
            f"SD1²+SD2² = {links:.3f} ≠ 2·SDNN² = {rechts:.3f} (Amplitude {amp} ms, "
            f"rundungsbedingt zulässig wären {toleranz:.3f})")
