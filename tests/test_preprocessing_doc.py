"""Hält `docs/PREPROCESSING.md` an den Code gebunden.

Eine aus dem Code abgeleitete Spezifikation veraltet leise: der Code ändert sich, das
Dokument bleibt stehen, und dann ist es schlimmer als keines — es behauptet einen Rechenweg,
den es nicht mehr gibt. Genau diese Sorte Widerspruch war der Ausgangspunkt des
Registry-Umbaus.

Deshalb liest dieser Test die tatsächlichen Parameter aus den Modulen und prüft, dass das
Dokument sie nennt. Er beweist nicht, dass die Prosa stimmt — aber er schlägt an, sobald
eine Zahl geändert wird, über die das Dokument eine Aussage trifft.
"""
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOC = os.path.join(ROOT, "docs", "PREPROCESSING.md")


def _doc():
    with open(DOC, encoding="utf-8") as fh:
        return fh.read()


def test_dokument_existiert():
    assert os.path.exists(DOC), "docs/PREPROCESSING.md fehlt"


def test_frequenzbaender_stimmen_mit_dem_code():
    """Die Delta-Untergrenze ist der heikelste Wert: sie folgt aus dem 1-Hz-Hochpass, und
    eine Änderung würde jeden Delta-abgeleiteten Quotienten verschieben."""
    from views.eeg_spectrum import BAND_DICT, FREQ_MAX
    assert BAND_DICT["Delta"] == (1.0, 4.0), (
        f"Delta-Band ist jetzt {BAND_DICT['Delta']} — docs/PREPROCESSING.md sagt 1–4 Hz und "
        f"erklärt ausführlich, warum. Beides zusammen ändern.")
    assert BAND_DICT["Alpha"] == (8.0, 13.0)
    assert FREQ_MAX == 30.0
    assert "Delta ab **1 Hz**" in _doc() or "Delta beginnt bei 1 Hz" in _doc()


def test_artefakt_parameter_stimmen_mit_dem_code():
    from analysis.artifacts import ArtifactParams
    p = ArtifactParams()
    doc = _doc()
    assert p.hp_hz == 1.0 and p.win_s == 1.0 and p.overlap == 0.5
    assert p.flag_sus == 4.0, f"Schwelle jetzt {p.flag_sus}× — Dokument sagt 4×"
    assert p.consensus_n == 3, f"Konsens jetzt {p.consensus_n} Kanäle — Dokument sagt 3"
    assert p.min_nonfrontal == 1
    assert p.guard_s == 0.5 and p.min_clean_island_s == 5.0
    assert p.ecg_ptp_ratio == 2.5
    for wert in ("4× Baseline", "≥ 3 Kanäle", "0,5 s", "< 5 s", "2,5×"):
        assert wert in doc, f"'{wert}' steht nicht im Dokument"


def test_hrv_frequenzparameter_stimmen_mit_dem_code():
    import inspect
    from analysis.hrv_freq import resample_rr, psd_burg, VLF_BAND, LF_BAND, HF_BAND
    assert inspect.signature(resample_rr).parameters["fs_interp"].default == 4.0
    assert inspect.signature(psd_burg).parameters["order"].default == 16
    assert (VLF_BAND, LF_BAND, HF_BAND) == ((0.0033, 0.04), (0.04, 0.15), (0.15, 0.40))
    doc = _doc()
    for wert in ("PCHIP", "4 Hz", "0,0033–0,04", "0,04–0,15", "0,15–0,40", "Ordnung 16"):
        assert wert in doc, f"'{wert}' steht nicht im Dokument"


def test_komplexitaets_parameter_stimmen_mit_dem_code():
    import inspect
    from analysis.complexity import lziv_complexity, sample_entropy
    lz = inspect.signature(lziv_complexity).parameters
    assert lz["ds_hz"].default == 128.0 and lz["n_surrogates"].default == 20
    assert lz["max_segments"].default == 8 and lz["seg_sec"].default == 5.0
    assert inspect.signature(sample_entropy).parameters["m"].default == 2
    doc = _doc()
    for wert in ("128 Hz", "8 Segmente", "20 Surrogate", "m=2"):
        assert wert in doc, f"'{wert}' steht nicht im Dokument"


def test_filterparameter_stehen_so_im_code():
    """Grobe, aber wirksame Sicherung: die im Dokument genannten Filter müssen als
    `butter(...)`-Aufruf mit genau diesen Werten auffindbar sein."""
    quellen = {}
    for rel in ("views/eeg_spectrum.py", "analysis/ecg.py", "core/shared.py",
                "analysis/p_wave_analysis.py", "analysis/artifacts.py"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            quellen[rel] = fh.read()

    # EEG-Analyse: Hochpass 1 Hz, Ordnung 4
    assert re.search(r"butter\(4,\s*cutoff\s*/\s*nyq,\s*btype=\"high\"\)",
                     quellen["views/eeg_spectrum.py"]), "EEG-Hochpass nicht mehr butter(4, …)"
    # QRS-Detektion: 5–15 Hz, Ordnung 2 — und KEIN 0,5–40-Hz-Vorfilter davor
    assert re.search(r"butter\(2,\s*\[5\s*/\s*nyq,\s*15\s*/\s*nyq\]", quellen["analysis/ecg.py"]), \
        "QRS-Bandpass ist nicht mehr 5–15 Hz / Ordnung 2"
    # EKG-Anzeige: 0,5–40 Hz, Ordnung 4
    assert re.search(r"butter\(4,\s*\[0\.5\s*/\s*nyq", quellen["core/shared.py"])
    # P-Welle: 0,5–30 Hz, Ordnung 2
    assert "lo: float = 0.5, hi: float = 30.0" in quellen["analysis/p_wave_analysis.py"]


def test_der_dokumentierte_ekg_pfad_ist_der_tatsaechliche():
    """Das Dokument hält fest, dass die R-Zacken-Erkennung KEINEN 0,5–40-Hz-Vorfilter hat und
    dass `run_ecg_analysis`/`preprocess_ecg` toter Code sind. Wird die Leiche entfernt oder
    wieder angeschlossen, muss das Dokument nachziehen."""
    import ast
    with open(os.path.join(ROOT, "analysis", "ecg.py"), encoding="utf-8") as fh:
        baum = ast.parse(fh.read())
    definiert = {n.name for n in ast.walk(baum) if isinstance(n, ast.FunctionDef)}
    if "run_ecg_analysis" not in definiert:
        # Aufgeräumt — dann darf das Dokument sie nicht mehr als Befund führen.
        assert "run_ecg_analysis" not in _doc(), \
            "run_ecg_analysis ist entfernt, steht aber noch als offener Befund im Dokument"
        return

    aufrufer = []
    for ordner, _, dateien in os.walk(ROOT):
        if any(t in ordner for t in (".git", "__pycache__", ".venv", "tests", "docs")):
            continue
        for name in dateien:
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(ordner, name)
            with open(pfad, encoding="utf-8") as fh:
                inhalt = fh.read()
            for treffer in re.finditer(r"run_ecg_analysis\s*\(", inhalt):
                if "def run_ecg_analysis" not in inhalt[max(0, treffer.start() - 4):treffer.start() + 20]:
                    aufrufer.append(os.path.relpath(pfad, ROOT))
    assert not aufrufer, (
        f"run_ecg_analysis wird jetzt aufgerufen ({aufrufer}) — dann ist der EKG-Pfad ein "
        f"anderer als dokumentiert (dort: KEIN 0,5–40-Hz-Vorfilter vor der QRS-Detektion). "
        f"docs/PREPROCESSING.md anpassen.")
