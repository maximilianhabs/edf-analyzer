"""
Design-Tokens — zentrale Quelle für Farben/Typografie/Radien, sowohl für CSS (core/shared.py
::apply_global_style()) als auch für Python-seitige Verwendung (Plotly-Diagramme, matplotlib/
Glory-Report, wo CSS-Variablen nicht gelesen werden können).

Konzept (Phase 0 des GUI-Redesigns, User-Vorgabe 2026-08-08): gedämpfte, "Apple-artige" Basis-
Palette (ein Akzentton statt Regenbogen-Emojis, neutrale Grautöne, kontinuierliche Ecken-Radien)
statt der bisherigen, über ~10 Dateien verstreuten Ad-hoc-Hex-Werte. Klinische Statusfarben
(Rot/Grün/Orange/Blau für pathologisch/normal/grenzwertig/info) bleiben fachlich reserviert und
werden hier nur auf JE EINEN kanonischen Wert konsolidiert (vorher z. B. 3 verschiedene Blau-Töne
parallel im Umlauf), nicht in ihrer Bedeutung verändert.

WICHTIG: Dies ist nur das FUNDAMENT (Phase 0) — die eigentliche Migration der ~10 Seiten auf
diese Tokens ist Gegenstand der folgenden Phasen (siehe [[project_edf_ui_redesign]]). Bestehende
Ad-hoc-Farben in views/*.py sind NICHT rückwirkend geändert, nur neu entstehender Code sollte ab
sofort diese Konstanten verwenden.
"""

# ── Neutrale Basis-Palette (Apple-artig: reines Weiß/Off-White, near-black Text) ──────────────
BG = "#ffffff"
BG_SUBTLE = "#f5f5f7"          # Apple-typisches Off-White für Sektions-/Card-Hintergründe
SURFACE = "#ffffff"            # Karten-Hintergrund auf BG_SUBTLE
BORDER = "rgba(0,0,0,0.08)"
TEXT_PRIMARY = "#1d1d1f"       # Apple near-black (ersetzt das bisherige #1c2833)
TEXT_SECONDARY = "#86868b"     # Apple-Grau — exakt wie im Referenz-Prompt spezifiziert

# ── EIN Akzentton (ersetzt bisherige uneinheitliche Blau-Variationen) ──────────────────────────
ACCENT = "#0071e3"             # Apple Blue (primaryColor in .streamlit/config.toml gespiegelt)
ACCENT_HOVER = "#0077ed"

# ── Klinische Statusfarben — konsolidiert auf JE EINEN kanonischen Wert ────────────────────────
# (vorher parallel im Umlauf: Rot #c0392b/#e74c3c, Grün #27ae60/#2ecc71, Orange #e67e22/#f39c12,
# Blau #2471a3/#1a5276/#5b8fc7 — Bedeutung unverändert, nur EIN Hex-Wert pro Bedeutung ab jetzt)
DANGER = "#c0392b"             # pathologisch / Artefakt / AFib-Verdacht
WARNING = "#e67e22"            # grenzwertig / auffällig
SUCCESS = "#27ae60"            # normal / unauffällig
INFO = "#2471a3"               # neutral-informativ (kein Befund, nur Hinweis)

# ── Radius-Skala ("continuous corners", Apple-typisch großzügiger als Standard-Bootstrap) ──────
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 24

# ── Typografie-Skala (Streamlit-Kontext, nicht die 64-80px Marketing-Hero-Größe des
# Referenz-Prompts — auf App-Seitentitel herunterskaliert) ────────────────────────────────────
FONT_EYEBROW_PX = 13
FONT_HERO_PX = 34
FONT_SUBTITLE_PX = 17
FONT_BODY_PX = 15

# ── Spacing-Skala (px) ──────────────────────────────────────────────────────────────────────
SPACE = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 64}

# ── Schriften ───────────────────────────────────────────────────────────────────────────────
# EINZIGE Quelle für die Icon-Schrift. Vorher stand der Name an drei Stellen einzeln im Code
# (core/shared.py, core/auth.py, views/channel_report.py). Beim Wechsel von „Outlined" auf
# „Rounded" wurde eine davon übersehen, weil sie den Namen anders schreibt als die CSS-Klasse
# — die Folge war kein Fehler, sondern der Ligaturname als Klartext im Kopf jeder Kanalzeile
# („neurology" statt des Gehirn-Symbols). Solche Fehler sind unsichtbar für Tests und fallen
# nur beim Hinsehen auf, deshalb: nur noch von hier importieren, nie neu hinschreiben.
#
# „Rounded" ist bewusst gewählt: diese Variante liefert STREAMLIT bereits lokal mit. Damit
# braucht es keine eigene Schriftdatei und keinen CDN-Zugriff (siehe NOTICE). Ein Wechsel auf
# eine andere Variante würde eine eigene Datei unter static/fonts/ erfordern.
ICON_FONT = "Material Symbols Rounded"
ICON_FONT_CSS = f"'{ICON_FONT}'"   # fertig gequotet für font-family in CSS
