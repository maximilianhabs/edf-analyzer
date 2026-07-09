"""
Nichtlineare Komplexitäts-/Entropiemaße für Biosignale.

Aktuell: Sample Entropy (Richman & Moorman 2000). Reserviert für spätere
Erweiterungen (Permutations-Entropie, Lempel-Ziv, Multiscale Entropy).

Sample Entropy (SampEn) misst die **Vorhersagbarkeit/Regelmäßigkeit** eines Signals:
Wie wahrscheinlich bleiben zwei ähnliche Muster der Länge m auch bei Länge m+1 ähnlich?
- niedrige SampEn → regelmäßig/vorhersagbar (weniger Komplexität)
- hohe SampEn   → komplex/unvorhersagbar

Klinisch sinkt die Komplexität typischerweise bei Müdigkeit, Sedierung, Delir,
Demenz und Bewusstseinsstörungen. Bereits ein einzelner Kanal genügt.
"""

from __future__ import annotations

import numpy as np


def sample_entropy(x: np.ndarray, m: int = 2, r: float | None = None,
                   max_n: int = 4000) -> float:
    """Sample Entropy = −ln(A/B).

    B = Anzahl Musterpaare der Länge m mit Chebyshev-Distanz ≤ r,
    A = dieselben Paare, die auch bei Länge m+1 noch ≤ r sind (Selbstvergleiche ausgeschlossen).

    Parameter
    ---------
    m:      Einbettungsdimension (Standard 2)
    r:      Toleranz; Standard 0.2 × Standardabweichung des Signals
    max_n:  Sicherheits-Cap gegen O(N²)-Explosion (zusammenhängendes Mittensegment)

    Rückgabe: float (nan bei zu kurzem Signal / keine Treffer).
    """
    x = np.asarray(x, dtype=float)
    N = len(x)
    if N > max_n:                       # zentrales Segment nehmen (Dynamik erhalten)
        start = (N - max_n) // 2
        x = x[start:start + max_n]
        N = max_n
    if N < m + 2:
        return float("nan")
    if r is None:
        r = 0.2 * float(np.std(x))
    if r <= 0:
        return float("nan")

    def _count(mm: int) -> int:
        M = N - mm + 1
        # Template-Matrix (M × mm)
        templ = np.lib.stride_tricks.sliding_window_view(x, mm)  # (N-mm+1, mm)
        total = 0
        for i in range(M):
            d = np.max(np.abs(templ - templ[i]), axis=1)
            total += int(np.count_nonzero(d <= r)) - 1  # Selbstvergleich abziehen
        return total

    B = _count(m)
    A = _count(m + 1)
    if B <= 0 or A <= 0:
        return float("nan")
    return float(-np.log(A / B))


# ── Lempel-Ziv-Komplexität (LZC) ────────────────────────────────────────────────

def _lz76(seq) -> int:
    """Lempel-Ziv-1976-Komplexität c(n) einer binären Sequenz (kanonische Variante)."""
    n = len(seq)
    i, c, l = 0, 1, 1
    k, k_max = 1, 1
    while True:
        if seq[i + k - 1] == seq[l + k - 1]:
            k += 1
            if l + k > n:
                c += 1
                break
        else:
            if k > k_max:
                k_max = k
            i += 1
            if i == l:
                c += 1
                l += k_max
                if l + 1 > n:
                    break
                i = 0
                k = 1
                k_max = 1
            else:
                k = 1
    return c


def _phase_randomize(x: np.ndarray, rng) -> np.ndarray:
    """Phasen-randomisiertes Surrogat: erhält das Leistungsspektrum, randomisiert die Phase."""
    n = len(x)
    X = np.fft.rfft(x)
    mag = np.abs(X)
    ph = np.angle(X)
    rand = rng.uniform(-np.pi, np.pi, len(ph))
    rand[0] = ph[0]                      # DC-Phase erhalten
    if n % 2 == 0:
        rand[-1] = ph[-1]               # Nyquist erhalten
    return np.fft.irfft(mag * np.exp(1j * rand), n=n)


def lziv_complexity(signal: np.ndarray, fs: float, seg_sec: float = 5.0,
                    n_surrogates: int = 20, max_segments: int = 8,
                    ds_hz: float = 128.0, seed: int = 0) -> dict:
    """Normalisierte Lempel-Ziv-Komplexität des EEG (Maschke 2025, Schartner 2015/17).

    Pro 5-s-Segment: Signal am Mittelwert binarisiert → LZ76-Komplexität, normalisiert auf
    zwei Arten (über Segmente gemittelt):
      - **shuffle**: c(x) / mean(c(zufällig gemischte Binärsequenz)) → ~0..1, hoch = komplex
      - **phase**:   c(x) / mean(c(phasen-randomisiertes Surrogat)) → >1 = komplexer als das
        Spektrum allein erwarten lässt (spektral-unabhängige Komplexität), <1 = weniger.

    Performance-Parameter (n_surrogates, max_segments, ds_hz) halten die reine Python-O(N²)-
    Berechnung interaktiv; leichtes Downsampling auf ds_hz vor der Binarisierung.

    Rückgabe: dict(shuffle, phase) — nan bei zu kurzem Signal.
    """
    x = np.asarray(signal, dtype=float)
    if fs > ds_hz and ds_hz > 0:                       # leichtes Downsampling
        step = max(1, int(round(fs / ds_hz)))
        x = x[::step]
        fs = fs / step
    seg = int(seg_sec * fs)
    if seg < 32 or len(x) < seg:
        return {"shuffle": float("nan"), "phase": float("nan")}

    starts = list(range(0, len(x) - seg + 1, seg))
    if len(starts) > max_segments:
        idx = np.linspace(0, len(starts) - 1, max_segments).astype(int)
        starts = [starts[i] for i in idx]

    rng = np.random.default_rng(seed)
    sh_vals, ph_vals = [], []
    for s in starts:
        xw = x[s:s + seg]
        b = (xw > xw.mean()).astype(np.int8)
        c0 = _lz76(b)
        sh = []
        for _ in range(n_surrogates):
            bs = b.copy(); rng.shuffle(bs)
            sh.append(_lz76(bs))
        ph = []
        for _ in range(n_surrogates):
            xs = _phase_randomize(xw, rng)
            ph.append(_lz76((xs > xs.mean()).astype(np.int8)))
        sh_m = float(np.mean(sh)) or 1e-9
        ph_m = float(np.mean(ph)) or 1e-9
        sh_vals.append(c0 / sh_m)
        ph_vals.append(c0 / ph_m)

    return {"shuffle": float(np.mean(sh_vals)), "phase": float(np.mean(ph_vals))}
