# EDF-Analyzer

**English · [Deutsch](README.de.md)**

**A browser-based research and teaching tool for the quantitative analysis of EEG and ECG
recordings in the European Data Format (EDF).** It derives quantitative neurophysiological and
autonomic (HRV) measures from routine recordings — with a strict separation between
established standard methods and literature-validated add-on procedures.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.9-blue)
![Status](https://img.shields.io/badge/status-active%20·%20research%20prototype-orange)

> ⚠️ **Not a medical device, not diagnostic software.** The EDF-Analyzer is a tool for
> research, methodological exploration and teaching. All reported values are **orientation**,
> not diagnostic criteria, and do not replace clinical assessment by a physician.

---

## What it does

You upload an EDF file; the app automatically detects the channel types (EEG/ECG/EOG/…),
computes quantitative markers (EEG spectral analysis, HRV time and frequency domain, aperiodic
component, complexity), and allows an artifact-corrected parallel analysis as well as tabular
and visual reports.

The interface is available in **German and English** (switch in the sidebar). Clinical
parameter names, units and reference values in tables remain in their established form.

## Why it exists

Commercial EEG/ECG systems often report quantitative measures as a black box — the underlying
methodology is rarely transparent, differs between vendors, and is hard to retrace. The
EDF-Analyzer makes the computations **explicit and traceable**: for every procedure it is
documented whether it follows a published gold standard or is a deliberate simplification (see
[Scientific transparency](#scientific-transparency)).

## Quick start

**With Docker (recommended):**

```bash
git clone https://github.com/maximilianhabs/edf-analyzer.git
cd edf-analyzer
docker build -t edf-analyzer .
docker run -p 8501:8501 -e EDF_PASSWORD=yourPassword edf-analyzer
```

**Locally (Python 3.9):**

```bash
pip install -r requirements.txt
EDF_PASSWORD=yourPassword streamlit run app.py
```

`EDF_PASSWORD` is a required environment variable — without it the app refuses to start for
security reasons (no default password in the source code).

**Optional — validated comparison detectors.** The published R-peak detectors (Hamilton 2002,
Pan-Tompkins 1985, …) come from `py-ecg-detectors`, which is **GPL-3.0** while this project is
Apache-2.0. It is therefore not a default dependency, so a standard install stays free of
copyleft. Add it deliberately if you want those comparisons:

```bash
pip install -r requirements-validated.txt
# or for the Docker image:
docker build --build-arg WITH_VALIDATED_DETECTORS=1 -t edf-analyzer .
```

Without it the app runs **in full** — only the comparison detectors are unavailable, and the
UI says so instead of quietly computing something else. The built-in detector is the default
either way.

Then open [http://localhost:8501](http://localhost:8501). The upload expects an EDF file
(max. 200 MB).

## Features

- **Channel identification** — signal-based classifier (EEG/ECG/EOG/EMG/reference/vital) with
  confidence scores and manual correction.
- **EEG spectral analysis** — Welch/multitaper PSD, absolute/relative band power, alpha
  background rhythm, A/P gradient, hemispheric asymmetry.
- **Aperiodic component (1/f)** — own log-log fit plus a validated FOOOF/specparam fit.
- **Rhythm screening** — AFib/ectopy screening upstream of the HRV analysis: artifact
  filtering (Orphanidou 2015), atrial fibrillation detection via CosEn (Lake & Moorman 2011)
  with graded certainty, P-wave detection via beat summation, ectopy detection (compensatory
  pause/QRS width), switchable detectors (own/Hamilton/Christov/Pan-Tompkins/…), automatic
  polarity correction with in-app diagnostics.
- **ECG & HRV** — QRS detection, RR cleaning, time domain (SDNN/RMSSD/pNN50/CV/Poincaré),
  frequency domain (Welch + Burg, Lomb-Scargle), DFA α₁/α₂, autonomic overall-activity warning
  for a "rigid heart rate".
- **Complexity** — sample entropy, Lempel-Ziv, permutation entropy.
- **Artifact correction** — rule-based auto mask plus click-based editing; the total and the
  corrected analysis run in parallel.
- **Reports** — tabular PDF/Excel export (total vs. corrected) and a visual PDF abstract.

## Scientific transparency

The aim is methodological honesty rather than feature marketing. A central registry
(`analysis/methods.py`) classifies **all 22 procedures in use**:

| Status | Count | Meaning |
|---|---|---|
| ✅ validated | 15 | follows a published standard (e.g. Task Force 1996 for HRV, Pan & Tompkins 1985, FOOOF/Donoghue 2020, Nuwer for asymmetry) |
| 🟡 simplified | 6 | working but deliberately simplified variant — labeled as such |
| 🔬 proxy | 1 | exploratory surrogate marker, not clinically established |

Following the **add-on principle**, the established standard methods stay unchanged; for every
simplified default method a validated counterpart exists for direct comparison under "Advanced
Analyses". Nothing is switched over silently.

## Limitations

- **Not clinically validated.** There is (as yet) no prospective validation against
  established reference systems or annotated datasets (e.g. MIT-BIH). Results are exploratory.
- **Artifact detection** is rule-based and conservative, so far tried on few recordings — no
  ICA/autoreject-based correction.
- **HRV frequency domain** requires sufficiently long, stationary segments (Task Force:
  ≥ 5 min); for short recordings it deliberately reports no values.
- **No normative database** — the reference ranges shown are orientation values from the
  literature, not age-/sex-adjusted reference cohorts.

## Privacy

- EDF files are **not part of this repository** and are excluded via `.gitignore` — no patient
  data whatsoever is part of the project.
- On upload the app checks the EDF header for identifying entries; a standalone script
  (`anonymize.py`) can anonymize headers.
- Uploaded files live in a session-specific temp folder and are deleted automatically by a
  cleanup daemon after at most ~4 h.
- **No external connections at runtime.** Fonts are served locally from `static/fonts/`
  (previously loaded from a CDN, which transmitted every visitor's IP address to a third
  party), and Streamlit's usage telemetry is switched off (`gatherUsageStats = false`).
  Verified on 2026-08-11 across six pages: zero requests to external hosts. You can check
  this yourself — open the browser console and run:
  `performance.getEntriesByType('resource').map(r => r.name).filter(n => !n.includes(location.host))`
  — the result should be an empty array. This covers **the application itself**; Streamlit is
  third-party software and a future version could change its behavior, which is why the check
  above is documented rather than a blanket guarantee.
- To anonymize EDF files locally *before* uploading, use the standalone companion tool
  [edf-anonymizer](https://github.com/maximilianhabs/edf-anonymizer) — a dependency-free CLI
  plus optional web UI that runs entirely offline on your own machine.

## Security

Access to the app is password-protected (`EDF_PASSWORD`, required environment variable, see
[Quick start](#quick-start)). Until 2026-08-10 the source code carried a default password as a
fallback in case the variable was missing — a mistake insofar as the repository was being
prepared for public release at the time, which would have made that fallback readable by
anyone. Fixed before the repository went public: no fallback anymore, the app does not start
without the variable set. See [CHANGELOG.md](CHANGELOG.md) for details, and
[SECURITY.md](SECURITY.md) for how to report a security issue (please use a private advisory
rather than a public issue).

## Tech stack

Python 3.9 · Streamlit · MNE · SciPy/NumPy/pandas · pyedflib · FOOOF · reportlab/openpyxl.
Full list in [`requirements.txt`](requirements.txt); the optional, GPL-licensed comparison
detectors live in [`requirements-validated.txt`](requirements-validated.txt). Third-party
licences are listed in [NOTICE](NOTICE).

## Project status & responsibility

An actively developed research project with a single author and maintainer. **Scientific and
content responsibility** — choice of methods, assessment, testing — lies with **Maximilian
Habs** (consultant neurologist). Parts of the code were written with AI assistance; review and
approval are done manually by the author.

Please report bugs and suggestions via
[Issues](https://github.com/maximilianhabs/edf-analyzer/issues).

## Self-hosting

The app is an ordinary Streamlit application and runs anywhere Docker is available. Behind a
reverse proxy (nginx, Caddy, Traefik) two things matter:

- **Pass through the WebSocket upgrade** — Streamlit needs it, otherwise the page hangs while
  loading.
- **Set `EDF_PASSWORD` as an environment variable** (see [Quick start](#quick-start)); without
  it the app will not start.

If you expose the app publicly, put TLS in front of it and — depending on your use case —
restrict access at the network level. Anyone processing personal recordings is themselves
responsible for compliance; see [Privacy](#privacy).

## License

[Apache License 2.0](LICENSE) © 2026 Maximilian Habs.

## More

[Changelog](CHANGELOG.md) · [Security policy](SECURITY.md)
