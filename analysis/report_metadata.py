"""
Gemeinsame Parameter-Metadaten (Einheit, kurze Erklärung) + Laborwert-Stil-Bewertung
für ALLE Report-Ausgaben (Standard-PDF/Excel, HRV-PDF, Visual/Glory-PDF).

Bündelt, was vorher pro Report-Generator separat (und teils nicht alters-adjustiert)
gepflegt wurde — Start der Report-Überarbeitung, siehe [[project_edf_report_audit]] für
den Gesamtplan. Die eigentliche Bewertungslogik bleibt in `analysis/hrv_reference.py`
(Single Source of Truth, identisch zur Live-App-Seite `views/ecg_hrv.py`) — dieses Modul
liefert nur eine dünne, report-taugliche Fassade (einheitliches Rückgabeformat, NaN-sicher)
plus die Definitionstexte (Akronym-Erklärungen für Leser ohne App-Kontext).
"""
from __future__ import annotations

# ── HRV-Parameter: Label, Einheit, kurze Erklärung (Akronym/Begriff → Bedeutung) ──────────
HRV_PARAM_DEFS = {
    "heart_rate":  {"label": "Herzfrequenz", "unit": "bpm",
                    "definition": "Mittlere Herzschlagfrequenz über den Analysezeitraum."},
    "mean_rr":     {"label": "Mittleres RR", "unit": "ms",
                    "definition": "Mittlerer Abstand zweier R-Zacken im EKG (= 60000 / Herzfrequenz)."},
    "sdnn":        {"label": "SDNN", "unit": "ms",
                    "definition": "Standardabweichung aller Normal-Normal(RR)-Intervalle — "
                                  "globales Maß der Gesamt-Herzratenvariabilität (Sympathikus + Parasympathikus)."},
    "cv":          {"label": "CV", "unit": "%",
                    "definition": "Variationskoeffizient (SDNN/mittleres RR) — herzfrequenz-"
                                  "unabhängiges globales Variabilitätsmaß."},
    "rmssd":       {"label": "RMSSD", "unit": "ms",
                    "definition": "Wurzel der mittleren quadrierten Differenz aufeinanderfolgender "
                                  "RR-Intervalle — robustester vagaler (parasympathischer) Kurzzeit-Marker."},
    "pnn50":       {"label": "pNN50", "unit": "%",
                    "definition": "Anteil aufeinanderfolgender RR-Intervalle, die sich um mehr als "
                                  "50 ms unterscheiden — vagaler Marker, eng korreliert mit RMSSD."},
    "pnn20":       {"label": "pNN20", "unit": "%",
                    "definition": "Wie pNN50, aber mit 20-ms-Schwelle — sensitiver, v. a. bei "
                                  "niedriger Gesamtvariabilität."},
    "nn50":        {"label": "NN50", "unit": "Anzahl",
                    "definition": "Absolute Zahl der RR-Intervall-Paare mit Differenz > 50 ms "
                                  "(Rohwert hinter pNN50, längenabhängig)."},
    "sd1":         {"label": "SD1", "unit": "ms",
                    "definition": "Poincaré-Plot-Querstreuung — kurzfristige (vagale) Variabilität, "
                                  "≈ RMSSD/√2."},
    "sd2":         {"label": "SD2", "unit": "ms",
                    "definition": "Poincaré-Plot-Längsstreuung — langfristige Variabilität, ≈ SDNN."},
    "sd2_sd1":     {"label": "SD2/SD1", "unit": "Ratio",
                    "definition": "Verhältnis lang- zu kurzfristiger Variabilität (Poincaré-Plot-Form)."},
    "dfa_a1":      {"label": "DFA α1", "unit": "—",
                    "definition": "Detrended-Fluctuation-Analysis-Skalierungsexponent (kurzfristig) — "
                                  "Maß der fraktalen Selbstähnlichkeit der RR-Serie; ~1,0 = gesunde "
                                  "1/f-artige Dynamik."},
    "samp_en":     {"label": "Sample Entropy", "unit": "—",
                    "definition": "Maß der Signalregelmäßigkeit/-komplexität — niedrigere Werte "
                                  "bedeuten eine regelmäßigere RR-Folge."},
    "edr_rate":    {"label": "Atemfrequenz (EDR)", "unit": "/min",
                    "definition": "Aus der R-Zacken-Amplitudenmodulation rekonstruierte Atemfrequenz "
                                  "(ECG-Derived Respiration)."},
    "pct_removed": {"label": "Artefaktrate RR", "unit": "%",
                    "definition": "Anteil der als Artefakt entfernten Herzschläge an der RR-Serie."},
    "total_power": {"label": "Total Power", "unit": "ms²",
                    "definition": "Gesamtleistung des RR-Spektrums (VLF+LF+HF) — globales Maß der "
                                  "autonomen Variabilität."},
    "vlf_power":   {"label": "VLF-Leistung", "unit": "ms²",
                    "definition": "Sehr niedrige Frequenz (0,003–0,04 Hz) — Thermoregulation/Renin-"
                                  "Angiotensin-System; bei Kurzzeitmessung methodisch unsicher."},
    "lf_power":    {"label": "LF-Leistung", "unit": "ms²",
                    "definition": "Niederfrequente Leistung (0,04–0,15 Hz) — gemischter Marker, "
                                  "v. a. Baroreflex."},
    "hf_power":    {"label": "HF-Leistung", "unit": "ms²",
                    "definition": "Hochfrequente Leistung (0,15–0,40 Hz) — vagaler Marker, entspricht "
                                  "der respiratorischen Sinusarrhythmie (Atmung)."},
    "lf_hf_ratio": {"label": "LF/HF-Ratio", "unit": "Ratio",
                    "definition": "Verhältnis LF/HF — historisch als sympathovagale Balance "
                                  "interpretiert, methodisch umstritten (Billman 2013)."},
    "lf_norm":     {"label": "LF normiert", "unit": "%",
                    "definition": "LF/(LF+HF)×100 — Task-Force-1996-Normierung, entkoppelt von "
                                  "VLF/Gesamtleistung."},
    "hf_norm":     {"label": "HF normiert", "unit": "%",
                    "definition": "HF/(LF+HF)×100 — normierter vagaler Anteil."},
    "lf_peak_freq": {"label": "LF-Gipfel", "unit": "Hz",
                     "definition": "Frequenz des höchsten Ausschlags im LF-Band (Mayer-Wellen, ~0,1 Hz)."},
    "hf_peak_freq": {"label": "HF-Gipfel", "unit": "Hz",
                     "definition": "Frequenz des höchsten Ausschlags im HF-Band — entspricht der Atemfrequenz."},
    "hf_resp_rate": {"label": "Atemfrequenz (HF-Gipfel)", "unit": "/min",
                     "definition": "Aus dem HF-Spektralgipfel abgeleitete Atemfrequenz — "
                                   "Quervergleich zur EDR-Schätzung."},
}

# Zonen → kompakte deutsche Bewertungs-Label (Laborwert-Stil)
_ZONE_LABEL = {"normal": "normal", "pathologisch": "auffällig", "grenzwertig": "grenzwertig",
              "info": "—"}


# ── EEG-Parameter: Label, Einheit, kurze Erklärung ─────────────────────────────────────────
EEG_PARAM_DEFS = {
    "par":         {"label": "Alpha-PAR (ganzer Kopf)", "unit": "Ratio",
                    "definition": "Anterior-Posterior-Ratio des Alpha-Bands über den ganzen "
                                  "Kopf — Maß des posterioren Grundrhythmus (Colombo 2023/"
                                  "Maschke 2025). >1 = physiologisch posterior-dominantes Alpha."},
    "ap_ratio":    {"label": "Post/Ant Alpha-Ratio", "unit": "Ratio",
                    "definition": "Verhältnis der Alpha-Power posterior (O1/O2) zu anterior "
                                  "(F3/F4) — analog zur Alpha-PAR, aber elektrodenpaarbasiert."},
    "ap_post":     {"label": "Alpha-Gipfel posterior", "unit": "Hz",
                    "definition": "Frequenz des dominanten Alpha-Peaks über den posterioren "
                                  "Elektroden (O1/O2) — der klassische posterior dominant rhythm."},
    "exp_own":     {"label": "Aperiod. Exponent 1–20 Hz", "unit": "—",
                    "definition": "Steilheit des 1/f-Hintergrundspektrums (aperiodische "
                                  "Komponente, ohne Alpha/Beta-Rhythmen) — Proxy für die "
                                  "Erregungs-/Hemmungs-Balance (E/I) des Kortex (Gao/Voytek 2017)."},
    "ai":          {"label": "Asymmetrie-Index (AI)", "unit": "%",
                    "definition": "(links−rechts)/(links+rechts) × 100 % je Frequenzband — "
                                  "Interhemisphären-Vergleich der Bandpower (Nuwer 1997)."},
}


def grade_eeg(param: str, value, age=None, band: str = None) -> dict:
    """Laborwert-Bewertung eines EEG-Parameters — nutzt dieselben Zonen-Schwellen wie die
    Live-App-Seiten (`views/eeg_spectrum.py`), damit Report und App nie auseinanderlaufen.
    `age` nötig für "ap_post" (altersadaptives Alpha-Suchband) und "exp_own" (altersadaptierter
    Exponenten-Erwartungsbereich). `band` nötig für "ai" (nur informativ im ref_text)."""
    if value is None or (isinstance(value, float) and value != value):
        return {"zone": "info", "label": "—", "ref_text": "—"}

    if param in ("par", "ap_ratio"):
        # Identische Schwellen wie views/eeg_spectrum.py (_pzone/_apl-Logik)
        if value >= 1.0:
            zone, label = "normal", "normal"
        elif value >= 0.6:
            zone, label = "grenzwertig", "grenzwertig"
        else:
            zone, label = "pathologisch", "auffällig"
        return {"zone": zone, "label": label, "ref_text": "≥ 1,0 (posterior-dominant)"}

    if param == "ai":
        # Binäres Nuwer-1997-Kriterium, identisch zur Live-App (kein zusätzlicher Zwischenwert
        # erfunden — nur EIN publizierter Cutoff bekannt)
        if abs(value) <= 20:
            zone, label = "normal", "normal"
        else:
            zone, label = "pathologisch", "auffällig"
        return {"zone": zone, "label": label, "ref_text": "|AI| ≤ 20 %"}

    if param == "ap_post":
        from views.eeg_spectrum import _alpha_band
        lo, hi = _alpha_band(age if age is not None else 50)
        if lo <= value <= hi:
            zone, label = "normal", "normal"
        elif lo - 1.0 <= value <= hi + 1.0:
            zone, label = "grenzwertig", "grenzwertig"
        else:
            zone, label = "pathologisch", "auffällig"
        return {"zone": zone, "label": label, "ref_text": f"{lo:.0f}–{hi:.0f} (altersadaptiv)"}

    if param == "exp_own":
        from views.aperiodic import _age_expected_band
        lo, hi, _lbl = _age_expected_band(age if age is not None else 50)
        if lo <= value <= hi:
            zone, label = "normal", "normal"
        else:
            zone, label = "grenzwertig", "grenzwertig"
        return {"zone": zone, "label": label, "ref_text": f"{lo:.1f}–{hi:.1f} ({_lbl})"}

    return {"zone": "info", "label": "—", "ref_text": "—"}


def grade_hrv(param: str, value, age, heart_rate, rmssd_ms=None, is_pediatric: bool = False) -> dict:
    """Einheitliche Laborwert-Bewertung eines HRV-Parameters — Hansen 2024 (Erwachsene)
    bzw. Gąsior 2018 (Kinder), IDENTISCH zur Live-App (`views/ecg_hrv.py::classify_parameter`,
    keine eigene/abweichende Logik). NaN-/None-sicher (gibt neutrale Info-Zone zurück).

    Rückgabe: {"zone", "severity", "direction", "label" (fertig formatiert, z.B. "leicht
    pathologisch"), "source" (zitierte Referenz), "ref_text" (kompakter Normbereich-String)}
    plus alle Original-Felder von classify_parameter (p5_threshold, ref_lo, ref_hi, position, …).
    """
    if value is None or (isinstance(value, float) and value != value):
        return {"zone": "info", "severity": "—", "direction": "—", "label": "—",
                "source": "—", "ref_text": "—"}
    from analysis.hrv_reference import classify_parameter, classify_parameter_pediatric
    try:
        if is_pediatric:
            cls = classify_parameter_pediatric(param, value, heart_rate, rmssd_ms=rmssd_ms)
            source = "Gąsior 2018 (pädiatrisch)"
        else:
            cls = classify_parameter(param, value, age, heart_rate, rmssd_ms=rmssd_ms)
            source = ("Hansen 2024" if param in
                      ("sdnn", "rmssd", "hf_power", "lf_power", "total_power", "cv")
                      else "Task Force 1996 / Literatur")
    except Exception:
        return {"zone": "info", "severity": "—", "direction": "—", "label": "—",
                "source": "—", "ref_text": "—"}

    zone = cls.get("zone", "info")
    severity = cls.get("severity") or "—"
    if zone == "normal":
        label = "normal"
    elif zone == "info":
        label = "—"
    elif severity and severity not in ("—", ""):
        label = f"{severity} {_ZONE_LABEL.get(zone, zone)}"
    else:
        label = _ZONE_LABEL.get(zone, zone)

    def _num(v: float) -> str:
        return f"{v:.0f}" if abs(v) >= 10 else f"{v:.2f}".rstrip("0").rstrip(".")

    ref_text = "—"
    if cls.get("p5_threshold") is not None:
        ref_text = f"≥ {_num(cls['p5_threshold'])} (P5, {source})"
    elif cls.get("ref_lo") is not None and cls.get("ref_hi") is not None:
        ref_text = f"{_num(cls['ref_lo'])}–{_num(cls['ref_hi'])}"

    return {**cls, "label": label, "source": source, "ref_text": ref_text}
