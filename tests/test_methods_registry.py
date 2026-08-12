"""Die Methoden-Registry und das, was die READMEs über sie behaupten.

`tools/check_methods.py` prüft dasselbe und läuft im schnellen CI-Job ohne Abhängigkeiten.
Hier liegt es zusätzlich in der Test-Suite, damit ein lokales `pytest tests/` den Widerspruch
ebenfalls findet — die alte Fehlklassifikation überlebte so lange, weil sie an keiner
einzigen Stelle geprüft wurde.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_methods", os.path.join(ROOT, "tools", "check_methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_registry_und_readmes_stimmen_ueberein():
    assert _checker().main() == 0, "siehe Ausgabe oben — Registry und README sind auseinander"


def test_keine_stufe_ohne_beleg():
    """Die zentrale Regel: „implementierungsvalidiert" ist ohne Nachweis nicht setzbar."""
    import pytest
    from analysis.methods import Method, Evidence, IMPLEMENTATION, LITERATURE, FULL
    with pytest.raises(ValueError):
        Method("X", "Y", "Z", "Ref", FULL, level=IMPLEMENTATION)
    # Mit Beleg geht es — sonst wäre die Regel nur eine Sperre und keine Anforderung.
    ok = Method("X", "Y", "Z", "Ref", FULL, level=IMPLEMENTATION,
                evidence=Evidence("tests/fixtures/test_edf_datei.edf", "HR",
                                  "60 bpm", "±2", "tests/test_ecg_pipeline.py::x"))
    assert ok.level == IMPLEMENTATION
    assert Method("X", "Y", "Z", "Ref", FULL).level == LITERATURE


def test_klinische_validierung_wird_nicht_behauptet():
    """Klinisch validiert ist bisher nichts, und das darf nicht versehentlich passieren:
    dafür bräuchte es eine annotierte Datenbank (MIT-BIH) mit Sensitivität/PPV, keinen
    weiteren synthetischen Datensatz."""
    from analysis.methods import count_by_level, CLINICAL
    assert count_by_level()[CLINICAL] == 0, (
        "klinische Validierung behauptet — dann gehört der Referenzstandard samt Kennzahlen "
        "in die Evidence, und diese Sperre wird bewusst entfernt")


def test_verbliebene_literaturbasierte_verfahren_nennen_einen_grund():
    """Nach Stufe 2 sind 4 der 22 Verfahren weiterhin literaturbasiert. Das ist in Ordnung —
    aber jedes davon muss sagen, WARUM, sonst sieht ein noch nicht geprüftes Verfahren
    genauso aus wie eines, das die Prüfung nicht bestanden hat. Genau diese Verwechslung war
    der Ausgangspunkt des ganzen Umbaus."""
    from analysis.methods import METHODS, LITERATURE
    ohne_begruendung = [m.parameter for m in METHODS
                        if m.level == LITERATURE and len(m.limitations.strip()) < 40]
    assert not ohne_begruendung, (
        f"literaturbasiert ohne Begründung in `limitations`: {ohne_begruendung}")
