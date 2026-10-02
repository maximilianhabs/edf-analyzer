"""Ergebnisse müssen zu den aktuellen Einstellungen passen — und Fehler dürfen nicht als Befund
erscheinen.

Anlass: drittes externes Review (2026-10-01), im Code bestätigt. Vier Punkte:
1. Ein visueller Report blieb nach geänderten Einstellungen stehen, sein Knopf verschwand.
2. Eine fehlgeschlagene Artefakterkennung erschien im Report als „0 Segmente, 100 % sauber".
3. Vier gecachte Funktionen lasen die Kanalkorrekturen am Cache-Schlüssel vorbei.
4. Der Report-Export setzte ohne Altersangabe 50 ein, die Oberfläche 52.
"""
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EDF_PASSWORD", "test")
DATEI = str(ROOT / "tests" / "fixtures" / "test_edf_datei.edf")


# ── 1. Veraltete Exporte ───────────────────────────────────────────────────────

def _report_app(monkeypatch, alter):
    from streamlit.testing.v1 import AppTest
    monkeypatch.chdir(ROOT)
    src = (f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
           "from views import report\nreport.render()\n")
    at = AppTest.from_string(src, default_timeout=600)
    at.session_state["edf_path"] = DATEI
    at.session_state["edf_display_name"] = "a.edf"
    at.session_state["phi_validated"] = True
    at.session_state["patient_age"] = alter
    return at


def _knopf(at, key):
    return next((b for b in at.button if b.key == key), None)


def test_visueller_report_veraltet_nach_einstellungsaenderung(monkeypatch):
    at = _report_app(monkeypatch, 40)
    at.run()
    at = _knopf(at, "report_build").click().run()
    at = _knopf(at, "visual_build").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    at.run()   # im Klick-Durchlauf steht der Knopf noch; im nächsten ist er weg
    assert _knopf(at, "visual_build") is None, "nach dem Erzeugen kein Knopf mehr erwartet"
    assert not [w for w in at.warning if "geändert" in w.value]

    # Alter ändern — dieselbe Sitzung, nichts neu erzeugt
    at.session_state["patient_age"] = 75
    at.run()
    assert [w for w in at.warning if "geändert" in w.value], (
        "Tabellen-Reports aus alter Konfiguration nicht als veraltet gekennzeichnet")
    assert _knopf(at, "visual_build") is not None, (
        "veralteter visueller Report wird weiter angeboten statt neu erzeugt")

    # Neu erzeugen: Warnung verschwindet, alter visueller Report ist verworfen
    at = _knopf(at, "report_build").click().run()
    assert not [w for w in at.warning if "geändert" in w.value]
    assert "visual_export" not in at.session_state


# ── 2. Fehler ≠ „100 % sauber" ────────────────────────────────────────────────

def _zeilen(sections):
    return [" ".join(str(c) for c in z) for s in sections for z in s.get("rows", [])]


def test_fehlgeschlagene_artefakterkennung_erscheint_nicht_als_sauber(monkeypatch):
    import analysis.artifacts as art
    import core.shared as sh
    from analysis.report_export import collect_sections

    def kaputt(_edf):
        raise RuntimeError("Testfehler")
    monkeypatch.setattr(art, "mask_from_edf", kaputt)

    edf = sh.load_and_prepare(DATEI)
    zeilen = _zeilen(collect_sections(edf, DATEI, age=52, sex="X", is_pediatric=False))
    artefakt = [z for z in zeilen if z.startswith("Artefakt-Korrektur")]
    assert artefakt and "fehlgeschlagen" in artefakt[0], artefakt
    assert not any("% sauber" in z for z in artefakt), (
        "technischer Fehler erscheint als Qualitätsaussage „sauber“")


def test_erfolgreiche_artefakterkennung_unveraendert():
    """Gegenprobe: der Normalfall sieht aus wie vorher."""
    import core.shared as sh
    from analysis.report_export import collect_sections

    edf = sh.load_and_prepare(DATEI)
    zeilen = _zeilen(collect_sections(edf, DATEI, age=52, sex="X", is_pediatric=False))
    artefakt = [z for z in zeilen if z.startswith("Artefakt-Korrektur")]
    assert artefakt and "Segmente" in artefakt[0] and "% sauber" in artefakt[0], artefakt


# ── 3. Versteckte Eingaben im Cache ───────────────────────────────────────────

def test_gecachte_funktionen_mit_kanalkorrekturen_haben_sie_im_schluessel():
    """Ratsche: Wer in einer gecachten Funktion `apply_channel_overrides()` aufruft oder den
    Session-State liest, muss die Korrekturen als Parameter im Schlüssel tragen. Die
    Unterstrich-Ratsche in test_cache_isolation.py erkennt diese Fehlerklasse nicht."""
    luecken = []
    for py in list((ROOT / "core").glob("*.py")) + list((ROOT / "views").glob("*.py")):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if not isinstance(fn, ast.FunctionDef):
                continue
            if not any("cache_data" in ast.unparse(d) for d in fn.decorator_list):
                continue
            src = ast.unparse(fn)
            if "apply_channel_overrides(" in src or "session_state" in src:
                params = [a.arg for a in fn.args.args]
                if not any("override" in p for p in params):
                    luecken.append(f"{py.name}:{fn.lineno} {fn.name}({', '.join(params)})")
    assert not luecken, "Kanalkorrekturen fehlen im Cache-Schlüssel:\n  " + "\n  ".join(luecken)


# ── 4. Eine Altersvorgabe ─────────────────────────────────────────────────────

def test_export_und_oberflaeche_verwenden_dieselbe_altersvorgabe():
    import core.shared as sh
    from analysis.hrv_reference import STANDARD_ALTER
    from analysis.report_export import collect_sections

    assert sh.STANDARD_ALTER == STANDARD_ALTER
    edf = sh.load_and_prepare(DATEI)
    zeilen = _zeilen(collect_sections(edf, DATEI, age=None, sex="X", is_pediatric=False))
    alter = [z for z in zeilen if z.startswith("Parameter: Alter ")]   # Herkunftsabschnitt
    assert alter and str(STANDARD_ALTER) in alter[0], alter


# ── 5. HRV-Wert der Report-Seite nach Kanalkorrektur ──────────────────────────

def test_report_hrv_wird_nach_kanalkorrektur_neu_berechnet(monkeypatch):
    """Bis 2026-10-01 blieb der zwischengespeicherte HRV-Wert der Report-Seite nach einer
    Kanalkorrektur stehen — er hing an keinem Schlüssel. Geprüft wird das Verhalten selbst:
    Nach einer Korrektur, die die EKG-Kanäle verändert, muss die HRV erneut berechnet werden;
    ohne Änderung dagegen nicht (sonst wäre der Zwischenspeicher wirkungslos)."""
    import core.shared as sh
    import views.report as rep
    from core.channel_classifier import ECG

    aufrufe = []
    original = rep._compute_hrv
    monkeypatch.setattr(rep, "_compute_hrv",
                        lambda p, e: aufrufe.append(tuple(e["ecg_channels"])) or original(p, e))

    at = _report_app(monkeypatch, 52)
    at.run()
    at.run()                                   # unverändert: kein zweites Rechnen
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(aufrufe) == 1, f"ohne Änderung erneut gerechnet: {aufrufe}"

    edf = sh.load_and_prepare(DATEI)
    anderer = next(c for c in edf["ch_names"] if c not in edf["ecg_channels"])
    at.session_state["channel_overrides"] = {anderer: ECG}
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(aufrufe) == 2, "HRV-Wert aus der alten Kanalzuordnung wird weiter angezeigt"
    assert anderer in aufrufe[-1]


# ── 6. Keine stillen Fehler ───────────────────────────────────────────────────

#: Stellen, an denen ein Fehler bewusst still bleiben darf — je mit Grund. Alles andere muss
#: protokollieren, eine Meldung zeigen oder den Fehler weiterreichen.
STILL_ERLAUBT = {
    ("core/auth.py", "require_login"): "Cookie-Komponente fehlt → Anmeldung nur über Session",
    ("core/auth.py", "logout_button"): "Cookie löschen ist best effort",
    ("core/auth.py", "_render_login"): "Cookie setzen ist best effort",
    ("core/i18n.py", "init_lang"): "Sprach-Cookie nicht lesbar → Standardsprache",
    ("core/i18n.py", "set_lang"): "Sprach-Cookie nicht schreibbar → nur für diese Sitzung",
    ("analysis/report_export.py", "_register_font"): "Schrift fehlt → Helvetica",
    ("analysis/ecg.py", "validated_detectors_available"): "Verfügbarkeitsprüfung, False ist die Antwort",
    ("analysis/glory_report.py", "build_glory_pdf"): "schreibt die Meldung sichtbar in den Report",
    ("analysis/report_export.py", "_add_provenance"): "schreibt die Meldung sichtbar in den Report",
}


def _stille_handler():
    erg = []
    for ordner in ("views", "core", "analysis"):
        for py in sorted((ROOT / ordner).glob("*.py")):
            baum = ast.parse(py.read_text(encoding="utf-8"))
            eltern = {k: n for n in ast.walk(baum) for k in ast.iter_child_nodes(n)}
            for n in ast.walk(baum):
                if not (isinstance(n, ast.ExceptHandler) and n.type is not None
                        and ast.unparse(n.type) in ("Exception", "BaseException")):
                    continue
                aufrufe = [ast.unparse(c.func) for c in ast.walk(n) if isinstance(c, ast.Call)]
                meldet = any(k in a for a in aufrufe for k in (
                    "log", "warning", "error", "info", "caption", "exception", "st.", "print",
                    "Paragraph", "_fallback"))
                if meldet or any(isinstance(c, ast.Raise) for c in ast.walk(n)):
                    continue
                f, fn = n, "<modul>"
                while f in eltern:
                    f = eltern[f]
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        fn = f.name
                        break
                erg.append((f"{ordner}/{py.name}", fn, n.lineno))
    return erg


def test_kein_fehler_wird_still_verschluckt():
    """Bis 2026-10-01 schluckten 30 Stellen Fehler ohne jede Spur — ein Wert fehlte, eine
    Qualitätsaussage stand falsch da, und niemand erfuhr warum. Ratsche: neue stille
    `except Exception` sind ein Fehler; bewusste Ausnahmen stehen begründet in STILL_ERLAUBT."""
    still = [f"{d}:{z} in {fn}" for d, fn, z in _stille_handler() if (d, fn) not in STILL_ERLAUBT]
    assert not still, "Fehler werden still verschluckt:\n  " + "\n  ".join(still)


def test_logging_wird_nie_funktionslokal_importiert():
    """`import logging` in einer Funktion macht `logging` dort zur lokalen Variable — für die
    GANZE Funktion. Steht der Import in einem except-Zweig, der nicht läuft, stürzt jede andere
    Log-Zeile derselben Funktion mit UnboundLocalError ab. Zweimal beim Bauen passiert."""
    funde = []
    for ordner in ("views", "core", "analysis"):
        for py in sorted((ROOT / ordner).glob("*.py")):
            for n in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for k in ast.walk(n):
                        if isinstance(k, ast.Import) and any(a.name == "logging" for a in k.names):
                            funde.append(f"{ordner}/{py.name}:{k.lineno} in {n.name}")
    assert not funde, "funktionslokales `import logging`:\n  " + "\n  ".join(funde)


def test_visueller_report_zeigt_fehlgeschlagene_artefakterkennung(monkeypatch):
    """Derselbe „100 % sauber"-Fehler wie im Tabellen-Report, hier im visuellen Report
    (glory_report: clean_frac = 1.0 bei jedem Fehler). Jetzt: grauer Ring, „fehlgeschlagen"."""
    import io

    import analysis.artifacts as art
    import core.shared as sh
    from analysis.glory_report import build_glory_pdf
    from pypdf import PdfReader

    def kaputt(_edf):
        raise RuntimeError("Testfehler")
    monkeypatch.setattr(art, "mask_from_edf", kaputt)

    pdf = build_glory_pdf(sh.load_and_prepare(DATEI), DATEI, "a.edf", age=52, is_pediatric=False)
    text = " ".join(s.extract_text() or "" for s in PdfReader(io.BytesIO(pdf)).pages)
    assert "fehlgeschlagen" in text, "fehlgeschlagene Erkennung nicht ausgewiesen"
    assert "100%" not in text.replace(" ", ""), "zeigt weiterhin 100 % sauberes EEG"


def test_visueller_report_bei_komplett_artefaktbehafteter_aufnahme(monkeypatch):
    """Ist alles als Artefakt markiert, darf der Report keine Spektralkennwerte erfinden.
    Bis 2026-10-02 rechnete er dann auf dem ganzen, artefaktbehafteten Signal (Review R7).
    Der Report muss trotzdem entstehen."""
    import io
    from types import SimpleNamespace

    import analysis.artifacts as art
    import analysis.glory_report as gr
    import core.shared as sh
    from pypdf import PdfReader

    edf = sh.load_and_prepare(DATEI)
    alles = SimpleNamespace(segments=[{"start_s": 0.0, "end_s": edf["duration_s"]}], clean_frac=0.0)
    monkeypatch.setattr(art, "mask_from_edf", lambda _edf: alles)

    d = gr._collect(edf, DATEI, age=52)
    assert d.get("psd_f") is None
    assert "rel" not in d and "par" not in d and "ap" not in d
    pdf = gr.build_glory_pdf(edf, DATEI, "a.edf", age=52, is_pediatric=False)
    assert len(PdfReader(io.BytesIO(pdf)).pages) >= 1
