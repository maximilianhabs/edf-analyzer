"""
🫀 Rhythmus-Screening — eigene Seite (Add-on, ändert die bestehende EKG&HRV-Seite NICHT).

Starke Visualisierung des Rhythmus-Screenings (Stufen ①–③b):
- Ampel-Übersicht (AFib-Verdacht / Ektopie-Verdacht / unauffällig)
- 1-Minuten-Fenster-Navigator über die gesamte Aufnahme (Rohsignal, R-Zacken farbcodiert,
  Artefakt-Zonen schattiert)
- PQRST-Ensemble & P-Welle (Stufe②b): Schlag-Summation des aktuellen Fensters, P-Wellen-
  Kohärenz als zweite, RR-unabhängige AFib-Evidenz — läuft auf JEDEM Fenster, nicht nur bei
  AFib-Verdacht (siehe analysis/p_wave_analysis.py)
- Artefakt-Galerie: exemplarische Ausschnitte der als Artefakt verworfenen Abschnitte
- Manuelle R-Zacken-Korrektur: Klick auf eine Markierung entfernt sie aus der Analyse

Siehe [[project_edf_rhythm_screening]] für Konzept, Literatur und Referenzfälle.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core.shared import get_edf_or_stop, section_header, safe_slider, render_banner, status_dot
from analysis.ecg import detect_r_peaks_validated
from analysis.ecg_quality import sqi_segments
from analysis.rhythm_screening import classify_afib_risk, combine_with_pwave
from analysis.ectopy_detection import ectopy_summary
from analysis.p_wave_analysis import bandpass_ecg, analyze_window as p_analyze_window, P_WIN

WIN_S = 60.0  # 1-Minuten-Fenster (User-Feedback 2026-08-08: 2 Minuten zu dicht für einzelne QRS)

# Detektor-Umschaltung (Backlog-Punkt, Anstoß Ruhid — siehe [[project_edf_rhythm_screening]]):
# "eigen" bleibt Default (bewährt, siehe [[feedback_edf_qrs_vorsicht]]); die anderen laufen über
# py-ecg-detectors (analysis/ecg.py:detect_r_peaks_validated). Method-Codes = Parameter für
# detect_r_peaks_validated(), None = eigener Detektor.
DETECTOR_METHODS = {
    "eigen (Standard, vereinfachtes Pan-Tompkins)": None,
    "Hamilton 2002 (validiert)": "hamilton",
    "Christov 2004 (validiert)": "christov",
    "Pan-Tompkins 1985 (validiert)": "pan_tompkins",
    "Engelse-Zeelenberg (validiert)": "engzee",
    "Two-Average / Elgendi 2013 (validiert)": "two_average",
}


def _overrides_key(edf_path: str, ch: str, method_label: str) -> str:
    return f"rhythm_removed_peaks::{edf_path}::{ch}::{method_label}"


@st.cache_data(show_spinner="Erkenne R-Zacken für Rhythmus-Screening…")
def _detect(edf_path: str, ch: str, method: str | None):
    from core.loader import load_edf
    raw = load_edf(edf_path, preload=True)
    idx = raw.ch_names.index(ch)
    fs = raw.info["sfreq"]
    sig_v = raw[:][0][idx].astype(np.float64)
    sig_v -= sig_v.mean()
    # Polaritäts-Flip + Nachverfeinerung über den gemeinsamen, getesteten Helfer (analysis/ecg.py
    # — genutzt von dieser Seite UND von ecg_hrv.py::compute_rr(), damit beide Pfade konsistent
    # bleiben). Details/Herleitung siehe [[project_edf_rhythm_screening]].
    from analysis.ecg import detect_r_peaks_polarity_safe
    sig_v, eigen_peaks, was_flipped = detect_r_peaks_polarity_safe(sig_v, fs)
    # Bei gewähltem validiertem Detektor (nicht "eigen"): läuft NACH dem Flip auf dem bereits
    # korrekt orientierten Signal (detect_r_peaks_validated ruft intern refine_peaks() auf,
    # ist also konsistent mit dem eigenen Pfad).
    peaks = eigen_peaks if method is None else detect_r_peaks_validated(sig_v, fs, method)
    # was_flipped=True heißt: die QRS-Auslenkung war im ROHEN Signal negativ dominant — bei
    # Standard-EKG-Elektrodenanlage sollte R positiv sein (User-Bestätigung 2026-08-08: verifiziert
    # an GA2410DH mit komplett unverarbeitetem Rohsignal, echte QRS-Komplexe, kein Artefakt).
    # Typische Ursache: vertauschte/falsch angelegte Elektroden bei der Ableitung. Analyse bleibt
    # trotzdem möglich (Polarität wird automatisch korrigiert) — UI zeigt einen Hinweis, siehe
    # render(). WICHTIG: EEG-Viewer/EDF-Cropper zeigen dasselbe Signal ggf. trotzdem "aufrecht",
    # weil sie die klinische EEG-Konvention "Negativität nach oben" (DGKN/IFCN) auf ALLE Kanäle
    # anwenden, auch EKG — ein negativer QRS erscheint dort durch Zufall zweier sich aufhebender
    # Konventionen aufrecht, ist aber nach EKG-Standard-Konvention trotzdem invertiert.
    return sig_v * 1e6, peaks, fs, was_flipped  # µV, Sample-Indizes, Hz, Polaritäts-Flag


@st.cache_data(show_spinner="Vergleiche mit/ohne Polaritäts-Korrektur…")
def _detect_flip_diagnostic(edf_path: str, ch: str):
    """UI-Wrapper um `analysis.ecg.flip_diagnostic()` (gemeinsamer, getesteter Helfer — auch
    von ecg_hrv.py genutzt). Reproduziert BEWUSST den alten, fehleranfälligen Pfad (Peak-
    Erkennung/-verfeinerung VOR dem Flip) neben dem korrigierten Pfad, NUR für die Diagnose-
    Visualisierung im UI (User-Anfrage 2026-08-08)."""
    from core.loader import load_edf
    from analysis.ecg import flip_diagnostic
    raw = load_edf(edf_path, preload=True)
    idx = raw.ch_names.index(ch)
    fs = raw.info["sfreq"]
    sig0 = raw[:][0][idx].astype(np.float64)
    sig0 -= sig0.mean()
    return {"fs": fs, **flip_diagnostic(sig0, fs)}


def render():
    st.title(":material/monitor_heart: Rhythmus-Screening")
    st.caption(
        "Add-on — prüft auf Vorhofflimmern-Verdacht (CosEn, Lake & Moorman 2011) und "
        "Extrasystolen-Hinweise (Kompensationspause + QRS-Breite), VOR der eigentlichen "
        "HRV-Analyse. Ändert die bestehende EKG-&-HRV-Seite nicht — reiner Zusatzbefund. "
        "**Screening, keine Diagnose.**"
    )
    edf, edf_path = get_edf_or_stop()
    ecg_channels = edf.get("ecg_channels") or []
    all_non_eeg = [c for c in edf["ch_idx"].keys() if c not in edf.get("eeg_map", {})]
    cch1, cch2 = st.columns([1, 1])
    ch = cch1.selectbox(
        "EKG-Kanal", ecg_channels + [c for c in all_non_eeg if c not in ecg_channels],
        index=0, key="rhythm_ch",
    )
    det_label = cch2.selectbox(
        "R-Zacken-Detektor", list(DETECTOR_METHODS.keys()), index=0, key="rhythm_detector",
        help="Der eigene Detektor bleibt Default (bewährt). Bei Zweifeln/unklaren Fällen "
             "auf einen validierten Detektor umschalten und vergleichen — beeinflusst das "
             "gesamte Rhythmus-Screening dieser Seite (Artefakte/AFib/Ektopie/P-Welle).",
    )
    det_method = DETECTOR_METHODS[det_label]
    if det_method is not None:
        st.caption(f"ℹ️ Aktiver Detektor: **{det_label}** (nicht Default) — Ergebnisse dieser "
                   "Seite basieren auf diesem Detektor, bis zurückgeschaltet wird.")

    sig_uv, peaks_all, fs, was_flipped = _detect(edf_path, ch, det_method)
    dur_s = len(sig_uv) / fs

    # Polaritäts-Hinweis (User-Vorgabe 2026-08-08, PRÄZISIERT 2026-08-08 nach Gegenprüfung mit
    # SYNTH_groundtruth.edf): Verifiziert an GA2410DH + CA177326 + 25-Datei-Stichprobe — ALLE
    # echten Aufnahmen mit POL-X1-Kanal zeigen dieselbe negative R-Zacke im Rohsignal. Das ist
    # NICHT eine Anomalie bei einzelnen Patienten/Ableitungen, sondern die durchgehende,
    # verlässliche GERÄTEKONVENTION dieses Aufnahmesystems für diesen Kanal — bestätigt durch
    # den Gegenbeweis mit unserem eigenen synthetischen Ground-Truth-EDF (nach Kardiologie-
    # Lehrbuch mit R positiv gebaut): GENAU DIESE Datei ist die einzige, die im EEG-Viewer/
    # EDF-Cropper "falsch herum" aussieht — weil deren Rohsignal tatsächlich standard-konform
    # ist, während echte Aufnahmen es systematisch nicht sind. Text bewusst als neutrale
    # Information, NICHT als Fehler-/Warnhinweis formuliert — siehe [[project_edf_rhythm_screening]].
    if was_flipped:
        render_banner(
            "info", "Kanal-Polaritätskonvention erkannt und für die Darstellung angepasst",
            "Die QRS-Auslenkung ist im Rohsignal dieses Kanals negativ dominant. Das ist bei "
            "diesem Kanal (POL X1) die durchgehende, verlässliche Konvention dieses "
            "Aufnahmesystems — kein Hinweis auf ein Problem bei dieser Ableitung. Für die "
            "Darstellung und Analyse wird die Polarität automatisch so ausgerichtet, dass die "
            "R-Zacke wie klinisch gewohnt nach oben zeigt; alle Zahlen bleiben unverändert gültig.")

        # Vergleichs-Diagnose "mit/ohne Flip" (User-Anfrage 2026-08-08): macht den Effekt an
        # DIESER konkreten Aufnahme sichtbar, statt nur zu behaupten. Zeigt exakt den Fehler,
        # den `views/ecg_hrv.py::compute_rr()` aktuell noch macht (Peak-Verfeinerung VOR dem
        # Flip) — Aufklärung, kein Ersatz für den noch ausstehenden Fix dort.
        with st.expander("🔍 Polaritäts-Check: Analyse mit vs. ohne Korrektur anzeigen"):
            diag = _detect_flip_diagnostic(edf_path, ch)
            st.markdown(
                "**Warum das wichtig ist:** Die Peak-Verfeinerung sucht per `argmax()` den "
                "höchsten Punkt in einem ±40ms-Fenster um jeden Kandidaten — das setzt voraus, "
                "dass die R-Zacke positiv ist. Bei einem invertierten Kanal (wie hier) springt "
                "sie stattdessen auf einen zufälligen Nebenpunkt (Überschwinger, T-Wellen-"
                "Anflanke) statt auf die echte R-Zacke. Da dieser Nebenpunkt je nach lokaler "
                "Kurvenform leicht unterschiedlich weit von der echten R-Zacke entfernt liegt, "
                "entstehen keine zufälligen, sondern **strukturierte Zeitfehler** — sichtbar als "
                "mehrere getrennte Bänder/Cluster im Tachogramm, obwohl der echte Rhythmus "
                "glatt und regelmäßig ist."
            )
            dfig = go.Figure()
            dfig.add_trace(go.Scatter(x=diag["t_ohne_s"], y=diag["rr_ohne_ms"], mode="markers",
                                      marker=dict(size=3, color="#c0392b"),
                                      name=f"ohne Flip (std={diag['std_ohne']:.0f}ms)"))
            dfig.add_trace(go.Scatter(x=diag["t_mit_s"], y=diag["rr_mit_ms"], mode="markers",
                                      marker=dict(size=3, color="#27ae60"),
                                      name=f"mit Flip-Korrektur (std={diag['std_mit']:.0f}ms)"))
            dfig.update_layout(
                title="Tachogramm — RR-Intervalle über die Zeit",
                xaxis_title="Zeit (s)", yaxis_title="RR (ms)", height=340,
                margin=dict(t=40, b=40, l=55, r=10), plot_bgcolor="#fafafa",
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(dfig, use_container_width=True, key="flip_diag_tacho")
            st.caption(
                "Ohne Korrektur: mehrere parallele Bänder (Peak-Verfeinerung springt auf "
                "Nebenpunkte). Mit Korrektur: eine kompakte, glatte Verteilung — das ist "
                "der Pfad, den diese Rhythmus-Screening-Seite tatsächlich verwendet. Die "
                "EKG&HRV-Seite nutzt aktuell noch den unkorrigierten Pfad."
            )

    ov_key = _overrides_key(edf_path, ch, det_label)
    if ov_key not in st.session_state:
        st.session_state[ov_key] = set()
    removed = st.session_state[ov_key]
    peaks = np.array([p for p in peaks_all if int(p) not in removed])
    if len(peaks) < 4:
        st.warning("Zu wenige R-Zacken nach manueller Korrektur — Entfernungen zurücksetzen?")
        if st.button("Manuelle Korrekturen zurücksetzen"):
            st.session_state[ov_key] = set()
            st.rerun()
        return

    # Stufe②b: einmal bandpassgefiltertes Signal für die P-Wellen-Ensemble-Analyse (nicht pro
    # Fenster neu filtern — filtfilt über die ganze Aufnahme reicht, siehe p_wave_analysis.py).
    sig_filt = bandpass_ecg(sig_uv, fs)

    sqi = sqi_segments(sig_uv, peaks, fs, seg_s=10.0, purpose="rhythm_screening")
    bad_zones = [(s["t0"], s["t1"], s["reason"]) for s in sqi if not s["good"]]
    # "Auffällige" Abschnitte (User-Feedback 2026-08-08): HF außerhalb 40-180bpm oder extreme
    # RR-Variabilität sind KEINE Artefakte — echte, potenziell relevante Befunde (z. B. schnelles
    # AFib). Bleiben in der Analyse (good=True), werden aber separat markiert/gezeigt.
    notable_zones = [(s["t0"], s["t1"], s["reason"]) for s in sqi if s.get("category") == "notable"]
    rhythm = classify_afib_risk(sig_uv, peaks, fs)

    # Stufe②b — P-Wellen-Kohärenz über alle 30s-CosEn-Fenster aggregiert, VOR der
    # Confidence-Anzeige berechnet (User-Vorgabe 2026-08-08: "wer eine saubere, sichere
    # P-Welle hat, hat eher kein AFib" — als ZWEITE, unabhängige Evidenzquelle in die
    # Sicherheitsstufe einspeisen, nicht nur informativ danebenstellen). Läuft weiterhin
    # IMMER, nicht nur bei AFib-Verdacht (Visualisierung im Fenster-Navigator unten).
    _pw_cohs, _pw_verdicts = [], []
    for _w in rhythm["windows"]:
        _pr = p_analyze_window(sig_filt, peaks, fs, _w["t0"], _w["t1"])
        if _pr and _pr["coherence"] == _pr["coherence"]:
            _pw_cohs.append(_pr["coherence"]); _pw_verdicts.append(_pr["verdict"])
    _pw_median = float(np.median(_pw_cohs)) if _pw_cohs else float("nan")
    if rhythm["verdict"] == "afib_verdaechtig":
        rhythm = combine_with_pwave(rhythm, _pw_median, len(_pw_cohs))

    ectopy = None
    if rhythm["verdict"] != "afib_verdaechtig":
        ectopy = ectopy_summary(sig_uv, peaks, fs)

    # ── Mehrstufiger Ablauf sichtbar machen (User-Feedback 2026-08-08) ────────
    n_good_seg = sum(1 for s in sqi if s["good"])
    _step2_status = {"afib_verdaechtig": (status_dot("danger"), "#c0392b", "Verdacht"),
                     "ektopie_richtung": (status_dot("warning"), "#e67e22", "Grenzbereich"),
                     "normal": (status_dot("success"), "#27ae60", "unauffällig"),
                     "nicht_auswertbar": (status_dot("neutral"), "#7f8c8d", "n. auswertbar")}[rhythm["verdict"]]
    if rhythm["verdict"] == "afib_verdaechtig":
        _step3_txt, _step3_col = "⏭ übersprungen (bei AFib nicht sinnvoll)", "#95a5a6"
    elif ectopy is not None:
        _step3_txt = f"{status_dot('warning') if ectopy['n_events'] else status_dot('success')} {ectopy['n_events']} Ereignisse"
        _step3_col = "#e67e22" if ectopy["n_events"] else "#27ae60"
    else:
        _step3_txt, _step3_col = "—", "#7f8c8d"

    def _step(n, title, status_txt, col):
        return (f"<div style='flex:1;background:{col}0d;border:1.5px solid {col};"
                f"border-radius:8px;padding:8px 10px;text-align:center'>"
                f"<div style='font-size:10px;color:#888;font-weight:700'>SCHRITT {n}</div>"
                f"<div style='font-size:12px;font-weight:700;color:{col}'>{title}</div>"
                f"<div style='font-size:12px;color:{col}'>{status_txt}</div></div>")
    st.markdown(
        "<div style='display:flex;gap:6px;align-items:center;margin-bottom:10px'>"
        + _step(1, "Artefakte", f"✓ {n_good_seg}/{len(sqi)} Segmente ok", "#2471a3")
        + "<div style='color:#bbb;font-size:16px'>→</div>"
        + _step(2, "Vorhofflimmern", f"{_step2_status[0]} {_step2_status[2]}", _step2_status[1])
        + "<div style='color:#bbb;font-size:16px'>→</div>"
        + _step(3, "Extrasystolen", _step3_txt, _step3_col)
        + "</div>", unsafe_allow_html=True)

    # ── Ampel-Übersicht ─────────────────────────────────────────────────────
    section_header("Ampel-Übersicht", f"Kanal {ch} · {dur_s/60:.1f} min · "
                   f"{len(peaks)} R-Zacken ({len(removed)} manuell entfernt)")
    if rhythm["verdict"] == "afib_verdaechtig":
        _conf = rhythm.get("confidence") or "verdacht"
        _conf_lbl = {"gesichert": "Sicherheit: hoch (gesichert)",
                    "wahrscheinlich": "Sicherheit: mittel (wahrscheinlich)",
                    "verdacht": "Sicherheit: geringer (Verdacht, z. B. nur kurzer Abschnitt)"}[_conf]
        _col, _lbl = "#c0392b", f"{status_dot('danger')} Verdacht auf Vorhofflimmern · {_conf_lbl}"
        _detail = (f"{rhythm['n_afib_windows']}/{rhythm['n_windows']} 30s-Fenster mit "
                   f"AFib-artiger Entropie-Signatur (CosEn-Median {rhythm['median_cosen']:.2f}). "
                   "Die normale HRV-Zeit-/Frequenzanalyse auf der EKG&HRV-Seite bleibt zwar "
                   "berechenbar, ist bei Vorhofflimmern aber methodisch nicht valide. "
                   "Sicherheitsstufe = Persistenz (Fensteranteil) + Tiefe der Entropie-Signatur, "
                   "jetzt zusätzlich mit P-Wellen-Nachweis abgeglichen (Stufe②b, siehe unten) — "
                   "auch bei 'gesichert' ein Screening-Marker, keine Diagnose.")
        if rhythm.get("pwave_note"):
            _pw_box_col = "#c0392b" if rhythm.get("pwave_contradiction") else "#2471a3"
            _detail += (f"<div style='margin-top:8px;padding:6px 10px;background:{_pw_box_col}0d;"
                       f"border-left:3px solid {_pw_box_col};border-radius:4px;font-size:12px;"
                       f"color:{_pw_box_col}'>"
                       f"{'⚠️' if rhythm.get('pwave_contradiction') else 'ℹ️'} "
                       f"{rhythm['pwave_note']}</div>")
    elif rhythm["verdict"] == "ektopie_richtung":
        _col, _lbl = "#e67e22", f"{status_dot('warning')} Erhöhte Rhythmus-Variabilität"
        _detail = (f"CosEn-Median {rhythm['median_cosen']:.2f} — im Übergangsbereich zwischen "
                   "normal und AFib-artig. Kein klarer AFib-Verdacht, aber unregelmäßiger als "
                   "ein typischer Sinusrhythmus.")
    elif rhythm["verdict"] == "normal":
        _col, _lbl = "#27ae60", f"{status_dot('success')} Unauffälliger Rhythmus"
        _detail = f"CosEn-Median {rhythm['median_cosen']:.2f} — im Normal-Sinusrhythmus-Bereich."
    else:
        _col, _lbl = "#7f8c8d", f"{status_dot('neutral')} Nicht auswertbar"
        _detail = "Zu wenige artefaktfreie 30s-Fenster für ein Screening-Urteil."
    st.markdown(
        f"<div style='background:{_col}12;border:2px solid {_col};border-radius:10px;"
        f"padding:14px 18px'><div style='font-size:16px;font-weight:800;color:{_col}'>"
        f"{_lbl}</div><div style='font-size:13px;color:#555;margin-top:4px'>{_detail}</div>"
        "<div style='font-size:11px;color:#888;margin-top:6px'>Screening-Marker, keine Diagnose "
        "— bitte klinisch einordnen.</div></div>", unsafe_allow_html=True)

    if ectopy and ectopy["n_events"] > 0:
        st.markdown(
            f"<div style='background:#e67e2212;border-left:4px solid #e67e22;border-radius:8px;"
            f"padding:10px 14px;margin-top:10px;font-size:13px'>"
            f"{status_dot('warning')} <b>{ectopy['n_events']} Ereignisse</b> ({ectopy['fraction_pct']:.1f}% der Schläge) "
            f"mit Kompensationspause-Muster (vorzeitiger Schlag + Pause) — "
            f"{ectopy['n_ves_verdaechtig']}× VES-verdächtig (breiter QRS), "
            f"{ectopy['n_sves_verdaechtig']}× SVES-verdächtig (schmaler QRS). "
            "Anteil-Größenordnung, nicht exakter Zählwert — detektorabhängig.</div>",
            unsafe_allow_html=True)

    # Stufe②b — P-Wellen-Kohärenz-Zusammenfassung (bereits weiter oben berechnet + in die
    # Confidence eingespeist, falls AFib-Verdacht — hier nur noch die Anzeige).
    if _pw_cohs:
        _pw_overall = {"sichtbar": (status_dot("success"), "P-Welle über die Aufnahme überwiegend sichtbar"),
                       "eingeschraenkt": (status_dot("warning"), "P-Welle eingeschränkt beurteilbar"),
                       "nicht_abgrenzbar": (status_dot("danger"), "P-Welle überwiegend NICHT abgrenzbar — "
                                            "stützt AFib-Verdacht zusätzlich")}[
            "sichtbar" if _pw_median >= 0.6 else ("eingeschraenkt" if _pw_median >= 0.35 else "nicht_abgrenzbar")]
        st.markdown(
            f"<div style='font-size:12px;color:#555;margin-top:8px'>{_pw_overall[0]} "
            f"<b>Stufe②b — P-Wellen-Nachweis (Schlag-Summation):</b> {_pw_overall[1]} "
            f"(Median-Kohärenz {_pw_median:.2f} über {len(_pw_cohs)} Fenster). Details & "
            "Diagramm im Fenster-Navigator unten.</div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='font-size:12px;color:#888;margin-top:8px'>Signalqualität: "
        f"{sum(1 for s in sqi if s['good'])}/{len(sqi)} 10s-Segmente unauffällig "
        f"({len(bad_zones)} als Artefakt markiert).</div>", unsafe_allow_html=True)

    # ── 1-Minuten-Fenster-Navigator ──────────────────────────────────────────
    section_header("1-Minuten-Fenster-Navigator", "Rohsignal · R-Zacken farbcodiert · Artefakt-Zonen schattiert")
    # Kurzen "Rest" (< 25% eines Fensters, z. B. 1s bei 10:01min) ins letzte reguläre Fenster
    # verschmelzen statt ein fast leeres Extra-Fenster zu erzeugen (User-Feedback 2026-08-08).
    n_full = int(dur_s // WIN_S)
    remainder = dur_s - n_full * WIN_S
    if n_full > 0 and remainder < 0.25 * WIN_S:
        n_windows = n_full
    else:
        n_windows = n_full + (1 if remainder > 0 else 0)
    n_windows = max(1, n_windows)
    if "rhythm_win_idx" not in st.session_state:
        st.session_state.rhythm_win_idx = 0
    w_idx = min(st.session_state.rhythm_win_idx, n_windows - 1)

    def _win_bounds(idx):
        t0_ = idx * WIN_S
        t1_ = dur_s if idx == n_windows - 1 else min((idx + 1) * WIN_S, dur_s)
        return t0_, t1_

    nc1, nc2, nc3 = st.columns([1, 3, 1])
    if nc1.button("◀ Zurück", disabled=w_idx == 0, key="rhythm_prev"):
        w_idx -= 1
    _lbl_t0, _lbl_t1 = _win_bounds(w_idx)
    nc2.markdown(
        f"<div style='text-align:center;padding-top:6px'>Fenster <b>{w_idx+1} / {n_windows}</b> "
        f"&nbsp;·&nbsp; {_lbl_t0/60:.1f}–{_lbl_t1/60:.1f} min</div>",
        unsafe_allow_html=True)
    if nc3.button("Weiter ▶", disabled=w_idx >= n_windows - 1, key="rhythm_next"):
        w_idx += 1
    st.session_state.rhythm_win_idx = w_idx

    t0, t1 = _win_bounds(w_idx)
    i0, i1 = int(t0 * fs), int(t1 * fs)
    t_axis = np.arange(i0, i1) / fs

    # Statistik-Zeile für DIESES Fenster (User-Feedback 2026-08-08: HF direkt sichtbar, nicht nur
    # global, plus 1-2 weitere Parameter — RR-Variabilität (CV%) und Segment-Status im Fenster)
    win_rr = np.diff(peaks[(peaks >= i0) & (peaks < i1)]) / fs * 1000.0
    win_hr = 60000.0 / np.mean(win_rr) if len(win_rr) else float("nan")
    win_cv = (np.std(win_rr) / np.mean(win_rr) * 100.0) if len(win_rr) >= 2 and np.mean(win_rr) > 0 else float("nan")
    _win_seg_status = [
        "Artefakt" if s["category"] == "artifact" else ("Auffällig" if s["category"] == "notable" else "ok")
        for s in sqi if s["t1"] > t0 and s["t0"] < t1
    ]
    # st.metric() rendert kein HTML -> hier bewusst nur Klartext, kein status_dot()
    if "Artefakt" in _win_seg_status:
        _seg_status_lbl = "Artefakt im Fenster"
    elif "Auffällig" in _win_seg_status:
        _seg_status_lbl = "auffällig im Fenster"
    elif _win_seg_status:
        _seg_status_lbl = "unauffällig"
    else:
        _seg_status_lbl = "—"
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("Herzfrequenz (dieses Fenster)", f"{win_hr:.0f} bpm" if win_hr == win_hr else "—")
    sc2.metric("R-Zacken im Fenster", f"{len(peaks[(peaks >= i0) & (peaks < i1)])}")
    sc3.metric("RR-Variabilität (CV%)", f"{win_cv:.0f}%" if win_cv == win_cv else "—")
    sc4.metric("Segmentstatus (Fenster)", _seg_status_lbl)
    sc5.metric("Rhythmus-Urteil (gesamt)", _step2_status[2])
    st.caption(
        "ℹ️ Das Vorhofflimmern-Screening (Schritt 2) bewertet nicht das EKG-Bild direkt, sondern "
        "die **statistische Vorhersagbarkeit der RR-Abstände** über 30s-Fenster (CosEn = "
        "Coefficient of Sample Entropy, Lake & Moorman 2011) — Details im Methodik-Abschnitt "
        "unten."
    )

    ectopy_beat_times = {e["t_s"]: e["hint"] for e in (ectopy["events"] if ectopy else [])}

    fig = go.Figure()
    for b0, b1, reason in bad_zones:
        if b1 <= t0 or b0 >= t1:
            continue
        fig.add_vrect(x0=max(b0, t0), x1=min(b1, t1), fillcolor="#c0392b", opacity=0.10,
                      line_width=0, annotation_text="Artefakt", annotation_font_size=9,
                      annotation_font_color="#c0392b")
    for b0, b1, reason in notable_zones:
        if b1 <= t0 or b0 >= t1:
            continue
        fig.add_vrect(x0=max(b0, t0), x1=min(b1, t1), fillcolor="#e67e22", opacity=0.10,
                      line_width=0, annotation_text="auffällig", annotation_font_size=9,
                      annotation_font_color="#e67e22")
    fig.add_trace(go.Scatter(x=t_axis, y=sig_uv[i0:i1], mode="lines",
                             line=dict(color="#374151", width=1.2), name="EKG",
                             hoverinfo="skip"))

    win_peaks = peaks[(peaks >= i0) & (peaks < i1)]
    colors, labels, custom = [], [], []
    for p in win_peaks:
        t_p = p / fs
        hint = None
        for et, eh in ectopy_beat_times.items():
            if abs(et - t_p) < 0.05:
                hint = eh
                break
        in_bad = any(b0 <= t_p < b1 for b0, b1, _ in bad_zones)
        if in_bad:
            colors.append("#95a5a6"); labels.append("in Artefakt-Zone")
        elif hint == "VES-verdächtig":
            colors.append("#c0392b"); labels.append("VES-verdächtig")
        elif hint == "SVES-verdächtig":
            colors.append("#e67e22"); labels.append("SVES-verdächtig")
        else:
            colors.append("#27ae60"); labels.append("normal")
        custom.append(int(p))
    if len(win_peaks):
        fig.add_trace(go.Scatter(
            x=win_peaks / fs, y=sig_uv[win_peaks], mode="markers",
            marker=dict(size=9, color=colors, line=dict(width=1, color="white")),
            customdata=list(zip(custom, labels)),
            hovertemplate="t=%{x:.2f}s · %{customdata[1]}<br>Klick = aus Analyse entfernen<extra></extra>",
            name="R-Zacken",
        ))
    fig.update_layout(
        xaxis_title="Zeit (s)", yaxis_title="µV", height=340,
        margin=dict(t=10, b=40, l=55, r=10), plot_bgcolor="#fafafa", showlegend=False,
    )
    # WICHTIG: stabiler Key (nicht pro Fenster wechselnd) — ein pro-Fenster wechselnder Key
    # verursachte einen Desync zwischen dem Fenster-Label und dem tatsächlich gezeichneten
    # Plot (gefunden 2026-08-08: Label zeigte "Fenster 5/6", Plot zeigte Daten von Fenster 6/6).
    ev = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                         selection_mode="points", key="rhythm_canvas")
    if ev and ev.get("selection", {}).get("points"):
        for pt in ev["selection"]["points"]:
            cd = pt.get("customdata")
            if cd and len(cd) >= 1:
                st.session_state[ov_key].add(int(cd[0]))
        # Auswahlzustand danach zurücksetzen — sonst könnte eine alte Auswahl beim nächsten
        # Fenster-Wechsel (ohne neuen Klick) fälschlich erneut als Klick interpretiert werden.
        st.session_state["rhythm_canvas"] = {"selection": {"points": [], "point_indices": [],
                                                            "point_indices_by_trace": []}}
        st.rerun()
    st.caption(
        "🟢 normal · 🟠 SVES-verdächtig · 🔴 VES-verdächtig · ⚪ in Artefakt-Zone · "
        "**Klick auf eine Markierung entfernt sie** aus der Analyse (z. B. bei sichtbarer "
        "Fehldetektion). Rot schattiert = automatisch als Artefakt verworfener Bereich."
    )
    if removed:
        if st.button(f"↺ Alle {len(removed)} manuellen Entfernungen zurücksetzen"):
            st.session_state[ov_key] = set()
            st.rerun()

    # ── PQRST-Ensemble & P-Welle (Stufe②b) ───────────────────────────────────
    # Schlag-Summation (User-Anregung 2026-08-08): alle R-Zacken des aktuellen Fensters
    # ausgerichtet und gemittelt — zeigt P-QRS-T als ein Diagramm. Läuft auf JEDEM Fenster,
    # unabhängig vom Rhythmus-Urteil. Details/Methodik siehe analysis/p_wave_analysis.py.
    section_header("PQRST-Ensemble & P-Welle", "Schlag-Summation des aktuellen Fensters — "
                   "zweite, RR-unabhängige AFib-Evidenz (P-Wellen-Kohärenz statt Amplitude)")
    _pw = p_analyze_window(sig_filt, peaks, fs, t0, t1)
    if _pw is None:
        st.info("Zu wenige vollständige Schläge in diesem Fenster für die Ensemble-Analyse "
                "(braucht mind. 5 Schläge mit vollem ±450ms-Rand).")
    else:
        _pw_col = {"sichtbar": "#27ae60", "eingeschraenkt": "#e67e22",
                  "nicht_abgrenzbar": "#c0392b", "nicht_auswertbar": "#7f8c8d"}[_pw["verdict"]]
        _pw_lbl = {"sichtbar": "P-Welle sichtbar", "eingeschraenkt": "eingeschränkt beurteilbar",
                  "nicht_abgrenzbar": "P-Welle nicht abgrenzbar (mit AFib vereinbar)",
                  "nicht_auswertbar": "nicht auswertbar"}[_pw["verdict"]]
        pfig = go.Figure()
        for _beat in _pw["beats"]:
            pfig.add_trace(go.Scatter(x=_pw["t_ms"], y=_beat, mode="lines",
                                      line=dict(color="#999", width=0.4), opacity=0.35,
                                      hoverinfo="skip", showlegend=False))
        pfig.add_vrect(x0=P_WIN[0], x1=P_WIN[1], fillcolor="#27ae60", opacity=0.12, line_width=0,
                       annotation_text="P-Fenster", annotation_font_size=9,
                       annotation_font_color="#1e8449")
        pfig.add_vline(x=0, line_color="#c0392b", line_width=1, line_dash="dash")
        pfig.add_trace(go.Scatter(x=_pw["t_ms"], y=_pw["ensemble"], mode="lines",
                                  line=dict(color="#1a5276", width=2.5), name="Ensemble (Median)"))
        pfig.update_layout(
            xaxis_title="ms relativ zu R", yaxis_title="µV", height=320,
            margin=dict(t=10, b=40, l=55, r=10), plot_bgcolor="#fafafa",
            showlegend=True, legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(pfig, use_container_width=True, key="pwave_ensemble_canvas")
        _excl_txt = f" ({_pw['n_excluded']} ausgeschlossen)" if _pw["n_excluded"] else ""
        st.markdown(
            f"<div style='background:{_pw_col}12;border:2px solid {_pw_col};border-radius:8px;"
            f"padding:10px 14px'><span style='font-weight:800;color:{_pw_col}'>{_pw_lbl}</span> "
            f"<span style='color:#555'>· Kohärenz {_pw['coherence']:.2f} · "
            f"{_pw['n_beats']}/{_pw['n_beats_total']} Schläge summiert{_excl_txt} · "
            f"P-Amplitude {_pw['amplitude_uv']:.0f}µV</span>"
            "</div>", unsafe_allow_html=True)
        st.caption(
            "Graue Linien = alle Einzelschläge im Fenster, ausgerichtet auf die R-Zacke "
            "(0ms). Blau = Median-Ensemble. **Kohärenz** = wie stark jeder Einzelschlag im "
            "grün markierten P-Fenster mit dem Ensemble übereinstimmt — hoch (≥0.6) spricht "
            "für eine zeitlich fixierte, echte P-Welle; niedrig (<0.35) für unkorrelierte "
            "atriale Aktivität (Flimmerwellen), wie bei Vorhofflimmern erwartet. Screening-"
            "Marker, keine Diagnose."
        )

    # ── Auffällige-Abschnitte-Galerie (User-Feedback 2026-08-08) ────────────────
    # Echte Befunde, keine Artefakte: HF außerhalb 40-180bpm oder extreme RR-Variabilität
    # (z. B. schnelles AFib). Bewusst separat von der roten Artefakt-Galerie (amber statt rot).
    if notable_zones:
        section_header("Auffällige Abschnitte", f"{len(notable_zones)} Abschnitte mit auffälliger "
                       "Herzfrequenz/RR-Variabilität — kein Artefakt, sondern möglicher Befund")
        n_show_n = min(6, len(notable_zones))
        step_n = max(1, len(notable_zones) // n_show_n)
        sample_notable = notable_zones[::step_n][:n_show_n]
        cols_n = st.columns(3)
        for i, (b0, b1, reason) in enumerate(sample_notable):
            pad = 1.0
            g0, g1 = max(0.0, b0 - pad), min(dur_s, b1 + pad)
            gi0, gi1 = int(g0 * fs), int(g1 * fs)
            gt = np.arange(gi0, gi1) / fs
            gfig = go.Figure()
            gfig.add_vrect(x0=b0, x1=b1, fillcolor="#e67e22", opacity=0.15, line_width=0)
            gfig.add_trace(go.Scatter(x=gt, y=sig_uv[gi0:gi1], mode="lines",
                                      line=dict(color="#e67e22", width=1.1), hoverinfo="skip"))
            gfig.update_layout(height=160, margin=dict(t=4, b=24, l=35, r=5),
                               plot_bgcolor="#fffaf0", showlegend=False,
                               xaxis=dict(title=None, tickfont=dict(size=8)),
                               yaxis=dict(title=None, tickfont=dict(size=8)))
            with cols_n[i % 3]:
                st.plotly_chart(gfig, use_container_width=True, config={"displayModeBar": False},
                                key=f"notablegallery_{i}")
                st.caption(f"t={b0/60:.2f}–{b1/60:.2f}min · {reason}")

    # ── Artefakt-Galerie ──────────────────────────────────────────────────────
    if bad_zones:
        section_header("Artefakt-Galerie", f"Exemplarische Ausschnitte der {len(bad_zones)} verworfenen Abschnitte")
        n_show = min(6, len(bad_zones))
        step = max(1, len(bad_zones) // n_show)
        sample_zones = bad_zones[::step][:n_show]
        cols = st.columns(3)
        for i, (b0, b1, reason) in enumerate(sample_zones):
            pad = 1.0
            g0, g1 = max(0.0, b0 - pad), min(dur_s, b1 + pad)
            gi0, gi1 = int(g0 * fs), int(g1 * fs)
            gt = np.arange(gi0, gi1) / fs
            gfig = go.Figure()
            gfig.add_vrect(x0=b0, x1=b1, fillcolor="#c0392b", opacity=0.15, line_width=0)
            gfig.add_trace(go.Scatter(x=gt, y=sig_uv[gi0:gi1], mode="lines",
                                      line=dict(color="#c0392b", width=1.1), hoverinfo="skip"))
            gfig.update_layout(height=160, margin=dict(t=4, b=24, l=35, r=5),
                               plot_bgcolor="#fff5f5", showlegend=False,
                               xaxis=dict(title=None, tickfont=dict(size=8)),
                               yaxis=dict(title=None, tickfont=dict(size=8)))
            with cols[i % 3]:
                st.plotly_chart(gfig, use_container_width=True, config={"displayModeBar": False},
                                key=f"artgallery_{i}")
                st.caption(f"t={b0/60:.2f}–{b1/60:.2f}min · {reason}")

    with st.expander("📖 Was bedeutet das? — Methodik", expanded=False):
        st.markdown(
            "**Ablauf:** ① Signalqualität prüfen (Orphanidou et al. 2015, angepasste Schwellen) "
            "→ ② Vorhofflimmern-Screening (CosEn, Lake & Moorman 2011) auf den verbleibenden, "
            "artefaktfreien Abschnitten, jetzt zusätzlich mit P-Wellen-Nachweis abgeglichen "
            "(Stufe②b) → ③ bei unauffälligem Rhythmus zusätzlich nach Extrasystolen-Mustern "
            "suchen (Kompensationspause + QRS-Breite).\n\n"
            "**Wichtig:** Alle Werte sind Screening-Hinweise, keine Diagnosen. Die automatische "
            "Artefakt-Erkennung ist konservativ, aber nicht perfekt — bitte die Artefakt-Galerie "
            "und den Fenster-Navigator stichprobenhaft gegenprüfen. Einzelne Fehldetektionen "
            "können oben per Klick entfernt werden."
        )

    with st.expander("🔬 Stufe①-Regeln im Detail — wonach wird ein 10s-Segment als Artefakt "
                     "verworfen?", expanded=False):
        st.markdown(
            "Jedes 10s-Segment durchläuft bis zu 6 Regeln (`analysis/ecg_quality.py`). Ein "
            "Segment gilt als **Artefakt** (wird von CosEn/Ektopie-Erkennung ausgeschlossen), "
            "sobald EINE der 4 folgenden Regeln zutrifft:\n\n"
            "1. **Flatline** — rollierende Standardabweichung < 5µV über ein 300ms-Fenster, "
            "in mehr als 10% des Segments → Sättigung/Elektroden-Diskonnektion.\n"
            "2. **Lücke** — größter Abstand zwischen zwei R-Zacken im Segment > 3s → "
            "vermutlich verpasster Schlag.\n"
            "3. **Template-Korrelation** — Pearson-Korrelation jedes Schlags mit dem "
            "Segment-Mittel-QRS < 0,66 (bzw. 0,35 im nachsichtigeren AFib-Screening-Modus, "
            "da AFib selbst schwankende Morphologie erzeugt) → kein erkennbarer, "
            "wiederkehrender QRS-Komplex.\n"
            "4. **🎯 Amplituden-Plausibilität** (die von dir angefragte Regel): Für jeden "
            "Schlag wird die Spitze-zu-Spitze-Amplitude (`peak-to-peak`) in einem Fenster um "
            "die R-Zacke gemessen. Referenz ist die **globale** Baseline — der Median-Wert "
            "über die GESAMTE Aufnahme, nicht nur das einzelne Segment (bewusst so: ein "
            "Artefakt, der ein ganzes 10s-Segment gleichmäßig betrifft, hätte sonst keinen "
            "internen Ausreißer und würde unentdeckt bleiben). Ein Schlag gilt als "
            "amplituden-unplausibel, wenn seine Amplitude **unter 30%** oder **über 300%** "
            "(das 0,3- bis 3,0-fache) der globalen Baseline liegt. Liegen **mehr als 30% "
            "der Schläge** im Segment außerhalb dieses Bereichs, wird das gesamte Segment "
            "als Artefakt verworfen (z. B. Bewegungsartefakt, Impedanzprüfung, lockere "
            "Elektrode).\n\n"
            "Zwei weitere Regeln (HF außerhalb 40–180 bpm, extreme RR-Variabilität) verwerfen "
            "NICHT mehr automatisch — sie gelten seit dem User-Feedback vom 2026-08-08 als "
            "**\"auffällig\"** statt als Artefakt (siehe amber Galerie oben), da z. B. "
            "schnelles Vorhofflimmern selbst der gesuchte Befund sein kann, kein "
            "Signalfehler."
        )
