"""Upload-Prüfung: die Fälle, die im Alltag wirklich vorkommen.

Der Upload prüfte bisher nur Dateiendung und Größe. Alles andere fiel erst beim Laden auf —
als Stacktrace. Ein Fall fiel sogar **gar nicht** auf: eine abgeschnitten übertragene Datei
lädt MNE klaglos als kürzere Aufnahme, und die Analyse rechnet auf dem Bruchstück weiter.
Genau der wird hier zuerst geprüft.

Die Testdateien werden aus der echten Fixture erzeugt und wieder verworfen — es liegt keine
kaputte Datei im Repository herum, und die Fälle bleiben nachvollziehbar, weil im Test steht,
wie sie kaputt gemacht wurden.
"""
import os
import shutil
import sys
import warnings

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")


@pytest.fixture
def bauplatz(tmp_path):
    return tmp_path


def _kopie(tmp_path, name="k.edf"):
    ziel = tmp_path / name
    shutil.copy(FIXTURE, ziel)
    return str(ziel)


def test_gueltige_datei_wird_angenommen():
    from core.edf_validation import validate_edf
    res = validate_edf(FIXTURE)
    assert res.ok, res.errors
    assert res.info["duration_s"] == 600.0
    assert res.info["n_signals"] == 21          # 19 EEG + EKG + EDF+-Annotationsspur
    assert res.info["max_sfreq_hz"] == 200.0
    assert not res.warnings, f"unerwartete Warnung: {res.warnings}"


def test_abgeschnittene_datei_wird_erkannt(bauplatz):
    """Der wichtigste Fall — und der einzige, der bisher gar nicht auffiel.

    Nachgemessen (2026-08-12): MNE lädt eine halbierte Datei ohne Fehlermeldung als 299-s-
    Aufnahme. Ohne diese Prüfung würde die App auf der Hälfte der Daten rechnen und ein
    unauffälliges Ergebnis ausgeben.
    """
    from core.edf_validation import validate_edf
    roh = open(FIXTURE, "rb").read()
    pfad = bauplatz / "halb.edf"
    pfad.write_bytes(roh[:len(roh) // 2])
    res = validate_edf(str(pfad))
    assert not res.ok
    assert "300" in res.message() and "600" in res.message(), (
        f"Die Meldung soll sagen, wie viel fehlt: {res.message()}")


def test_nur_header_ohne_daten(bauplatz):
    from core.edf_validation import validate_edf
    roh = open(FIXTURE, "rb").read()
    pfad = bauplatz / "kopflos.edf"
    pfad.write_bytes(roh[:256 + 21 * 256])
    assert not validate_edf(str(pfad)).ok


def test_umbenannte_fremddatei(bauplatz):
    """Die häufigste Verwechslung überhaupt: irgendetwas wurde auf `.edf` umbenannt."""
    from core.edf_validation import validate_edf
    pfad = bauplatz / "text.edf"
    pfad.write_text("Das ist ein Arztbrief und keine Aufnahme.\n" * 50)
    res = validate_edf(str(pfad))
    assert not res.ok
    assert "umbenannt" in res.message()


def test_bdf_wird_als_solche_benannt(bauplatz):
    """BDF (BioSemi) ist die nächstliegende Nachbardatei — die Meldung soll das sagen und
    nicht bloß „ungültig", sonst sucht jemand den Fehler bei sich."""
    from core.edf_validation import validate_edf
    roh = open(FIXTURE, "rb").read()
    pfad = bauplatz / "bio.edf"
    pfad.write_bytes(b"\xffBIOSEMI" + roh[8:2048])
    res = validate_edf(str(pfad))
    assert not res.ok and "BDF" in res.message()


def test_leere_datei(bauplatz):
    from core.edf_validation import validate_edf
    pfad = bauplatz / "leer.edf"
    pfad.write_bytes(b"")
    assert not validate_edf(str(pfad)).ok


def test_zu_kurze_aufnahme_wird_abgelehnt(bauplatz):
    """Unter 10 s ergibt keine Kennzahl einen Sinn. Erzeugt durch Kürzen der Blockzahl im
    Header UND der Daten — sonst schlüge die Vollständigkeitsprüfung zuerst an und der Test
    würde das Falsche messen."""
    from core.edf_validation import validate_edf, MAIN_HEADER_BYTES, PER_SIGNAL_HEADER_BYTES
    roh = bytearray(open(FIXTURE, "rb").read())
    kopf = MAIN_HEADER_BYTES + 21 * PER_SIGNAL_HEADER_BYTES
    bytes_pro_block = (len(roh) - kopf) // 600
    roh[236:244] = b"%-8d" % 5                      # 5 Blöcke à 1 s
    neu = bytes(roh[:kopf + 5 * bytes_pro_block])
    pfad = bauplatz / "kurz.edf"
    pfad.write_bytes(neu)
    res = validate_edf(str(pfad))
    assert not res.ok, f"5-s-Aufnahme durchgelassen (info: {res.info})"
    assert "5.0 s" in res.message()


def test_kurze_aufnahme_warnt_nur(bauplatz):
    """Zwei Minuten sind für die HRV-Frequenzdomäne zu kurz, für das EEG-Spektrum aber
    brauchbar — das ist eine Warnung, kein Grund zur Ablehnung. Die App ist ein
    Forschungswerkzeug, kein Torwächter."""
    from core.edf_validation import validate_edf, MAIN_HEADER_BYTES, PER_SIGNAL_HEADER_BYTES
    roh = bytearray(open(FIXTURE, "rb").read())
    kopf = MAIN_HEADER_BYTES + 21 * PER_SIGNAL_HEADER_BYTES
    bytes_pro_block = (len(roh) - kopf) // 600
    roh[236:244] = b"%-8d" % 120
    pfad = bauplatz / "zweimin.edf"
    pfad.write_bytes(bytes(roh[:kopf + 120 * bytes_pro_block]))
    res = validate_edf(str(pfad))
    assert res.ok, res.errors
    assert any("HRV" in w for w in res.warnings), res.warnings


def test_meldungen_gibt_es_in_beiden_sprachen():
    """Eine abgelehnte Datei ist genau die Stelle, an der ein anderssprachiger Nutzer sonst
    stecken bleibt — ohne zu verstehen, warum."""
    from core.edf_validation import _MSG, msg
    for code, (de, en) in _MSG.items():
        assert de and en, f"'{code}' hat keine zwei Fassungen"
        assert de != en, f"'{code}': englische Fassung ist die deutsche"
        import re
        assert set(re.findall(r"\{(\w+)", de)) == set(re.findall(r"\{(\w+)", en)), \
            f"'{code}': unterschiedliche Platzhalter in DE und EN"
    assert msg("not_edf", "en") != msg("not_edf", "de")


def test_validierung_braucht_kein_streamlit():
    """Das Modul muss ohne Streamlit importierbar bleiben — es läuft auch in Tests und
    perspektivisch in einem CLI. Deshalb liegen seine Meldungen dort und nicht in
    `core/i18n.py` (das Streamlit importiert)."""
    import ast
    pfad = os.path.join(os.path.dirname(__file__), "..", "core", "edf_validation.py")
    with open(pfad, encoding="utf-8") as fh:
        baum = ast.parse(fh.read())
    module = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            module |= {a.name.split(".")[0] for a in knoten.names}
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            module.add(knoten.module.split(".")[0])
    verboten = module & {"streamlit", "mne", "numpy", "scipy", "pandas"}
    assert not verboten, f"unnötige Abhängigkeit in edf_validation: {verboten}"
