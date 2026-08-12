"""Die altersadjustierten HRV-Normgrenzen — gegen die Quellstudie geprüft, nicht gegen sich selbst.

Anlass (2026-08-12): Das log-lineare Modell nach Hansen et al. 2024 lief als ungebremster
Exponentialabfall über den gesamten Altersbereich hinaus. Für HF-Power ergab das bei 85 Jahren
eine 5.-Perzentil-Grenze von 1,9 ms². Das kann nicht stimmen, und zwar aus einem Grund, der
sich ohne jede zusätzliche Literatur prüfen lässt: der über ALLE Altersgruppen gepoolte P5
derselben Studie liegt bei rund 9,5 ms². Eine altersadjustierte Grenze, die um ein Vielfaches
unter der gepoolten liegt, ist in sich widersprüchlich — die gepoolte Gruppe enthält die Alten.

Genau diese Selbstkonsistenz prüft der zentrale Test hier. Er braucht keine externen Daten und
schlägt an, sobald jemand am Modell dreht.
"""
import math
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

PARAMS = ("sdnn", "rmssd", "hf_power", "lf_power", "total_power")


def _gepoolter_p5(param):
    """P5 aus Median und IQR der Studie (Table 2), log-normal genähert — altersunabhängig."""
    from analysis.hrv_reference import POOLED_REFERENCE
    ref = POOLED_REFERENCE[param]
    lo, hi = ref["iqr"]
    sigma = (math.log(hi) - math.log(lo)) / 1.349
    return math.exp(math.log(ref["median"]) - 1.645 * sigma)


def test_altersgrenze_faellt_nicht_unter_die_gepoolte_groessenordnung():
    """Der Kern des Befunds. Eine altersadjustierte P5-Grenze darf nicht drastisch unter dem
    gepoolten P5 liegen — sonst behauptet das Modell, ein typischer alter Mensch sei
    auffälliger als die Gesamtbevölkerung, aus der er stammt.

    Toleranz bewusst großzügig (Faktor 3): Alte haben real weniger HRV, ein Stück darunter ist
    also richtig. Vor der Korrektur lag HF-Power beim 24-Fachen darunter.
    """
    from analysis.hrv_reference import hansen_p5_threshold
    for param in PARAMS:
        gepoolt = _gepoolter_p5(param)
        # Referenz-Herzfrequenz 70 min⁻¹ (Studienmedian 67) — so isoliert der Test den
        # Alterseffekt vom HF-Effekt.
        aeltester = hansen_p5_threshold(param, 85, 70)
        assert aeltester > gepoolt / 3, (
            f"{param}: P5 bei 85 J. = {aeltester:.2f}, gepoolter P5 = {gepoolt:.2f} — "
            f"Faktor {gepoolt / aeltester:.1f} darunter. Modell extrapoliert ins Unbeobachtete?")


def test_hf_und_lf_flachen_ab_55_jahren_ab():
    """Kein selbst gewähltes Plateau: die Quellstudie berichtet für HF und LF ausdrücklich
    einen horizontalen Verlauf oberhalb ~55 Jahren."""
    from analysis.hrv_reference import hansen_p5_threshold
    for param in ("hf_power", "lf_power"):
        bei_55 = hansen_p5_threshold(param, 55, 70)
        for alter in (60, 70, 85):
            assert hansen_p5_threshold(param, alter, 70) == bei_55, \
                f"{param} fällt nach 55 Jahren weiter — Plateau der Quellstudie fehlt"


def test_sdnn_rmssd_und_total_power_fallen_weiter():
    """Für diese drei berichtet die Studie KEIN Plateau. Ein pauschal über alle Parameter
    gelegtes Plateau wäre genauso falsch wie gar keines."""
    from analysis.hrv_reference import hansen_p5_threshold
    for param in ("sdnn", "rmssd", "total_power"):
        assert hansen_p5_threshold(param, 80, 70) < hansen_p5_threshold(param, 40, 70), \
            f"{param} fällt nicht mehr mit dem Alter"


def test_ausserhalb_des_studienbereichs_wird_nicht_extrapoliert():
    """15–85 Jahre ist der Bereich, den die Studie abdeckt; darüber hinaus gibt es keine
    Beobachtung, an der sich eine Grenze festmachen ließe."""
    from analysis.hrv_reference import hansen_p5_threshold
    for param in PARAMS:
        assert hansen_p5_threshold(param, 95, 70) == hansen_p5_threshold(param, 85, 70)
        assert hansen_p5_threshold(param, 5, 70) == hansen_p5_threshold(param, 15, 70)
        # Gleiches für die Herzfrequenz: eine Tachykardie von 160 lag nie im Kollektiv.
        assert hansen_p5_threshold(param, 50, 160) == hansen_p5_threshold(param, 50, 100)


def test_der_alte_fehlerfall_bleibt_behoben():
    """Regressionsschutz mit konkreten Zahlen: 80 Jahre, HF-Power. Vor der Korrektur 2,6 ms²
    bei 70 min⁻¹ — jetzt auf dem Plateau."""
    from analysis.hrv_reference import hansen_p5_threshold, classify_parameter
    p5 = hansen_p5_threshold("hf_power", 80, 70)
    assert 9.0 < p5 < 13.0, f"HF-Power-Grenze bei 80 J. = {p5:.2f} ms² (erwartet ~11)"
    # Ein Wert, der vorher fälschlich „normal" hieß, ist jetzt auffällig.
    assert classify_parameter("hf_power", 3.0, 80, 70)["zone"] == "pathologisch"


def test_keine_zweite_frei_gewaehlte_konstante():
    """Der frühere `_min_delta`-Behelf ist entfallen — er behandelte das Symptom einer zu
    tiefen Normgrenze mit einer zusätzlich erfundenen Zahl. Kommt er zurück, ist das ein
    Hinweis, dass jemand wieder am Symptom arbeitet."""
    pfad = os.path.join(os.path.dirname(__file__), "..", "analysis", "hrv_reference.py")
    with open(pfad, encoding="utf-8") as fh:
        quelle = fh.read()
    assert "_min_delta = {" not in quelle, \
        "`_min_delta` ist zurück — bitte erst prüfen, ob die Normgrenze selbst stimmt"
