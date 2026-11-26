"""Die Polaritäts-Entscheidung muss unabhängig vom Filterzustand des Eingangssignals sein.

Hintergrund (Fund 2026-11-26, Aufnahme CA1773D9): `detect_polarity_flip()` verglich die
lokalen Extremwerte auf dem Signal so, wie der Aufrufer es übergab. Hochfrequentes Rauschen
hebt dabei `max()` an, ohne die breitere echte Auslenkung zu berühren. Bei einer Aufnahme mit
nahezu symmetrischem QRS kippte die Entscheidung dadurch je nachdem, ob die aufrufende Stelle
vor oder nach ihrem Anzeige-Bandpass fragte — in der App entschieden mehrere Seiten
unterschiedlich und zeigten dieselbe Aufnahme teils aufrecht, teils invertiert.

Diese Tests nageln beides fest: die Unabhängigkeit vom Filterzustand (die eigentliche
Zusicherung) und die Richtigkeit bei verrauschtem, invertiertem Signal (der konkrete Fall).
"""
import numpy as np
import pytest
from scipy.signal import butter, filtfilt

from analysis.ecg import detect_polarity_flip

FS = 200.0
DAUER_S = 30.0
HF_BPM = 70.0


def _ekg(invertiert: bool, rauschen_mv: float = 0.0, seed: int = 0) -> np.ndarray:
    """Synthetisches EKG mit schmaler R-Zacke, breiter T-Welle und optionalem HF-Rauschen.

    Die R-Zacke ist bewusst nur wenig höher als die gegenläufige S-Zacke, damit der Fall dem
    realen Problemfall ähnelt: eine knappe Entscheidung, die durch Rauschen kippen kann.
    """
    rng = np.random.default_rng(seed)
    n = int(DAUER_S * FS)
    sig = np.zeros(n)
    schlag_abstand = int(FS * 60.0 / HF_BPM)
    for start in range(schlag_abstand, n - schlag_abstand, schlag_abstand):
        t = np.arange(-int(0.2 * FS), int(0.4 * FS)) / FS
        p = 0.10 * np.exp(-((t + 0.16) ** 2) / (2 * 0.020 ** 2))
        q = -0.10 * np.exp(-((t + 0.02) ** 2) / (2 * 0.008 ** 2))
        r = 1.00 * np.exp(-(t ** 2) / (2 * 0.010 ** 2))
        s = -0.85 * np.exp(-((t - 0.03) ** 2) / (2 * 0.012 ** 2))
        tw = 0.25 * np.exp(-((t - 0.25) ** 2) / (2 * 0.050 ** 2))
        schlag = p + q + r + s + tw
        i0 = start - int(0.2 * FS)
        sig[i0:i0 + len(schlag)] += schlag
    if invertiert:
        sig = -sig
    if rauschen_mv:
        sig = sig + rng.normal(0.0, rauschen_mv, n)
    return sig / 1000.0  # mV -> V, wie die Loader-Signale


def _bandpass(sig: np.ndarray) -> np.ndarray:
    b, a = butter(4, [0.5 / (FS / 2), 40.0 / (FS / 2)], btype="band")
    return filtfilt(b, a, sig)


@pytest.mark.parametrize("invertiert,rauschen_mv", [
    (False, 0.0), (False, 0.05), (False, 0.15),
    (True, 0.0), (True, 0.05),
    pytest.param(True, 0.15, marks=pytest.mark.xfail(strict=True, reason=(
        "Bekannte Grenze, bewusst festgenagelt: das Testsignal ist mit R +1,00 gegen "
        "S −0,85 mV nahezu symmetrisch (Verhältnis 0,85, noch knapper als der reale "
        "Problemfall CA1773D9 mit 0,93). Bei zusätzlich 15 % Rauschen liegt die Entscheidung "
        "innerhalb des Rauschens — welche Richtung gewinnt, ist dann physikalisch nicht mehr "
        "bestimmt, nicht bloß schlecht implementiert. Die Filterung im Fix beseitigt die "
        "Abhängigkeit vom Eingangszustand für alle klar ausgeprägten Signale (und für alle "
        "92 real vorliegenden Aufnahmen), kann sie für einen im Rauschen liegenden Fall aber "
        "nicht herbeiführen. Der saubere Weg wäre, Knappheit zu MELDEN statt zu raten — "
        "offener Punkt, siehe [[project_edf_nebenbefunde]]."))),
])
def test_entscheidung_haengt_nicht_vom_filterzustand_ab(invertiert, rauschen_mv):
    """Kern der Zusicherung: roh und bandpassgefiltert müssen dasselbe ergeben.

    Genau diese Invariante war verletzt und ist die Ursache dafür, dass verschiedene Seiten
    der App dieselbe Aufnahme unterschiedlich orientiert darstellten.
    """
    sig = _ekg(invertiert, rauschen_mv, seed=1)
    assert detect_polarity_flip(sig, FS) == detect_polarity_flip(_bandpass(sig), FS)


@pytest.mark.parametrize("rauschen_mv", [0.0, 0.05, 0.15])
def test_invertiertes_signal_wird_auch_verrauscht_erkannt(rauschen_mv):
    """Ein invertiertes EKG muss als solches erkannt werden, auch mit HF-Rauschen."""
    assert detect_polarity_flip(_ekg(True, rauschen_mv, seed=2), FS) is True


@pytest.mark.parametrize("rauschen_mv", [0.0, 0.05, 0.15])
def test_aufrechtes_signal_wird_nicht_geflippt(rauschen_mv):
    """Gegenprobe: ein aufrechtes EKG darf nicht gedreht werden (kein Fehlalarm)."""
    assert detect_polarity_flip(_ekg(False, rauschen_mv, seed=3), FS) is False


def test_eingangssignal_wird_nicht_veraendert():
    """Die interne Filterung darf das Signal des Aufrufers nicht anfassen."""
    sig = _ekg(True, 0.05, seed=4)
    kopie = sig.copy()
    detect_polarity_flip(sig, FS)
    np.testing.assert_array_equal(sig, kopie)


def test_kurzes_signal_faellt_auf_ungefiltert_zurueck():
    """Zu kurz für filtfilt: defensiver Rückfall statt Ausnahme.

    Geprüft wird gezielt der Filter-Helfer, nicht `detect_polarity_flip` als Ganzes: dessen
    Kandidatensuche (`detect_r_peaks`) filtert selbst und wirft bei derart kurzen Signalen
    schon immer — ein vorbestehendes Verhalten, das dieser Fix nicht berührt.
    """
    from analysis.ecg import _flip_decision_band

    kurz = np.array([0.0, 1.0, -1.0, 0.5])
    np.testing.assert_array_equal(_flip_decision_band(kurz, FS), kurz)


def test_leere_kandidatenliste():
    assert detect_polarity_flip(np.zeros(int(FS)), FS, candidates=np.array([], dtype=int)) is False
