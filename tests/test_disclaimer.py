"""Der Haftungshinweis muss dort stehen, wo jemand ihn tatsächlich liest.

Bis 2026-08-12 stand „Kein Medizinprodukt" **ausschließlich** in den beiden READMEs — im
laufenden Programm kam der Satz an keiner Stelle vor, und in keinem exportierten Report.
Wer die App benutzt, liest kein README; wer einen ausgedruckten Report in der Hand hält,
erst recht nicht.

Geprüft wird deshalb an allen vier Orten, an denen jemand mit dem Werkzeug in Berührung
kommt: Login-Seite, Sidebar (auf jeder Seite, weil der Login-Cookie 30 Tage hält),
Tabellen-Report und die beiden PDF-Reports.
"""
import io
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test_edf_datei.edf")


def _pdf_text(pdf_bytes):
    import pypdf
    return "\n".join((p.extract_text() or "")
                     for p in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_hinweis_existiert_in_beiden_sprachen():
    from core.i18n import STRINGS
    for lang in ("de", "en"):
        for key in ("disclaimer_short", "disclaimer_long"):
            text = STRINGS[lang]["auth"][key]
            assert text.strip(), f"{lang}/{key} ist leer"
    assert "Medizinprodukt" in STRINGS["de"]["auth"]["disclaimer_short"]
    assert "medical device" in STRINGS["en"]["auth"]["disclaimer_short"]


def test_login_und_sidebar_zeigen_den_hinweis():
    """Quelltext-Prüfung statt Rendern: beide Stellen laufen nur innerhalb eines
    Streamlit-Durchlaufs, die Aussage „der Aufruf steht dort" ist aber genau die, um die es
    geht — vorher stand er nirgends."""
    for rel in ("core/auth.py", "core/shared.py"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            inhalt = fh.read()
        assert 'tr("auth.disclaimer_short")' in inhalt, f"{rel} zeigt keinen Hinweis"


def test_tabellen_report_beginnt_mit_dem_hinweis():
    from core.shared import load_and_prepare
    from analysis.report_export import collect_sections, build_pdf, build_excel
    edf = load_and_prepare(FIXTURE)
    secs = collect_sections(edf, FIXTURE, age=45)
    assert secs[0]["name"] == "Hinweis", \
        f"erste Sektion ist '{secs[0]['name']}' — der Hinweis gehört nach vorn"
    text = _pdf_text(build_pdf(secs, "Fixture"))
    assert "Kein Medizinprodukt" in text
    assert "keine Diagnosekriterien" in text
    # Excel darf ihn ebenso wenig verlieren — er wird genauso weitergereicht.
    assert build_excel(secs, edf, "Fixture")


def test_hrv_report_zeigt_den_hinweis():
    from analysis.pdf_report import build_hrv_pdf
    pdf = build_hrv_pdf(patient_age=45, patient_sex="M", file_label="Fixture",
                        duration_min=10.0, mean_hr=70.0, sdnn=42.4, rmssd=52.9, pnn50=57.1,
                        pct_removed=2.4, quality_label="gut", balance_label="ausgeglichen",
                        lab_rows=[], method_used="welch", edf_path=FIXTURE)
    assert "Kein Medizinprodukt" in _pdf_text(pdf)


def test_visueller_report_zeigt_den_hinweis_auf_jeder_seite():
    """Einzelseiten werden ausgedruckt und weitergereicht — eine Seite ohne Hinweis wandert
    sonst allein durch die Welt."""
    from core.shared import load_and_prepare
    from analysis.glory_report import build_glory_pdf
    import pypdf
    pdf = build_glory_pdf(load_and_prepare(FIXTURE), FIXTURE, "Fixture", age=45)
    seiten = pypdf.PdfReader(io.BytesIO(pdf)).pages
    assert len(seiten) >= 3
    for i, seite in enumerate(seiten):
        text = seite.extract_text() or ""
        assert "Kein Medizinprodukt" in text, f"Seite {i + 1} ohne Hinweis"
