"""DE/EN-Sprachumschaltung für die App.

Stufe 1 (Navigation & Rahmen) des i18n-Konzepts, siehe [[project_edf_i18n_konzept]]:
Seitentitel/Navigation, Login-Bildschirm, Sidebar-Statuskarte, Logout, sowie die App-weit
geteilten Chrome-Komponenten (Epochen-Navigator, Datei-Auswahl-Hinweise aus core/shared.py) —
identisch auf jeder Seite, daher hier statt in den einzelnen views/*.py behandelt. Inhalte
der einzelnen Seiten folgen in Stufe 2.

Kein gettext/Babel (Konsistenz mit dem Muster in edf-anonymizer/webui/i18n.py) — bei diesem
deutlich größeren Umfang (~600–900 Strings app-weit) aber PRO MODUL verschachtelt statt eines
flachen Dicts, damit es navigierbar bleibt.

Persistenz per Cookie (User-Vorgabe) über eine gemeinsam genutzte CookieManager-Instanz, siehe
get_cookie_manager() — dort stehen die beiden nicht offensichtlichen Fallstricke dokumentiert.

"""

import streamlit as st

_LANG_COOKIE = "edf_lang_v1"
_LANG_COOKIE_EXP_DAYS = 365

STRINGS = {
    "de": {
        "nav": {
            "file_patient": "Datei & Patient",
            "channel_report": "Kanal-Identifikation",
            "eeg_viewer": "EEG-Viewer",
            "rhythm_screening": "Rhythmus-Screening",
            "ecg_hrv": "EKG & HRV",
            "eeg_spectrum": "EEG-Spektrum",
            "aperiodic": "Aperiodisch (1/f)",
            "artifact_selection": "Artefaktkorrektur & Selektion",
            "advanced_analysis": "Erweiterte Analysen & Methodik",
            "report": "Report",
        },
        "auth": {
            "subtitle": "Neuro-Vibe · Zugang geschützt",
            "password_placeholder": "Passwort eingeben",
            "login_button": "Anmelden",
            "wrong_password": "Falsches Passwort. Bitte erneut versuchen.",
            "empty_password": "Bitte Passwort eingeben.",
            "config_error": "Konfigurationsfehler: Umgebungsvariable `EDF_PASSWORD` ist nicht "
                             "gesetzt. Die App startet aus Sicherheitsgründen ohne "
                             "Default-Passwort nicht.",
        },
        "sidebar": {
            "no_file_title": "Keine Datei geladen",
            "no_file_hint": "Bitte auf ",
            "no_file_hint_page": "Datei & Patient",
            "no_file_hint_suffix": " starten.",
            "active_recording": "Aktive Aufnahme",
            "not_checked": "nicht geprüft",
            "phi_warning": "PHI — DSGVO beachten",
            "anonymized": "anonymisiert",
            "age_label": "Alter",
            "duration_label": "Dauer",
            "channels_label": "Kanäle",
            "features_label": "Merkmale",
            "years_suffix": "J.",
            "logout": "Abmelden",
        },
        "shared": {
            "epoch_label": "Epoche",
            "epoch_select_label": "Epoche auswählen ({label})",
            "first_epoch_tooltip": "Erste Epoche",
            "prev_epoch_tooltip": "Vorherige Epoche (−10 s)",
            "next_epoch_tooltip": "Nächste Epoche (+10 s)",
            "last_epoch_tooltip": "Letzte Epoche",
            "total_duration_suffix": "min gesamt",
            "please_select_file": "Bitte zuerst auf der Seite **Datei & Patient** eine "
                                   "gültige EDF-Datei wählen.",
            "phi_not_validated": "Datei wurde nicht durch den Datenschutz-Check validiert. "
                                  "Bitte erneut hochladen.",
            "loading_edf": "Lade und verarbeite EDF…",
            "filtering_eeg": "Filtere EEG…",
            "channel_override_reason": "Manuell geändert von {old} auf {new}",
        },
        "file_patient": {
            "title": "Datei & Patient",
            "subtitle": "Lade die EDF-Datei hoch und trage Alter/Geschlecht ein — gilt für "
                         "die gesamte Analyse.",
            "section_file": "EDF-Datei",
            "file_active": "**{name}** ist geladen und aktiv verankert.",
            "file_active_hint": "Diese Datei bleibt für die gesamte Sitzung aktiv. Zum "
                                 "Wechseln zuerst entfernen.",
            "remove": "Entfernen",
            "remove_help": "Datei aus der Anwendung entfernen, um eine neue hochzuladen",
            "phi_warning": "**Datei enthält Patientendaten — Bestätigung erforderlich**\n\n"
                            "Die Datei **{name}** enthält identifizierende Informationen im "
                            "EDF-Header (Name, Fallnummer oder Aufnahmedatum).\n\n"
                            "**Empfehlung:** Nutze den [edf-anonymizer]"
                            "(https://github.com/maximilianhabs/edf-anonymizer) zur lokalen "
                            "De-Identifikation vor dem Upload — besonders für gemeinsam "
                            "genutzte oder Server-basierte Umgebungen.\n\n"
                            "Für lokale Einzelnutzung (Alpha-/Beta-Test) kann die Datei mit "
                            "Bestätigung direkt geladen werden. Die Daten werden nicht "
                            "gespeichert oder übertragen — Verarbeitung erfolgt "
                            "ausschließlich im lokalen Arbeitsspeicher dieser Sitzung.",
            "phi_confirm": "Ich bestätige, dass ich zur Verarbeitung dieser Patientendaten "
                            "berechtigt bin und die geltenden Datenschutzbestimmungen (DSGVO) "
                            "einhalte.",
            "load_anyway": "Datei trotzdem laden",
            "cancel": "Abbrechen",
            "uploader_label": "EDF-Datei hinzufügen — öffnet den Datei-Dialog",
            "section_patient": "Patient",
            "age_group": "Altersgruppe",
            "sex": "Geschlecht",
            "sex_male": "♂ M",
            "sex_female": "♀ W",
            "sex_unknown": "—",
            "pediatric_group": "Pädiatrische Altersgruppe (Gąsior 2018)",
            "upload_prompt": "Bitte oben eine EDF-Datei hochladen, um die Vorschau zu sehen.",
            "section_preview": "Vorschau der Aufnahme",
            "metric_duration": "Dauer",
            "metric_sampling": "Sampling",
            "metric_channels": "Kanäle",
            "metric_ecg_detected": "EKG-Kanäle erkannt",
            "channel_mapping": "**Kanalzuordnung**",
            "col_type": "Typ",
            "col_count": "Anzahl",
            "col_channels": "Kanäle",
            "type_eeg": "EEG (10-20)",
            "type_ecg": "EKG (erkannt)",
            "format_note": "Format: EDF+D · Encoding: latin1 (NeuroFax) · "
                            "**Abtastrate EKG: {sfreq:.0f} Hz**{note}",
            "sfreq_low_note": " · <500 Hz — RMSSD-Präzision eingeschränkt",
            "annotations": "**Klinische Annotations**",
            "col_time_s": "Zeit (s)",
            "col_event": "Ereignis",
            "no_annotations": "Keine Annotations in dieser Datei.",
            "loaded_success": "Datei geladen — wechsle links zu **EEG-Viewer** oder "
                               "**EKG & HRV**, um die Analyse zu starten.",
            "age_child": "Kind (6–14 J.)",
            "age_15_29": "15–29 J.",
            "age_30_44": "30–44 J.",
            "age_45_59": "45–59 J.",
            "age_60_74": "60–74 J.",
            "age_75_plus": "≥ 75 J.",
        },
        "eeg_viewer": {
            "title": "EEG-Viewer",
            "montage": "Montage (DGKN)",
            "epoch_length": "Epochenlänge",
            "uv_per_trace": "µV / Spur",
            "freq_filter": "Frequenzfilter",
            "time_constant": "Zeitkonstante / untere Grenzfreq.",
            "upper_cutoff": "Obere Grenzfreq. (Hz)",
            "ecg_lane_note": "EKG-Spur fix unten: **{ch}** (eigene mV-Skala)",
            "missing_electrodes": "Für die Montage **{montage}** fehlen {n} Elektrode(n): "
                                   "**{list}** — die betroffenen Ableitungen bleiben leer. "
                                   "Häufig Fehlklassifikation (Artefakt/Muskel) → in "
                                   "**Kanal-Identifikation** auf EEG korrigieren.",
            "active_montage": "Aktive Montage",
            "calibration_phase": "**Kalibrier-/Impedanzphase in dieser Epoche** (z. B. REC "
                                  "START · IMP CHECK · A1+A2 OFF) — hier ist das EEG technisch "
                                  "bedingt flach bzw. ungültig (gemeinsames Kalibriersignal "
                                  "hebt sich in bipolarer Montage auf). Für echtes EEG eine "
                                  "**spätere Epoche** wählen.",
            "bandpass": "Bandpass: {low:.2f}–{high} Hz",
            "annotations_prefix": "Annotations: ",
        },
    },
    "en": {
        "nav": {
            "file_patient": "File & Patient",
            "channel_report": "Channel Identification",
            "eeg_viewer": "EEG Viewer",
            "rhythm_screening": "Rhythm Screening",
            "ecg_hrv": "ECG & HRV",
            "eeg_spectrum": "EEG Spectrum",
            "aperiodic": "Aperiodic (1/f)",
            "artifact_selection": "Artifact Correction & Selection",
            "advanced_analysis": "Advanced Analyses & Methodology",
            "report": "Report",
        },
        "auth": {
            "subtitle": "Neuro-Vibe · Access protected",
            "password_placeholder": "Enter password",
            "login_button": "Sign in",
            "wrong_password": "Wrong password. Please try again.",
            "empty_password": "Please enter a password.",
            "config_error": "Configuration error: the `EDF_PASSWORD` environment variable is "
                             "not set. For security reasons the app will not start without it "
                             "using a default password.",
        },
        "sidebar": {
            "no_file_title": "No file loaded",
            "no_file_hint": "Please start on ",
            "no_file_hint_page": "File & Patient",
            "no_file_hint_suffix": ".",
            "active_recording": "Active recording",
            "not_checked": "not checked",
            "phi_warning": "PHI — mind GDPR",
            "anonymized": "anonymized",
            "age_label": "Age",
            "duration_label": "Duration",
            "channels_label": "Channels",
            "features_label": "Features",
            "years_suffix": "y.",
            "logout": "Log out",
        },
        "shared": {
            "epoch_label": "Epoch",
            "epoch_select_label": "Select epoch ({label})",
            "first_epoch_tooltip": "First epoch",
            "prev_epoch_tooltip": "Previous epoch (−10 s)",
            "next_epoch_tooltip": "Next epoch (+10 s)",
            "last_epoch_tooltip": "Last epoch",
            "total_duration_suffix": "min total",
            "please_select_file": "Please select a valid EDF file on the **File & Patient** "
                                   "page first.",
            "phi_not_validated": "File has not been validated by the privacy check. Please "
                                  "upload it again.",
            "loading_edf": "Loading and processing EDF…",
            "filtering_eeg": "Filtering EEG…",
            "channel_override_reason": "Manually changed from {old} to {new}",
        },
        "file_patient": {
            "title": "File & Patient",
            "subtitle": "Upload the EDF file and enter age/sex — applies to the whole "
                         "analysis.",
            "section_file": "EDF file",
            "file_active": "**{name}** is loaded and anchored.",
            "file_active_hint": "This file stays active for the whole session. Remove it "
                                 "first to switch to another one.",
            "remove": "Remove",
            "remove_help": "Remove the file from the app so a new one can be uploaded",
            "phi_warning": "**File contains patient data — confirmation required**\n\n"
                            "The file **{name}** contains identifying information in the EDF "
                            "header (name, case number, or recording date).\n\n"
                            "**Recommendation:** use [edf-anonymizer]"
                            "(https://github.com/maximilianhabs/edf-anonymizer) for local "
                            "de-identification before uploading — especially in shared or "
                            "server-based environments.\n\n"
                            "For local single-user use (alpha/beta testing) the file can be "
                            "loaded directly after confirmation. The data is neither stored "
                            "nor transmitted — processing happens exclusively in this "
                            "session's local memory.",
            "phi_confirm": "I confirm that I am authorized to process this patient data and "
                            "that I comply with the applicable data protection regulations "
                            "(GDPR).",
            "load_anyway": "Load file anyway",
            "cancel": "Cancel",
            "uploader_label": "Add EDF file — opens the file dialog",
            "section_patient": "Patient",
            "age_group": "Age group",
            "sex": "Sex",
            "sex_male": "♂ M",
            "sex_female": "♀ F",
            "sex_unknown": "—",
            "pediatric_group": "Pediatric age group (Gąsior 2018)",
            "upload_prompt": "Please upload an EDF file above to see the preview.",
            "section_preview": "Recording preview",
            "metric_duration": "Duration",
            "metric_sampling": "Sampling",
            "metric_channels": "Channels",
            "metric_ecg_detected": "ECG channels detected",
            "channel_mapping": "**Channel mapping**",
            "col_type": "Type",
            "col_count": "Count",
            "col_channels": "Channels",
            "type_eeg": "EEG (10-20)",
            "type_ecg": "ECG (detected)",
            "format_note": "Format: EDF+D · encoding: latin1 (NeuroFax) · "
                            "**ECG sample rate: {sfreq:.0f} Hz**{note}",
            "sfreq_low_note": " · <500 Hz — limited RMSSD precision",
            "annotations": "**Clinical annotations**",
            "col_time_s": "Time (s)",
            "col_event": "Event",
            "no_annotations": "No annotations in this file.",
            "loaded_success": "File loaded — switch to **EEG Viewer** or **ECG & HRV** on the "
                               "left to start the analysis.",
            "age_child": "Child (6–14 y.)",
            "age_15_29": "15–29 y.",
            "age_30_44": "30–44 y.",
            "age_45_59": "45–59 y.",
            "age_60_74": "60–74 y.",
            "age_75_plus": "≥ 75 y.",
        },
        "eeg_viewer": {
            "title": "EEG Viewer",
            "montage": "Montage (DGKN)",
            "epoch_length": "Epoch length",
            "uv_per_trace": "µV / trace",
            "freq_filter": "Frequency filter",
            "time_constant": "Time constant / low cutoff",
            "upper_cutoff": "High cutoff (Hz)",
            "ecg_lane_note": "ECG lane fixed at the bottom: **{ch}** (own mV scale)",
            "missing_electrodes": "Montage **{montage}** is missing {n} electrode(s): "
                                   "**{list}** — the affected derivations stay empty. Often a "
                                   "misclassification (artifact/muscle) → correct it to EEG "
                                   "under **Channel Identification**.",
            "active_montage": "Active montage",
            "calibration_phase": "**Calibration/impedance phase in this epoch** (e.g. REC "
                                  "START · IMP CHECK · A1+A2 OFF) — the EEG is technically "
                                  "flat or invalid here (the common calibration signal cancels "
                                  "out in a bipolar montage). Choose a **later epoch** for "
                                  "real EEG.",
            "bandpass": "Bandpass: {low:.2f}–{high} Hz",
            "annotations_prefix": "Annotations: ",
        },
    },
}


def begin_run():
    """Muss als ERSTES in app.py laufen (vor jedem Cookie-Zugriff). Verwirft die
    CookieManager-Instanz des vorherigen Durchlaufs — siehe get_cookie_manager()."""
    st.session_state.pop("_cookie_mgr", None)


def get_cookie_manager():
    """EINE gemeinsame CookieManager-Instanz PRO SKRIPTDURCHLAUF (auch core/auth.py nutzt sie).

    Zwei Fallstricke, beide 2026-08-11 mit Minimal-Repros verifiziert — nicht ändern ohne Test:

    1. Mehrere Instanzen pro Durchlauf: nur die ZUERST erzeugte liefert die Cookies des
       Browsers, jede weitere gibt `None` zurück. Als die Sprachumschaltung noch einen eigenen
       Manager mit eigenem Key anlegte, verdrängte sie den Login-Manager von der ersten
       Position und zerstörte dessen 30-Tage-Persistenz.
    2. Instanz NICHT über Durchläufe hinweg wiederverwenden: `CookieManager.__init__` liest die
       Cookies genau einmal und legt sie als einfaches dict ab. Beim allerersten Durchlauf einer
       Session ist die Komponente noch nicht mit dem Browser synchronisiert → das dict bleibt
       leer. Eine dauerhaft zwischengespeicherte Instanz würde diesen leeren Stand für immer
       festhalten.

    Daher: pro Durchlauf genau eine frische Instanz. Cache liegt im Session-State (nicht als
    Modul-Global — das wäre prozessweit und würde Cookies zwischen Nutzern vermischen) und wird
    von begin_run() zu Beginn jedes Durchlaufs geleert."""
    if "_cookie_mgr" not in st.session_state:
        from extra_streamlit_components import CookieManager
        st.session_state["_cookie_mgr"] = CookieManager(key="edf_cookie_mgr")
    return st.session_state["_cookie_mgr"]


def init_lang():
    """Läuft bei JEDEM Skriptdurchlauf (wie core/auth.py's Cookie-Check für den Login) — NICHT
    nur einmalig. Grund: die CookieManager-Komponente ist beim allerersten Durchlauf einer
    Session noch nicht mit dem Browser synchronisiert, `.get()` liefert dann `None`, obwohl der
    Browser den Cookie längst hat. Erst ein späterer Durchlauf sieht den echten Wert — würde man
    nach dem ersten Durchlauf aufhören zu lesen, bliebe die Sprache dauerhaft auf dem Default
    hängen.

    Sobald der Nutzer in dieser Session aktiv umgeschaltet hat (`_lang_user_choice`), hat das
    Vorrang und der Cookie überschreibt nichts mehr."""
    if st.session_state.get("_lang_user_choice"):
        return
    lang = "de"
    try:
        cookie_val = get_cookie_manager().get(_LANG_COOKIE)
        if cookie_val in ("de", "en"):
            lang = cookie_val
    except Exception:
        pass
    st.session_state["lang"] = lang
    # Widget-State mitziehen, damit der Schalter nicht "DE" anzeigt, während der Text bereits
    # englisch ist. Muss VOR dem Rendern des Widgets passieren (init_lang läuft ganz oben in
    # app.py, das Widget erst später) — sonst ignoriert Streamlit die Zuweisung.
    st.session_state["_lang_switch"] = "EN" if lang == "en" else "DE"


def _on_lang_change():
    """Callback des Umschalters — feuert NUR bei echter Nutzerinteraktion (nicht bei jedem
    Rerun), daher der saubere Ort, um die Nutzerwahl festzuhalten und zu persistieren."""
    val = st.session_state.get("_lang_switch")
    if val not in ("DE", "EN"):
        return
    st.session_state["_lang_user_choice"] = True
    set_lang("de" if val == "DE" else "en")


def set_lang(lang: str):
    st.session_state["lang"] = lang
    try:
        get_cookie_manager().set(_LANG_COOKIE, lang, key="lang_set",
                                 max_age=_LANG_COOKIE_EXP_DAYS * 86400)
    except Exception:
        pass  # Cookie-Persistenz optional — Session-State trägt die aktuelle Sitzung trotzdem


def current_lang() -> str:
    return st.session_state.get("lang", "de")


def tr(key: str, **kwargs) -> str:
    """z. B. tr('sidebar.age_label') oder tr('shared.epoch_select_label', label='EEG').

    Heisst bewusst `tr`, nicht `t`: `t` ist in diesem Projekt vielerorts eine lokale Variable
    fuer die Zeitachse (z. B. views/eeg_viewer.py, analysis/ecg.py) — ein Import namens `t`
    wuerde davon still ueberschrieben und erst zur Laufzeit als TypeError auffallen."""
    ns, _, k = key.partition(".")
    text = STRINGS[current_lang()][ns][k]
    return text.format(**kwargs) if kwargs else text


def render_lang_switch(container=None):
    """Kleiner DE/EN-Umschalter. `container` z. B. st.sidebar, sonst Hauptbereich.
    `init_lang()` muss vorher (am Skriptanfang, via begin_run/app.py) gelaufen sein.

    Bewusst KEIN explizites st.rerun() im Callback: das Rerun, das Streamlit beim Anklicken
    ohnehin auslöst, reicht. Ein zusätzliches manuelles Rerun direkt nach dem Cookie-`.set()`
    würde dessen asynchrones Schreiben (Component-Postback zum Browser) abbrechen, bevor der
    Cookie tatsächlich gesetzt ist (beobachtet 2026-08-11: Cookie blieb nach Reload leer)."""
    target = container if container is not None else st
    target.segmented_control(
        "Sprache / Language", options=["DE", "EN"],
        key="_lang_switch", label_visibility="collapsed",
        on_change=_on_lang_change,
    )
