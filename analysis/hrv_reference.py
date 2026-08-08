"""
HRV-Referenzwerte und Schweregrad-Klassifikation — Laborwert-Stil.

Erwachsenen-Quellen:
- Hansen CS et al. (2024) Clin Auton Res 35:101-113 — n=875, 15-85 J., 5-Min-Ruhe-EKG,
  alters-/HF-adjustierte log-lineare Modelle für die untere 5.-Perzentil-Grenze.
- Task Force ESC/NASPE (1996) Circulation 93:1043-1065 — Frequenzbänder, Methodik.
- Billman GE (2013) Front Physiol 4:26 — Kritik an LF/HF als Sympathikus-Marker.

Pädiatrische Quellen (6–14 Jahre):
- Gąsior JS et al. (2018) Front Physiol 9:1495 — n=312 Kinder 6-13 J., 5-Min-EKG,
  HR-adjustierte Normwerte; HR ist Hauptprädiktor aller HRV-Parameter.
- Jarrin DC et al. (2015) J Sleep Res 24(5):554-7 — 9–11 J., Schlaflabor.
- Springer Meta-Analyse (2026): Pediatric Reference Limits for Holter HRV Parameters.
  Gąsior-Werte werden als HR-Quartil-Tabelle implementiert (P5/Median/P95).

Wichtig Pädiatrie: Grenzwertig-Zone ist eine pragmatische Annäherung analog zum
Erwachsenen-Modul — KEIN direkt publizierter Populationswert. Alle Werte orientierend.
"""

import numpy as np
from typing import Optional

# Pooled-Mediane [IQR] aus Hansen et al. 2024, Table 2 (n=875, 5-Min-Ruhe-EKG)
POOLED_REFERENCE = {
    "heart_rate": {"median": 67, "iqr": (61, 74), "unit": "bpm"},
    "sdnn":       {"median": 37, "iqr": (27, 54), "unit": "ms"},
    "rmssd":      {"median": 27, "iqr": (17, 44), "unit": "ms"},
    "lf_power":   {"median": 152, "iqr": (67, 368), "unit": "ms²"},
    "hf_power":   {"median": 100, "iqr": (38, 263), "unit": "ms²"},
    "total_power": {"median": 486, "iqr": (235, 1033), "unit": "ms²"},
}

# LF/HF-Ratio: unabhängig gegengeprüfter Wert (Billman 2013 zit. n. Frontiers-Übersicht)
LF_HF_MEAN = 2.8
LF_HF_SD = 2.6

# Marker-Typ pro Parameter — für die schnelle visuelle Einordnung (Badge in der UI)
# "para" = Parasympathikus/vagal, "symp" = Sympathikus-assoziiert, "mixed" = gemischt,
# "global" = globales autonomes Maß ohne Seitenzuordnung, "none" = kein ANS-Marker
MARKER_TYPE = {
    "heart_rate":    {"type": "none",   "label": "kein ANS-Marker"},
    "sdnn":          {"type": "global", "label": "Globaler Marker (Sympathikus + Parasympathikus)"},
    "rmssd":         {"type": "para",   "label": "Parasympathikus-Marker (vagal)"},
    "lf_power":      {"type": "mixed",  "label": "Gemischter Marker (v. a. Baroreflex)"},
    "hf_power":      {"type": "para",   "label": "Parasympathikus-Marker (vagal)"},
    "total_power":   {"type": "global", "label": "Globaler Marker"},
    "lf_hf_ratio":   {"type": "mixed",  "label": "↓ niedrig = parasympathikoton · ↑ hoch = sympathikoton"},
    "pnn50":         {"type": "para",   "label": "Parasympathikus-Marker (vagal)"},
    "cv":            {"type": "global", "label": "Globaler Marker (HF-normierte Gesamtvariabilität)"},
    "nn50":          {"type": "para",   "label": "Parasympathikus-Marker (vagal, längenabhängig)"},
    "dfa_a1":        {"type": "global", "label": "Nichtlinear — fraktale Korrelationsstruktur (α₁)"},
    # Neue Parameter (NeuroFax-analog)
    "lf_norm":       {"type": "mixed",  "label": "LF-Anteil (normiert) — Baroreflex-Dominanz"},
    "hf_norm":       {"type": "para",   "label": "HF-Anteil (normiert) — vagale Dominanz"},
    "hf_resp_rate":  {"type": "none",   "label": "Atemfrequenz aus EKG (RSA-Gipfel)"},
    "lf_peak_freq":  {"type": "none",   "label": "LF-Gipfelfrequenz (Mayer-Wellen)"},
}
MARKER_COLOR = {"para": "#1a5276", "symp": "#c0392b", "mixed": "#8e44ad", "global": "#555", "none": "#999"}

# Gedämpfte, augenfreundliche Grundfarben für Badge-Darstellung
# (Parasympathikus=Blau, Sympathikus=Rot) — analog zum Ampel-Stil: getönter
# Hintergrund + farbiger Text statt voller, satter Farbfläche.
BADGE_PARA = "#3d7ea6"
BADGE_SYMP = "#c0695f"
BADGE_NONE = "#888888"


def _iqr_sigma(iqr: tuple) -> float:
    """Schätzt Sigma einer (angenommen log-normalen) Verteilung aus dem IQR."""
    return (iqr[1] - iqr[0]) / 1.349


def hansen_p5_threshold(param: str, age: float, heart_rate: float) -> float:
    """
    Untere 5.-Perzentil-Normgrenze nach Hansen et al. 2024 (log-lineares Modell).
    param: 'sdnn', 'rmssd', 'hf_power', 'lf_power', 'total_power'
    """
    coefs = {
        "sdnn":        (5.43, 0.018, 0.022),
        "rmssd":       (6.46, 0.025, 0.039),
        "hf_power":    (10.21, 0.058, 0.066),
        "lf_power":    (7.86, 0.047, 0.031),
        "total_power": (9.33, 0.039, 0.037),
    }
    c0, c_age, c_hr = coefs[param]
    return float(np.exp(c0 - c_age * age - c_hr * heart_rate))


def pnn50_expected_from_rmssd(rmssd_ms: float) -> float:
    """
    Empirische Näherungsformel: erwartetes pNN50 [%] aus RMSSD [ms].
    Basis: Mietus JE et al. (2002) — pNN50 und RMSSD messen denselben physiologischen
    Prozess (vagale Kurzzeitvariabilität) mit r>0.92. Die sigmoide Beziehung ergibt sich
    aus der Normalverteilungsannahme der RR-Differenzen ΔRR ~ N(0, RMSSD²):
        pNN50 = P(|ΔRR| > 50) = 2 × [1 − Φ(50 / RMSSD)] = erfc(50 / (√2 × RMSSD))
    (die scipy-Identität erfc(x) = 2×[1−Φ(x×√2)] liefert direkt die zweiseitige
    Wahrscheinlichkeit — daher unten keine zusätzliche Division/Multiplikation mit 2).
    Praktische Kalibrierung: RMSSD=20ms → ~1%, RMSSD=40ms → ~21%, RMSSD=70ms → ~48%.
    """
    if rmssd_ms <= 0:
        return 0.0
    from scipy.special import erfc
    # erfc() gibt bereits die zweiseitige Wahrscheinlichkeit P(|ΔRR|>50ms) zurück —
    # keine Division durch 2 (das wäre nur für einseitige P(ΔRR>50ms) korrekt).
    return float(100.0 * erfc(50.0 / (np.sqrt(2) * rmssd_ms)))


def classify_parameter(param: str, value: float, age: float, heart_rate: float,
                        rmssd_ms: Optional[float] = None) -> dict:
    """
    Klassifiziert einen HRV-Parameter im Laborwert-Stil:
    Zone (pathologisch/grenzwertig/normal), Position auf 0-1-Skala für die Balkendarstellung,
    Schweregrad-Label.

    Für sdnn/rmssd/hf_power/lf_power/total_power: nutzt Hansen-2024-Formel (5. Perzentil).
    Für lf_hf_ratio: nutzt Mean±SD aus unabhängiger Übersichtsarbeit.
    """
    if param == "pnn50":
        # Bewertung via RMSSD-Konkordanz (Mietus 2002): pNN50 und RMSSD messen denselben
        # Prozess. Aus dem aktuellen RMSSD wird ein erwartetes pNN50 abgeleitet.
        # Abweichung >40% nach unten = Diskordanz-Hinweis (mögliche Ektopie/Artefakte).
        scale_max = max(50.0, value * 1.25)
        pos = float(np.clip(value / scale_max, 0, 1))
        pnn50_exp = pnn50_expected_from_rmssd(rmssd_ms) if rmssd_ms is not None else None
        if pnn50_exp is not None and pnn50_exp > 0.05:
            ratio = value / pnn50_exp if pnn50_exp > 0 else float("nan")
            # Bei sehr niedrigem erwartetem Wert (<2%) ist das Ratio unzuverlässig
            if pnn50_exp < 2.0:
                zone, severity = "normal", "—"
                direction = f"beide Werte sehr niedrig (erwartet {pnn50_exp:.2f}%)"
            elif ratio < 0.40:
                zone, severity = "grenzwertig", "stark diskordant"
                direction = f"↓ {ratio*100:.0f}% des Erwarteten — Ektopie/Artefakte prüfen"
            elif ratio < 0.65:
                zone, severity = "grenzwertig", "mäßig diskordant"
                direction = f"↓ {ratio*100:.0f}% des Erwarteten"
            elif ratio > 1.6:
                zone, severity = "grenzwertig", "hoch diskordant"
                direction = f"↑ {ratio*100:.0f}% des Erwarteten — ungewöhnlich"
            else:
                zone, severity = "normal", "—"
                direction = f"konkordant ({ratio*100:.0f}% des Erwarteten)"
        else:
            zone, severity, direction = "info", "—", "kein RMSSD-Vergleich"
        return {
            "param": param, "value": value, "zone": zone, "severity": severity,
            "direction": direction, "position": pos,
            "p5_threshold": pnn50_exp, "ref_lo": None, "ref_hi": None,
            "scale_max": scale_max, "pnn50_expected": pnn50_exp,
        }

    if param == "cv":
        # CV% = SDNN/mean_RR × 100 = SDNN × HR/600. Normgrenze aus der SDNN-P5
        # (Hansen 2024, alters-/HF-adjustiert) in CV umgerechnet → konsistent mit SDNN,
        # aber entkoppelt von der absoluten Herzfrequenz.
        sdnn_p5 = hansen_p5_threshold("sdnn", age, heart_rate)
        cv_p5 = sdnn_p5 * heart_rate / 600.0
        scale_max = max(12.0, value * 1.25)
        if value < cv_p5:
            zone = "pathologisch"
            severity = "stark" if value < cv_p5 * 0.6 else "mäßig"
        elif value < cv_p5 * 1.5:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        direction = "reduzierte Gesamtvariabilität" if value < cv_p5 * 1.5 else "—"
        return {
            "param": param, "value": value, "zone": zone, "severity": severity,
            "direction": direction, "position": float(np.clip(value / scale_max, 0, 1)),
            "p5_threshold": cv_p5, "ref_lo": cv_p5, "ref_hi": None, "scale_max": scale_max,
        }

    if param == "nn50":
        # Absolutzahl aufeinanderfolgender NN-Intervalle > 50 ms. Stark längen-/
        # schlagzahlabhängig → KEINE feste Populationsgrenze. Wertung erfolgt über
        # pNN50 (gleicher Prozess); hier deskriptiv/info, Marker wird in der UI
        # nach der pNN50-Zone eingefärbt.
        scale_max = max(10.0, value * 1.3)
        return {
            "param": param, "value": value, "zone": "info", "severity": "—",
            "direction": "Absolutzahl — längenabhängig, Wertung über pNN50", "position": 0.0,
            "p5_threshold": None, "ref_lo": None, "ref_hi": None, "scale_max": scale_max,
        }

    if param == "dfa_a1":
        # DFA α₁: gesunde fraktale Dynamik ~1.0. Zweiseitig — sowohl Abfall Richtung
        # 0.5 (Zufälligkeit/Dysregulation) als auch Anstieg >1.4 (Brown'sch) auffällig.
        # Orientierende Grenzen (Ruhe-HRV); kein publizierter harter Cutoff.
        ref_lo, ref_hi = 0.75, 1.25
        if value < 0.5 or value > 1.5:
            zone, severity = "pathologisch", "stark"
        elif value < ref_lo or value > ref_hi:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        if value < ref_lo:
            direction = "↓ Richtung Zufälligkeit (Korrelationsverlust/Dysregulation)"
        elif value > ref_hi:
            direction = "↑ Richtung Brown'sches Rauschen"
        else:
            direction = "gesunde 1/f-Dynamik"
        return {
            "param": param, "value": value, "zone": zone, "severity": severity,
            "direction": direction, "position": float(np.clip(value / 1.6, 0, 1)),
            "p5_threshold": None, "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": 1.6,
        }

    if param in ("lf_norm", "hf_norm"):
        # Task Force 1996: LF norm = 54 ± 4 nu, HF norm = 29 ± 3 nu (Ruhe, liegend)
        # Als %: LF 40–70%, HF 20–50% (grober klinischer Richtwert, keine harten Grenzen)
        scale_max = 100.0
        pos = float(np.clip(value / scale_max, 0, 1))
        if param == "lf_norm":
            ref_lo, ref_hi = 40.0, 70.0
            direction = "erhöht (sympathikoton)" if value > 70 else ("erniedrigt (vagal)" if value < 40 else "—")
        else:
            ref_lo, ref_hi = 20.0, 50.0
            direction = "erhöht (vagal)" if value > 50 else ("erniedrigt (sympathikoton)" if value < 20 else "—")
        zone = "normal" if ref_lo <= value <= ref_hi else "grenzwertig"
        return {
            "param": param, "value": value, "zone": zone, "severity": "—",
            "direction": direction, "position": pos,
            "p5_threshold": ref_lo, "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": scale_max,
        }

    if param == "hf_resp_rate":
        # Respiratorische Sinusarrhythmie-Gipfel = Atemfrequenz (Yasuma & Hayano 2004).
        # Normal im Ruhezustand: 12–20 /min.
        scale_max = 50.0
        pos = float(np.clip(value / scale_max, 0, 1))
        ref_lo, ref_hi = 12.0, 20.0
        if value < 10:
            zone, severity, direction = "grenzwertig", "Bradypnoe", "erniedrigt"
        elif value < 12:
            zone, severity, direction = "grenzwertig", "Untere Normgrenze", "erniedrigt"
        elif value > 25:
            zone, severity, direction = "grenzwertig", "Tachypnoe", "erhöht"
        elif value > 20:
            zone, severity, direction = "grenzwertig", "Obere Normgrenze", "erhöht"
        else:
            zone, severity, direction = "normal", "—", "—"
        return {
            "param": param, "value": value, "zone": zone, "severity": severity,
            "direction": direction, "position": pos,
            "p5_threshold": ref_lo, "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": scale_max,
        }

    if param == "lf_peak_freq":
        # Mayer-Wellen: typisch 0.07–0.12 Hz (Eckberg 1997, J Physiol 504:315)
        # Kein klinischer Cutoff — rein deskriptiv
        scale_max = 0.15
        pos = float(np.clip(value / scale_max, 0, 1))
        return {
            "param": param, "value": value, "zone": "info", "severity": "—",
            "direction": "—", "position": pos,
            "p5_threshold": None, "ref_lo": 0.07, "ref_hi": 0.12, "scale_max": scale_max,
        }

    if param == "heart_rate":
        # Klassische klinische Grenzen (Bradykardie/Tachykardie), nicht Hansen-formelbasiert
        if value < 40 or value > 150:
            zone, severity = "pathologisch", "stark"
        elif value < 60 or value > 100:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        direction = "bradykard" if value < 60 else ("tachykard" if value > 100 else "—")
        ref_lo, ref_hi = 60, 100
        scale_max = 180.0
        pos = float(np.clip(value / scale_max, 0, 1))
        return {
            "param": param, "value": value, "zone": zone, "severity": severity,
            "direction": direction, "position": pos,
            "p5_threshold": None,  # keine Perzentile — klinische Festgrenzen
            "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": scale_max,
        }

    if param == "lf_hf_ratio":
        lo_patho = LF_HF_MEAN - 2 * LF_HF_SD   # praktisch nie negativ relevant
        lo_border = LF_HF_MEAN - 1 * LF_HF_SD
        hi_border = LF_HF_MEAN + 1 * LF_HF_SD
        hi_patho = LF_HF_MEAN + 2 * LF_HF_SD
        ref_lo, ref_hi = max(0, lo_border), hi_border
        p5 = max(0.01, lo_border)
    else:
        p5 = hansen_p5_threshold(param, age, heart_rate)
        # Mindest-Delta für Gelbe Zone: bei sehr alten/kranken Patienten kann
        # 1.5×P5 biologisch zu schmal werden (z.B. RMSSD P5=10ms → Gelbe Zone nur 10–15ms).
        # Lösung: Gelbe Zone mindestens 5ms/ms²/% breit halten (je nach Einheit).
        _min_delta = {"sdnn": 5.0, "rmssd": 5.0,
                      "hf_power": 20.0, "lf_power": 20.0, "total_power": 50.0}.get(param, 0)
        border_hi = max(p5 * 1.5, p5 + _min_delta)
        ref = POOLED_REFERENCE[param]
        ref_lo, ref_hi = ref["iqr"]

    # Zonen-Klassifikation
    if param == "lf_hf_ratio":
        if value < lo_patho or value > hi_patho:
            zone, severity = "pathologisch", "stark"
        elif value < lo_border or value > hi_border:
            zone, severity = "grenzwertig", "leicht-mäßig"
        else:
            zone, severity = "normal", "—"
        direction = "erhöht (sympathikoton)" if value > hi_border else (
                    "erniedrigt (parasympathikoton)" if value < lo_border else "—")
    else:
        if value < p5:
            zone = "pathologisch"
            severity = "stark" if value < p5 * 0.6 else "mäßig"
        elif value < p5 * 1.5:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        direction = "erniedrigt" if value < p5 * 1.5 else "—"

    # scale_max: mindestens ref_hi*1.8, aber immer groß genug für den tatsächlichen Wert
    # (wichtig für Kinder mit physiologisch höherer HRV als Erwachsenen-Referenz)
    scale_max_base = ref_hi * 1.8 if param != "lf_hf_ratio" else hi_patho * 1.3
    scale_max = max(scale_max_base, value * 1.25)
    pos = float(np.clip(value / scale_max, 0, 1))

    return {
        "param": param, "value": value, "zone": zone, "severity": severity,
        "direction": direction, "position": pos,
        "p5_threshold": p5 if param != "lf_hf_ratio" else lo_border,
        "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": scale_max,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Pädiatrische Referenzwerte (Gąsior et al. 2018, Front Physiol 9:1495)
# n=312 Kinder 6-13 Jahre, 5-Min-Ruhe-EKG, HR-stratifiziert
# Werte: (P5, Median, P95) — P5 = untere Normgrenze (entspricht klinischer Alarmgrenze)
# Frequenzdomäne approximiert aus Gąsior-Tabellen + Massin 2000 + Jarrin 2015
# ──────────────────────────────────────────────────────────────────────────────
_PED_REF = {
    # HR ≤ 77 bpm (Q1 — niedrigste HR, höchste HRV)
    "Q1": {"hr_max": 77,
           "sdnn":        (30, 72, 135), "rmssd":       (28, 80, 160),
           "hf_power":    (160, 950, 4000), "lf_power":  (120, 650, 2800),
           "total_power": (650, 2400, 9000)},
    # HR 77-85 bpm (Q2)
    "Q2": {"hr_max": 85,
           "sdnn":        (25, 58, 112), "rmssd":       (24, 62, 135),
           "hf_power":    (120, 680, 3000), "lf_power":  (100, 520, 2200),
           "total_power": (500, 1900, 7500)},
    # HR 85-95 bpm (Q3 — typisch für Schulkind Ruhe)
    "Q3": {"hr_max": 95,
           "sdnn":        (22, 48, 95), "rmssd":        (20, 50, 110),
           "hf_power":    (95,  450, 2400), "lf_power":  (88, 400, 1900),
           "total_power": (440, 1550, 6000)},
    # HR > 95 bpm (Q4 — höchste HR, niedrigste HRV)
    "Q4": {"hr_max": 999,
           "sdnn":        (17, 38, 76), "rmssd":        (16, 40, 90),
           "hf_power":    (58, 270, 1600), "lf_power":  (65, 280, 1300),
           "total_power": (340, 1100, 4200)},
}

# Altersgruppen für die UI
PEDIATRIC_AGE_GROUPS = {
    "6–9 Jahre":  (6, 9),
    "10–14 Jahre": (10, 14),
}


def _ped_quartile(heart_rate: float) -> dict:
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        if heart_rate <= _PED_REF[q]["hr_max"]:
            return _PED_REF[q]
    return _PED_REF["Q4"]


def classify_parameter_pediatric(param: str, value: float, heart_rate: float,
                                   rmssd_ms: Optional[float] = None) -> dict:
    """
    Klassifiziert HRV-Parameter nach pädiatrischen Normwerten (Gąsior 2018).
    Gibt dasselbe Dict-Schema zurück wie classify_parameter() für Erwachsene.
    """
    if param == "pnn50":
        # Gleiche Konkordanz-Logik wie Erwachsene (Mietus-Formel ist altersunabhängig)
        scale_max = max(50.0, value * 1.25)
        pos = float(np.clip(value / scale_max, 0, 1))
        pnn50_exp = pnn50_expected_from_rmssd(rmssd_ms) if rmssd_ms is not None else None
        if pnn50_exp is not None and pnn50_exp > 0.05:
            ratio = value / pnn50_exp if pnn50_exp > 0 else float("nan")
            if pnn50_exp < 2.0:
                zone, severity = "normal", "—"
                direction = f"beide Werte sehr niedrig (erwartet {pnn50_exp:.2f}%)"
            elif ratio < 0.40:
                zone, severity = "grenzwertig", "stark diskordant"
                direction = f"↓ {ratio*100:.0f}% des Erwarteten — Ektopie/Artefakte prüfen"
            elif ratio < 0.65:
                zone, severity = "grenzwertig", "mäßig diskordant"
                direction = f"↓ {ratio*100:.0f}% des Erwarteten"
            elif ratio > 1.6:
                zone, severity = "grenzwertig", "hoch diskordant"
                direction = f"↑ {ratio*100:.0f}% des Erwarteten — ungewöhnlich"
            else:
                zone, severity = "normal", "—"
                direction = f"konkordant ({ratio*100:.0f}% des Erwarteten)"
        else:
            zone, severity, direction = "info", "—", "kein RMSSD-Vergleich"
        return {"param": param, "value": value, "zone": zone, "severity": severity,
                "direction": direction, "position": pos,
                "p5_threshold": pnn50_exp, "ref_lo": None, "ref_hi": None,
                "scale_max": scale_max, "pnn50_expected": pnn50_exp}

    if param == "cv":
        # CV% = SDNN × HR/600. Pädiatrische SDNN-P5 (Gąsior, HR-stratifiziert) → CV.
        ref = _ped_quartile(heart_rate)
        sdnn_p5 = ref["sdnn"][0]
        cv_p5 = sdnn_p5 * heart_rate / 600.0
        scale_max = max(14.0, value * 1.25)
        if value < cv_p5:
            zone = "pathologisch"
            severity = "stark" if value < cv_p5 * 0.6 else "mäßig"
        elif value < cv_p5 * 1.5:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        direction = "reduzierte Gesamtvariabilität" if value < cv_p5 * 1.5 else "—"
        return {"param": param, "value": value, "zone": zone, "severity": severity,
                "direction": direction, "position": float(np.clip(value / scale_max, 0, 1)),
                "p5_threshold": cv_p5, "ref_lo": cv_p5, "ref_hi": None, "scale_max": scale_max}

    if param == "nn50":
        scale_max = max(10.0, value * 1.3)
        return {"param": param, "value": value, "zone": "info", "severity": "—",
                "direction": "Absolutzahl — längenabhängig, Wertung über pNN50", "position": 0.0,
                "p5_threshold": None, "ref_lo": None, "ref_hi": None, "scale_max": scale_max}

    if param == "dfa_a1":
        # Fraktale Dynamik ~1.0 weitgehend altersunabhängig — gleiche orientierende Grenzen.
        ref_lo, ref_hi = 0.75, 1.25
        if value < 0.5 or value > 1.5:
            zone, severity = "pathologisch", "stark"
        elif value < ref_lo or value > ref_hi:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        direction = ("↓ Richtung Zufälligkeit" if value < ref_lo else
                     ("↑ Richtung Brown'sch" if value > ref_hi else "gesunde 1/f-Dynamik"))
        return {"param": param, "value": value, "zone": zone, "severity": severity,
                "direction": direction, "position": float(np.clip(value / 1.6, 0, 1)),
                "p5_threshold": None, "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": 1.6}

    if param == "heart_rate":
        if value < 40 or value > 200:
            zone, severity = "pathologisch", "stark"
        elif value < 60 or value > 130:
            zone, severity = "grenzwertig", "leicht"
        else:
            zone, severity = "normal", "—"
        direction = "bradykard" if value < 60 else ("tachykard" if value > 130 else "—")
        scale_max = max(200.0, value * 1.25)
        pos = float(np.clip(value / scale_max, 0, 1))
        return {"param": param, "value": value, "zone": zone, "severity": severity,
                "direction": direction, "position": pos,
                "p5_threshold": 60.0, "ref_lo": 60, "ref_hi": 130, "scale_max": scale_max}

    if param == "lf_hf_ratio":
        # Kinder haben physiologisch niedrigere LF/HF-Ratio (mehr Parasympathikus)
        lo_patho, lo_border = 0.0, 0.3
        hi_border, hi_patho = 3.5, 6.0
        ref_lo, ref_hi = lo_border, hi_border
        if value < lo_patho or value > hi_patho:
            zone, severity = "pathologisch", "stark"
        elif value < lo_border or value > hi_border:
            zone, severity = "grenzwertig", "leicht-mäßig"
        else:
            zone, severity = "normal", "—"
        direction = "erhöht (sympathikoton)" if value > hi_border else (
                    "erniedrigt (parasympathikoton)" if value < lo_border else "—")
        scale_max = max(hi_patho * 1.3, value * 1.25)
        pos = float(np.clip(value / scale_max, 0, 1))
        return {"param": param, "value": value, "zone": zone, "severity": severity,
                "direction": direction, "position": pos,
                "p5_threshold": lo_border, "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": scale_max}

    q = _ped_quartile(heart_rate)
    if param not in q:
        # Fallback auf Erwachsenen-Klassifikation für unbekannte Parameter
        return classify_parameter(param, value, age=12, heart_rate=heart_rate)

    p5, median, p95 = q[param]
    ref_lo, ref_hi = p5, p95

    if value < p5:
        zone = "pathologisch"
        severity = "stark" if value < p5 * 0.6 else "mäßig"
    elif value < p5 * 1.5:
        zone, severity = "grenzwertig", "leicht"
    else:
        zone, severity = "normal", "—"

    direction = "erniedrigt" if value < p5 * 1.5 else "—"

    scale_max = max(p95 * 1.5, value * 1.25)
    pos = float(np.clip(value / scale_max, 0, 1))

    return {"param": param, "value": value, "zone": zone, "severity": severity,
            "direction": direction, "position": pos,
            "p5_threshold": p5, "ref_lo": ref_lo, "ref_hi": ref_hi, "scale_max": scale_max}


def compute_autonomic_balance(rmssd: float, hf_power: float, lf_hf_ratio: float) -> dict:
    """
    Heuristischer Sympathikus/Parasympathikus-Balance-Index (-100 .. +100).
    NICHT klinisch validiert — kombiniert vorhandene Marker zu einer
    orientierenden Gesamttendenz. Negativ = parasympathikoton, positiv = sympathikoton.
    """
    z_rmssd = (rmssd - POOLED_REFERENCE["rmssd"]["median"]) / _iqr_sigma(POOLED_REFERENCE["rmssd"]["iqr"])
    z_hf = (hf_power - POOLED_REFERENCE["hf_power"]["median"]) / _iqr_sigma(POOLED_REFERENCE["hf_power"]["iqr"])
    z_lfhf = (lf_hf_ratio - LF_HF_MEAN) / LF_HF_SD

    # hohe RMSSD/HF = parasympathisch (negativer Beitrag zum "sympathisch positiv" Index)
    raw = (z_lfhf - z_rmssd - z_hf) / 3.0
    scaled = float(np.tanh(raw / 1.5) * 100)   # weiche Begrenzung auf ±100

    abs_s = abs(scaled)
    if abs_s < 15:
        label = "ausgeglichen"
    elif abs_s < 40:
        label = "leicht " + ("sympathikoton" if scaled > 0 else "parasympathikoton")
    elif abs_s < 70:
        label = "mäßig " + ("sympathikoton" if scaled > 0 else "parasympathikoton")
    else:
        label = "stark " + ("sympathikoton" if scaled > 0 else "parasympathikoton")

    return {"index": scaled, "label": label}
