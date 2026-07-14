"""W0 — Methoden-Transparenz: zentrale Registry aller Analyseverfahren mit Referenz und
Reifegrad. Macht sichtbar, wo wir den Goldstandard nutzen und wo (noch) vereinfacht.

Reifegrad:
  ✅ validiert          — publizierter/akzeptierter Standard-Algorithmus
  🟡 Standard, vereinf. — akzeptierte Methode, aber vereinfachte Umsetzung
  🔬 Forschungs-Proxy   — orientierend, (noch) keine validierte Norm/Implementierung
"""

VALIDATED = "✅ validiert"
SIMPLIFIED = "🟡 Standard, vereinfacht"
PROXY = "🔬 Forschungs-Proxy"

# (Bereich, Parameter, Verfahren, Referenz, Reifegrad)
METHODS = [
    ("EKG", "R-Zacken-Detektion", "eigener Pan-Tompkins (BP 5–15 Hz → diff → square → 150-ms-Integration → adaptive Schwelle → ±40-ms-Refinement)",
     "Pan & Tompkins 1985", SIMPLIFIED),
    ("EKG", "R-Zacken (validierte Option, W1)", "Hamilton-Detektor (py-ecg-detectors) + Maximum-Refinement",
     "Hamilton 2002; Howell & Porr 2019", VALIDATED),
    ("HRV Zeit", "SDNN, RMSSD, pNN50, pNN20, CV, NN50", "Standarddefinitionen auf bereinigter RR-Reihe",
     "Task Force 1996", VALIDATED),
    ("HRV Zeit", "Poincaré SD1/SD2", "SD1=√½·SDSD, SD2=√(2·SDNN²−½·SDSD²)", "Brennan 2001", VALIDATED),
    ("HRV nichtlin.", "DFA α₁ (Default)", "Peng-DFA, nicht überlappende Fenster 4–16; nur α₁",
     "Peng 1995", SIMPLIFIED),
    ("HRV nichtlin.", "DFA α₁+α₂ (Add-on, G6)", "Standard-DFA: überlappende Fenster (50 %), α₁ (4–16) + α₂ (16–64) — Seite Erweiterte Analysen",
     "Peng 1995", VALIDATED),
    ("HRV nichtlin.", "Sample Entropy", "m=2, r=0,2·SD, zentrales Segment ≤4000 Punkte (innerhalb der empfohlenen N-Spanne)", "Richman & Moorman 2000", VALIDATED),
    ("HRV Freq.", "VLF/LF/HF/Total, LFnu/HFnu", "PCHIP-Resample 4 Hz → Welch & Burg(16); Bänder VLF 0,0033–0,04 / LF 0,04–0,15 / HF 0,15–0,40 Hz; nu = LF/(LF+HF) — Task-Force-konform verifiziert",
     "Task Force 1996", VALIDATED),
    ("HRV Freq.", "Lomb-Scargle (Add-on, W3)", "interpolationsfreies Periodogramm direkt aus RR-Zeitpunkten — auf Seite Erweiterte Analysen",
     "Laguna 1998; Moody 1993", VALIDATED),
    ("EEG Spektrum", "Bandpower / rel. Power", "Welch (4 s, Hann, 50 %) bzw. Multitaper (DPSS); Trapez-Integral",
     "Welch 1967; Thomson 1982", VALIDATED),
    ("EEG Spektrum", "Alpha-Peak (CoG, Default)", "Schwerpunkt im 8–13-Hz-Band nach linearer 1/f-Baseline",
     "Klimesch 1999", SIMPLIFIED),
    ("EEG Spektrum", "Alpha-Peak aperiodik-bereinigt (Add-on, G2)", "FOOOF-Gipfel-Mittenfrequenz — echt vom 1/f-Untergrund getrennt",
     "Donoghue 2020", VALIDATED),
    ("EEG Spektrum", "Multitaper-Vergleich (Add-on, G7)", "DPSS NW=3/K=5 gegen Welch — weniger Leakage, schärfere Gipfel",
     "Thomson 1982", VALIDATED),
    ("EEG Spektrum", "SEF95 / Medianfrequenz", "kumulative Leistung, lineare Bin-Interpolation",
     "Drummond 1991", VALIDATED),
    ("EEG Aperiodik", "1/f-Exponent (1–20/1–40 Hz)", "eigener Sigma-Clip-Log-Log-Fit, **kein Knee**, keine parametr. Gipfel",
     "Donoghue 2020 (FOOOF)", SIMPLIFIED),
    ("EEG Aperiodik", "FOOOF/specparam (Add-on, W2)", "Referenz-Implementierung mit Knee-Option + Gipfel CF/PW/BW — auf Seite Erweiterte Analysen",
     "Donoghue 2020", VALIDATED),
    ("EEG Komplex.", "LZC (shuffle/phase)", "LZ76, am Median binarisiert, 20 Surrogate, ds 128 Hz, ≤8 Segmente",
     "Lempel & Ziv 1976; Schartner 2015", SIMPLIFIED),
    ("EEG", "Asymmetrie-Index (Default)", "AI=(L−R)/(L+R)×100 auf absoluter Bandpower",
     "Nuwer 1997", SIMPLIFIED),
    ("EEG", "Asymmetrie relativ (Add-on, G1)", "AI auf relativer Bandpower — robuster gegen Impedanz/Amplitude",
     "Nuwer 1997", VALIDATED),
    ("EEG Komplex.", "Permutationsentropie (G3)", "Ordinale Muster, m=3, normalisiert",
     "Bandt & Pompe 2002", VALIDATED),
    ("EEG", "Anterior-Posterior-Gradient (PAR)", "geom. Mittel posteriore/anteriore abs. Alpha-Power",
     "Colombo 2023; Maschke 2025", VALIDATED),
    ("Artefakt", "Artefakt-Markierung", "ptp vs. Eigen-Baseline (Median) + Multikanal-Konsens + EKG-Bestätigung",
     "regelbasiert (hausintern), validiert an 2 Aufnahmen", PROXY),
]
