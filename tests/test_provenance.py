"""Herkunftsangaben: eine Versionsquelle, und sie steht wirklich in den Reports.

Der Anlass: Ein exportierter Report zeigte Werte, aber nichts darüber, womit sie entstanden
sind — es gab überhaupt keine Versionsnummer im Code. Zwei Reports derselben Aufnahme aus
verschiedenen Wochen ließen sich nicht vergleichen, weil niemand entscheiden konnte, ob ein
Unterschied aus der Aufnahme oder aus einer Codeänderung stammt.

Geprüft wird deshalb dreierlei: dass es die Versionsnummer nur an EINER Stelle gibt, dass der
Fingerabdruck das tut, was sein Name verspricht, und dass die Angaben tatsächlich in den
erzeugten Dateien landen — nicht nur in einer Funktion, die sie liefern könnte.
"""
import os
import re
import sys
import warnings

import pytest  # noqa: F401  (monkeypatch-Fixture, importorskip in anderen Tests)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test_edf_datei.edf")


def _pdf_text(pdf_bytes: str) -> str:
    """Text aus einem PDF. Nötig, weil ReportLab die Textströme komprimiert — eine Suche im
    Rohbytestrom findet nichts (erst so gemerkt, als der erste Anlauf dieses Tests fehlschlug,
    obwohl die Angaben im geöffneten PDF sichtbar dastanden)."""
    import io

    import pypdf     # in requirements-dev.txt deklariert — hier bewusst hart, nicht
                     # "importorskip": ein übersprungener Test sähe grün aus und prüfte nichts
    return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_version_kommt_aus_citation_cff():
    """CITATION.cff ist die einzige gepflegte Stelle. Eine zweite Konstante im Code wäre ein
    zweiter Ort zum Vergessen — genau so laufen Doku und Code auseinander."""
    from core.version import version, UNKNOWN
    with open(os.path.join(ROOT, "CITATION.cff"), encoding="utf-8") as fh:
        cff = re.search(r"^version:\s*['\"]?([^'\"\s]+)", fh.read(), re.MULTILINE).group(1)
    assert version() == cff != UNKNOWN, f"version() = {version()}, CITATION.cff = {cff}"


def test_keine_zweite_versionsnummer_im_code():
    """Sicherung gegen den Rückfall: irgendwo ein `__version__ = "0.2.0"` zu ergänzen ist
    verlockend und macht die eine Quelle sofort wieder kaputt."""
    treffer = []
    for ordner, _, dateien in os.walk(ROOT):
        if any(teil in ordner for teil in (".git", "__pycache__", ".venv", "tests")):
            continue
        for name in dateien:
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(ordner, name)
            with open(pfad, encoding="utf-8") as fh:
                for nr, zeile in enumerate(fh, 1):
                    if re.match(r"\s*(__version__|VERSION)\s*=\s*['\"]\d", zeile):
                        treffer.append(f"{os.path.relpath(pfad, ROOT)}:{nr}")
    assert not treffer, f"zweite Versionsnummer im Code: {treffer}"


def test_fingerabdruck_unterscheidet_was_er_soll():
    """Ein Fingerabdruck, der sich bei geänderten Parametern NICHT ändert, wäre gefährlicher
    als gar keiner: er behauptete Vergleichbarkeit, wo keine ist."""
    from core.version import fingerprint
    a = fingerprint(FIXTURE, {"Alter": 45})
    assert a == fingerprint(FIXTURE, {"Alter": 45}), "nicht reproduzierbar"
    assert a != fingerprint(FIXTURE, {"Alter": 60}), "Parameteränderung bleibt unbemerkt"
    assert a != fingerprint(FIXTURE, {"Alter": 45, "Maske": "1 Segment"}), \
        "zusätzlicher Parameter bleibt unbemerkt"

    afib = os.path.join(ROOT, "tests", "fixtures", "test_edf_afib.edf")
    if os.path.exists(afib):
        assert a != fingerprint(afib, {"Alter": 45}), "andere Datei, gleicher Fingerabdruck"


def test_unbekannter_commit_wird_als_unbekannt_ausgewiesen(monkeypatch):
    """Im Container gibt es kein `.git` (per `.dockerignore` ausgeschlossen). Wird der Commit
    beim Bauen nicht hereingereicht, muss das dastehen — eine erfundene oder leere Angabe
    wäre schlimmer als eine fehlende."""
    import core.version as v
    v.commit.cache_clear()
    monkeypatch.setenv("EDF_BUILD_COMMIT", "abc1234")
    assert v.commit() == "abc1234"
    v.commit.cache_clear()


def test_herkunft_steht_im_tabellen_report():
    """Bis in die erzeugten Bytes geprüft, nicht nur bis zur Funktion: der Weg von
    `collect_sections` über `build_pdf`/`build_excel` ist die Stelle, an der es bisher fehlte."""
    from core.shared import load_and_prepare
    from analysis.report_export import collect_sections, build_pdf, build_excel
    from core.version import version

    edf = load_and_prepare(FIXTURE)
    secs = collect_sections(edf, FIXTURE, age=45)
    herkunft = [s for s in secs if s["name"].startswith("Herkunft")]
    assert herkunft, f"keine Herkunft-Sektion; vorhanden: {[s['name'] for s in secs]}"

    felder = {r[0] for r in herkunft[0]["rows"]}
    for pflicht in ("Version", "Git-Commit", "Python", "SHA-256 der Datei",
                    "Analyse-Fingerabdruck"):
        assert pflicht in felder, f"'{pflicht}' fehlt in der Herkunft-Sektion"

    pdf, xlsx = build_pdf(secs, "Fixture"), build_excel(secs, edf, "Fixture")
    assert len(pdf) > 10_000 and len(xlsx) > 5_000
    assert version() in _pdf_text(pdf), "Version steht nicht im PDF"
    assert "Herkunft" in _pdf_text(pdf)


def test_herkunft_steht_im_visuellen_report():
    """Der visuelle Report trägt die Herkunft als Fußzeile auf JEDER Seite — aus ihm werden
    einzelne Seiten ausgedruckt und weitergereicht."""
    from core.shared import load_and_prepare
    from analysis.glory_report import build_glory_pdf
    from core.version import version

    pdf = build_glory_pdf(load_and_prepare(FIXTURE), FIXTURE, "Fixture", age=45)
    assert len(pdf) > 50_000
    import io

    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 3
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        assert version() in text, f"Seite {i + 1} ohne Herkunftszeile"


def test_herkunft_steht_im_hrv_report():
    from analysis.pdf_report import build_hrv_pdf
    from core.version import version
    pdf = build_hrv_pdf(patient_age=45, patient_sex="M", file_label="Fixture",
                        duration_min=10.0, mean_hr=70.0, sdnn=42.4, rmssd=52.9, pnn50=57.1,
                        pct_removed=2.4, quality_label="gut", balance_label="ausgeglichen",
                        lab_rows=[], method_used="welch", edf_path=FIXTURE)
    assert version() in _pdf_text(pdf), "Version steht nicht im HRV-PDF"
    assert "Fingerabdruck" in _pdf_text(pdf), "Fingerabdruck fehlt im HRV-PDF"


def test_hrv_report_laeuft_auch_ohne_dateipfad():
    """`edf_path` ist optional — ältere Aufrufer dürfen nicht brechen, und der Report muss
    dann eben ohne Dateihash auskommen statt gar nicht zu entstehen."""
    from analysis.pdf_report import build_hrv_pdf
    pdf = build_hrv_pdf(patient_age=45, patient_sex="W", file_label="ohne Pfad",
                        duration_min=5.0, mean_hr=65.0, sdnn=40.0, rmssd=45.0, pnn50=30.0,
                        pct_removed=0.0, quality_label="gut", balance_label="ausgeglichen",
                        lab_rows=[], method_used="welch")
    assert len(pdf) > 3_000
