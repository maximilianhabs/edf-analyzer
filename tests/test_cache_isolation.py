"""Zwei Aufnahmen dürfen sich im Zwischenspeicher nie gegenseitig ersetzen.

Anlass (externes Review, 2026-10-01): `get_filtered_eeg` nahm die Datenmatrix als `_data`
entgegen. Streamlit lässt Parameter mit führendem Unterstrich beim Cache-Schlüssel weg — der
Schlüssel bestand also nur aus Kanalbelegung, Abtastrate und Filter. Zwei verschiedene
Aufnahmen vom selben Gerätetyp bekamen dieselbe gefilterte Matrix, prozessweit, über
Sitzungen und Nutzer hinweg: Der EEG-Viewer konnte das EEG eines anderen Patienten zeigen.

Die beiden Fixtures haben genau diese Konstellation (gleiche Kanalbelegung, gleiche
Abtastrate, verschiedene Signale) und eignen sich deshalb als Prüfstein.
"""
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EDF_PASSWORD", "test")

A = str(ROOT / "tests" / "fixtures" / "test_edf_datei.edf")
B = str(ROOT / "tests" / "fixtures" / "test_edf_afib.edf")


def test_viewer_filter_vermischt_keine_aufnahmen():
    import core.shared as sh

    ea, eb = sh.load_and_prepare(A), sh.load_and_prepare(B)
    # Voraussetzung des Tests: genau die gefährliche Konstellation.
    assert ea["eeg_map"] == eb["eeg_map"] and ea["sfreq"] == eb["sfreq"]
    assert not np.array_equal(ea["data"], eb["data"])

    fa = sh.get_filtered_eeg(ea["data"], ea["eeg_map"], ea["sfreq"], 0.53, 70.0, datei_id=A)
    fb = sh.get_filtered_eeg(eb["data"], eb["eeg_map"], eb["sfreq"], 0.53, 70.0, datei_id=B)

    assert not np.array_equal(fa, fb), (
        "Datei B bekam die gefilterte Matrix von Datei A — der Cache-Schlüssel kennt die "
        "Aufnahme nicht")
    # Und B muss wirklich B sein, nicht nur „irgendetwas anderes":
    idx = list(eb["eeg_map"].values())
    assert np.allclose(fb[idx].std(axis=1) > 0, True)
    assert not np.allclose(fb[idx], fa[idx])


def test_unterstrich_parameter_haben_eine_kennung_daneben():
    """Ratsche über alle Zwischenspeicher: Wer eine Datenmatrix ungehasht (`_x`) übergibt,
    muss im selben Aufruf etwas Gehashtes mitgeben, das die Aufnahme benennt — sonst kehrt
    genau dieser Fehler an anderer Stelle zurück."""
    import ast

    befunde = []
    for py in list((ROOT / "core").glob("*.py")) + list((ROOT / "views").glob("*.py")):
        baum = ast.parse(py.read_text(encoding="utf-8"))
        for fn in ast.walk(baum):
            if not isinstance(fn, ast.FunctionDef):
                continue
            ist_cache = any(
                "cache_data" in ast.unparse(d) or "cache_resource" in ast.unparse(d)
                for d in fn.decorator_list)
            if not ist_cache:
                continue
            namen = [a.arg for a in fn.args.args]
            ungehasht = [n for n in namen if n.startswith("_")]
            gehasht = [n for n in namen if not n.startswith("_")]
            kennung = any(k in n.lower() for n in gehasht
                          for k in ("path", "pfad", "datei", "file", "id", "hash", "key"))
            if ungehasht and not kennung:
                befunde.append(f"{py.name}:{fn.lineno} {fn.name}({', '.join(namen)})")
    assert not befunde, (
        "Zwischenspeicher mit ungehashtem Parameter, aber ohne Datei-Kennung im Schlüssel:\n  "
        + "\n  ".join(befunde))


def _report_seite():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd()))
    from views import report
    report.render()


def _report_fuer(pfad, name, monkeypatch):
    """Ein Nutzer erzeugt auf der Report-Seite die Reports für `pfad`. Alle Aufrufe laufen im
    selben Python-Prozess — wie zwei Nutzer auf demselben Server, der Cache wird geteilt."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(ROOT)
    at = AppTest.from_function(_report_seite, default_timeout=300)
    at.session_state["edf_path"] = pfad
    at.session_state["edf_display_name"] = name
    at.session_state["phi_validated"] = True
    at.run()
    knopf = [b for b in at.button if b.key == "report_build"]
    assert knopf, "Knopf 'Reports erzeugen' nicht gefunden"
    at = knopf[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at.session_state["report_export"]   # (pdf, excel, manifest)


def test_report_seite_liefert_jedem_nutzer_seinen_eigenen_report(monkeypatch):
    """Der Fund aus dem August („es werden alte Reports genommen"), mit zwei Dateien geprüft.
    Bis 2026-10-01 bekam Nutzer B hier exakt den Report von Nutzer A."""
    _, _, manifest_a = _report_fuer(A, "aufnahme_A.edf", monkeypatch)
    _, _, manifest_b = _report_fuer(B, "aufnahme_B.edf", monkeypatch)
    assert manifest_a != manifest_b, "Nutzer B hat den Report von Nutzer A bekommen"
    # Das Manifest enthält bewusst keinen Dateinamen (keine Kopfdaten), wohl aber die
    # SHA-256-Prüfsumme der Aufnahme — die eindeutige Antwort auf „wessen Report ist das?".
    import hashlib
    sha_a = hashlib.sha256(Path(A).read_bytes()).hexdigest().encode()
    sha_b = hashlib.sha256(Path(B).read_bytes()).hexdigest().encode()
    assert sha_b in manifest_b, "Report von Nutzer B trägt nicht die Prüfsumme seiner Datei"
    assert sha_a not in manifest_b, "Report von Nutzer B trägt die Prüfsumme der Datei von A"


def test_jeder_zwischenspeicher_ist_begrenzt():
    """Ratsche: Bis 2026-10-01 hatte keiner der Zwischenspeicher eine Grenze; jeder Upload legte
    neue Einträge an (gemessen ≈ +50 MB), die erst ein Neustart freigab. Jeder `st.cache_data`
    braucht deshalb `ttl` UND `max_entries` (siehe core/cleanup.py, CACHE_TTL_S)."""
    import ast

    unbegrenzt = []
    for py in list((ROOT / "core").glob("*.py")) + list((ROOT / "views").glob("*.py")):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for d in fn.decorator_list:
                if isinstance(d, ast.Call) and "cache_data" in ast.unparse(d.func):
                    kws = {k.arg for k in d.keywords}
                    if not {"ttl", "max_entries"} <= kws:
                        unbegrenzt.append(f"{py.name}:{fn.lineno} {fn.name}")
                elif not isinstance(d, ast.Call) and "cache_data" in ast.unparse(d):
                    unbegrenzt.append(f"{py.name}:{fn.lineno} {fn.name} (ohne Klammern)")
    assert not unbegrenzt, "Zwischenspeicher ohne ttl/max_entries:\n  " + "\n  ".join(unbegrenzt)
