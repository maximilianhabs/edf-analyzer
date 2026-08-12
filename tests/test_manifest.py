"""Das maschinenlesbare Manifest.

PDF und Excel sind für Menschen. Wer eine Serie auswertet, zwei Aufnahmen vergleicht oder ein
Ergebnis in einer anderen Umgebung nachrechnet, musste die Werte bisher abtippen. Geprüft wird
deshalb vor allem, was ein *Programm* am Manifest braucht: dass es strikt parsebar ist, dass
die Herkunft vollständig drinsteht, und dass es nichts enthält, was die Aufnahme identifiziert.
"""
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test_edf_datei.edf")


def _manifest(**kw):
    from core.shared import load_and_prepare
    from analysis.report_export import collect_sections, build_manifest
    edf = load_and_prepare(FIXTURE)
    secs = collect_sections(edf, FIXTURE, age=kw.get("age", 45))
    roh = build_manifest(secs, edf, FIXTURE, "Fixture", **kw)
    return roh, json.loads(roh)


def test_ist_striktes_json():
    """`json.dumps` schreibt für NaN das Literal `NaN` — gültiges Python, **ungültiges JSON**.
    Ein Report voller fehlender Werte hätte damit eine Datei erzeugt, die jeder strenge
    Parser ablehnt. Deshalb steht dieser Test an erster Stelle."""
    roh, _ = _manifest()
    assert b"NaN" not in roh and b"Infinity" not in roh, \
        "ungültige JSON-Literale — fehlende Werte müssen null werden"
    json.loads(roh.decode("utf-8"))          # würde bei NaN scheitern


def test_enthaelt_die_vollstaendige_herkunft():
    from core.version import version
    _, m = _manifest()
    assert m["manifest_schema"] == "1.0", "Formatversion fehlt oder hat sich geändert"
    p = m["provenance"]
    for feld in ("version", "commit", "python", "platform", "packages", "params",
                 "file_sha256", "fingerprint"):
        assert feld in p, f"'{feld}' fehlt in der Herkunft"
    assert p["version"] == version()
    assert p["packages"], "keine Paketversionen — dann ist das Ergebnis nicht nachrechenbar"


def test_enthaelt_keine_kopfdaten_der_aufnahme():
    """Ein Manifest soll weitergegeben werden können, auch wenn die Aufnahme es nicht darf.
    Die Datei wird über ihren Hash identifiziert, nicht über Namen oder Patientenfelder."""
    roh, m = _manifest()
    assert "sha256" in m["recording"] and len(m["recording"]["sha256"]) == 64
    for verboten in ("patient", "SYNTH001", "TestSynthetic", "filename", "file_name"):
        assert verboten.lower() not in roh.decode("utf-8").lower(), \
            f"'{verboten}' steht im Manifest — das gehört dort nicht hin"


def test_werte_stimmen_mit_dem_report_ueberein():
    """Wenn Manifest und PDF auseinanderlaufen, ist das Manifest wertlos — dann weiß man bei
    einer Abweichung nicht, welchem der beiden zu glauben ist."""
    from core.shared import load_and_prepare
    from analysis.report_export import collect_sections, build_manifest
    edf = load_and_prepare(FIXTURE)
    secs = collect_sections(edf, FIXTURE, age=45)
    m = json.loads(build_manifest(secs, edf, FIXTURE, "Fixture", age=45))

    assert [s["section"] for s in m["results"]] == [s["name"] for s in secs]
    for sec, block in zip(secs, m["results"]):
        assert len(block["rows"]) == len(sec["rows"]), f"Zeilenzahl weicht ab: {sec['name']}"

    assert m["recording"]["duration_s"] == 600.0
    assert m["recording"]["n_eeg_channels"] == 19


def test_fingerabdruck_unterscheidet_zwei_laeufe_mit_anderen_parametern():
    """Der Fingerabdruck ist die Antwort auf „sind diese beiden Läufe vergleichbar?" — er
    muss sich ändern, sobald sie es nicht sind."""
    _, a = _manifest(age=45)
    _, b = _manifest(age=70)
    assert a["provenance"]["fingerprint"] != b["provenance"]["fingerprint"]
    assert a["recording"]["sha256"] == b["recording"]["sha256"], "gleiche Datei, gleicher Hash"
