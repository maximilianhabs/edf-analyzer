"""Kanal-Identifikations-Report: Classifier-Ergebnisse + manuelle Korrekturen."""

import re

import streamlit as st
import numpy as np
import plotly.graph_objects as go

from core.i18n import tr
from core.shared import get_edf_or_stop, section_header, apply_global_style, status_dot
from core.channel_classifier import ECG, EEG, EOG, EMG, REF, VITAL, UNKN


# Nur Icon/Farbe hier — die Beschriftung kommt über _type_label() aus core/i18n.py. Ein
# fertiger Text in diesem Modul-Dict würde beim Import ausgewertet und damit die Sprache
# auf den beim Prozessstart geltenden Wert einfrieren.
_TYPE_META = {
    ECG:   {"icon": "ecg_heart",      "color": "#c0392b", "key": "type_ecg"},
    EEG:   {"icon": "neurology",      "color": "#2471a3", "key": "type_eeg"},
    EOG:   {"icon": "visibility",     "color": "#8e44ad", "key": "type_eog"},
    EMG:   {"icon": "fitness_center", "color": "#e67e22", "key": "type_emg"},
    REF:   {"icon": "⏚",              "color": "#7f8c8d", "key": "type_ref"},
    VITAL: {"icon": "vital_signs",    "color": "#27ae60", "key": "type_vital"},
    UNKN:  {"icon": "help",           "color": "#95a5a6", "key": "type_unknown"},
}


def _type_label(ch_type) -> str:
    meta = _TYPE_META.get(ch_type, _TYPE_META[UNKN])
    return tr(f"channel_report.{meta['key']}")


def _type_icon_html(meta: dict, size: str = "1.6rem") -> str:
    """Material-Symbols-Glyph für einen Kanaltyp (Phase 6 GUI-Redesign, siehe
    [[project_edf_ui_redesign]]) — ersetzt die bisherigen Emoji in `_TYPE_META`. Für
    unsafe_allow_html-Kontexte (rohes HTML). `REF` behält sein technisches Massesymbol
    (⏚, kein Emoji, bleibt unverändert)."""
    icon = meta["icon"]
    if icon == "⏚":
        return f"<span style='font-size:{size}'>{icon}</span>"
    return (f"<span class='material-symbols-outlined' "
            f"style='font-size:{size};color:{meta['color']}'>{icon}</span>")


_ALL_TYPES = [EEG, ECG, EOG, EMG, REF, VITAL, UNKN]

_CONFIDENCE_COLOR = {
    "high":   "#27ae60",
    "medium": "#e67e22",
    "low":    "#c0392b",
}


def _conf_tier(conf: float) -> str:
    if conf >= 70:
        return "high"
    if conf >= 40:
        return "medium"
    return "low"


def _override_key() -> str:
    return "channel_overrides"


def _get_overrides() -> dict:
    return st.session_state.setdefault(_override_key(), {})


def render():
    apply_global_style()

    # Load edf WITHOUT applying overrides here — we display the raw classifier
    # result AND the override side-by-side; overrides are already in session state
    # and will be picked up by get_edf_or_stop in all other views.
    from core.shared import load_and_prepare, get_edf_path, apply_channel_overrides
    edf_path = get_edf_path()
    if not edf_path or not __import__("os").path.exists(edf_path):
        st.info(tr("shared.please_select_file"), icon=":material/folder_open:")
        st.stop()
    if not st.session_state.get("phi_validated"):
        st.error(tr("channel_report.not_validated"), icon=":material/block:")
        st.stop()
    edf_raw = load_and_prepare(edf_path)

    st.title(":material/search: " + tr("channel_report.title"))
    st.markdown(tr("channel_report.intro"))

    classifications = edf_raw.get("channel_classifications", {})
    ch_names  = edf_raw["ch_names"]
    overrides = _get_overrides()

    if not classifications:
        st.warning(tr("channel_report.no_classification"))
        return

    # ── Globale Korrektur-Steuerung ───────────────────────────────────────────
    n_overrides = len(overrides)
    if n_overrides:
        oc1, oc2 = st.columns([4, 1])
        with oc1:
            _ov_key = ("channel_report.overrides_active_one" if n_overrides == 1
                       else "channel_report.overrides_active_many")
            st.info(tr(_ov_key, n=n_overrides), icon=":material/edit:")
        with oc2:
            if st.button(tr("channel_report.reset_all"), type="secondary",
                         use_container_width=True):
                st.session_state[_override_key()] = {}
                st.rerun()

    # ── Zusammenfassung ──────────────────────────────────────────────────────
    section_header(tr("channel_report.summary"),
                   tr("channel_report.summary_sub", n=len(ch_names)))

    # Count using current effective types (including overrides)
    counts: dict = {}
    for ch, r in classifications.items():
        eff_type = overrides.get(ch, r.channel_type)
        counts[eff_type] = counts.get(eff_type, 0) + 1

    cols = st.columns(len(counts) if len(counts) <= 6 else 6)
    for i, (t, n) in enumerate(sorted(counts.items())):
        meta = _TYPE_META.get(t, _TYPE_META[UNKN])
        with cols[i % 6]:
            st.markdown(
                f"<div style='text-align:center;padding:12px 6px;"
                f"border-radius:10px;border:1px solid {meta['color']}20;"
                f"background:{meta['color']}08'>"
                f"<div style='font-size:1.6rem'>{_type_icon_html(meta)}</div>"
                f"<div style='font-size:1.4rem;font-weight:700;color:{meta['color']}'>{n}</div>"
                f"<div style='font-size:0.75rem;color:#555'>{_type_label(t)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Vollständigkeits- & Plausibilitäts-Hinweise ──────────────────────────
    from core.channel_classifier import make_short_name as _short
    _STD_1020 = {"FP1", "FP2", "F3", "F4", "F7", "F8", "C3", "C4", "P3", "P4",
                 "O1", "O2", "T3", "T4", "T5", "T6", "FZ", "CZ", "PZ"}
    _eff_eeg_shorts = {
        _short(ch).upper().replace(" ", "")
        for ch, r in classifications.items()
        if overrides.get(ch, r.channel_type) == EEG
    }
    _present = _STD_1020 & _eff_eeg_shorts
    _missing = _STD_1020 - _eff_eeg_shorts
    _n_ecg = sum(1 for ch, r in classifications.items()
                 if overrides.get(ch, r.channel_type) == ECG)

    if len(_present) < 16:
        st.warning(tr("channel_report.missing_electrodes_warning",
                      n=len(_present), list=", ".join(sorted(_missing))),
                   icon=":material/warning:")
    elif _missing:
        st.info(tr("channel_report.missing_electrodes_info",
                   n=len(_present), list=", ".join(sorted(_missing))))

    if _n_ecg >= 2:
        _ecg_names = [ch for ch, r in classifications.items()
                      if overrides.get(ch, r.channel_type) == ECG]
        st.info(tr("channel_report.multiple_ecg", n=_n_ecg,
                   list=", ".join(_ecg_names)), icon=":material/ecg_heart:")

    # ── Filter & Sort ────────────────────────────────────────────────────────
    section_header(tr("channel_report.channels_detail"))
    st.markdown(
        "<span style='font-size:0.9rem;color:var(--text-secondary,#6b7684)'>"
        + tr("channel_report.confidence_legend",
             dot_ok=status_dot("success"), dot_warn=status_dot("warning"),
             dot_bad=status_dot("danger"))
        + "</span>",
        unsafe_allow_html=True,
    )

    # Compute effective types for filter
    all_eff_types = sorted(set(
        overrides.get(ch, r.channel_type) for ch, r in classifications.items()
    ))
    filter_col, sort_col = st.columns([3, 1])
    with filter_col:
        sel_types = st.multiselect(
            tr("channel_report.type_filter"),
            options=all_eff_types,
            default=all_eff_types,
            format_func=_type_label,
            label_visibility="collapsed",
        )
    with sort_col:
        # Sprachneutrale IDs, Anzeige über format_func — ein übersetztes Label als
        # Vergleichswert würde die Sortierung beim Sprachwechsel still deaktivieren.
        sort_by = st.selectbox(
            tr("channel_report.sort"), ["channel_order", "confidence", "type"],
            format_func=lambda v: tr(f"channel_report.sort_{v}"),
            label_visibility="collapsed")

    items = [
        (ch, classifications[ch], overrides.get(ch))
        for ch in ch_names
        if ch in classifications
        and overrides.get(ch, classifications[ch].channel_type) in sel_types
    ]

    if sort_by == "confidence":
        items.sort(key=lambda x: -x[1].confidence)
    elif sort_by == "type":
        items.sort(key=lambda x: overrides.get(x[0], x[1].channel_type))

    # ── Kanaldetails ─────────────────────────────────────────────────────────
    for ch, result, override_type in items:
        eff_type = override_type or result.channel_type
        meta      = _TYPE_META.get(eff_type, _TYPE_META[UNKN])
        orig_meta = _TYPE_META.get(result.channel_type, _TYPE_META[UNKN])
        tier      = _conf_tier(result.confidence)
        c_conf    = _CONFIDENCE_COLOR[tier]
        f         = result.features

        # Badge: show override indicator
        override_badge = (
            f" <span style='font-size:10px;background:#e67e22;color:white;"
            f"padding:1px 6px;border-radius:10px;vertical-align:middle'>"
            + tr("channel_report.corrected_badge") + "</span>"
            if override_type else ""
        )

        # ── Kopfleiste nach Konfidenz einfärben + Typ-Icon farblich absetzen ──
        # Ganze Klickleiste des Expanders nach Konfidenz tönen (Hintergrund/Randfarbe) UND
        # zusätzlich, unabhängig davon, das Typ-Icon (EEG/EKG/…) in der jeweiligen Typfarbe
        # zeigen (User-Feedback 2026-08-09: im zusammengeklappten Header war das Icon bisher
        # farblos, obwohl die Zusammenfassungs-Kacheln oben schon farbcodiert sind). Da
        # st.expander()-Label kein rohes HTML/individuelle Farben rendert, wird der native
        # `:material/...:`-Shortcode NICHT genutzt — stattdessen zeichnet ein CSS `::before`
        # auf dem scoped `.st-key-<key>`-Container das Icon selbst in der Typfarbe; die
        # Kanalbezeichnung (**{ch}**, von Streamlit als <strong> gerendert) wird über den
        # `strong`-Selektor ebenfalls in der Typfarbe eingefärbt, der Rest der Zeile bleibt
        # regulär schwarz — genau die vom User gewünschte selektive Färbung.
        _ck = "chan_" + re.sub(r"[^0-9A-Za-z]", "_", ch)
        _icon_is_symbol = meta["icon"] == "⏚"
        _icon_font = "inherit" if _icon_is_symbol else "'Material Symbols Outlined'"
        st.markdown(
            f"<style>.st-key-{_ck} details > summary{{"
            f"background:{c_conf}1f !important;"
            f"border-left:5px solid {c_conf} !important;"
            f"border-radius:8px !important;"
            f"padding-left:34px !important;"
            f"position:relative !important;}}"
            f".st-key-{_ck} details > summary::before{{"
            f"content:'{meta['icon']}';"
            f"font-family:{_icon_font};font-weight:normal;font-style:normal;"
            f"color:{meta['color']};font-size:17px;line-height:1;"
            f"position:absolute;left:11px;top:50%;transform:translateY(-50%);}}"
            f".st-key-{_ck} details > summary strong{{color:{meta['color']} !important;}}"
            f".st-key-{_ck} details > summary:hover{{background:{c_conf}33 !important;}}"
            f"</style>",
            unsafe_allow_html=True,
        )
        _chan_box = st.container(key=_ck)
        with _chan_box, st.expander(
            f"**{ch}** — "
            f"{_type_label(eff_type)} · {result.confidence:.0f}% "
            + tr("channel_report.confidence_suffix")
            + (" :material/edit:" if override_type else ""),
            expanded=False,
        ):
            r1, r2 = st.columns([1, 2])

            with r1:
                # Type card
                if override_type:
                    st.markdown(
                        f"<div style='padding:8px 12px;border-radius:10px;"
                        f"border:2px solid {meta['color']};background:{meta['color']}0d'>"
                        f"<div style='font-size:1.8rem;text-align:center'>{_type_icon_html(meta, '1.8rem')}</div>"
                        f"<div style='text-align:center;font-weight:700;font-size:1.0rem;"
                        f"color:{meta['color']}'>{_type_label(eff_type)}</div>"
                        f"<div style='text-align:center;font-size:10px;color:#e67e22;margin-top:4px'>"
                        + tr("channel_report.manual_was", orig=_type_label(result.channel_type))
                        + "</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div style='padding:10px 12px;border-radius:10px;"
                        f"border:2px solid {meta['color']};background:{meta['color']}0d'>"
                        f"<div style='font-size:2rem;text-align:center'>{_type_icon_html(meta, '2rem')}</div>"
                        f"<div style='text-align:center;font-weight:700;font-size:1.1rem;"
                        f"color:{meta['color']}'>{_type_label(eff_type)}</div>"
                        f"<div style='text-align:center;margin-top:6px'>"
                        f"<span style='font-size:1.3rem;font-weight:700;color:{c_conf}'>"
                        f"{result.confidence:.0f}%</span>"
                        f"<span style='font-size:0.75rem;color:#888;margin-left:4px'>"
                        + tr("channel_report.confidence_label") + "</span>"
                        f"</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown(tr("channel_report.reasons"))
                for reason in result.reasons:
                    st.markdown(f"- {reason}")

                # ── Override control ────────────────────────────────────────
                st.markdown("---")
                st.markdown(tr("channel_report.correct_type"))
                current_idx = _ALL_TYPES.index(eff_type) if eff_type in _ALL_TYPES else 0
                new_type = st.selectbox(
                    tr("channel_report.type"),
                    options=_ALL_TYPES,
                    index=current_idx,
                    format_func=_type_label,
                    key=f"override_sel_{ch}",
                    label_visibility="collapsed",
                )
                btn_col, reset_col = st.columns(2)
                with btn_col:
                    if st.button(tr("channel_report.apply"), key=f"override_apply_{ch}",
                                 type="primary", use_container_width=True):
                        if new_type == result.channel_type:
                            # Remove override if reset to original
                            overrides.pop(ch, None)
                        else:
                            overrides[ch] = new_type
                        st.session_state[_override_key()] = overrides
                        st.rerun()
                with reset_col:
                    if override_type and st.button(
                        tr("channel_report.reset"), key=f"override_reset_{ch}",
                        use_container_width=True
                    ):
                        overrides.pop(ch, None)
                        st.session_state[_override_key()] = overrides
                        st.rerun()

            with r2:
                if f and not f.get("is_flat"):
                    st.markdown(tr("channel_report.signal_features"))
                    fa, fb, fc = st.columns(3)
                    fa.metric(tr("channel_report.feat_std"), f"{f.get('std_mv', 0)*1000:.1f} µV")
                    fb.metric(tr("channel_report.feat_p2p"), f"{f.get('p2p_mv', 0):.3f} mV")
                    fc.metric(tr("channel_report.feat_kurtosis"), f"{f.get('kurtosis', 0):.1f}")

                    fd, fe, ff = st.columns(3)
                    fd.metric(tr("channel_report.feat_dom_freq"), f"{f.get('dom_freq', 0):.1f} Hz")
                    fe.metric(tr("channel_report.feat_qrs_rate"),
                              f"{f.get('qrs_rate', 0):.0f} bpm" if f.get('qrs_rate', 0) > 0 else "—")
                    ff.metric(tr("channel_report.feat_rhythmicity"), f"{f.get('rhythmicity', 0):.2f}")

                    # Mini spectrum bar
                    bands = [
                        ("δ",     f.get("delta_rel", 0)),
                        ("θ",     f.get("theta_rel", 0)),
                        ("α",     f.get("alpha_rel", 0)),
                        ("β",     f.get("beta_rel",  0)),
                        ("γ",     f.get("gamma_rel", 0)),
                    ]
                    st.markdown(tr("channel_report.spectral_distribution"))
                    bar_html = "<div style='display:flex;gap:4px;align-items:flex-end;height:50px'>"
                    colors = ["#3498db","#9b59b6","#e74c3c","#2ecc71","#e67e22"]
                    for (lbl, val), col in zip(bands, colors):
                        h = max(4, int(val * 48))
                        bar_html += (
                            f"<div style='display:flex;flex-direction:column;"
                            f"align-items:center;flex:1'>"
                            f"<div style='width:100%;height:{h}px;background:{col};"
                            f"border-radius:3px 3px 0 0' title='{val:.1%}'></div>"
                            f"<div style='font-size:10px;color:#555'>{lbl}</div>"
                            f"<div style='font-size:9px;color:#888'>{val:.0%}</div>"
                            f"</div>"
                        )
                    bar_html += "</div>"
                    st.markdown(bar_html, unsafe_allow_html=True)

                    # ── Signal-Vorschau (10 s) ──────────────────────────────
                    sfreq    = edf_raw["sfreq"]
                    ch_idx_v = edf_raw["ch_idx"].get(ch)
                    dur_s    = edf_raw["duration_s"]
                    if ch_idx_v is not None:
                        # Start bei 30 s (Elektroden-Settling überspringen),
                        # aber nicht über Aufnahmelänge hinaus
                        prev_start = min(30.0, max(0.0, dur_s - 10.0))
                        prev_end   = min(prev_start + 10.0, dur_s)
                        i_s = int(prev_start * sfreq)
                        i_e = int(prev_end   * sfreq)
                        raw_seg = edf_raw["data"][ch_idx_v, i_s:i_e].copy()
                        raw_seg -= raw_seg.mean()
                        t_vec = np.arange(len(raw_seg)) / sfreq + prev_start

                        # Einheit und Polarität je Kanaltyp
                        if eff_type == ECG:
                            y_vals = raw_seg * 1000  # → mV
                            y_label = "mV"
                            # Polaritäts-sicherer Pfad (User-Audit 2026-08-08): R-Zacke soll
                            # wie klinisch gewohnt nach oben zeigen, unabhängig von der rohen
                            # Gerätekonvention (z. B. POL X1, systematisch invertiert in diesem
                            # Aufnahmesystem). Siehe [[project_edf_rhythm_screening]].
                            from analysis.ecg import detect_polarity_flip
                            try:
                                negate = detect_polarity_flip(raw_seg, sfreq)
                            except Exception:
                                negate = False
                        else:
                            y_vals = raw_seg * 1e6   # → µV
                            y_label = "µV"
                            negate  = (eff_type == EEG)  # EEG-Konvention: neg. oben

                        if negate:
                            y_vals = -y_vals

                        st.markdown(tr("channel_report.signal_preview"))
                        fig_prev = go.Figure()
                        fig_prev.add_trace(go.Scatter(
                            x=t_vec, y=y_vals, mode="lines",
                            line=dict(width=1.0, color=meta["color"]),
                            hovertemplate=f"%{{y:.3f}} {y_label}<extra></extra>",
                        ))
                        fig_prev.update_layout(
                            height=160,
                            margin=dict(t=4, b=32, l=55, r=6),
                            xaxis=dict(title=tr("channel_report.time_s"), showgrid=True, dtick=1),
                            yaxis=dict(title=y_label, showgrid=False,
                                       zeroline=True, zerolinewidth=0.8),
                            showlegend=False,
                        )
                        st.plotly_chart(fig_prev, use_container_width=True,
                                        config={"displayModeBar": False},
                                        key=f"chreport_prev_{ch}")

                elif f.get("is_flat"):
                    st.warning(tr("channel_report.flat_channel"))

    # ── EEG Map Übersicht ────────────────────────────────────────────────────
    edf_eff = apply_channel_overrides(edf_raw)
    eeg_map = edf_eff.get("eeg_map", {})
    if eeg_map:
        section_header(tr("channel_report.detected_eeg"),
                       tr("channel_report.detected_eeg_sub", n=len(eeg_map)))
        cols = st.columns(min(6, len(eeg_map)))
        for i, (short, idx) in enumerate(eeg_map.items()):
            with cols[i % len(cols)]:
                st.markdown(
                    f"<div style='text-align:center;padding:6px;border-radius:8px;"
                    f"background:#2471a308;border:1px solid #2471a330;font-size:12px'>"
                    f"<b>{short}</b><br><span style='color:#888;font-size:10px'>Ch {idx}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── EKG / EOG / EMG Übersicht ────────────────────────────────────────────
    ecg = edf_eff.get("ecg_channels", [])
    eog = edf_eff.get("eog_channels", [])
    emg = edf_eff.get("emg_channels", [])

    if ecg or eog or emg:
        section_header(tr("channel_report.aux_channels"))
        hc = st.columns(3)
        for col, label, icon, channels, color in (
            (hc[0], "EKG", "<span class='material-symbols-outlined' "
                          f"style='font-size:1.1rem;color:#c0392b'>ecg_heart</span>", ecg, "#c0392b"),
            (hc[1], "EOG", "<span class='material-symbols-outlined' "
                          f"style='font-size:1.1rem;color:#8e44ad'>visibility</span>", eog, "#8e44ad"),
            (hc[2], "EMG", "<span class='material-symbols-outlined' "
                          f"style='font-size:1.1rem;color:#e67e22'>fitness_center</span>", emg, "#e67e22"),
        ):
            with col:
                st.markdown(
                    f"<div style='padding:10px;border-radius:10px;"
                    f"border:1px solid {color}30;background:{color}08'>"
                    f"<b style='color:{color}'>{icon} {label}</b><br>"
                    + ("".join(
                        f"<div style='font-size:12px;padding:2px 0'>{ch}</div>"
                        for ch in channels
                    ) if channels else "<div style='color:#aaa;font-size:12px'>—</div>")
                    + "</div>",
                    unsafe_allow_html=True,
                )
