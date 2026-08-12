"""Strukturprüfung einer hochgeladenen EDF-Datei, bevor die Analyse sie anfasst.

Bisher prüfte der Upload nur die Dateiendung (`type=["edf"]`) und die Größe (200 MB). Alles
Weitere fiel erst auf, wenn MNE beim Laden stolperte — mit einem Stacktrace statt einer
Erklärung. Die realistische Ursache ist dabei fast nie ein Angreifer, sondern der Alltag:
eine umbenannte Datei, ein abgebrochener Export, eine Aufnahme mit 12 Sekunden Dauer, ein
Netzwerk-Kopiervorgang, der nach der Hälfte abbrach.

Der EDF-Header hat ein festes Format: 256 Byte mit Feldern an bekannten Bytepositionen,
danach je Signal weitere 256 Byte. Daraus lässt sich in Millisekunden feststellen, ob eine
Datei überhaupt eine EDF ist und ob ihre Angaben zur tatsächlichen Dateigröße passen — ohne
sie zu laden. Genau das macht dieses Modul.

Zwei Stufen, bewusst getrennt:

* **Fehler** (`ok = False`) — die Datei ist nicht verwendbar. Ablehnen, nicht laden.
* **Warnungen** — die Datei ist ladbar, aber etwas daran ist ungewöhnlich (sehr kurz, sehr
  niedrige Abtastrate). Der Nutzer soll es wissen und trotzdem entscheiden dürfen; die
  Analyse ist ein Forschungswerkzeug, kein Torwächter.

Gibt es einen Grund abzulehnen, dann steht im Text, **was** nicht stimmt und **was zu tun
ist** — nicht „ungültige Datei".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

#: Feste Bytepositionen des EDF-Hauptheaders (EDF/EDF+-Spezifikation, Kemp 1992/2003).
_HEADER = {
    "version": (0, 8),
    "patient_id": (8, 88),
    "recording_id": (88, 168),
    "startdate": (168, 176),
    "starttime": (176, 184),
    "header_bytes": (184, 192),
    "reserved": (192, 236),
    "num_records": (236, 244),
    "duration": (244, 252),
    "num_signals": (252, 256),
}

MAIN_HEADER_BYTES = 256
PER_SIGNAL_HEADER_BYTES = 256

#: Unterhalb dieser Dauer ist keine der Kennzahlen sinnvoll — die Frequenzanalyse braucht
#: mehrere Epochen à 4 s, die Artefaktbaseline einen Median über die Aufnahme.
MIN_DURATION_S = 10.0

#: Warnschwelle: die HRV-Frequenzdomäne verlangt nach Task Force 1996 mindestens 5 Minuten.
SHORT_DURATION_S = 300.0

#: Unter dieser Abtastrate ist ein EEG-Spektrum bis 30 Hz nicht mehr sauber darstellbar
#: (Nyquist 30 Hz → 60 Hz, plus Reserve für den Antialiasing-Übergang).
MIN_SFREQ_HZ = 100.0


# ── Meldungen ───────────────────────────────────────────────────────────────────────────────
# Bewusst hier und nicht in `core/i18n.py`: dieses Modul soll ohne Streamlit importierbar
# bleiben (es wird auch von Tests und vom CLI-Weg benutzt). Der Preis ist ein zweiter
# Übersetzungsort — `tools/check_i18n.py` prüft ihn deshalb mit.
_MSG = {
    "too_small": (
        "Die Datei ist mit {size} Byte kleiner als ein EDF-Header (256 Byte) — sie ist leer "
        "oder der Upload wurde abgebrochen. Bitte erneut hochladen.",
        "At {size} bytes the file is smaller than an EDF header (256 bytes) — it is empty or "
        "the upload was interrupted. Please upload it again."),
    "unreadable": (
        "Datei nicht lesbar: {exc}",
        "File cannot be read: {exc}"),
    "is_bdf": (
        "Das sieht nach einer BDF-Datei aus (BioSemi), nicht nach EDF. Sie lässt sich mit "
        "gängigen Werkzeugen nach EDF konvertieren.",
        "This looks like a BDF file (BioSemi), not EDF. Common tools can convert it to EDF."),
    "not_edf": (
        "Der Dateikopf entspricht keinem EDF-Format. Häufigste Ursache: die Datei wurde nur "
        "umbenannt oder stammt aus einem anderen Aufnahmesystem.",
        "The file header is not EDF. Most common cause: the file was merely renamed, or it "
        "comes from a different recording system."),
    "header_broken": (
        "Der EDF-Header ist beschädigt: {exc}. Die Datei ist vermutlich unvollständig "
        "übertragen worden.",
        "The EDF header is damaged: {exc}. The file was probably transferred incompletely."),
    "no_signals": (
        "Der Header nennt kein einziges Signal.",
        "The header declares no signals at all."),
    "bad_record_duration": (
        "Die angegebene Blockdauer ist {dur} s — daraus lässt sich keine Zeitachse bilden.",
        "The declared record duration is {dur} s — no time axis can be derived from that."),
    "header_length_mismatch": (
        "Die Headerlänge passt nicht zur Signalzahl: angegeben {got} Byte, für {n} Signale "
        "wären {want} Byte nötig.",
        "Header length does not match the signal count: {got} bytes declared, {want} bytes "
        "needed for {n} signals."),
    "shorter_than_header": (
        "Die Datei ist kürzer als ihr eigener Header ({size} statt mindestens {want} Byte) — "
        "der Upload ist unvollständig.",
        "The file is shorter than its own header ({size} instead of at least {want} bytes) — "
        "the upload is incomplete."),
    "signal_headers_broken": (
        "Die Signal-Kopfdaten sind unvollständig — die Datei ist beschädigt.",
        "The per-signal headers are incomplete — the file is damaged."),
    "truncated": (
        "Die Datei enthält weniger Daten, als ihr Header ankündigt: {have:.0f} von {want} "
        "Blöcken. Sie wurde unvollständig übertragen — bitte erneut hochladen.",
        "The file holds less data than its header announces: {have:.0f} of {want} records. "
        "It was transferred incompletely — please upload it again."),
    "unknown_length": (
        "Der Header gibt die Aufnahmelänge nicht an (Anzahl Datenblöcke = −1); sie wurde aus "
        "der Dateigröße abgeleitet.",
        "The header does not state the recording length (record count = −1); it was derived "
        "from the file size."),
    "too_short": (
        "Die Aufnahme ist nur {dur:.1f} s lang. Unter {min:.0f} s lässt sich keine der "
        "Kennzahlen sinnvoll berechnen — die Spektralanalyse braucht mehrere "
        "4-Sekunden-Epochen.",
        "The recording is only {dur:.1f} s long. Below {min:.0f} s none of the measures can "
        "be computed meaningfully — the spectral analysis needs several 4-second epochs."),
    "short_for_hrv": (
        "Die Aufnahme ist mit {min_len:.1f} min kürzer als 5 Minuten. Die HRV-Frequenzdomäne "
        "(Task Force 1996) verlangt längere Abschnitte und bleibt deshalb möglicherweise leer.",
        "At {min_len:.1f} min the recording is shorter than 5 minutes. The HRV frequency "
        "domain (Task Force 1996) requires longer segments and may therefore stay empty."),
    "low_sfreq": (
        "Die höchste Abtastrate der Datei beträgt {fs:.0f} Hz. Für ein EEG-Spektrum bis 30 Hz "
        "sind mindestens {min_fs:.0f} Hz empfohlen; höhere Frequenzanteile fehlen bzw. sind "
        "unsicher.",
        "The highest sampling rate in the file is {fs:.0f} Hz. An EEG spectrum up to 30 Hz "
        "wants at least {min_fs:.0f} Hz; higher frequency content is missing or unreliable."),
}


def msg(code: str, lang: str = "de", **kw) -> str:
    de, en = _MSG[code]
    return (en if lang == "en" else de).format(**kw)


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def message(self) -> str:
        return " ".join(self.errors) if self.errors else ""


def _int(raw: bytes, span, feld: str) -> int:
    """EDF speichert Zahlen als ASCII in fester Feldbreite — leer bzw. Unsinn kommt vor."""
    text = raw[span[0]:span[1]].decode("latin1", errors="replace").strip()
    if not text:
        raise ValueError(f"Feld '{feld}' im EDF-Header ist leer")
    try:
        return int(float(text))
    except ValueError:
        raise ValueError(f"Feld '{feld}' im EDF-Header ist keine Zahl: {text!r}")


def validate_edf(path: str, lang: str = "de") -> ValidationResult:
    """Prüft Struktur und Plausibilität einer EDF-Datei allein anhand ihrer Header."""
    def m(code, **kw):
        return msg(code, lang, **kw)
    res = ValidationResult(ok=True)

    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return ValidationResult(False, [msg("unreadable", lang, exc=exc)])

    if size < MAIN_HEADER_BYTES:
        return ValidationResult(False, [m("too_small", size=size)])

    with open(path, "rb") as fh:
        raw = fh.read(MAIN_HEADER_BYTES)

    # ── 1. Ist es überhaupt eine EDF? ────────────────────────────────────────────────────
    # Das Versionsfeld ist "0" plus Leerzeichen. EDF+ und BDF weichen ab; BDF beginnt mit
    # 0xFF + "BIOSEMI" und wird hier ausdrücklich benannt, weil das eine häufige und leicht
    # zu verwechselnde Nachbardatei ist.
    version = raw[_HEADER["version"][0]:_HEADER["version"][1]]
    if version[:1] == b"\xff":
        return ValidationResult(False, [m("is_bdf")])
    if version.decode("latin1", errors="replace").strip() not in ("0",):
        return ValidationResult(False, [m("not_edf")])

    # ── 2. Sind die Kopfangaben in sich schlüssig? ───────────────────────────────────────
    try:
        n_signals = _int(raw, _HEADER["num_signals"], "Anzahl Signale")
        n_records = _int(raw, _HEADER["num_records"], "Anzahl Datenblöcke")
        header_bytes = _int(raw, _HEADER["header_bytes"], "Headerlänge")
        rec_dur_text = raw[_HEADER["duration"][0]:_HEADER["duration"][1]].decode(
            "latin1", errors="replace").strip()
        rec_dur = float(rec_dur_text)
    except (ValueError, TypeError) as exc:
        return ValidationResult(False, [m("header_broken", exc=exc)])

    if n_signals <= 0:
        return ValidationResult(False, [m("no_signals")])
    if rec_dur <= 0:
        return ValidationResult(False, [m("bad_record_duration", dur=rec_dur)])

    erwartet_header = MAIN_HEADER_BYTES + n_signals * PER_SIGNAL_HEADER_BYTES
    if header_bytes != erwartet_header:
        return ValidationResult(False, [m("header_length_mismatch", got=header_bytes,
                                          n=n_signals, want=erwartet_header)])
    if size < header_bytes:
        return ValidationResult(False, [m("shorter_than_header", size=size,
                                          want=header_bytes)])

    # ── 3. Passt die Dateigröße zu den angekündigten Daten? ──────────────────────────────
    # Der klassische Fall eines abgebrochenen Kopiervorgangs: Header vollständig, Daten
    # abgeschnitten. MNE liest so eine Datei teilweise klaglos und liefert eine zu kurze
    # Aufnahme — die Analyse rechnet dann auf einem Bruchstück, ohne dass es jemand merkt.
    with open(path, "rb") as fh:
        fh.seek(MAIN_HEADER_BYTES)
        sig_header = fh.read(n_signals * PER_SIGNAL_HEADER_BYTES)
    samples_pro_block = _lies_samples_pro_block(sig_header, n_signals)
    if samples_pro_block is None:
        return ValidationResult(False, [m("signal_headers_broken")])

    bytes_pro_block = 2 * sum(samples_pro_block)   # EDF: 2 Byte je Sample (16 Bit)
    daten_bytes = size - header_bytes

    if n_records == -1:
        # Laut Standard erlaubt (Dauer unbekannt) — dann aus der Dateigröße herleiten.
        n_records = daten_bytes // bytes_pro_block if bytes_pro_block else 0
        res.warnings.append(m("unknown_length"))
    elif bytes_pro_block and daten_bytes < n_records * bytes_pro_block:
        vorhanden = daten_bytes / bytes_pro_block if bytes_pro_block else 0
        return ValidationResult(False, [m("truncated", have=vorhanden, want=n_records)])

    dauer_s = n_records * rec_dur
    sfreqs = [s / rec_dur for s in samples_pro_block if s > 0]
    max_sfreq = max(sfreqs) if sfreqs else 0.0

    res.info = {
        "n_signals": n_signals,
        "duration_s": dauer_s,
        "record_duration_s": rec_dur,
        "max_sfreq_hz": max_sfreq,
        "size_bytes": size,
    }

    # ── 4. Plausibilität — Warnungen, keine Ablehnung ────────────────────────────────────
    if dauer_s < MIN_DURATION_S:
        res.ok = False
        res.errors.append(m("too_short", dur=dauer_s, min=MIN_DURATION_S))
    elif dauer_s < SHORT_DURATION_S:
        res.warnings.append(m("short_for_hrv", min_len=dauer_s / 60))

    if max_sfreq and max_sfreq < MIN_SFREQ_HZ:
        res.warnings.append(m("low_sfreq", fs=max_sfreq, min_fs=MIN_SFREQ_HZ))

    return res


def _lies_samples_pro_block(sig_header: bytes, n_signals: int):
    """Samples je Datenblock aus den Signal-Kopfdaten.

    Aufbau: alle Felder liegen blockweise hintereinander (erst alle Labels, dann alle
    Transducer, …), NICHT signalweise. Die Sample-Zahl ist das siebte Feld — davor liegen
    Label (16), Transducer (80), Dimension (8), physical min/max (je 8), digital min/max
    (je 8) und Prefiltering (80), jeweils mal `n_signals`.
    """
    versatz = n_signals * (16 + 80 + 8 + 8 + 8 + 8 + 8 + 80)
    if len(sig_header) < versatz + n_signals * 8:
        return None
    werte = []
    for i in range(n_signals):
        text = sig_header[versatz + i * 8: versatz + (i + 1) * 8].decode(
            "latin1", errors="replace").strip()
        try:
            werte.append(int(float(text)))
        except ValueError:
            return None
    return werte
