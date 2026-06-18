"""Seite: Datei & Patient — Datei-Upload (Finder-Dialog), Patienteninfo, deskriptive Vorschau."""

import os
import tempfile
import uuid

import pandas as pd
import streamlit as st

from analysis.hrv_reference import PEDIATRIC_AGE_GROUPS
from core.loader import check_privacy
from core.shared import load_and_prepare

def _session_upload_dir() -> str:
    """Gibt einen session-eigenen /tmp/-Unterordner zurück (erstellt ihn bei Bedarf).

    Jede Streamlit-Session erhält eine UUID aus session_state — so landen EDF-Dateien
    verschiedener gleichzeitiger Benutzer in getrennten Ordnern.
    """
    import secrets
    if "session_upload_token" not in st.session_state:
        st.session_state.session_upload_token = secrets.token_hex(16)
    path = os.path.join(tempfile.gettempdir(),
                        "edf_analyzer", st.session_state.session_upload_token)
    os.makedirs(path, exist_ok=True)
    return path


def render():
    st.title("📂 Datei & Patient")
    st.caption("Lade die EDF-Datei hoch und trage Alter/Geschlecht ein — gilt für die gesamte Analyse.")

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
        st.subheader("EDF-Datei")

        if file_active:
            col_info, col_remove = st.columns([4, 1])
            with col_info:
                st.success(f"✅ **{st.session_state.edf_display_name}** ist geladen und aktiv verankert.")
                st.caption("Diese Datei bleibt für die gesamte Sitzung aktiv. Zum Wechseln zuerst entfernen.")
            with col_remove:
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if st.button("🗑️ Entfernen", use_container_width=True,
                             help="Datei aus der Anwendung entfernen, um eine neue hochzuladen"):
                    try:
                        os.remove(st.session_state.edf_path)
                    except OSError:
                        pass
                    st.session_state.edf_path = ""
                    st.session_state.edf_display_name = ""
                    st.rerun()
        else:
            uploaded = st.file_uploader(
                "📁 EDF-Datei hinzufügen — öffnet den Datei-Dialog (Finder)",
                type=["edf"], accept_multiple_files=False,
            )
            if uploaded is not None:
                dest_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{uploaded.name}")
                with open(dest_path, "wb") as f:
                    f.write(uploaded.getbuffer())

                # ── PHI-Gate: Datei blockieren wenn Patientendaten im Header ──
                # DEV_MODE: Gate deaktiviert für lokales Testen — VOR DEPLOYMENT wieder aktivieren
                _phi_gate_active = os.environ.get("EDF_PHI_GATE", "1") != "0"
                privacy = check_privacy(dest_path)
                if _phi_gate_active and (privacy["has_patient_id"] or privacy["has_recording_id"]):
                    os.remove(dest_path)
                    st.error(
                        "🚫 **Upload blockiert — Patientendaten im EDF-Header gefunden.**\n\n"
                        "Diese Datei enthält noch identifizierende Informationen (Name, Fallnummer "
                        "oder Aufnahmedatum). Bitte zuerst lokal anonymisieren:\n\n"
                        "```\npython anonymize.py <dateiname.edf>\n```\n\n"
                        "Danach die anonymisierte Datei hochladen."
                    )
                    st.stop()
                elif not _phi_gate_active and (privacy["has_patient_id"] or privacy["has_recording_id"]):
                    st.warning("⚠️ **DEV-Modus** — PHI-Gate deaktiviert. Datei enthält Patientendaten. Vor Deployment `EDF_PHI_GATE=1` setzen.")

                st.session_state.edf_path = dest_path
                st.session_state.edf_display_name = uploaded.name
                st.session_state.phi_validated = True
                st.rerun()

    edf_path = st.session_state.edf_path

    if edf_path and os.path.exists(edf_path):
        _edf_preview = load_and_prepare(edf_path)
    else:
        _edf_preview = None

    # ── Patient ───────────────────────────────────────────────────────────
    # Altersgruppen → repräsentativer Mittelpunkt für Normwert-Formeln
    AGE_GROUPS = [
        ("Kind (6–14 J.)",   10, True),
        ("15–29 J.",         22, False),
        ("30–44 J.",         37, False),
        ("45–59 J.",         52, False),
        ("60–74 J.",         67, False),
        ("≥ 75 J.",          80, False),
    ]
    AGE_LABELS = [g[0] for g in AGE_GROUPS]

    def _age_label_for(age: int) -> str:
        for label, mid, _ in AGE_GROUPS:
            if label == "Kind (6–14 J.)" and age <= 14:
                return label
            if label == "15–29 J." and 15 <= age <= 29:
                return label
            if label == "30–44 J." and 30 <= age <= 44:
                return label
            if label == "45–59 J." and 45 <= age <= 59:
                return label
            if label == "60–74 J." and 60 <= age <= 74:
                return label
            if label == "≥ 75 J." and age >= 75:
                return label
        return "45–59 J."

    if "patient_age" not in st.session_state:
        st.session_state.patient_age = 52
    if "patient_age_label" not in st.session_state:
        st.session_state.patient_age_label = _age_label_for(st.session_state.patient_age)
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
        st.subheader("Patient")

        col_age, col_sex = st.columns([3, 2])

        with col_age:
            st.markdown("**Altersgruppe**")
            cur_label = st.session_state.patient_age_label
            if cur_label not in AGE_LABELS:
                cur_label = AGE_LABELS[3]
            age_label = st.selectbox(
                "Altersgruppe", AGE_LABELS,
                index=AGE_LABELS.index(cur_label),
                label_visibility="collapsed",
                key="patient_age_group_widget",
            )
            for lbl, mid, is_ped_grp in AGE_GROUPS:
                if lbl == age_label:
                    st.session_state.patient_age = mid
                    st.session_state.patient_age_label = lbl
                    if is_ped_grp != st.session_state.is_pediatric:
                        st.session_state.is_pediatric = is_ped_grp
                    break

        with col_sex:
            st.markdown("**Geschlecht**")
            sx = st.session_state.patient_sex
            b1, b2, b3 = st.columns(3)
            if b1.button("♂ M", type="primary" if sx == "M" else "secondary",
                         use_container_width=True, key="sex_m"):
                st.session_state.patient_sex = "M"
                st.rerun()
            if b2.button("♀ W", type="primary" if sx == "F" else "secondary",
                         use_container_width=True, key="sex_f"):
                st.session_state.patient_sex = "F"
                st.rerun()
            if b3.button("—", type="primary" if sx == "X" else "secondary",
                         use_container_width=True, key="sex_x"):
                st.session_state.patient_sex = "X"
                st.rerun()

        if st.session_state.is_pediatric:
            grp_options = list(PEDIATRIC_AGE_GROUPS.keys())
            cur_grp = st.session_state.pediatric_age_group
            if cur_grp not in grp_options:
                cur_grp = grp_options[0]
            grp_val = st.selectbox(
                "Pädiatrische Altersgruppe (Gąsior 2018)", grp_options,
                index=grp_options.index(cur_grp),
                key="pediatric_age_group_widget",
            )
            st.session_state.pediatric_age_group = grp_val

    if not edf_path or not os.path.exists(edf_path):
        st.info("👆 Bitte oben eine EDF-Datei hochladen, um die Vorschau zu sehen.")
        return

    edf = _edf_preview if _edf_preview else load_and_prepare(edf_path)

    # ── Deskriptive Vorschau ──────────────────────────────────────────────
    st.divider()
    st.subheader("Vorschau der Aufnahme")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dauer", f"{edf['duration_s']/60:.1f} min")
    c2.metric("Sampling", f"{edf['sfreq']:.0f} Hz")
    c3.metric("Kanäle", len(edf["ch_names"]))
    c4.metric("EKG-Kanäle erkannt", len(edf["ecg_channels"]))

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Kanalzuordnung**")
        st.dataframe(pd.DataFrame([
            {"Typ": "EEG (10-20)", "Anzahl": len(edf["eeg_map"]),
             "Kanäle": ", ".join(sorted(edf["eeg_map"].keys()))},
            {"Typ": "EKG (erkannt)", "Anzahl": len(edf["ecg_channels"]),
             "Kanäle": ", ".join(edf["ecg_channels"]) or "—"},
        ]), hide_index=True, use_container_width=True)
        sfreq = edf["sfreq"]
        sfreq_note = ""
        if sfreq < 500:
            sfreq_note = f" ⚠️ <500 Hz — RMSSD-Präzision eingeschränkt"
        st.caption(f"Format: EDF+D · Encoding: latin1 (NeuroFax) · **Abtastrate EKG: {sfreq:.0f} Hz**{sfreq_note}")

    with col_r:
        st.markdown("**Klinische Annotations**")
        if edf["annotations"]:
            st.dataframe(
                pd.DataFrame([{"Zeit (s)": a["onset_s"], "Ereignis": a["description"]}
                              for a in edf["annotations"]]),
                hide_index=True, use_container_width=True, height=220,
            )
        else:
            st.caption("Keine Annotations in dieser Datei.")

    st.success("✅ Datei geladen — wechsle links zu **EEG-Viewer** oder **EKG & HRV**, um die Analyse zu starten.")
