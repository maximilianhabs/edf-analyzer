"""
Hyperventilation (HVT) und Fotostimulation (PHOTO) Segmentierung.

Erkennt standardisierte NeuroFax-Annotations und teilt die Aufnahme in
klinisch definierte Phasen. Berechnet phasenspezifische HRV-Metriken
mit methodischen Hinweisen für jede Phase.

Annotation-Konventionen (NeuroFax):
  HVT START          — Beginn der Hyperventilation
  HVT MM:SS          — 30-s-Taktmarker während HV
  HVT END            — Ende der Hyperventilation
  POST HVT MM:SS     — Post-HV-Erholungsmarker (üblicherweise bis 02:00)
  PHOTO XHz          — Fotostimulationsfrequenz (je ~13 s)

Literaturgrundlage HRV während HV:
  - Sympathikusaktivierung → HR ↑, LF/HF ↑, RMSSD ↓
  - SDNN methodisch kompromittiert: Atemfrequenz > 0.4 Hz verschiebt RSA
    aus dem HF-Band heraus → artifizielle SDNN-Erhöhung durch mechanische
    Atemvariabilität, kein Abbild autonomer Modulation.
  - Post-HV: vagaler Rebound (~60–120 s), HR transienter < Baseline,
    RMSSD/HF-Power Anstieg.
  Quellen: Ravenswaaij-Arts 1993 Circulation; Brown 1993 Circulation;
           SUDEP-HV-HRV: PMC11531865 (2024).
"""

import re
from typing import Optional, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from analysis.ecg import RRSeries


# ─── Annotations-Parser ──────────────────────────────────────────────────────

def detect_hv_phases(annotations: list) -> dict:
    """
    Erkennt HVT/PHOTO-Phasen aus NeuroFax-Annotations.

    Rückgabe:
        {
          "has_hv": bool,
          "has_photo": bool,
          "pre_hv_end": float | None,        # = HVT START Zeit (s)
          "hvt_start": float | None,
          "hvt_end": float | None,
          "post_hv_end": float | None,        # hvt_end + 120 s
          "photo_events": list[dict],         # [{t, freq_hz}]
          "hvt_markers": list[float],         # 30-s-Taktmarker
          "post_hv_markers": list[float],
        }
    """
    result = {
        "has_hv": False, "has_photo": False,
        "pre_hv_end": None,
        "hvt_start": None, "hvt_end": None, "post_hv_end": None,
        "photo_events": [],
        "hvt_markers": [], "post_hv_markers": [],
    }

    for ann in annotations:
        t = float(ann["onset_s"])
        d = ann["description"].strip().upper()

        if d == "HVT START":
            result["hvt_start"] = t
            result["pre_hv_end"] = t
            result["has_hv"] = True

        elif d == "HVT END":
            result["hvt_end"] = t
            result["post_hv_end"] = t + 120.0

        elif re.match(r"HVT \d{2}:\d{2}$", d):
            result["hvt_markers"].append(t)

        elif re.match(r"POST HVT \d{2}:\d{2}$", d):
            result["post_hv_markers"].append(t)

        else:
            m = re.match(r"PHOTO\s+(\d+(?:\.\d+)?)\s*HZ?$", d)
            if m:
                result["photo_events"].append({"t": t, "freq_hz": float(m.group(1))})
                result["has_photo"] = True

    # Fallback: kein HVT END → letzte POST-Marker + 30 s als Schätzung
    if result["has_hv"] and result["hvt_end"] is None and result["hvt_markers"]:
        result["hvt_end"] = result["hvt_markers"][-1] + 30.0
        result["post_hv_end"] = result["hvt_end"] + 120.0

    return result


# ─── Segment-HRV ─────────────────────────────────────────────────────────────

def hrv_for_segment(rr_ms: np.ndarray, r_times: np.ndarray,
                    t0: float, t1: float) -> Optional[dict]:
    """
    Berechnet Basis-HRV-Metriken für ein Zeitfenster [t0, t1].
    Gibt None zurück wenn zu wenige Schläge vorhanden (< 10).

    Akzeptiert auch eine RRSeries statt roher Arrays:
        hrv_for_segment(rr_series.clean_rr, rr_series.clean_times, t0, t1)
    """
    mask = (r_times >= t0) & (r_times < t1)
    rr = rr_ms[mask]
    if len(rr) < 10:
        return None

    diff = np.diff(rr)
    return {
        "n_beats":   len(rr),
        "duration_s": t1 - t0,
        "mean_rr":   float(np.mean(rr)),
        "mean_hr":   float(60000 / np.mean(rr)),
        "sdnn":      float(np.std(rr, ddof=1)),
        "rmssd":     float(np.sqrt(np.mean(diff**2))) if len(diff) > 0 else 0.0,
        "pnn50":     float(np.sum(np.abs(diff) > 50) / max(len(diff), 1) * 100),
        "hr_min":    float(60000 / rr.max()),
        "hr_max":    float(60000 / rr.min()),
        "rr_ms":     rr,
        "r_times":   r_times[mask],
    }


# ─── Vagaler Rebound Check ────────────────────────────────────────────────────

def assess_vagal_rebound(pre_hv: dict, post_hv: dict) -> dict:
    """
    Bewertet den vagalen Rebound nach HV anhand Vergleich mit Prä-HV-Baseline.
    Kriterien nach Brown et al. 1993 / klinischer Praxis:
      - HR-Abfall: Post-HR deutlich < Prä-HR  (Rebound positiv)
      - RMSSD-Anstieg: Post-RMSSD > Prä-RMSSD
    """
    delta_hr   = post_hv["mean_hr"] - pre_hv["mean_hr"]
    delta_rmssd = post_hv["rmssd"] - pre_hv["rmssd"]
    pct_hr     = delta_hr / pre_hv["mean_hr"] * 100
    pct_rmssd  = delta_rmssd / pre_hv["rmssd"] * 100 if pre_hv["rmssd"] > 0 else 0.0

    if delta_hr < -3 and delta_rmssd > 2:
        rebound = "positiv"
        rebound_color = "#27ae60"
        rebound_icon  = "🟢"
        rebound_text  = "Vagaler Rebound vorhanden: HR < Baseline, RMSSD ↑"
    elif delta_hr < -1 or delta_rmssd > 1:
        rebound = "angedeutet"
        rebound_color = "#f39c12"
        rebound_icon  = "🟡"
        rebound_text  = "Leichter vagaler Rebound angedeutet"
    elif delta_hr > 3:
        rebound = "ausgeblieben / sympathisch"
        rebound_color = "#c0392b"
        rebound_icon  = "🔴"
        rebound_text  = "Kein vagaler Rebound — Post-HV HR > Baseline (sympathische Persistenz)"
    else:
        rebound = "neutral"
        rebound_color = "#7f8c8d"
        rebound_icon  = "⚪"
        rebound_text  = "Post-HV normalisiert, kein eindeutiger Rebound"

    return {
        "rebound": rebound,
        "color": rebound_color,
        "icon": rebound_icon,
        "text": rebound_text,
        "delta_hr": delta_hr,
        "delta_rmssd": delta_rmssd,
        "pct_hr": pct_hr,
        "pct_rmssd": pct_rmssd,
    }


# ─── Tachogramm mit Phasenbändern ────────────────────────────────────────────

PHASE_COLORS = {
    "pre_hv":  ("rgba(52,152,219,0.12)",  "#2980b9", "Prä-HV"),
    "hvt":     ("rgba(231,76,60,0.14)",   "#c0392b", "HVT aktiv"),
    "post_hv": ("rgba(39,174,96,0.14)",   "#27ae60", "Post-HVT"),
    "photo":   ("rgba(155,89,182,0.12)",  "#8e44ad", "Foto"),
}


def add_phase_bands(fig, phases: dict, duration_s: float):
    """Fügt farbige Phasenbänder in ein Plotly-Figure ein."""
    hvt_s = phases.get("hvt_start")
    hvt_e = phases.get("hvt_end")
    post_e = phases.get("post_hv_end")

    if hvt_s is not None:
        # Prä-HV
        _add_band(fig, 0, hvt_s, "pre_hv")
        # HVT
        if hvt_e is not None:
            _add_band(fig, hvt_s, hvt_e, "hvt")
            # Post-HV
            pe = min(post_e or (hvt_e + 120), duration_s)
            _add_band(fig, hvt_e, pe, "post_hv")

    photo_evs = phases.get("photo_events", [])
    if photo_evs:
        _add_band(fig, photo_evs[0]["t"], photo_evs[-1]["t"] + 13, "photo")


def _add_band(fig, x0, x1, phase_key):
    fill, line_c, label = PHASE_COLORS[phase_key]
    fig.add_vrect(
        x0=x0, x1=x1, fillcolor=fill, line_width=0,
        annotation_text=label, annotation_position="top left",
        annotation_font_size=9, annotation_font_color=line_c,
    )
