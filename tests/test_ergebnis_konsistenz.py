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
