"""Zentrale Registry aller Analyseverfahren — mit Referenz, Umsetzungstreue und **belegtem**
Validierungsgrad.

Warum diese Datei 2026-08-12 umgebaut wurde
-------------------------------------------
Die alte Fassung führte einen einzigen Reifegrad mit dem Wert „✅ validiert", definiert als
„publizierter/akzeptierter Standard-Algorithmus". Das ist **literaturbasiert** — es sagt aus,
dass das Verfahren einer publizierten Vorschrift folgt, nicht dass *diese* Implementierung
gegen etwas geprüft wurde. Das Etikett „validiert" behauptet aber genau Letzteres. Ein
externes Review hat den Widerspruch zu Recht als Kernproblem des Transparenzversprechens
benannt: er saß mitten in dem Teil des Projekts, der Ehrlichkeit verspricht.

Zwei Konsequenzen:

1. **Zwei getrennte Achsen statt einer.** Vorher steckten in einem Feld zwei verschiedene
   Aussagen: „wie gut ist das Verfahren belegt?" und „wie treu ist unsere Umsetzung?".
   „🟡 Standard, vereinfacht" beschrieb die zweite Frage, „✅ validiert" die erste — sie
   waren nie vergleichbar. Jetzt: `level` (Belegstufe) und `fidelity` (Umsetzungstreue).
2. **Eine Stufe über literaturbasiert hinaus muss man sich verdienen.** `IMPLEMENTATION`
   darf nur setzen, wer ein `Evidence`-Objekt mitliefert: Datensatz, geprüfte Größe,
   Toleranz, Test. Ohne Beleg kein Etikett — das erzwingt `tools/check_methods.py`.

Der Ausgangszustand war deshalb bewusst **22 literaturbasiert, 0 implementierungsvalidiert**.
Anschließend (2026-08-12) sind die Sollwerte der synthetischen Fixtures und die analytisch
bekannten Werte in die Tests gewandert; jede Methode, die ihren Sollwert trifft, steht jetzt
mit Beleg auf `implementation-validated`. Stand: **18 implementierungsvalidiert,
4 literaturbasiert, 0 klinisch validiert.**

Die vier verbliebenen sind kein Versehen, sondern das Ergebnis:

  * **Hamilton & Co. (validierte Option)** — auf der Fixture brechen Hamilton und
    Pan-Tompkins nach einem Amplitudensprung ab und verlieren ein Drittel der Schläge, ohne
    einen Fehler zu melden. Ein Verfahren, das im Test durchfällt, bekommt kein Etikett.
  * **Alpha-Peak aus FOOOF (G2)** — die Fixture enthält reine Sinus-Linien, an denen FOOOF
    konstruktionsbedingt scheitert; für den Nachweis fehlt ein Testsignal mit breitem Gipfel.
  * **Asymmetrie relativ (G1)** und **PAR** — die Fixture legt für beide kein Zahlenniveau
    fest. Ein selbst gesetzter Sollwert wäre keine Validierung, sondern ihr Gegenteil.

Wer eine Methode hochstuft, liefert den Beleg mit; `tools/check_methods.py` prüft, dass die
genannten Tests und Datensätze wirklich existieren.
"""

from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Achse 1 — Belegstufe: WORAUF stützt sich die Aussage, dass das Verfahren stimmt?
# ---------------------------------------------------------------------------

#: Das Verfahren folgt einer publizierten Vorschrift. Über *diese* Implementierung sagt das
#: nichts aus — sie wurde nicht gegen bekannte Sollwerte geprüft. Ehrliche Ausgangsstufe.
LITERATURE = "literature-based"

#: Die Implementierung liefert auf einem Datensatz mit bekannter Wahrheit die erwarteten Werte
#: innerhalb einer festgelegten Toleranz. Nur mit `Evidence` zulässig.
IMPLEMENTATION = "implementation-validated"

#: Gegen einen klinischen Referenzstandard oder eine annotierte Datenbank geprüft
#: (z. B. MIT-BIH), mit Kennzahlen wie Sensitivität/PPV. Derzeit für kein Verfahren erreicht.
CLINICAL = "clinically-validated"

LEVELS = (LITERATURE, IMPLEMENTATION, CLINICAL)

#: Anzeige-Etiketten. Bewusst ohne das Wort „validiert" auf der untersten Stufe.
LEVEL_LABEL = {
    LITERATURE: "📖 literaturbasiert",
    IMPLEMENTATION: "✅ implementierungsvalidiert",
    CLINICAL: "🏥 klinisch validiert",
}

LEVEL_LABEL_EN = {
    LITERATURE: "📖 literature-based",
    IMPLEMENTATION: "✅ implementation-validated",
    CLINICAL: "🏥 clinically validated",
}

# ---------------------------------------------------------------------------
# Achse 2 — Umsetzungstreue: WIE NAH ist unsere Umsetzung an der Vorschrift?
# ---------------------------------------------------------------------------

FULL = "full"            # folgt der Vorschrift vollständig
SIMPLIFIED = "simplified"  # akzeptierte Methode, bewusst vereinfachte Umsetzung
PROXY = "proxy"          # orientierender Ersatzmarker ohne etablierte Norm

FIDELITIES = (FULL, SIMPLIFIED, PROXY)

FIDELITY_LABEL = {
    FULL: "vollständig",
    SIMPLIFIED: "🟡 vereinfacht",
    PROXY: "🔬 Proxy",
}

FIDELITY_LABEL_EN = {
    FULL: "full",
    SIMPLIFIED: "🟡 simplified",
    PROXY: "🔬 proxy",
}


@dataclass(frozen=True)
class Evidence:
    """Der Beleg für eine Stufe oberhalb von `LITERATURE`.

    Ohne diese Angaben ist „validiert" eine Behauptung. Mit ihnen kann jemand die Prüfung
    nachvollziehen und wiederholen — das ist der ganze Zweck.
    """
    dataset: str      # woran geprüft, z. B. "tests/fixtures/test_edf_datei.edf"
    checked: str      # welche Größe, z. B. "Alpha-Peak O1/O2"
    expected: str     # Sollwert samt Herkunft, z. B. "10,0 Hz (Manifest)"
    tolerance: str    # zulässige Abweichung, z. B. "±0,3 Hz"
    test: str         # der Test, der es prüft, z. B. "tests/test_eeg_groundtruth.py::…"


@dataclass(frozen=True)
class Method:
    domain: str
    parameter: str
    procedure: str
    reference: str
    fidelity: str
    level: str = LITERATURE
    evidence: Optional[Evidence] = None
    limitations: str = ""

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"unbekannte Belegstufe: {self.level!r}")
        if self.fidelity not in FIDELITIES:
            raise ValueError(f"unbekannte Umsetzungstreue: {self.fidelity!r}")
        # Die eine Regel, um die es hier geht: kein Etikett ohne Beleg.
        if self.level != LITERATURE and self.evidence is None:
            raise ValueError(
                f"'{self.parameter}': Stufe {self.level} ohne Evidence — genau das war der "
                f"Fehler der alten Registry. Beleg mitliefern oder auf {LITERATURE} lassen.")

    def level_label(self, lang: str = "de") -> str:
        return (LEVEL_LABEL_EN if lang == "en" else LEVEL_LABEL)[self.level]

    def fidelity_label(self, lang: str = "de") -> str:
        return (FIDELITY_LABEL_EN if lang == "en" else FIDELITY_LABEL)[self.fidelity]


# Kurzschreibweisen für die beiden wiederkehrenden Datensätze.
FIXTURE = "tests/fixtures/test_edf_datei.edf (synthetisch, Sollwerte im Manifest)"
ANALYTIC = "rechnerisch erzeugte Reihen mit exakt bekanntem Sollwert"

T_EEG = "tests/test_eeg_groundtruth.py"
T_ANA = "tests/test_analytic_groundtruth.py"
T_ECG = "tests/test_ecg_pipeline.py"


METHODS: List[Method] = [
    Method("EKG", "R-Zacken-Detektion",
           "eigener Pan-Tompkins (BP 5–15 Hz → diff → square → 150-ms-Integration → adaptive "
           "Schwelle → ±40-ms-Refinement)",
           "Pan & Tompkins 1985", SIMPLIFIED, IMPLEMENTATION,
           Evidence(FIXTURE, "Anzahl R-Zacken über 10 min", "702 Schläge (Manifest)",
                    "−7 %/+2 %", f"{T_ECG}::test_ekg_kennwerte_treffen_die_sollwerte"),
           limitations="Die Untergrenze der Toleranz ist begründet: die Fixture enthält "
                       "absichtlich ein Schwachsignal-Fenster (330–345 s, 5 % Amplitude), in "
                       "dem 17 Schläge verloren gehen. Deckt den Amplitudensprung bei "
                       "400–410 s ohne Aussetzer ab — anders als Hamilton/Pan-Tompkins aus "
                       "py-ecg-detectors, siehe dort."),
    Method("EKG", "R-Zacken (validierte Option, W1)",
           "Hamilton-Detektor (py-ecg-detectors) + Maximum-Refinement",
           "Hamilton 2002; Howell & Porr 2019", FULL,
           limitations="BEWUSST nicht implementierungsvalidiert. Auf der Fixture brechen "
                       "Hamilton und Pan-Tompkins nach dem Amplitudensprung bei 400–410 s "
                       "vollständig ab (letzter Schlag 409 s, 462 statt 702). Seit 2026-08-12 "
                       "meldet die App das über die Abdeckungsprüfung — vorher lief es "
                       "unbemerkt durch; Engzee liefert ohne vorherige Polaritätskorrektur nur "
                       "7 Schläge. Nachgewiesen ist die Schlagzahl nur für Christov und "
                       "Two-Average. Festgehalten in "
                       f"{T_ECG}::test_hamilton_und_pan_tompkins_brechen_nach_dem_"
                       "amplitudensprung_ab."),
    Method("HRV Zeit", "SDNN, RMSSD, pNN50, pNN20, CV, NN50",
           "Standarddefinitionen auf bereinigter RR-Reihe", "Task Force 1996", FULL,
           IMPLEMENTATION,
           Evidence(ANALYTIC, "SDNN und mittlere HF einer sinusförmig modulierten RR-Reihe",
                    "SDNN = A/√2 = 42,43 ms; HF = 70,0 min⁻¹", "±1,0 ms bzw. ±0,2 min⁻¹",
                    f"{T_ANA}::test_hrv_zeitdomaene_gegen_analytische_werte"),
           limitations="Die Funktion gibt alle Werte auf 0,1 ms gerundet zurück; wer daraus "
                       "weiterrechnet, erbt bei kleiner Variabilität einige Prozent Fehler."),
    Method("HRV Zeit", "Poincaré SD1/SD2",
           "SD1=√½·SDSD, SD2=√(2·SDNN²−½·SDSD²)", "Brennan 2001", FULL, IMPLEMENTATION,
           Evidence(ANALYTIC, "definierende Identität SD1² + SD2² = 2·SDNN²",
                    "exakte Gleichheit", "aus der 0,1-ms-Rundung hergeleitet",
                    f"{T_ANA}::test_poincare_erfuellt_die_definierende_identitaet")),
    Method("HRV nichtlin.", "DFA α₁ (Default)",
           "Peng-DFA, nicht überlappende Fenster 4–16; nur α₁", "Peng 1995", SIMPLIFIED,
           IMPLEMENTATION,
           Evidence(ANALYTIC, "DFA-Exponent auf großen Skalen",
                    "0,5 (unkorreliertes Rauschen), 1,0 (1/f)", "±0,05 bzw. ±0,15",
                    f"{T_ANA}::test_dfa_konvergiert_auf_grossen_skalen_gegen_die_theorie"),
           limitations="Auf dem klinischen α₁-Fenster (Skalen 4–16) liegt der Wert für "
                       "unkorreliertes Rauschen bei 0,584 statt 0,5 — der bekannte "
                       "Kleinskalen-Versatz der DFA, kein Rechenfehler (derselbe Code trifft "
                       "auf Skalen 16–256 die Theorie). α₁-Werte sind untereinander "
                       "vergleichbar, aber nicht gegen 0,5 als Normwert zu lesen."),
    Method("HRV nichtlin.", "DFA α₁+α₂ (Add-on, G6)",
           "Standard-DFA: überlappende Fenster (50 %), α₁ (4–16) + α₂ (16–64) — Seite "
           "Erweiterte Analysen", "Peng 1995", FULL, IMPLEMENTATION,
           Evidence(ANALYTIC, "DFA-Exponent auf großen Skalen",
                    "0,5 (unkorreliertes Rauschen), 1,0 (1/f)", "±0,05 bzw. ±0,15",
                    f"{T_ANA}::test_dfa_konvergiert_auf_grossen_skalen_gegen_die_theorie"),
           limitations="Gleicher Kleinskalen-Versatz im α₁-Fenster wie beim Default."),
    Method("HRV nichtlin.", "Sample Entropy",
           "m=2, r=0,2·SD, zentrales Segment ≤4000 Punkte (innerhalb der empfohlenen N-Spanne)",
           "Richman & Moorman 2000", FULL, IMPLEMENTATION,
           Evidence(ANALYTIC, "SampEn von gaußschem weissem Rauschen bzw. reinem Sinus",
                    "≈2,2 (Richman & Moorman) bzw. ≪1", "2,0–2,4 bzw. <0,5",
                    f"{T_ANA}::test_sample_entropy_gegen_publizierten_richtwert")),
    Method("HRV Freq.", "VLF/LF/HF/Total, LFnu/HFnu",
           "PCHIP-Resample 4 Hz → Welch & Burg(16); Bänder VLF 0,0033–0,04 / LF 0,04–0,15 / "
           "HF 0,15–0,40 Hz; nu = LF/(LF+HF)", "Task Force 1996", FULL, IMPLEMENTATION,
           Evidence(FIXTURE, "HF-Peak der eingebauten RSA-Modulation", "0,25 Hz (Manifest)",
                    "±0,02 Hz", f"{T_ECG}::test_ekg_kennwerte_treffen_die_sollwerte"),
           limitations="Belegt ist die Frequenzlage, nicht die absolute ms²-Kalibrierung der "
                       "Bandleistungen."),
    Method("HRV Freq.", "Lomb-Scargle (Add-on, W3)",
           "interpolationsfreies Periodogramm direkt aus RR-Zeitpunkten — auf Seite "
           "Erweiterte Analysen", "Laguna 1998; Moody 1993", FULL, IMPLEMENTATION,
           Evidence(FIXTURE, "HF-Peak und HF>LF ohne jedes Resampling", "0,25 Hz (Manifest)",
                    "±0,02 Hz", f"{T_ECG}::test_lomb_scargle_findet_denselben_hf_peak")),
    Method("EEG Spektrum", "Bandpower / rel. Power",
           "Welch (4 s, Hann, 50 %) bzw. Multitaper (DPSS); Trapez-Integral",
           "Welch 1967; Thomson 1982", FULL, IMPLEMENTATION,
           Evidence(FIXTURE, "Bandintegral über das Alpha-Band, links/rechts verglichen",
                    "aus den Kanalamplituden 33,0/27,5 µV berechnete 18,03 %", "±1,0 %-Punkte",
                    f"{T_EEG}::test_asymmetrie_index_trifft_den_eingebauten_wert"),
           limitations="Belegt sind Bandintegral und Bandverhältnisse. Die ABSOLUTE "
                       "Kalibrierung in µV²/Hz ist damit nicht geprüft — der Nachweis läuft "
                       "über ein Verhältnis, in dem ein gemeinsamer Skalenfehler herausfiele. "
                       "**Delta beginnt bei 1 Hz, nicht bei den literaturüblichen 0,5 Hz** — "
                       "bewusste Entscheidung: unter 1 Hz liegt der Gipfel von Schwitz- und "
                       "Driftartefakten. Preis: rund 47 % der wahren 0,5–4-Hz-Delta-Leistung "
                       "werden nicht erfasst, eine Umstellung würde Delta um 121 % anheben. "
                       "Begründung und Messung in docs/PREPROCESSING.md."),
    Method("EEG Spektrum", "Alpha-Peak (CoG, Default)",
           "Schwerpunkt im 8–13-Hz-Band nach linearer 1/f-Baseline", "Klimesch 1999",
           SIMPLIFIED, IMPLEMENTATION,
           Evidence(FIXTURE, "Alpha-Peak auf allen 19 EEG-Kanälen", "10,0 Hz (Manifest)",
                    "±0,3 Hz", f"{T_EEG}::test_alpha_peak_cog_auf_allen_kanaelen"),
           limitations="Auch die frontalen Kanäle mit nur 3 µV Alpha werden getroffen; ein "
                       "Signal ohne echten Alpha-Gipfel ist damit nicht abgedeckt."),
    Method("EEG Spektrum", "Alpha-Peak aperiodik-bereinigt (Add-on, G2)",
           "FOOOF-Gipfel-Mittenfrequenz — echt vom 1/f-Untergrund getrennt",
           "Donoghue 2020", FULL,
           limitations="Geprüft ist bisher nur der FOOOF-EXPONENT, nicht die Mittenfrequenz "
                       "der Gipfel. Für einen Nachweis braucht es ein Testsignal mit einem "
                       "realistisch BREITEN Gipfel — die Fixture enthält reine Sinus-Linien, "
                       "die FOOOF konstruktionsbedingt nicht modellieren kann."),
    Method("EEG Spektrum", "Multitaper-Vergleich (Add-on, G7)",
           "DPSS NW=3/K=5 gegen Welch — weniger Leakage, schärfere Gipfel",
           "Thomson 1982", FULL, IMPLEMENTATION,
           Evidence(FIXTURE, "Alpha-Peak aus dem Multitaper-Spektrum, gegen Welch",
                    "10,0 Hz (Manifest), beide Schätzer einig", "±0,3 Hz bzw. ±0,1 Hz",
                    f"{T_EEG}::test_alpha_peak_multitaper_stimmt_mit_welch_ueberein")),
    Method("EEG Spektrum", "SEF95 / Medianfrequenz",
           "kumulative Leistung, lineare Bin-Interpolation", "Drummond 1991", FULL,
           IMPLEMENTATION,
           Evidence(ANALYTIC, "Edge-Frequenz eines flachen Spektrums über 1–41 Hz",
                    "1 + p·40 Hz, also 21,0 (Median) und 39,0 (SEF95)", "±0,15 Hz",
                    f"{T_ANA}::test_spektrale_edge_frequenz_auf_flachem_spektrum")),
    Method("EEG Aperiodik", "1/f-Exponent (1–20/1–40 Hz)",
           "eigener Sigma-Clip-Log-Log-Fit, **kein Knee**, keine parametr. Gipfel",
           "Donoghue 2020 (FOOOF)", SIMPLIFIED, IMPLEMENTATION,
           Evidence(f"{ANALYTIC}; zusätzlich {FIXTURE}",
                    "Exponent dreier Potenzgesetz-Reihen und aller 19 Fixture-Kanäle",
                    "1,0 / 1,5 / 2,2 bzw. 2,2", "±0,05 analytisch, ±0,15 je Kanal",
                    f"{T_ANA}::test_eigener_aperiodik_fit_trifft_bekannten_exponenten"),
           limitations="Der Sigma-Clip lässt einen Rest schmalbandiger Linien durch: über die "
                       "19 Fixture-Kanäle streut der Exponent mit SD 0,038 gegenüber 0,017 "
                       "bei linienfreien Kontrollreihen, schwach negativ mit der "
                       "Alpha-Amplitude korreliert (r = −0,37). Der Mittelwert bleibt "
                       "unverzerrt. Oberhalb ~25 Hz ist die Fixture wegen des "
                       "Quantisierungsbodens der EDF-Datei keine 1/f-Wahrheit mehr, deshalb "
                       "wird dort über 1–20 Hz gefittet."),
    Method("EEG Aperiodik", "FOOOF/specparam (Add-on, W2)",
           "Referenz-Implementierung mit Knee-Option + Gipfel CF/PW/BW — auf Seite "
           "Erweiterte Analysen", "Donoghue 2020", FULL, IMPLEMENTATION,
           Evidence(ANALYTIC, "Exponent dreier Potenzgesetz-Reihen ohne Gipfel",
                    "1,0 / 1,5 / 2,2", "±0,05",
                    f"{T_ANA}::test_fooof_trifft_bekannten_exponenten"),
           limitations="Bei SCHMALBANDIGEN Linien (Netzbrumm, reine Sinus) unterschätzt FOOOF "
                       "den Exponenten deutlich — auf der Fixture 1,74 statt 2,2 bei R²=0,80, "
                       "während der eigene Fit 2,20 trifft. Ursache ist die untere Grenze von "
                       "`peak_width_limits` (1 Hz): eine spektrale Linie lässt sich nicht als "
                       "Gaußgipfel modellieren und landet im aperiodischen Anteil. Bei "
                       "realistisch breiten Gipfeln tritt der Effekt nicht auf."),
    Method("EEG Komplex.", "LZC (shuffle/phase)",
           "LZ76, am Median binarisiert, 20 Surrogate, ds 128 Hz, ≤8 Segmente",
           "Lempel & Ziv 1976; Schartner 2015", SIMPLIFIED, IMPLEMENTATION,
           Evidence(ANALYTIC, "shuffle-normalisierte LZC von weissem Rauschen und Sinus",
                    "≈1,0 bzw. deutlich darunter", "±0,1 bzw. <0,6",
                    f"{T_ANA}::test_lempel_ziv_komplexitaet_gegen_die_extremfaelle"),
           limitations="Nur die shuffle-Normierung ist belegt. Die phase-Normierung kann bei "
                       "schmalbandigen Signalen über 1 hinausgehen (für einen reinen Sinus "
                       "≈3,8), weil das phasenrandomisierte Surrogat dann selbst fast "
                       "periodisch ist — eine Eigenschaft der Normierung, kein Rechenfehler."),
    Method("EEG", "Asymmetrie-Index (Default)",
           "AI=(L−R)/(L+R)×100 auf absoluter Bandpower", "Nuwer 1997", SIMPLIFIED,
           IMPLEMENTATION,
           Evidence(FIXTURE, "Alpha-Asymmetrie O1 gegen O2",
                    "18,03 %, aus 33,0/27,5 µV berechnet (AI wirkt auf die Leistung)",
                    "±1,0 %-Punkte",
                    f"{T_EEG}::test_asymmetrie_index_trifft_den_eingebauten_wert")),
    Method("EEG", "Asymmetrie relativ (Add-on, G1)",
           "AI auf relativer Bandpower — robuster gegen Impedanz/Amplitude",
           "Nuwer 1997", FULL,
           limitations="Kein eigener Nachweis: die Fixture legt nur die absoluten "
                       "Alpha-Amplituden fest, nicht die Gesamtleistung je Kanal, aus der "
                       "sich ein Sollwert für die relative Variante ergäbe."),
    Method("EEG Komplex.", "Permutationsentropie (G3)",
           "Ordinale Muster, m=3, normalisiert", "Bandt & Pompe 2002", FULL, IMPLEMENTATION,
           Evidence(ANALYTIC, "normalisierte PE von weissem Rauschen und reinem Sinus",
                    "1,0 (alle Ordinalmuster gleich häufig) bzw. deutlich darunter",
                    "±0,01 bzw. <0,7",
                    f"{T_ANA}::test_permutationsentropie_gegen_die_beiden_extremfaelle")),
    Method("EEG", "Anterior-Posterior-Gradient (PAR)",
           "geom. Mittel posteriore/anteriore abs. Alpha-Power",
           "Colombo 2023; Maschke 2025", FULL,
           limitations="Bewusst nur richtungsgeprüft (posterior ≫ anterior). Die Fixture legt "
                       "kein Zahlenniveau für den PAR fest; ein selbst gesetzter Sollwert "
                       "wäre keine Validierung. Zudem junge Kennzahl aus der "
                       "Bewusstseinsforschung ohne breite Normdatenbasis."),
    Method("Artefakt", "Artefakt-Markierung",
           "ptp vs. Eigen-Baseline (Median) + Multikanal-Konsens + EKG-Bestätigung",
           "regelbasiert (hausintern)", PROXY, IMPLEMENTATION,
           Evidence(FIXTURE, "Zeitliche Lage des eingebauten Bursts und Anteil sauberer Zeit",
                    "Burst 240–245 s auf 6 Kanälen; Rest artefaktfrei konstruiert",
                    "Treffer ±2 s, sauberer Anteil > 90 %",
                    f"{T_EEG}::test_artefakt_burst_wird_zeitlich_getroffen"),
           limitations="Ein einzelnes, sehr deutliches Ereignis (300 µV) in einer sonst "
                       "sauberen Datei. Schwache oder einkanalige Artefakte und die "
                       "Falsch-Positiv-Rate auf echten Aufnahmen sind damit nicht geprüft; "
                       "kalibriert wurde an zwei Routineaufnahmen."),
]


def count_by_level() -> dict:
    """Zählung je Belegstufe — Grundlage für die README-Tabelle und deren Test."""
    return {lvl: sum(1 for m in METHODS if m.level == lvl) for lvl in LEVELS}


def count_by_fidelity() -> dict:
    return {f: sum(1 for m in METHODS if m.fidelity == f) for f in FIDELITIES}
