"""Seite: Datei & Patient — Datei-Upload (Finder-Dialog), Patienteninfo, deskriptive Vorschau."""

import os
import tempfile
import time
import uuid

import pandas as pd
import streamlit as st

from analysis.hrv_reference import PEDIATRIC_AGE_GROUPS
from core.i18n import tr
from core.loader import check_privacy
from core.shared import load_and_prepare

_UPLOAD_MAX_AGE_H = 4  # Dateien älter als 4 Stunden werden gelöscht


def _session_upload_dir() -> str:
    """Gibt einen session-eigenen /tmp/-Unterordner zurück (erstellt ihn bei Bedarf).

    Jede Streamlit-Session erhält eine UUID aus session_state — so landen EDF-Dateien
    verschiedener gleichzeitiger Benutzer in getrennten Ordnern.
    """
    import secrets
    if "session_upload_token" not in st.session_state:
        st.session_state.session_upload_token = secrets.token_hex(16)
        _cleanup_old_uploads()  # einmalig beim Session-Start aufräumen
    path = os.path.join(tempfile.gettempdir(),
                        "edf_analyzer", st.session_state.session_upload_token)
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup_old_uploads() -> None:
    """Löscht session-Ordner die älter als _UPLOAD_MAX_AGE_H Stunden sind."""
    base = os.path.join(tempfile.gettempdir(), "edf_analyzer")
    if not os.path.isdir(base):
        return
    cutoff = time.time() - _UPLOAD_MAX_AGE_H * 3600
    for entry in os.scandir(base):
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            try:
                import shutil
                shutil.rmtree(entry.path, ignore_errors=True)
            except OSError:
                pass


def render():
    st.title(":material/folder_open: " + tr("file_patient.title"))
    st.caption(tr("file_patient.subtitle"))

    UPLOAD_DIR = _session_upload_dir()

    # ── Dateiauswahl ──────────────────────────────────────────────────────
    # Wichtig: Wert liegt in einem eigenen, NICHT-Widget-gebundenen Session-State-Key
    # ("edf_path"), nicht im Widget-Key selbst. Streamlit verwirft den State von
    # Widgets, die auf einer anderen Seite nicht mehr gerendert werden — würde der
    # Pfad direkt im Widget-Key liegen, ginge er beim ersten Rerun auf einer anderen
    # Seite (z.B. durch Pfeiltasten-Navigation) verloren ("bitte Datei wählen"-Bug).
    if "edf_path" not in st.session_state:
        st.session_state.edf_path = ""
    if "edf_display_name" not in st.session_state:
        st.session_state.edf_display_name = ""

    file_active = bool(st.session_state.edf_path) and os.path.exists(st.session_state.edf_path)

    with st.container(border=True):
        st.subheader(tr("file_patient.section_file"))

        if file_active:
            col_info, col_remove = st.columns([4, 1])
            with col_info:
                st.success(tr("file_patient.file_active", name=st.session_state.edf_display_name))
                st.caption(tr("file_patient.file_active_hint"))
            with col_remove:
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if st.button(tr("file_patient.remove"), icon=":material/delete:", use_container_width=True,
                             help=tr("file_patient.remove_help")):
                    try:
                        os.remove(st.session_state.edf_path)
                    except OSError:
                        pass
                    st.session_state.edf_path = ""
                    st.session_state.edf_display_name = ""
                    st.rerun()
        else:
            # ── Ausstehender PHI-Disclaimer (aus vorherigem Upload) ───────────
            if st.session_state.get("phi_pending_path"):
                _pending_name = st.session_state.get("phi_pending_name", "")
                st.warning(tr("file_patient.phi_warning", name=_pending_name))
                _phi_accepted = st.checkbox(
                    tr("file_patient.phi_confirm"),
                    key="phi_disclaimer_checkbox",
                )
                col_load, col_cancel = st.columns([2, 1])
                with col_load:
                    if st.button(tr("file_patient.load_anyway"), icon=":material/check:",
                                 disabled=not _phi_accepted,
                                 use_container_width=True, type="primary"):
                        st.session_state.edf_path = st.session_state.pop("phi_pending_path")
                        st.session_state.edf_display_name = st.session_state.pop("phi_pending_name", "")
                        st.session_state.phi_validated = True
                        st.session_state.phi_has_patient_data = True
                        st.rerun()
                with col_cancel:
                    if st.button(tr("file_patient.cancel"), icon=":material/close:", use_container_width=True):
                        try:
                            os.remove(st.session_state.pop("phi_pending_path", ""))
                        except OSError:
                            pass
                        st.session_state.pop("phi_pending_name", None)
                        st.rerun()
            else:
                uploaded = st.file_uploader(
                    ":material/folder_open: " + tr("file_patient.uploader_label"),
                    type=["edf"], accept_multiple_files=False,
                )
                if uploaded is not None:
                    dest_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{os.path.basename(uploaded.name)}")
                    with open(dest_path, "wb") as f:
                        f.write(uploaded.getbuffer())

                    privacy = check_privacy(dest_path)
                    if privacy["has_patient_id"] or privacy["has_recording_id"]:
                        # Nicht sofort blockieren — Disclaimer-Flow
                        st.session_state["phi_pending_path"] = dest_path
                        st.session_state["phi_pending_name"] = uploaded.name
                        st.rerun()
                    else:
                        st.session_state.edf_path = dest_path
                        st.session_state.edf_display_name = uploaded.name
                        st.session_state.phi_validated = True
                        st.session_state.phi_has_patient_data = False
                        st.rerun()

    edf_path = st.session_state.edf_path

    if edf_path and os.path.exists(edf_path):
        _edf_preview = load_and_prepare(edf_path)
    else:
        _edf_preview = None

    # ── Patient ───────────────────────────────────────────────────────────
    # Altersgruppen: (sprachneutrale ID, Mittelpunkt für Normwert-Formeln, ist_pädiatrisch,
    # Altersspanne). Die ID — NICHT das angezeigte Label — landet im Session-State und wird
    # verglichen: ein übersetztes Label würde beim Sprachwechsel mitten in der Sitzung nicht
    # mehr auf den gespeicherten Wert passen und die Auswahl still zurücksetzen.
    AGE_GROUPS = [
        ("age_child",   10, True,  (0, 14)),
        ("age_15_29",   22, False, (15, 29)),
        ("age_30_44",   37, False, (30, 44)),
        ("age_45_59",   52, False, (45, 59)),
        ("age_60_74",   67, False, (60, 74)),
        ("age_75_plus", 80, False, (75, 200)),
    ]
    AGE_IDS = [g[0] for g in AGE_GROUPS]
    _DEFAULT_AGE_ID = "age_45_59"

    def _age_id_for(age: int) -> str:
        for gid, _mid, _ped, (lo, hi) in AGE_GROUPS:
            if lo <= age <= hi:
                return gid
        return _DEFAULT_AGE_ID

    if "patient_age" not in st.session_state:
        st.session_state.patient_age = 52
    if "patient_age_label" not in st.session_state:
        st.session_state.patient_age_label = _age_id_for(st.session_state.patient_age)
    if "patient_sex" not in st.session_state:
        st.session_state.patient_sex = "X"
    if "is_pediatric" not in st.session_state:
        st.session_state.is_pediatric = False
    if "pediatric_age_group" not in st.session_state:
        st.session_state.pediatric_age_group = list(PEDIATRIC_AGE_GROUPS.keys())[1]

    # Einmalig aus EDF-Header vorausfüllen (Geschlecht)
    if _edf_preview:
        h_sex = _edf_preview.get("header_sex")
        if "patient_data_from_header" not in st.session_state:
            st.session_state.patient_data_from_header = True
            if h_sex in ("M", "F"):
                st.session_state.patient_sex = h_sex

    with st.container(border=True):
        st.subheader(tr("file_patient.section_patient"))

        col_age, col_sex = st.columns([3, 2])

        with col_age:
            st.markdown("**" + tr("file_patient.age_group") + "**")
            cur_id = st.session_state.patient_age_label
            if cur_id not in AGE_IDS:
                cur_id = _DEFAULT_AGE_ID
            age_id = st.selectbox(
                tr("file_patient.age_group"), AGE_IDS,
                index=AGE_IDS.index(cur_id),
                format_func=lambda gid: tr(f"file_patient.{gid}"),
                label_visibility="collapsed",
                key="patient_age_group_widget",
            )
            for gid, mid, is_ped_grp, _span in AGE_GROUPS:
                if gid == age_id:
                    st.session_state.patient_age = mid
                    st.session_state.patient_age_label = gid
                    if is_ped_grp != st.session_state.is_pediatric:
                        st.session_state.is_pediatric = is_ped_grp
                    break

        with col_sex:
            st.markdown("**" + tr("file_patient.sex") + "**")
            sx = st.session_state.patient_sex
            b1, b2, b3 = st.columns(3)
            if b1.button(tr("file_patient.sex_male"), type="primary" if sx == "M" else "secondary",
                         use_container_width=True, key="sex_m"):
                st.session_state.patient_sex = "M"
                st.rerun()
            if b2.button(tr("file_patient.sex_female"), type="primary" if sx == "F" else "secondary",
                         use_container_width=True, key="sex_f"):
                st.session_state.patient_sex = "F"
                st.rerun()
            if b3.button(tr("file_patient.sex_unknown"), type="primary" if sx == "X" else "secondary",
                         use_container_width=True, key="sex_x"):
                st.session_state.patient_sex = "X"
                st.rerun()

        if st.session_state.is_pediatric:
            grp_options = list(PEDIATRIC_AGE_GROUPS.keys())
            cur_grp = st.session_state.pediatric_age_group
            if cur_grp not in grp_options:
                cur_grp = grp_options[0]
            grp_val = st.selectbox(
                tr("file_patient.pediatric_group"), grp_options,
                index=grp_options.index(cur_grp),
                key="pediatric_age_group_widget",
            )
            st.session_state.pediatric_age_group = grp_val

    if not edf_path or not os.path.exists(edf_path):
        st.info(tr("file_patient.upload_prompt"), icon=":material/upload_file:")
        return

    edf = _edf_preview if _edf_preview else load_and_prepare(edf_path)

    # ── Deskriptive Vorschau ──────────────────────────────────────────────
    st.divider()
    st.subheader(tr("file_patient.section_preview"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(tr("file_patient.metric_duration"), f"{edf['duration_s']/60:.1f} min")
    c2.metric(tr("file_patient.metric_sampling"), f"{edf['sfreq']:.0f} Hz")
    c3.metric(tr("file_patient.metric_channels"), len(edf["ch_names"]))
    c4.metric(tr("file_patient.metric_ecg_detected"), len(edf["ecg_channels"]))

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(tr("file_patient.channel_mapping"))
        _c_type, _c_count, _c_ch = (tr("file_patient.col_type"), tr("file_patient.col_count"),
                                    tr("file_patient.col_channels"))
        st.dataframe(pd.DataFrame([
            {_c_type: tr("file_patient.type_eeg"), _c_count: len(edf["eeg_map"]),
             _c_ch: ", ".join(sorted(edf["eeg_map"].keys()))},
            {_c_type: tr("file_patient.type_ecg"), _c_count: len(edf["ecg_channels"]),
             _c_ch: ", ".join(edf["ecg_channels"]) or "—"},
        ]), hide_index=True, use_container_width=True)
        sfreq = edf["sfreq"]
        sfreq_note = tr("file_patient.sfreq_low_note") if sfreq < 500 else ""
        st.caption(tr("file_patient.format_note", sfreq=sfreq, note=sfreq_note))

    with col_r:
        st.markdown(tr("file_patient.annotations"))
        if edf["annotations"]:
            _c_time, _c_event = tr("file_patient.col_time_s"), tr("file_patient.col_event")
            st.dataframe(
                pd.DataFrame([{_c_time: a["onset_s"], _c_event: a["description"]}
                              for a in edf["annotations"]]),
                hide_index=True, use_container_width=True, height=220,
            )
        else:
            st.caption(tr("file_patient.no_annotations"))

    st.success(tr("file_patient.loaded_success"))
