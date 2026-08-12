"""Pipeline-Test gegen die SYNTHETISCHE Ground-Truth-Datei.

Vorher hing dieser Test an einem festen Pfad auf eine echte Patientenaufnahme, die nur auf
dem Rechner des Autors liegt. Für alle anderen war er nicht lauffähig, und die Fallnummer
stand im Repository. Ausserdem war eine Erwartung veraltet (2 EKG-Kanäle, der
nachgeschärfte Klassifizierer findet 1) — unbemerkt, weil die Tests nie automatisch liefen.

Jetzt gegen `tests/fixtures/test_edf_datei.edf`: rein mathematisch erzeugt, keine
Patientendaten, im Repo versioniert. Die Sollwerte stehen im zugehörigen Manifest — die
Erwartungen hier sind also belegt und nicht geraten.

Geprüft wird bewusst der Pfad, den die App WIRKLICH nutzt (`load_and_prepare` mit dem
signalbasierten Klassifizierer), nicht der namensbasierte Alt-Helfer `get_channel_groups()`:
der erkennt EEG am Präfix „EEG …-Ref" des Aufnahmesystems und findet in einer Datei mit
schlichten Elektrodennamen (Fp1, F3, …) folgerichtig nichts.
"""
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")
MANIFEST = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei_manifest.json")


def _manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


def test_fixture_vorhanden():
    """Ohne die Fixture ist alles Weitere sinnlos — dann lieber hier klar scheitern."""
    assert os.path.exists(FIXTURE), f"Fixture fehlt: {FIXTURE}"
    assert os.path.exists(MANIFEST), f"Manifest fehlt: {MANIFEST}"


def test_fixture_enthaelt_keine_patientendaten():
    """Die Fixture liegt öffentlich im Repo — sie darf keine echten Kopfdaten tragen."""
    from core.loader import check_privacy
    with open(FIXTURE, "rb") as fh:
        header = fh.read(256)
    patient = header[8:88].decode("latin1").strip()
    assert "SYNTH" in patient.upper() or "TEST" in patient.upper(), \
        f"Patientenfeld sieht nicht synthetisch aus: {patient!r}"
    assert isinstance(check_privacy(FIXTURE)["has_patient_id"], bool)


def test_format_und_kanalerkennung():
    from core.shared import load_and_prepare
    edf = load_and_prepare(FIXTURE)
    m = _manifest()["format"]
    assert edf["sfreq"] == m["fs_hz"]
    assert abs(edf["duration_s"] - m["duration_s"]) < 1.0
    # Signalbasierter Klassifizierer: findet alle 19 EEG-Kanäle trotz herstellerfremder Namen
    assert len(edf["eeg_map"]) == m["n_eeg_channels"], \
        f"erwartet {m['n_eeg_channels']} EEG-Kanäle, erkannt {len(edf['eeg_map'])}"
    assert edf["ecg_channels"] == [m["ecg_channel"]]


def test_ekg_kennwerte_treffen_die_sollwerte():
    """HR und HF-Peak sind im Manifest exakt festgelegt — hier wird die ganze Kette geprüft:
    Polaritätskorrektur → R-Zacken → RR-Serie → Zeit-/Frequenzbereich."""
    from core.shared import load_and_prepare
    from analysis.ecg import (detect_r_peaks_polarity_safe, build_rr_series,
                              compute_hrv_time_domain)
    from analysis.hrv_freq import compute_frequency_domain

    m = _manifest()["ecg"]
    edf = load_and_prepare(FIXTURE)
    sig = edf["data"][edf["ch_idx"][_manifest()["format"]["ecg_channel"]]].astype(float)
    _, peaks, _ = detect_r_peaks_polarity_safe(sig, edf["sfreq"])

    # Toleranz statt exakter Zahl mit Grund: die Datei enthält ABSICHTLICH ein
    # Schwachsignal-Fenster (330–345 s, 5 % Amplitude). Dass dort einzelne Schläge nicht
    # erkannt werden, ist gewolltes Verhalten — 685 von 702 gemessen (2,4 % Ausfall).
    assert 0.93 * m["n_beats"] <= len(peaks) <= 1.02 * m["n_beats"], \
        f"R-Zacken {len(peaks)}, erwartet ~{m['n_beats']}"

    rr = build_rr_series(peaks, edf["sfreq"])
    clean = rr.rr_ms[~rr.artifact_mask]
    td = compute_hrv_time_domain(clean)
    assert abs(td["mean_hr_bpm"] - m["mean_hr_bpm"]) < 2.0, \
        f"HR {td['mean_hr_bpm']:.1f}, erwartet {m['mean_hr_bpm']}"

    fd = compute_frequency_domain(clean, rr.rr_times_s[~rr.artifact_mask], method="welch")
    assert abs(fd["hf_peak_freq"] - m["expected_hf_peak_hz"]) < 0.02, \
        f"HF-Peak {fd['hf_peak_freq']:.3f} Hz, erwartet {m['expected_hf_peak_hz']}"


def test_afib_fixture_laedt():
    """Die zweite Fixture deckt den unregelmässigen Rhythmus ab."""
    from core.shared import load_and_prepare
    afib = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_afib.edf")
    if not os.path.exists(afib):
        import pytest
        pytest.skip("AFib-Fixture nicht vorhanden")
    edf = load_and_prepare(afib)
    assert edf["ecg_channels"], "kein EKG-Kanal in der AFib-Fixture erkannt"


def test_lomb_scargle_findet_denselben_hf_peak():
    """Beleg für: „Lomb-Scargle (Add-on, W3)". Das interpolationsfreie Periodogramm muss die
    eingebaute RSA-Frequenz genauso treffen wie Welch — sonst vergleicht die Seite
    „Erweiterte Analysen" zwei Verfahren, von denen keines nachweislich richtig liegt."""
    from core.shared import load_and_prepare
    from analysis.ecg import detect_r_peaks_polarity_safe, build_rr_series
    from analysis.hrv_lombscargle import lombscargle_hrv

    m = _manifest()
    edf = load_and_prepare(FIXTURE)
    sig = edf["data"][edf["ch_idx"][m["format"]["ecg_channel"]]].astype(float)
    _, peaks, _ = detect_r_peaks_polarity_safe(sig, edf["sfreq"])
    rr = build_rr_series(peaks, edf["sfreq"])
    ok = ~rr.artifact_mask
    res = lombscargle_hrv(rr.rr_ms[ok], rr.rr_times_s[ok])
    assert res is not None
    soll = m["ecg"]["expected_hf_peak_hz"]
    assert abs(res["hf_peak_freq"] - soll) < 0.02, \
        f"Lomb-Scargle HF-Peak {res['hf_peak_freq']:.3f} Hz, erwartet {soll} Hz"
    # Die Modulation sitzt ausschliesslich im HF-Band — HF muss LF klar dominieren.
    assert res["hf"] > res["lf"], f"HF {res['hf']:.3g} nicht über LF {res['lf']:.3g}"


def test_validierte_detektoren_laufen_und_melden_ihr_verfahren():
    """Beleg für: die Umschaltung selbst. Jeder angebotene Detektor muss laufen und
    ausweisen, dass er wirklich gelaufen ist — ein stiller Rückfall auf den eigenen
    Detektor wäre die schlimmste Variante, weil der Vergleich dann sich selbst vergleicht."""
    import pytest
    from analysis.ecg import validated_detectors_available, detect_r_peaks_validated_ex
    if not validated_detectors_available():
        pytest.skip("py-ecg-detectors nicht installiert (optionale Abhängigkeit)")
    from core.shared import load_and_prepare
    from analysis.ecg import detect_r_peaks_polarity_safe

    edf = load_and_prepare(FIXTURE)
    sig = edf["data"][edf["ch_idx"][_manifest()["format"]["ecg_channel"]]].astype(float)
    corr, _, _ = detect_r_peaks_polarity_safe(sig, edf["sfreq"])
    for method in ("hamilton", "pan_tompkins", "christov", "engzee", "two_average"):
        res = detect_r_peaks_validated_ex(corr, edf["sfreq"], method=method)
        assert res.method == method, f"{method} lief als '{res.method}'"
        assert not res.fell_back, f"{method} fiel zurück: {res.reason}"
        assert len(res.peaks) > 0


def test_zwei_validierte_detektoren_treffen_die_schlagzahl():
    """Christov und Two-Average treffen die im Manifest festgelegte Schlagzahl. Nur für
    diese beiden ist der Nachweis erbracht — siehe den folgenden Test."""
    import pytest
    from analysis.ecg import validated_detectors_available, detect_r_peaks_validated_ex
    if not validated_detectors_available():
        pytest.skip("py-ecg-detectors nicht installiert (optionale Abhängigkeit)")
    from core.shared import load_and_prepare
    from analysis.ecg import detect_r_peaks_polarity_safe

    m = _manifest()
    edf = load_and_prepare(FIXTURE)
    sig = edf["data"][edf["ch_idx"][m["format"]["ecg_channel"]]].astype(float)
    corr, _, _ = detect_r_peaks_polarity_safe(sig, edf["sfreq"])
    soll = m["ecg"]["n_beats"]
    for method in ("christov", "two_average"):
        n = len(detect_r_peaks_validated_ex(corr, edf["sfreq"], method=method).peaks)
        assert 0.93 * soll <= n <= 1.02 * soll, f"{method}: {n} R-Zacken, erwartet ~{soll}"


def test_hamilton_und_pan_tompkins_brechen_nach_dem_amplitudensprung_ab():
    """Festgehaltener BEFUND (2026-08-12), kein Sollwert-Test — und der Grund, warum die
    validierten Vergleichsdetektoren in `analysis/methods.py` NICHT auf
    `implementation-validated` stehen.

    Die Fixture enthält bei 400–410 s ein Fenster mit siebenfacher EKG-Amplitude (reine
    Skalierung, keine Formänderung). Hamilton und Pan-Tompkins aus `py-ecg-detectors`
    detektieren bis dorthin sauber und **hören danach vollständig auf**: letzter erkannter
    Schlag bei 409 s, danach 190 s Aufnahme ohne einen einzigen Schlag — 462 statt 702, ein
    Drittel fehlt. Ihre adaptive Schwelle steigt mit dem Ausschlag und erholt sich nicht.

    Zwei Dinge daran sind wichtig:

      1. Der **eigene** Detektor der App übersteht denselben Sprung (685 Schläge, letzter bei
         599,9 s). Die als „validiert" geltende Referenz ist hier also nicht die bessere.
      2. `fell_back` ist dabei **False** — die Detektoren melden keinen Fehler, sie liefern
         still ein plausibel aussehendes, aber um ein Drittel unvollständiges Ergebnis. Eine
         HRV-Auswertung darauf wäre falsch, ohne dass es jemandem auffiele.

    Daraus folgt ein offener Punkt (Backlog): eine Abdeckungs-Plausibilisierung, die meldet,
    wenn ein Detektor über einen längeren Abschnitt gar nichts findet. Dieser Test hält den
    Befund fest, bis das umgesetzt ist.

    Ausserdem hier festgehalten: **Engzee ist polaritätskritisch** — auf dem unkorrigierten
    Signal findet er 7 Schläge, nach der Polaritätskorrektur 678. Die Korrektur ist für
    diesen Detektor also nicht Kosmetik, sondern Voraussetzung.
    """
    import pytest
    from analysis.ecg import validated_detectors_available, detect_r_peaks_validated_ex
    if not validated_detectors_available():
        pytest.skip("py-ecg-detectors nicht installiert (optionale Abhängigkeit)")
    from core.shared import load_and_prepare
    from analysis.ecg import detect_r_peaks_polarity_safe

    m = _manifest()
    edf = load_and_prepare(FIXTURE)
    fs = edf["sfreq"]
    sig = edf["data"][edf["ch_idx"][m["format"]["ecg_channel"]]].astype(float)
    corr, own, _ = detect_r_peaks_polarity_safe(sig, fs)
    hoch_ende = m["ecg_amplitude_artifacts"]["high_amplitude_window_s"][1]

    for method in ("hamilton", "pan_tompkins"):
        peaks = detect_r_peaks_validated_ex(corr, fs, method=method).peaks
        letzter_s = peaks[-1] / fs
        assert letzter_s < hoch_ende + 5, (
            f"{method} findet jetzt Schläge bis {letzter_s:.1f} s — der Befund ist behoben "
            f"oder die Fixture hat sich geändert. Dann diesen Test entfernen und den "
            f"Registry-Eintrag samt limitations neu bewerten.")

    # Der eigene Detektor deckt die volle Aufnahme ab — das ist der Kontrast, um den es geht.
    assert own[-1] / fs > 0.95 * edf["duration_s"], \
        f"eigener Detektor endet schon bei {own[-1] / fs:.1f} s"

    # Polaritätsabhängigkeit von Engzee — festgehalten, weil sie die Reihenfolge
    # Polaritätskorrektur → Detektion zwingend macht.
    roh = len(detect_r_peaks_validated_ex(sig, fs, method="engzee").peaks)
    korr = len(detect_r_peaks_validated_ex(corr, fs, method="engzee").peaks)
    assert korr > 10 * roh, f"Engzee: roh {roh}, polaritätskorrigiert {korr}"


def test_abdeckungsluecken_werden_erkannt():
    """Beleg für die Plausibilisierung, die aus dem Hamilton-Befund entstanden ist.

    Der Detektor-Abbruch war deshalb gefährlich, weil das Ergebnis plausibel AUSSAH: 462
    Schläge sind für sich genommen keine auffällige Zahl, und niemand kennt die Sollzahl
    einer fremden Aufnahme. Die Abdeckung verrät es trotzdem — sie misst nicht, wie viele
    Schläge gefunden wurden, sondern ob über die ganze Aufnahme hinweg überhaupt welche
    kommen.
    """
    from analysis.ecg import coverage_gaps
    import numpy as np

    fs, dauer = 200.0, 600.0
    # Sauberer Fall: durchgehend ein Schlag pro Sekunde → keine Lücke.
    peaks = np.arange(0, dauer, 1.0) * fs
    assert coverage_gaps(peaks, fs, dauer) == ()

    # Der reale Fall: Detektor hört bei 409 s auf.
    peaks = np.arange(0, 409.0, 1.0) * fs
    luecken = coverage_gaps(peaks, fs, dauer)
    assert len(luecken) == 1
    a, b = luecken[0]
    assert 405 < a < 412 and b == 600.0, luecken

    # Lücke am ANFANG — wird ebenso erkannt (ein Detektor, der erst spät anspringt).
    peaks = np.arange(120.0, dauer, 1.0) * fs
    assert coverage_gaps(peaks, fs, dauer)[0][0] == 0.0

    # Gar nichts gefunden → die ganze Aufnahme ist eine Lücke.
    assert coverage_gaps(np.array([]), fs, dauer) == ((0.0, 600.0),)

    # Eine einzelne ausgelassene R-Zacke ist KEINE Lücke — sonst warnt die App bei jeder
    # Extrasystole und wird ignoriert.
    peaks = np.concatenate([np.arange(0, 300.0, 1.0), np.arange(302.0, dauer, 1.0)]) * fs
    assert coverage_gaps(peaks, fs, dauer) == ()


def test_hamilton_abbruch_wird_jetzt_als_luecke_gemeldet():
    """Die Verbindung zwischen Befund und Gegenmaßnahme: derselbe Detektor, der still ein
    Drittel verlor, meldet das jetzt über seine Abdeckung."""
    import pytest
    from analysis.ecg import validated_detectors_available, detect_r_peaks_validated_ex
    if not validated_detectors_available():
        pytest.skip("py-ecg-detectors nicht installiert (optionale Abhängigkeit)")
    from core.shared import load_and_prepare
    from analysis.ecg import detect_r_peaks_polarity_safe

    m = _manifest()
    edf = load_and_prepare(FIXTURE)
    sig = edf["data"][edf["ch_idx"][m["format"]["ecg_channel"]]].astype(float)
    corr, own, _ = detect_r_peaks_polarity_safe(sig, edf["sfreq"])

    res = detect_r_peaks_validated_ex(corr, edf["sfreq"], method="hamilton")
    assert res.has_coverage_gap, "der Abbruch bei 409 s wird nicht mehr gemeldet"
    assert res.coverage_frac < 0.8, f"Abdeckung {res.coverage_frac:.2f} — zu optimistisch"

    # Two-Average kommt durch und darf deshalb NICHT warnen — eine Prüfung, die immer
    # anschlägt, wäre wertlos.
    ok = detect_r_peaks_validated_ex(corr, edf["sfreq"], method="two_average")
    assert not ok.has_coverage_gap, f"Fehlalarm: {ok.coverage_gaps}"
    assert ok.coverage_frac > 0.99
