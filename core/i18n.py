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
