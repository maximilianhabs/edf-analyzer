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
            "disclaimer_short": "Kein Medizinprodukt · Forschung und Lehre · keine Diagnose",
            "disclaimer_long":
                "**Kein Medizinprodukt, keine Diagnosesoftware.** Dieses Werkzeug dient "
                "Forschung, methodischer Exploration und Lehre. Alle ausgegebenen Werte sind "
                "**Orientierung**, keine Diagnosekriterien, und ersetzen keine ärztliche "
                "Befundung.",
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
            "download_manifest": "Manifest (JSON) — maschinenlesbar",
            "manifest_caption":
                "Dieselben Werte wie im Report, zusätzlich Herkunft, Parameter und die "
                "SHA-256-Prüfsumme der Aufnahme — zum Einlesen, Vergleichen und Nachrechnen. "
                "Enthält keine Kopfdaten der Aufnahme.",
            "visual_caption": "**Visual Report** = grafischer Abstract (A4 quer, 6 Seiten): "
                               "Roh-EEG, Spektrogramm, Bandverteilung, A/P-Gradient, Asymmetrie, "
                               "EKG mit QRS-Erkennung, RR vor/nach Bereinigung, Poincaré & "
                               "HRV-Spektrum — nur robuste Marker, zum Zeigen und Präsentieren.",
            "export_failed": "Report-Export fehlgeschlagen: {err}",
        },
    "rhythm": {
            "title": "Rhythmus-Screening",
            "polarity_check": "Polaritäts-Check: Analyse mit vs. ohne Korrektur anzeigen",
            "too_few_rpeaks": "Zu wenige R-Zacken nach manueller Korrektur — Entfernungen zurücksetzen?",
            "reset_manual": "Manuelle Korrekturen zurücksetzen",
            "reset_all_removals": "↺ Alle {n} manuellen Entfernungen zurücksetzen",
            "too_few_beats_ensemble": "Zu wenige vollständige Schläge in diesem Fenster für die Ensemble-Analyse ",
            "methodology": "Was bedeutet das? — Methodik",
            "traffic_light": "Ampel-Übersicht",
            "window_navigator": "1-Minuten-Fenster-Navigator",
            "window_navigator_sub": "Rohsignal · R-Zacken farbcodiert · Artefakt-Zonen schattiert",
            "pqrst_ensemble": "PQRST-Ensemble & P-Welle",
            "notable_sections": "Auffällige Abschnitte",
            "artifact_gallery": "Artefakt-Galerie",
            "artifact_gallery_sub": "Exemplarische Ausschnitte der {n} verworfenen Abschnitte",
            "stage1_rules": "Stufe①-Regeln im Detail — wonach wird ein 10s-Segment als Artefakt ",
            "ecg_channel": "EKG-Kanal",
            "detector": "R-Zacken-Detektor",
            "validated_unavailable": "Nur der eigene Detektor verfügbar — die validierten "
                                      "Vergleichsverfahren brauchen das optionale Paket "
                                      "`py-ecg-detectors` (siehe requirements-validated.txt).",
            "detector_help": "Der eigene Detektor bleibt Default (bewährt). Bei Zweifeln/"
                              "unklaren Fällen auf einen validierten Detektor umschalten und "
                              "vergleichen — beeinflusst das gesamte Rhythmus-Screening dieser "
                              "Seite (Artefakte/AFib/Ektopie/P-Welle).",
        },
        "aperiodic": {
            "title": "Aperiodische Komponente (1/f)",
            "how_measured": "Wie wird das gemessen? (Trennung von Hintergrund & Rhythmus)",
            "load_file_first": "Bitte zuerst auf **Datei & Patient** eine EDF-Datei laden.",
            "no_eeg": "Keine EEG-Kanäle (10-20) erkannt.",
            "channel": "Kanal",
            "which_channel": "Welchen Kanal wählen?",
            "signal_too_short": "Signal zu kurz für die Spektralschätzung.",
            "fit_impossible": "Aperiodischer Fit nicht möglich (zu wenige Frequenzpunkte).",
            "methodology": "Was ist die aperiodische Komponente? — Methodik & Literatur",
            "metrics": "Kennzahlen",
            "spectral_decomposition": "Spektrale Zerlegung",
            "spectral_decomposition_sub": "log-log: Original vs. aperiodischer Fit",
            "corrected_spectrum": "Untergrund-bereinigtes Spektrum",
            "corrected_spectrum_sub": "Vielfaches über dem 1/f-Untergrund",
            "exponent_per_channel": "Exponent je Kanal",
            "exponent_per_channel_sub": "Konsistenz-Check & Kanalwahl",
        },
        "advanced": {
            "title": "Erweiterte Analysen & Methodik",
            "no_ecg": "Kein EKG-Kanal identifiziert.",
            "no_eeg": "Keine EEG-Kanäle.",
            "fooof_unavailable": "FOOOF nicht verfügbar (Lib fehlt) — nur eigener Fit angezeigt.",
            "ecg_channel": "EKG-Kanal",
            "channel": "Kanal",
            "too_few_rr": "Zu wenige RR-Intervalle für ein HRV-Spektrum.",
            "no_posterior_anterior": "O1/O2 bzw. F3/F4 nicht verfügbar.",
            "too_few_beats_dfa": "Zu wenige Schläge für DFA (α2 braucht ~≥256).",
            "spectrum_uncomputable": "Spektrum nicht berechenbar.",
            "methods_validity": "Methoden & Validität",
            "methods_validity_sub": "Welche Verfahren, welche Referenz, welcher Beleg",
            "col_domain": "Bereich",
            "col_parameter": "Parameter",
            "col_procedure": "Verfahren",
            "col_reference": "Referenz",
            "col_fidelity": "Umsetzung",
            "col_level": "Belegstufe",
            "col_evidence": "Beleg",
            "col_limitations": "Einschränkungen",
            "methods_legend":
                "Zwei getrennte Achsen: **Umsetzung** sagt, wie treu wir der publizierten "
                "Vorschrift folgen (vollständig · 🟡 vereinfacht · 🔬 Proxy). **Belegstufe** "
                "sagt, worauf sich das stützt: 📖 literaturbasiert = das Verfahren ist "
                "publiziert, *diese* Implementierung aber nicht nachgemessen · "
                "✅ implementierungsvalidiert = liefert auf einem Datensatz mit bekannter "
                "Wahrheit die Sollwerte · 🏥 klinisch validiert = gegen einen klinischen "
                "Referenzstandard geprüft. Stand: {n_lit} literaturbasiert, {n_impl} "
                "implementierungsvalidiert, {n_clin} klinisch validiert.",
            "detector_comparison": "R-Zacken-Detektor — Vergleich & visuelle Kontrolle",
            "aperiodic_comparison": "Aperiodik 1/f — FOOOF vs. eigener Fit (W2)",
            "hrv_spectrum_comparison": "HRV-Spektrum — Lomb-Scargle vs. Welch/Burg (W3)",
            "asymmetry": "Hemisphärische Asymmetrie — relativ vs. absolut (G1)",
            "dfa": "DFA — α1 + α2 mit überlappenden Fenstern (G6)",
            "multitaper": "EEG-Spektrum — Multitaper vs. Welch (G7)",
            "window_width": "Fensterbreite",
            "position_s": "Position (s)",
            "overlay_detectors": "Overlay-Detektoren",
            "validated_unavailable": "Dieser Vergleich braucht das optionale Paket "
                                      "`py-ecg-detectors` (GPL-3.0, bewusst nicht in den "
                                      "Standard-Abhängigkeiten). Installieren mit "
                                      "`pip install -r requirements-validated.txt` — die "
                                      "übrige App funktioniert unabhängig davon vollständig.",
        },
    "spectrum": {
            "title": "EEG-Spektrum",
            "delta_from_1hz":
                "Delta wird ab **1 Hz** gerechnet, nicht ab den literaturüblichen 0,5 Hz. "
                "Das ist Absicht: unterhalb 1 Hz liegt der Schwerpunkt von Schwitzartefakten, "
                "Elektrodendrift und langsamer Bewegung, die sonst als Verlangsamung "
                "erschienen. Der Preis ist, dass sehr langsames Delta zu schwach gemessen "
                "wird — beim Vergleich mit Fremdsystemen zu bedenken.",
            "load_file_first": "Bitte zuerst auf **Datei & Patient** eine EDF-Datei laden.",
            "no_eeg": "Keine EEG-Kanäle (10-20) erkannt.",
            "window_start": "Fenster-Start (s)",
            "duration": "Dauer",
            "duration_help": "Analysefensterlänge ab Start",
            "analysis_options": "⚙️ Analyse-Optionen",
            "multitaper": "Multitaper-Methode (Thomson 1982)",
            "multitaper_help": "Verwendet DPSS-Fenster (NW=3, K=5) statt Welch. Schärfere "
                                "Alpha-Peaks, weniger Spectral Leakage. Hilfreich wenn der "
                                "Alpha-Gipfel in Welch verbreitert erscheint. Etwas langsamer "
                                "bei langen Aufnahmen.",
            "artifact_filter": "Extremartefakt-Filter (≥150 µV)",
            "artifact_filter_help": "Epochs mit Peak-Amplitude ≥150 µV werden durch lineare "
                                     "Interpolation ersetzt — nur für wirklich extreme "
                                     "Artefakte (Elektrode ab, Bewegung). Standard: aus — das "
                                     "Gesamtsignal inklusive aller physiologischen Phasen "
                                     "(Augen auf/zu, HV) wird vollständig analysiert.",
            "consensus_panel": "Konsensus-Panel",
            "consensus_panel_sub": "Posterior O1+O2 vs. Anterior F3+F4 · ACNS-Empfehlung",
            "consensus_unavailable": "ℹ️ Konsensus-Panel nicht verfügbar — fehlende Kanäle: {list}",
            "asymmetry": "Hemisphärische Asymmetrie",
            "ap_gradient": "Anterior-Posterior-Gradient (PAR)",
            "ap_gradient_sub": "Ganzer Kopf · ganzes Gehirn",
            "heavy_calc": "Rechenintensive Maße berechnen (A/P-Gradient hier + LZC-Komplexität "
                           "weiter unten + 1/f-korrigierte dominante Frequenzband-Erkennung in "
                           "den FFT-Kacheln oben)",
            "heavy_calc_help": "Alle drei sind rechenintensiver (O(N²)/kopfweit bzw. "
                                "zusätzlicher 1/f-Kurven-Fit je Ableitung). Standard aus, damit "
                                "die Ansicht schnell bleibt — bei Bedarf hier aktivieren; gilt "
                                "für die ganze Seite. Die 1/f-Korrektur behebt eine "
                                "systematische Verzerrung Richtung Delta bei der "
                                "Dominante-Frequenz-Erkennung — ohne sie wird ein moderater "
                                "Theta-Rhythmus oft fälschlich als 'Delta-dominant' angezeigt.",
            "heavy_calc_hint": "ℹ️ Rechenintensiv — obigen Schalter aktivieren, um den "
                                "A/P-Gradienten (ganzer Kopf) zu berechnen.",
            "single_channel": "Einzelkanal-Analyse",
            "single_channel_sub": "Bandpower · FFT · Klinische Ratios pro Kanal",
            "channels_max2": "Kanal(e) — max. 2",
            "select_channel": "Bitte mindestens einen Kanal auswählen.",
            "reference_epoch": "Referenz-Epoch",
            "reference_epoch_sub": "Interne Validierung · Kanal wählbar · FFT-Overlay",
            "ref_channel": "Kanal für Referenz-Epoch",
            "ref_channel_help": "Standard: O2 (posteriores Alpha). Wähle jeden verfügbaren "
                                 "EEG-Kanal.",
            "position_in_recording": "Position im Recording (s)",
            "no_alpha_peak": "Kein Alpha-Peak detektierbar.",
            "segment_too_short": "Segment zu kurz für PSD.",
            "appendix": "Appendix — Parameter, Methoden und klinische Interpretation",
        },
        "artifact": {
            "title": "Artefaktkorrektur & EEG/EKG-Selektion",
            "spectral_comparison": "Spektralanalyse — Gesamt vs. artefaktkorrigiert",
            "no_artifacts_marked": "Keine Artefakt-Segmente markiert → korrigiert = Gesamt "
                                    "(nichts zu entfernen).",
            "little_clean_eeg": "Nur {s:.0f}s sauberes EEG — Korrektur-Spektrum wenig belastbar.",
            "compare_channel": "Kanal für den Vergleich",
            "segment_too_short": "Segment zu kurz für eine stabile Spektralschätzung.",
            "hrv_comparison": "HRV — Gesamt vs. artefaktkorrigiert",
            "no_ecg": "Kein EKG-Kanal identifiziert → HRV-Vergleich nicht möglich. Ggf. in der ",
            "too_few_rpeaks": "Zu wenige R-Zacken auf **{ch}** für eine HRV-Auswertung.",
            "too_few_clean_rr": "Zu wenige saubere RR-Intervalle für die HRV-Berechnung.",
            "review_all_channels": "Review-Ansicht — alle Kanäle",
            "montage": "Montage",
            "screen": "Screen",
            "edit_segments": "Artefakt-Segmente — bearbeiten",
            "reset": "Zurücksetzen",
            "mark_artifact_again": "↩︎ doch Artefakt",
            "not_artifact": "kein Artefakt",
            "delete": "löschen",
            "no_artifact_segments": "Keine Artefakt-Segmente — die Aufnahme läuft ruhig durch.",
            "add_artifact_range": "Artefakt-Bereich hinzufügen (übersehenen Bereich ausklammern)",
            "add": "Hinzufügen",
            "end_after_start": "Ende muss nach Start liegen.",
            "detector_settings": "Detektor-Einstellungen — Feinjustierung der Artefakt-Erkennung",
            "reset_to_default": "Auf Standard zurücksetzen",
            "overview": "Übersicht",
            "overview_sub": "Effektive Maske = Auto + deine Änderungen · live berechnet",
            "no_manual_changes": "Noch keine manuellen Änderungen — es gilt die **Auto-Maske**. "
                                  "Sobald du oben im ",
            "little_clean_warning": "Nur **{s:.0f}s** sauberes EEG — für stabile Spektralwerte "
                                     "grenzwertig ",
            "timeline": "Zeitleiste",
            "timeline_sub": "Rote Flächen = Multikanal-Ausschläge · schattiert = Artefakt-Segment",
            "amplitude_distribution": "Amplituden-Verteilung je Kanal",
            "detail_histogram_channel": "Kanal für Detail-Histogramm",
            "all_channels_boxplot": "Alle Kanäle im Vergleich (Boxplot)",
            "bad_channel_suggestions": "Bad-Channel-Vorschläge",
            "bad_channel_sub": "Elektrode dauerhaft auffällig",
        },
    "ecg_hrv": {
            "title": "EKG & HRV",
            "coverage_gap_title": "In {min} min der Aufnahme wurde kein einziger Herzschlag erkannt",
            "coverage_gap_body":
                "Betroffene Abschnitte: {segments}. Alle HRV-Werte beziehen sich ausschließlich "
                "auf die übrigen Abschnitte. Mögliche Ursachen: Elektrodenablösung, "
                "Verstärkersättigung, ein Amplitudensprung, an dem sich die adaptive Schwelle "
                "des Detektors nicht mehr erholt — oder tatsächlich fehlende Schläge. Bitte im "
                "Rohsignal nachsehen, bevor die Werte verwendet werden.",
            "too_few_beats_segment": "Zu wenige Schläge in diesem Segment für HRV-Analyse.",
            "chart_explanation": "Diagramm-Erklärung",
            "diagnosis_no_channel": "Diagnose — warum wurde kein Kanal erkannt?",
            "manual_channel": "Kanal manuell auswählen",
            "analyzing_channel": "Analysiere Kanal **{ch}** — bitte EKG-Spur visuell prüfen.",
            "too_few_rpeaks": "Zu wenige R-Peaks erkannt. Kanal oder Filter prüfen.",
            "polarity_check": "Polaritäts-Check: Analyse mit vs. ohne Korrektur anzeigen",
            "spectral_method": "Spektralmethode für HRV-Befund",
            "spectral_method_help": "Welch: klassisch, robust. Burg/MEM: schärfere Peaks, "
                                     "kürzer stabil.",
            "tab_rr": "RR & Zeitdomäne",
            "tab_freq": "Frequenzdomäne",
            "tab_findings": "HRV-Befund",
            "tab_hv": "Hyperventilation",
            "no_rpeaks_epoch": "Keine R-Peaks in dieser Epoche erkannt — andere Epoche wählen "
                                "oder Kanal prüfen.",
            "analysis_window": "Analysefenster für Zeitbereichsparameter",
            "analysis_window_help": "SDNN & Spektralwerte skalieren mit der Fensterlänge. Für "
                                     "Vergleiche mit NeuroFax-Kurzzeit-HRV (3 min) auf ein "
                                     "3-min-Subfenster einschränken.",
            "window_full": "Gesamtaufnahme",
            "window_first3": "Erste 3 min",
            "window_stablest3": "Stabilste 3 min",
            "window_subwindow": "Subfenster {t0:.0f}–{t1:.0f} s",
            "window_header": "Fenster {t0:.0f}–{t1:.0f} s",
            "dfa_uncomputable": "ℹ️ DFA α₁ nicht berechenbar — zu wenige Schläge (mind. ~32 nötig).",
            "edr_uncomputable": "ℹ️ EDR nicht berechenbar — zu wenige/instabile R-Zacken oder "
                                 "Segment zu kurz.",
            "no_welch": "Kein Welch-Spektrum berechenbar (zu wenige RR-Intervalle).",
            "no_burg": "Kein Burg-Spektrum berechenbar (zu wenige RR-Intervalle).",
            "parameter_explanations": "Parameter-Erklärungen, Synonyme & Quellen",
            "rr_table": "RR-Tabelle (alle Schläge)",
            "export_excel": "HRV-Ergebnisse als Excel exportieren",
            "create_pdf": "PDF-Report erzeugen",
            "creating_pdf": "Erzeuge PDF…",
            "download_pdf": "PDF herunterladen",
            "no_hyperventilation": "**Keine Hyperventilation** in dieser Aufnahme erkannt "
                                    "(keine HVT-Annotations).",
            "hv_manual": "HV manuell",
            "adjust": "Anpassen",
            "no_hvt_annotations": "Keine HVT-Annotations im EDF — Phasen manuell gesetzt.",
            "manual_phases_active": "Manuelle Phasengrenzen aktiv — Auto-Erkennung überschrieben.",
            "hvt_start": "HVT Start (s)",
            "hvt_end": "HVT Ende (s)",
            "post_hv_end": "Post-HV Ende (s)",
            "auto": "↩ Auto",
            "too_few_beats_hvt": "Zu wenige Schläge im HVT-Segment.",
            "too_few_beats_photic": "Zu wenige Schläge im Fotostimulations-Segment.",
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
            "disclaimer_short": "Not a medical device · research and teaching · not for diagnosis",
            "disclaimer_long":
                "**Not a medical device, not diagnostic software.** This tool is for research, "
                "methodological exploration and teaching. All reported values are "
                "**orientation**, not diagnostic criteria, and do not replace clinical "
                "assessment by a physician.",
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
            "download_manifest": "Manifest (JSON) — machine-readable",
            "manifest_caption":
                "The same values as in the report, plus provenance, parameters and the "
                "SHA-256 checksum of the recording — for parsing, comparing and recomputing. "
                "Contains none of the recording's header data.",
            "visual_caption": "**Visual report** = graphical abstract (A4 landscape, 6 pages): "
                               "raw EEG, spectrogram, band distribution, A/P gradient, asymmetry, "
                               "ECG with QRS detection, RR before/after cleaning, Poincaré & HRV "
                               "spectrum — robust markers only, made for showing and presenting.",
            "export_failed": "Report export failed: {err}",
        },
        "rhythm": {
            "title": "Rhythm Screening",
            "polarity_check": "Polarity check: show analysis with vs. without correction",
            "too_few_rpeaks": "Too few R peaks after manual correction — reset the removals?",
            "reset_manual": "Reset manual corrections",
            "reset_all_removals": "↺ Reset all {n} manual removals",
            "too_few_beats_ensemble": "Too few complete beats in this window for ensemble analysis ",
            "methodology": "What does this mean? — methodology",
            "traffic_light": "Traffic-light overview",
            "window_navigator": "1-minute window navigator",
            "window_navigator_sub": "Raw signal · R peaks color-coded · artifact zones shaded",
            "pqrst_ensemble": "PQRST ensemble & P wave",
            "notable_sections": "Notable sections",
            "artifact_gallery": "Artifact gallery",
            "artifact_gallery_sub": "Representative excerpts of the {n} rejected sections",
            "stage1_rules": "Stage ① rules in detail — what makes a 10 s segment an artifact ",
            "ecg_channel": "ECG channel",
            "detector": "R-peak detector",
            "validated_unavailable": "Only the built-in detector is available — the validated "
                                      "comparison methods need the optional package "
                                      "`py-ecg-detectors` (see requirements-validated.txt).",
            "detector_help": "The built-in detector stays the default (proven). In doubtful or "
                              "unclear cases, switch to a validated detector and compare — this "
                              "affects the entire rhythm screening on this page (artifacts/"
                              "AFib/ectopy/P wave).",
        },
        "aperiodic": {
            "title": "Aperiodic component (1/f)",
            "how_measured": "How is this measured? (separating background & rhythm)",
            "load_file_first": "Please load an EDF file on **File & Patient** first.",
            "no_eeg": "No EEG channels (10-20) detected.",
            "channel": "Channel",
            "which_channel": "Which channel to pick?",
            "signal_too_short": "Signal too short for spectral estimation.",
            "fit_impossible": "Aperiodic fit not possible (too few frequency points).",
            "methodology": "What is the aperiodic component? — methodology & literature",
            "metrics": "Metrics",
            "spectral_decomposition": "Spectral decomposition",
            "spectral_decomposition_sub": "log-log: original vs. aperiodic fit",
            "corrected_spectrum": "Background-corrected spectrum",
            "corrected_spectrum_sub": "Multiple above the 1/f background",
            "exponent_per_channel": "Exponent per channel",
            "exponent_per_channel_sub": "Consistency check & channel choice",
        },
        "advanced": {
            "title": "Advanced Analyses & Methodology",
            "no_ecg": "No ECG channel identified.",
            "no_eeg": "No EEG channels.",
            "fooof_unavailable": "FOOOF unavailable (library missing) — showing own fit only.",
            "ecg_channel": "ECG channel",
            "channel": "Channel",
            "too_few_rr": "Too few RR intervals for an HRV spectrum.",
            "no_posterior_anterior": "O1/O2 or F3/F4 not available.",
            "too_few_beats_dfa": "Too few beats for DFA (α2 needs ~≥256).",
            "spectrum_uncomputable": "Spectrum cannot be computed.",
            "methods_validity": "Methods & validity",
            "methods_validity_sub": "Which methods, which reference, which evidence",
            "col_domain": "Domain",
            "col_parameter": "Parameter",
            "col_procedure": "Procedure",
            "col_reference": "Reference",
            "col_fidelity": "Implementation",
            "col_level": "Evidence level",
            "col_evidence": "Evidence",
            "col_limitations": "Limitations",
            "methods_legend":
                "Two separate axes: **implementation** says how closely we follow the "
                "published procedure (full · 🟡 simplified · 🔬 proxy). **Evidence level** "
                "says what that rests on: 📖 literature-based = the method is published, but "
                "*this* implementation has not been measured against known values · "
                "✅ implementation-validated = reproduces the expected values on a dataset "
                "with known ground truth · 🏥 clinically validated = checked against a "
                "clinical reference standard. Current state: {n_lit} literature-based, "
                "{n_impl} implementation-validated, {n_clin} clinically validated.",
            "detector_comparison": "R-peak detector — comparison & visual check",
            "aperiodic_comparison": "Aperiodic 1/f — FOOOF vs. own fit (W2)",
            "hrv_spectrum_comparison": "HRV spectrum — Lomb-Scargle vs. Welch/Burg (W3)",
            "asymmetry": "Hemispheric asymmetry — relative vs. absolute (G1)",
            "dfa": "DFA — α1 + α2 with overlapping windows (G6)",
            "multitaper": "EEG spectrum — multitaper vs. Welch (G7)",
            "window_width": "Window width",
            "position_s": "Position (s)",
            "overlay_detectors": "Overlay detectors",
            "validated_unavailable": "This comparison needs the optional package "
                                      "`py-ecg-detectors` (GPL-3.0, deliberately not among the "
                                      "default dependencies). Install it with "
                                      "`pip install -r requirements-validated.txt` — the rest "
                                      "of the app works fully without it.",
        },
        "spectrum": {
            "title": "EEG Spectrum",
            "delta_from_1hz":
                "Delta is computed from **1 Hz**, not from the 0.5 Hz common in the "
                "literature. That is deliberate: below 1 Hz sits the bulk of sweat artifacts, "
                "electrode drift and slow movement, which would otherwise appear as slowing. "
                "The price is that very slow delta is under-measured — worth keeping in mind "
                "when comparing with other systems.",
            "load_file_first": "Please load an EDF file on **File & Patient** first.",
            "no_eeg": "No EEG channels (10-20) detected.",
            "window_start": "Window start (s)",
            "duration": "Duration",
            "duration_help": "Analysis window length from the start",
            "analysis_options": "⚙️ Analysis options",
            "multitaper": "Multitaper method (Thomson 1982)",
            "multitaper_help": "Uses DPSS tapers (NW=3, K=5) instead of Welch. Sharper alpha "
                                "peaks, less spectral leakage. Useful when the alpha peak "
                                "looks broadened in Welch. Somewhat slower on long recordings.",
            "artifact_filter": "Extreme-artifact filter (≥150 µV)",
            "artifact_filter_help": "Epochs with a peak amplitude ≥150 µV are replaced by "
                                     "linear interpolation — only for genuinely extreme "
                                     "artifacts (electrode off, movement). Default: off — the "
                                     "full signal including all physiological phases (eyes "
                                     "open/closed, HV) is analyzed completely.",
            "consensus_panel": "Consensus panel",
            "consensus_panel_sub": "Posterior O1+O2 vs. anterior F3+F4 · ACNS recommendation",
            "consensus_unavailable": "ℹ️ Consensus panel unavailable — missing channels: {list}",
            "asymmetry": "Hemispheric asymmetry",
            "ap_gradient": "Anterior-posterior gradient (PAR)",
            "ap_gradient_sub": "Whole head · whole brain",
            "heavy_calc": "Compute heavy measures (A/P gradient here + LZC complexity further "
                           "down + 1/f-corrected dominant frequency band detection in the FFT "
                           "tiles above)",
            "heavy_calc_help": "All three are computationally heavier (O(N²)/whole-head, or an "
                                "extra 1/f curve fit per derivation). Off by default to keep "
                                "the view fast — enable here when needed; applies to the whole "
                                "page. The 1/f correction fixes a systematic bias toward delta "
                                "in dominant-frequency detection — without it a moderate theta "
                                "rhythm is often wrongly shown as 'delta-dominant'.",
            "heavy_calc_hint": "ℹ️ Computationally heavy — enable the switch above to compute "
                                "the A/P gradient (whole head).",
            "single_channel": "Single-channel analysis",
            "single_channel_sub": "Band power · FFT · clinical ratios per channel",
            "channels_max2": "Channel(s) — max. 2",
            "select_channel": "Please select at least one channel.",
            "reference_epoch": "Reference epoch",
            "reference_epoch_sub": "Internal validation · channel selectable · FFT overlay",
            "ref_channel": "Channel for the reference epoch",
            "ref_channel_help": "Default: O2 (posterior alpha). Pick any available EEG channel.",
            "position_in_recording": "Position in the recording (s)",
            "no_alpha_peak": "No alpha peak detectable.",
            "segment_too_short": "Segment too short for PSD.",
            "appendix": "Appendix — parameters, methods and clinical interpretation",
        },
        "artifact": {
            "title": "Artifact Correction & EEG/ECG Selection",
            "spectral_comparison": "Spectral analysis — total vs. artifact-corrected",
            "no_artifacts_marked": "No artifact segments marked → corrected = total (nothing "
                                    "to remove).",
            "little_clean_eeg": "Only {s:.0f}s of clean EEG — the corrected spectrum is weakly "
                                 "supported.",
            "compare_channel": "Channel for the comparison",
            "segment_too_short": "Segment too short for a stable spectral estimate.",
            "hrv_comparison": "HRV — total vs. artifact-corrected",
            "no_ecg": "No ECG channel identified → HRV comparison not possible. If needed, in the ",
            "too_few_rpeaks": "Too few R peaks on **{ch}** for an HRV analysis.",
            "too_few_clean_rr": "Too few clean RR intervals for the HRV computation.",
            "review_all_channels": "Review view — all channels",
            "montage": "Montage",
            "screen": "Screen",
            "edit_segments": "Artifact segments — edit",
            "reset": "Reset",
            "mark_artifact_again": "↩︎ artifact after all",
            "not_artifact": "not an artifact",
            "delete": "delete",
            "no_artifact_segments": "No artifact segments — the recording runs cleanly through.",
            "add_artifact_range": "Add artifact range (exclude a missed range)",
            "add": "Add",
            "end_after_start": "End must be after start.",
            "detector_settings": "Detector settings — fine-tuning the artifact detection",
            "reset_to_default": "Reset to defaults",
            "overview": "Overview",
            "overview_sub": "Effective mask = auto + your changes · computed live",
            "no_manual_changes": "No manual changes yet — the **auto mask** applies. As soon as "
                                  "you, above in the ",
            "little_clean_warning": "Only **{s:.0f}s** of clean EEG — borderline for stable "
                                     "spectral values ",
            "timeline": "Timeline",
            "timeline_sub": "Red areas = multichannel excursions · shaded = artifact segment",
            "amplitude_distribution": "Amplitude distribution per channel",
            "detail_histogram_channel": "Channel for the detail histogram",
            "all_channels_boxplot": "All channels compared (box plot)",
            "bad_channel_suggestions": "Bad-channel suggestions",
            "bad_channel_sub": "Electrode persistently abnormal",
        },
        "ecg_hrv": {
            "title": "ECG & HRV",
            "coverage_gap_title": "No heartbeat at all was detected in {min} min of the recording",
            "coverage_gap_body":
                "Affected sections: {segments}. All HRV values refer to the remaining sections "
                "only. Possible causes: a detached electrode, amplifier saturation, an "
                "amplitude step from which the detector's adaptive threshold does not recover "
                "— or genuinely absent beats. Please check the raw signal before using these "
                "values.",
            "too_few_beats_segment": "Too few beats in this segment for HRV analysis.",
            "chart_explanation": "Chart explanation",
            "diagnosis_no_channel": "Diagnostics — why was no channel detected?",
            "manual_channel": "Select channel manually",
            "analyzing_channel": "Analyzing channel **{ch}** — please check the ECG trace "
                                  "visually.",
            "too_few_rpeaks": "Too few R peaks detected. Check the channel or the filter.",
            "polarity_check": "Polarity check: show analysis with vs. without correction",
            "spectral_method": "Spectral method for the HRV findings",
            "spectral_method_help": "Welch: classic, robust. Burg/MEM: sharper peaks, stable "
                                     "on shorter segments.",
            "tab_rr": "RR & time domain",
            "tab_freq": "Frequency domain",
            "tab_findings": "HRV findings",
            "tab_hv": "Hyperventilation",
            "no_rpeaks_epoch": "No R peaks detected in this epoch — pick another epoch or "
                                "check the channel.",
            "analysis_window": "Analysis window for time-domain parameters",
            "analysis_window_help": "SDNN and spectral values scale with window length. For "
                                     "comparisons with NeuroFax short-term HRV (3 min), "
                                     "restrict to a 3-minute subwindow.",
            "window_full": "Whole recording",
            "window_first3": "First 3 min",
            "window_stablest3": "Most stable 3 min",
            "window_subwindow": "Subwindow {t0:.0f}–{t1:.0f} s",
            "window_header": "Window {t0:.0f}–{t1:.0f} s",
            "dfa_uncomputable": "ℹ️ DFA α₁ not computable — too few beats (~32 needed).",
            "edr_uncomputable": "ℹ️ EDR not computable — too few/unstable R peaks or the "
                                 "segment is too short.",
            "no_welch": "No Welch spectrum computable (too few RR intervals).",
            "no_burg": "No Burg spectrum computable (too few RR intervals).",
            "parameter_explanations": "Parameter explanations, synonyms & sources",
            "rr_table": "RR table (all beats)",
            "export_excel": "Export HRV results as Excel",
            "create_pdf": "Create PDF report",
            "creating_pdf": "Creating PDF…",
            "download_pdf": "Download PDF",
            "no_hyperventilation": "**No hyperventilation** detected in this recording (no HVT "
                                    "annotations).",
            "hv_manual": "HV manual",
            "adjust": "Adjust",
            "no_hvt_annotations": "No HVT annotations in the EDF — phases set manually.",
            "manual_phases_active": "Manual phase boundaries active — auto-detection overridden.",
            "hvt_start": "HVT start (s)",
            "hvt_end": "HVT end (s)",
            "post_hv_end": "Post-HV end (s)",
            "auto": "↩ Auto",
            "too_few_beats_hvt": "Too few beats in the HVT segment.",
            "too_few_beats_photic": "Too few beats in the photic-stimulation segment.",
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
