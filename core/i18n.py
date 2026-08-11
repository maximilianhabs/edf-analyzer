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
        "channel_report": {
            "title": "Kanal-Identifikation",
            "intro": "Automatische, signalbasierte Kanalerkennung — herstellerunabhängig. "
                      "Typ-Korrekturen werden für alle anderen Ansichten übernommen.",
            "not_validated": "Datei nicht validiert.",
            "no_classification": "Keine Klassifikationsdaten verfügbar. Bitte Datei neu laden.",
            "overrides_active_one": "**{n} manuelle Korrektur aktiv** — werden in EEG-Viewer, "
                                     "EKG & HRV und Report verwendet.",
            "overrides_active_many": "**{n} manuelle Korrekturen aktiv** — werden in "
                                      "EEG-Viewer, EKG & HRV und Report verwendet.",
            "reset_all": "Alle zurücksetzen",
            "summary": "Zusammenfassung",
            "summary_sub": "{n} Kanäle analysiert",
            "missing_electrodes_warning": "**Nur {n} / 19 Standard-10-20-Elektroden als EEG "
                                           "erkannt** — fehlen: {list}. Für eine vollständige "
                                           "Montage (z. B. Doppelte Banane) reicht das evtl. "
                                           "nicht. Häufige Ursache: Artefakte / "
                                           "Muskelaktivität → betroffene Kanäle unten manuell "
                                           "auf **EEG** korrigieren.",
            "missing_electrodes_info": "{n} / 19 Standard-Elektroden als EEG erkannt · nicht "
                                        "dabei: {list}",
            "multiple_ecg": "**{n} EKG-Kandidaten erkannt** ({list}) — physiologisch gibt es "
                             "meist nur **einen**. Im EKG-Viewer den korrekten Kanal wählen; "
                             "die übrigen unten ggf. auf einen anderen Typ korrigieren.",
            "channels_detail": "Kanäle im Detail",
            "confidence_legend": "Die <b>Kopfleiste</b> jedes Kanals ist nach "
                                  "Erkennungs-Konfidenz eingefärbt: {dot_ok} hoch "
                                  "(&gt;70&nbsp;%) · {dot_warn} mittel (40–70&nbsp;%) · "
                                  "{dot_bad} niedrig (&lt;40&nbsp;%) — bei orange/rot lohnt "
                                  "ein Blick + ggf. manuelle Korrektur.",
            "type_filter": "Typ-Filter",
            "sort": "Sortieren",
            "sort_channel_order": "Kanalreihenfolge",
            "sort_confidence": "Konfidenz ↓",
            "sort_type": "Typ",
            "confidence_suffix": "Konfidenz",
            "corrected_badge": "korrigiert",
            "manual_was": "Manuell (war: {orig})",
            "confidence_label": "Konfidenz",
            "reasons": "**Begründung:**",
            "correct_type": "**Typ korrigieren:**",
            "type": "Typ",
            "apply": "Übernehmen",
            "reset": "Zurücksetzen",
            "signal_features": "**Signal-Features:**",
            "feat_std": "Std",
            "feat_p2p": "Peak-Peak",
            "feat_kurtosis": "Kurtosis",
            "feat_dom_freq": "Dom. Freq.",
            "feat_qrs_rate": "QRS-Rate",
            "feat_rhythmicity": "Rhythmizität",
            "spectral_distribution": "**Spektrale Verteilung:**",
            "signal_preview": "**Signal-Vorschau (10 s):**",
            "time_s": "Zeit (s)",
            "flat_channel": "Flacher/toter Kanal — kein Signal.",
            "detected_eeg": "Erkannte EEG-Kanäle",
            "detected_eeg_sub": "{n} Elektroden für EEG-Analyse",
            "aux_channels": "Hilfskanäle",
            "type_ecg": "EKG",
            "type_eeg": "EEG",
            "type_eog": "EOG",
            "type_emg": "EMG",
            "type_ref": "Referenz",
            "type_vital": "Vital",
            "type_unknown": "Unbekannt",
        },
    "report": {
            "title": "Report",
            "subtitle": "Tabellarische Gesamtübersicht — Aufnahme, Herzanalyse, EEG-Spektrum.",
            "section_recording": "Aufnahme & Metadaten",
            "col_parameter": "Parameter",
            "col_value": "Wert",
            "col_unit": "Einheit",
            "col_reference": "Referenz",
            "meta_filename": "Dateiname",
            "meta_duration": "Dauer",
            "meta_samplerate": "Abtastrate",
            "meta_channels_total": "Kanäle gesamt",
            "meta_eeg_channels": "EEG-Kanäle",
            "meta_ecg_detected": "EKG erkannt",
            "meta_yes": "ja",
            "meta_no": "nein",
            "meta_epochs": "Epochen (10 s)",
            "meta_privacy": "Datenschutz",
            "meta_phi_present": "⚠️ PHI im Header",
            "meta_anonymized": "✅ anonymisiert",
            "annotations_header": "**Annotationen / Ereignisse**",
            "col_time_s": "Zeit (s)",
            "col_event": "Ereignis",
            "all_channels_stats": "Alle Kanäle — Signal-Statistik",
            "col_nr": "Nr",
            "col_channel": "Kanal",
            "section_hrv": "Herzanalyse — HRV",
            "no_ecg": "Kein EKG-Kanal in dieser Aufnahme erkannt.",
            "computing_hrv": "Berechne HRV …",
            "hrv_failed": "HRV-Berechnung fehlgeschlagen: {err}",
            "no_hrv_data": "Keine HRV-Daten verfügbar.",
            "hrv_time_basic": "**Zeitbereich — Grundwerte & Variabilität**",
            "hrv_time_vagal": "**Zeitbereich — vagale (parasympathische) Marker**",
            "hrv_nonlinear": "**Nichtlinear — Poincaré & Komplexität**",
            "p_hr": "Herzfrequenz (HR)",
            "p_mean_rr": "Mittleres RR",
            "p_cv": "CV (Variationskoeff.)",
            "ref_hr_independent": "HF-unabhängig",
            "p_nn50": "NN50 (Absolutzahl)",
            "ref_length_dependent": "längenabhängig",
            "ref_more_sensitive": "sensitiver als pNN50",
            "p_sd1": "SD1 (kurzfristig/vagal)",
            "p_sd2": "SD2 (langfristig)",
            "ref_balance": "Balance lang/kurz",
            "p_dfa": "DFA α₁ (fraktal)",
            "ref_healthy_1": "~1,0 gesund",
            "p_sampen": "Sample Entropy",
            "ref_low_regular": "niedrig=regelmäßig",
            "p_resp_edr": "Atemfrequenz (EDR)",
            "p_artifact_rate": "Artefaktrate",
            "ref_below_5_good": "< 5 % gut",
            "fd_welch": "Frequenzbereich — Welch (FFT)",
            "fd_burg": "Frequenzbereich — Burg (MEM)",
            "p_total_power": "Total Power",
            "p_lf_power": "LF-Leistung",
            "p_hf_power": "HF-Leistung",
            "p_lf_hf": "LF/HF-Ratio",
            "p_lf_norm": "LF normiert",
            "p_hf_norm": "HF normiert",
            "p_lf_peak": "LF-Gipfel",
            "p_hf_peak": "HF-Gipfel",
            "p_resp_rsa": "Atemfrequenz (RSA)",
            "section_eeg": "EEG-Spektralanalyse",
            "no_eeg": "Keine EEG-Kanäle gefunden.",
            "no_posterior": "Keine posterioren Kanäle (O1/O2) verfügbar.",
            "analysis_window": "Analysefenster: {t0}–{t1} s ({min:.0f} min) · Methode: Welch",
            "bandpower_header": "**Bandpower — absolut (µV²) und relativ**",
            "col_band": "Band",
            "col_post_abs": "Post absolut (µV²)",
            "col_post_rel": "Post relativ",
            "col_ant_abs": "Ant absolut (µV²)",
            "col_ant_rel": "Ant relativ",
            "alpha_peak_header": "**Alpha-Gipfelfrequenz & Posterior/Anterior-Gradient**",
            "p_alpha_post": "Alpha-Gipfel posterior (O1/O2)",
            "p_alpha_ant": "Alpha-Gipfel anterior (F3/F4)",
            "p_alpha_ratio": "Post/Ant Alpha-Ratio",
            "ref_posterior_dominant": "> 1.0  (posterior dominant)",
            "clinical_ratios": "**Klinische Frequenzratios**",
            "col_ratio": "Ratio",
            "col_normal_range": "Normbereich",
            "col_clinical_hint": "Klinischer Hinweis",
            "hint_slowing": "Diffuse Verlangsamung / Enzephalopathie",
            "hint_cognitive": "Frühmarker kognitiver Dysfunktion",
            "hint_vigilance": "Vigilanz / Wachheit",
            "hint_drowsiness": "Schläfrigkeit / Aktivierung",
            "hint_dtab": "(D+T)/(A+B) — kortikale Funktionsstörung",
            "computing_spectral": "Berechne spektrale Kennzahlen & Komplexität …",
            "spectral_header": "**Spektrale Kennzahlen, Aperiodik & Komplexität (posterior O1/O2)**",
            "p_sef95": "SEF95 (spektrale Randfrequenz)",
            "p_medfreq": "Medianfrequenz (SEF50)",
            "ref_drops_slowing": "sinkt bei Verlangsamung",
            "p_aperiodic_exp": "Aperiod. Exponent (1–20 Hz)",
            "ref_flat_activated": "R²={r2} · flach=aktiviert",
            "p_alpha_flattened": "Alpha flattened (aperiodik-bereinigt)",
            "ref_true_alpha": ">0 = echter Alpha-Gipfel",
            "ref_low_regular_consciousness": "niedrig=regelmäßig (↓ Bewusstsein)",
            "p_lzc_shuffle": "LZC (shuffle)",
            "ref_high_complex": "hoch=komplex",
            "p_lzc_phase": "LZC (phase)",
            "ref_spectral_independent": ">1=spektral-unabh. komplex",
            "ap_gradient_header": "**Anterior-Posterior-Gradient (ganzer Kopf)**",
            "p_alpha_par": "Alpha-PAR (post/ant, geom. Mittel)",
            "ref_par_posterior": ">1 posterior-dominant",
            "p_exp_gradient": "Exponent-Gradient (post−ant)",
            "ref_post_ant_count": "{n_post} post · {n_ant} ant",
            "export_header": "Gesamt-Report exportieren",
            "export_caption": "Alle Werte kompakt und sortiert (Aufnahme · HRV · EEG-Spektrum · "
                               "Aperiodik · Asymmetrie) — je Zeile Wert, Einheit und kurze Norm. "
                               "Ohne Kommentar.",
            "creating_reports": "Erstelle Report-Dateien …",
            "creating_visual": "Erstelle Visual Report …",
            "download_pdf": "PDF herunterladen",
            "download_excel": "Excel herunterladen",
            "download_visual": "Visual Report (PDF)",
            "visual_unavailable": "Visual Report nicht verfügbar: {err}",
            "visual_caption": "**Visual Report** = grafischer Abstract (A4 quer, 6 Seiten): "
                               "Roh-EEG, Spektrogramm, Bandverteilung, A/P-Gradient, Asymmetrie, "
                               "EKG mit QRS-Erkennung, RR vor/nach Bereinigung, Poincaré & "
                               "HRV-Spektrum — nur robuste Marker, zum Zeigen und Präsentieren.",
            "export_failed": "Report-Export fehlgeschlagen: {err}",
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
        "channel_report": {
            "title": "Channel Identification",
            "intro": "Automatic, signal-based channel detection — manufacturer-independent. "
                      "Type corrections carry over to all other views.",
            "not_validated": "File not validated.",
            "no_classification": "No classification data available. Please reload the file.",
            "overrides_active_one": "**{n} manual correction active** — used in EEG Viewer, "
                                     "ECG & HRV and Report.",
            "overrides_active_many": "**{n} manual corrections active** — used in EEG Viewer, "
                                      "ECG & HRV and Report.",
            "reset_all": "Reset all",
            "summary": "Summary",
            "summary_sub": "{n} channels analyzed",
            "missing_electrodes_warning": "**Only {n} / 19 standard 10-20 electrodes detected "
                                           "as EEG** — missing: {list}. That may not be enough "
                                           "for a complete montage (e.g. double banana). "
                                           "Common cause: artifacts / muscle activity → "
                                           "correct the affected channels to **EEG** below.",
            "missing_electrodes_info": "{n} / 19 standard electrodes detected as EEG · not "
                                        "included: {list}",
            "multiple_ecg": "**{n} ECG candidates detected** ({list}) — physiologically there "
                             "is usually only **one**. Pick the correct channel in the ECG "
                             "viewer; correct the others to a different type below if needed.",
            "channels_detail": "Channels in detail",
            "confidence_legend": "Each channel's <b>header bar</b> is colored by detection "
                                  "confidence: {dot_ok} high (&gt;70&nbsp;%) · {dot_warn} "
                                  "medium (40–70&nbsp;%) · {dot_bad} low (&lt;40&nbsp;%) — "
                                  "orange/red is worth a look and possibly a manual "
                                  "correction.",
            "type_filter": "Type filter",
            "sort": "Sort",
            "sort_channel_order": "Channel order",
            "sort_confidence": "Confidence ↓",
            "sort_type": "Type",
            "confidence_suffix": "confidence",
            "corrected_badge": "corrected",
            "manual_was": "Manual (was: {orig})",
            "confidence_label": "Confidence",
            "reasons": "**Rationale:**",
            "correct_type": "**Correct type:**",
            "type": "Type",
            "apply": "Apply",
            "reset": "Reset",
            "signal_features": "**Signal features:**",
            "feat_std": "Std",
            "feat_p2p": "Peak-to-peak",
            "feat_kurtosis": "Kurtosis",
            "feat_dom_freq": "Dom. freq.",
            "feat_qrs_rate": "QRS rate",
            "feat_rhythmicity": "Rhythmicity",
            "spectral_distribution": "**Spectral distribution:**",
            "signal_preview": "**Signal preview (10 s):**",
            "time_s": "Time (s)",
            "flat_channel": "Flat/dead channel — no signal.",
            "detected_eeg": "Detected EEG channels",
            "detected_eeg_sub": "{n} electrodes for EEG analysis",
            "aux_channels": "Auxiliary channels",
            "type_ecg": "ECG",
            "type_eeg": "EEG",
            "type_eog": "EOG",
            "type_emg": "EMG",
            "type_ref": "Reference",
            "type_vital": "Vital",
            "type_unknown": "Unknown",
        },
        "report": {
            "title": "Report",
            "subtitle": "Tabular overview — recording, cardiac analysis, EEG spectrum.",
            "section_recording": "Recording & metadata",
            "col_parameter": "Parameter",
            "col_value": "Value",
            "col_unit": "Unit",
            "col_reference": "Reference",
            "meta_filename": "File name",
            "meta_duration": "Duration",
            "meta_samplerate": "Sample rate",
            "meta_channels_total": "Channels total",
            "meta_eeg_channels": "EEG channels",
            "meta_ecg_detected": "ECG detected",
            "meta_yes": "yes",
            "meta_no": "no",
            "meta_epochs": "Epochs (10 s)",
            "meta_privacy": "Privacy",
            "meta_phi_present": "⚠️ PHI in header",
            "meta_anonymized": "✅ anonymized",
            "annotations_header": "**Annotations / events**",
            "col_time_s": "Time (s)",
            "col_event": "Event",
            "all_channels_stats": "All channels — signal statistics",
            "col_nr": "No.",
            "col_channel": "Channel",
            "section_hrv": "Cardiac analysis — HRV",
            "no_ecg": "No ECG channel detected in this recording.",
            "computing_hrv": "Computing HRV …",
            "hrv_failed": "HRV computation failed: {err}",
            "no_hrv_data": "No HRV data available.",
            "hrv_time_basic": "**Time domain — basic values & variability**",
            "hrv_time_vagal": "**Time domain — vagal (parasympathetic) markers**",
            "hrv_nonlinear": "**Nonlinear — Poincaré & complexity**",
            "p_hr": "Heart rate (HR)",
            "p_mean_rr": "Mean RR",
            "p_cv": "CV (coeff. of variation)",
            "ref_hr_independent": "HR-independent",
            "p_nn50": "NN50 (absolute count)",
            "ref_length_dependent": "length-dependent",
            "ref_more_sensitive": "more sensitive than pNN50",
            "p_sd1": "SD1 (short-term/vagal)",
            "p_sd2": "SD2 (long-term)",
            "ref_balance": "long/short balance",
            "p_dfa": "DFA α₁ (fractal)",
            "ref_healthy_1": "~1.0 healthy",
            "p_sampen": "Sample entropy",
            "ref_low_regular": "low = regular",
            "p_resp_edr": "Respiratory rate (EDR)",
            "p_artifact_rate": "Artifact rate",
            "ref_below_5_good": "< 5 % good",
            "fd_welch": "Frequency domain — Welch (FFT)",
            "fd_burg": "Frequency domain — Burg (MEM)",
            "p_total_power": "Total power",
            "p_lf_power": "LF power",
            "p_hf_power": "HF power",
            "p_lf_hf": "LF/HF ratio",
            "p_lf_norm": "LF normalized",
            "p_hf_norm": "HF normalized",
            "p_lf_peak": "LF peak",
            "p_hf_peak": "HF peak",
            "p_resp_rsa": "Respiratory rate (RSA)",
            "section_eeg": "EEG spectral analysis",
            "no_eeg": "No EEG channels found.",
            "no_posterior": "No posterior channels (O1/O2) available.",
            "analysis_window": "Analysis window: {t0}–{t1} s ({min:.0f} min) · method: Welch",
            "bandpower_header": "**Band power — absolute (µV²) and relative**",
            "col_band": "Band",
            "col_post_abs": "Post absolute (µV²)",
            "col_post_rel": "Post relative",
            "col_ant_abs": "Ant absolute (µV²)",
            "col_ant_rel": "Ant relative",
            "alpha_peak_header": "**Alpha peak frequency & posterior/anterior gradient**",
            "p_alpha_post": "Alpha peak posterior (O1/O2)",
            "p_alpha_ant": "Alpha peak anterior (F3/F4)",
            "p_alpha_ratio": "Post/ant alpha ratio",
            "ref_posterior_dominant": "> 1.0  (posterior dominant)",
            "clinical_ratios": "**Clinical frequency ratios**",
            "col_ratio": "Ratio",
            "col_normal_range": "Normal range",
            "col_clinical_hint": "Clinical note",
            "hint_slowing": "Diffuse slowing / encephalopathy",
            "hint_cognitive": "Early marker of cognitive dysfunction",
            "hint_vigilance": "Vigilance / wakefulness",
            "hint_drowsiness": "Drowsiness / activation",
            "hint_dtab": "(D+T)/(A+B) — cortical dysfunction",
            "computing_spectral": "Computing spectral measures & complexity …",
            "spectral_header": "**Spectral measures, aperiodic & complexity (posterior O1/O2)**",
            "p_sef95": "SEF95 (spectral edge frequency)",
            "p_medfreq": "Median frequency (SEF50)",
            "ref_drops_slowing": "drops with slowing",
            "p_aperiodic_exp": "Aperiodic exponent (1–20 Hz)",
            "ref_flat_activated": "R²={r2} · flat = activated",
            "p_alpha_flattened": "Alpha flattened (aperiodic-corrected)",
            "ref_true_alpha": ">0 = genuine alpha peak",
            "ref_low_regular_consciousness": "low = regular (↓ consciousness)",
            "p_lzc_shuffle": "LZC (shuffle)",
            "ref_high_complex": "high = complex",
            "p_lzc_phase": "LZC (phase)",
            "ref_spectral_independent": ">1 = spectrally independent complexity",
            "ap_gradient_header": "**Anterior-posterior gradient (whole head)**",
            "p_alpha_par": "Alpha PAR (post/ant, geometric mean)",
            "ref_par_posterior": ">1 posterior-dominant",
            "p_exp_gradient": "Exponent gradient (post−ant)",
            "ref_post_ant_count": "{n_post} post · {n_ant} ant",
            "export_header": "Export full report",
            "export_caption": "All values compact and sorted (recording · HRV · EEG spectrum · "
                               "aperiodic · asymmetry) — value, unit and a short norm per row. "
                               "No commentary.",
            "creating_reports": "Creating report files …",
            "creating_visual": "Creating visual report …",
            "download_pdf": "Download PDF",
            "download_excel": "Download Excel",
            "download_visual": "Visual report (PDF)",
            "visual_unavailable": "Visual report unavailable: {err}",
            "visual_caption": "**Visual report** = graphical abstract (A4 landscape, 6 pages): "
                               "raw EEG, spectrogram, band distribution, A/P gradient, asymmetry, "
                               "ECG with QRS detection, RR before/after cleaning, Poincaré & HRV "
                               "spectrum — robust markers only, made for showing and presenting.",
            "export_failed": "Report export failed: {err}",
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
