# LAM+ Core QC

Quality Control Protocol for Avaatech XRF Core Scanner

Developed at **LAM+** — Laboratório de Análise Multiespectral e Inteligência Artificial para Sedimentos  
Universidade Federal Fluminense (UFF)

---

## Overview

This tool implements a multi-module QC pipeline for XRF core scanner data produced by the Avaatech system. It provides an interactive web interface for uploading raw scan data, running automated quality control checks, visualizing diagnostics, and downloading the annotated output. It supports both single-energy files and **multi-energy workbooks** (separate 10 kV/30 kV/50 kV tabs), each processed and displayed independently.

## Validation Status

This pipeline must be validated internally by the LAM+ team — cross-checked against known reference cores and manually-reviewed datasets — **before being used to QC data from external clients**. The thresholds, weights, and default module configuration described in this document reflect engineering decisions made during development; they have not yet been validated against an independent ground-truth dataset.

The pipeline has been run end-to-end against several real multi-energy core files beyond the bundled example (see `data/` and `TODO.md` for the per-file QF distributions and any warnings raised). This confirms the pipeline runs cleanly on real data of varying size and structure — it is not, by itself, the ground-truth validation described above.

## Modules

| Module | Method | Target |
|--------|--------|--------|
| QC1 | Robust z-score | Throughput, combined with the Argon peak (Ar-Kα) when present — 10 kV mode only |
| QC2 | Robust z-score | Coherent scatter (Rh-Lα at 10 kV, Rh-Kα-Coh at 30 kV; not measured at 50 kV) |
| QC3 | Robust z-score | Incoherent scatter (Rh-Lα-Inc at 10 kV, Rh-Kα-Inc at 30 kV; not measured at 50 kV) |
| QC4 | Rolling mean deviation | Energy-dependent variable set (Throughput, Argon, coherent/incoherent scatter — whichever the energy measures) |
| QC5 | Mean RPD | Replicate measurements |
| QC6 | PCA + Mahalanobis distance | Multivariate geochemistry |

Each module contributes to a weighted **Quality Index (QI)** and a **Quality Flag (QF)** per measurement point. A module a given energy doesn't measure (e.g. QC2/QC3 at 50 kV) is scored neutrally and excluded from the QI weighting for that sheet, rather than being flagged as missing data. Configurable exceptions: QC4's variable set (default: the energy's incoherent-scatter variable only), QC4's temporal persistence requirement (default off), QC6's inclusion in QI/QF (default excluded, diagnostic-only), and the QF assignment rule itself (default: weighted QI; opt-in: non-compensatory module-count, see "QF Modes" below).

### About QC1 (Instrument Stability) and Argon

Throughput reflects the detector's total count rate. In **10 kV mode**, the file also carries the Argon peak (Ar-Kα area), which reflects the quality of the atmosphere between tube, sample, and detector (helium loss, air ingress, sealing issues) — a problem there can degrade the measurement without necessarily showing up in Throughput, and vice-versa. QC1 combines both into a single `Instrument_z` value per point (the **worse** of the two z-scores, not an average), so either failure mode is caught. When Argon isn't present in the file (30/50 kV, or any file that simply lacks the column), QC1 falls back transparently to Throughput alone.

### About QC4 (Rolling QC)

Throughput, Argon, and coherent/incoherent scatter are not chemical concentrations — they are **instrumental/physical indicators** of the measurement itself. Coherent and incoherent scatter are the Rayleigh and Compton scatter of the X-ray tube's own anode line off the sample surface (Rh-Lα/Rh-Lα-Inc at 10 kV, Rh-Kα-Coh/Rh-Kα-Inc at 30 kV — see "Multi-Energy Support" below).

**By default**, QC4 considers only the energy's **incoherent-scatter** variable: it is the actual spectral signal measured at that point, whereas Throughput, coherent scatter, and Argon are secondary instrumental parameters that describe the measurement conditions rather than the spectral data itself. (At 50 kV, where neither scatter variable is measured, QC4 falls back to whatever instrumental variable is available — in practice, Throughput.)

The sidebar also has a checkbox to **combine all available variables** instead. A physical measurement issue (a crack, an air gap, a dry/wet transition, detector drift) tends to disturb **at least one** of them simultaneously, since all depend on the same measurement geometry/matrix at that point. When enabled, QC4 takes the **largest** absolute rolling z-score (`|delta_z|`) among the available variables — rather than the mean, which would dilute a real, localized disturbance that may only show up strongly in one of them — at the cost of also reacting to instrumental drift that isn't necessarily reflected in the spectral signal itself.

A separate sidebar checkbox adds a **temporal persistence requirement** (opt-in, default off): by default, a single point with an isolated drift deviation above the threshold is enough to trigger the QC4 criterion ("defense in depth" — a real, isolated problem shouldn't be masked just because its neighbors look fine). When enabled, a drift anomaly is only kept if it appears in at least 2 consecutive points or 2 points within a window of 3 measurements — isolated single-point deviations are treated as statistical noise and suppressed, reducing false positives at the cost of potentially missing a genuinely isolated one-point issue.

### About QC6 (PCA)

PCA (QC6) is an **exploratory diagnostic module**, not an automated-flagging criterion by default. It is always calculated and shown in the PCA tab — projecting the available trace elements (`ELEMENTS_PCA`) onto two principal components and computing the Mahalanobis distance of each measurement to the group center — regardless of any setting.

**By default**, PCA does **not** contribute to the QI or QF: it stays purely visual/exploratory, useful for spotting geochemical groupings or multivariate anomalies without those observations driving automated rejection. A sidebar checkbox lets PCA be included in the QF criterion instead — re-adding its 5% QI weight and a direct Mahalanobis-distance threshold check (QF=2/3 on multivariate outliers) — for users who want multivariate anomalies to also drive automated flagging.

## Multi-Energy Support

Avaatech workbooks can export separate tabs per X-ray tube energy — 10 kV, 30 kV, and/or 50 kV — each measuring a different subset of parameters (e.g. only 10 kV measures Argon; 30 kV measures coherent/incoherent scatter under different column names; 50 kV measures neither scatter variable, only Throughput and trace elements). The app detects the energy of each tab from its name and processes every tab independently: a tab/energy selector appears whenever a workbook has more than one processable sheet, and a module a given energy doesn't measure is scored neutrally and excluded from that sheet's QI weighting rather than being treated as missing data. The downloaded `.xlsx` contains one sheet per processed energy, each preserving its original columns and cell coloring. Single-sheet files whose tab name doesn't follow the energy-naming convention are still processed normally (assumed 10 kV).

## QF Modes

Two ways to turn the individual module scores into a final Quality Flag are available, selectable via a sidebar checkbox:

- **Weighted QI (default)**: QF thresholds are derived from a continuous, weighted Quality Index — a very good module can partially compensate for a weaker one, alongside a few direct per-module z-score/Mahalanobis criteria (see `compute_flags` in `qc_core.py`).
- **Module count (opt-in)**: each QC module is classified into an OK/ALERT/CRITICAL state using its own thresholds, and QF is a non-compensatory function of how many modules alert/fail (QF1 = 1 ALERT, QF2 = 2–3 ALERTs or 1 CRITICAL, QF3 = 2+ CRITICALs or 4+ ALERTs) — more transparent, but a single bad module can't be offset by the rest.

In both modes, a row missing critical input data is always flagged as indeterminate (QF=ND), never silently treated as OK.

## Excel Export

The downloaded `.xlsx` mirrors the app's cell-level color coding (green/yellow/red for OK/Attention/Suspect-Rejected) on every QC column added by the pipeline, leaving the original Avaatech columns untouched. For multi-energy files, each processed energy gets its own sheet in the same workbook, under its original tab name.

## Roadmap (planned — not yet implemented)

- **PCA biplot and clustering**: the PCA tab currently shows a PC1/PC2 scatter colored by Mahalanobis distance. Planned additions: loading vectors (biplot) showing which elements drive each principal component, and clustering (e.g. k-means) to group measurements geochemically. Purely visual/exploratory, same as the rest of QC6 — not tied to QF.
- **AI-based gap filling for isolated QF=3 measurements**: for isolated rejected points (a single QF=3 measurement surrounded by otherwise acceptable data, not part of a larger problem interval — see `report_pdf.detect_intervals`), a future module could estimate a plausible replacement value from neighboring valid measurements, rather than leaving a gap or naively interpolating. Suggested methods-section text:

  > *"Isolated QF=3 measurements (rejected points not part of a contiguous problem interval) were estimated using [model] trained on neighboring valid measurements within a depth window of ±N mm, with [predictor variables] as features. Estimated values are explicitly flagged as imputed and are not used to validate the model itself, which was assessed via leave-one-out cross-validation against known-good measurements."*

  Any such replacement must always be clearly flagged as imputed/estimated, never indistinguishable from a real measurement, and should only ever apply to truly isolated single points — not to multi-point problem intervals.
- **Core image integration**: align core-scan photographs (e.g. line-scan camera images, typically captured alongside the XRF scan) by depth, so QC flags and problem intervals can be visually cross-checked against the physical appearance of the core (cracks, lithological changes, color banding) — in both the Streamlit app and the PDF report.
- **Full XRF processor (future umbrella)**: longer-term, this QC pipeline could become one stage of a broader XRF data processing tool covering calibration, unit conversion, multi-core stitching, and export to standard paleoclimate/sedimentology data formats, with this QC module as its quality-gating step.

## Files

- `qc_core.py` — QC pipeline (importable module, no Streamlit dependency)
- `qc_avaatech.py` — Streamlit frontend
- `report_pdf.py` — PDF report generation (partial — currently produces a "problem intervals" summary page; not yet wired into the Streamlit UI)
- `i18n.py` / `locales/pt.json` / `locales/en.json` — bilingual (PT/EN) text loader; PT is the default language
- `requirements.txt` — Python dependencies
- `installer/` — PyInstaller packaging (standalone executable), see below

## Usage

```bash
streamlit run qc_avaatech.py
```

See `INSTALL.md` for environment setup instructions.

## Standalone Executable

The app can be packaged as a standalone executable (no Python/`.venv`
required on the target machine) via [PyInstaller](https://pyinstaller.org/).
Build scripts and the spec file live in `installer/`; full build
instructions and known caveats are in `installer/README_BUILD.md`.

```bash
# Windows
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe installer\build_exe.py

# Ubuntu
.venv/bin/python -m pip install pyinstaller
.venv/bin/python installer/build_exe.py
```

Tested end-to-end on Windows (2026-06-29): the build completes, the
generated executable launches the Streamlit server correctly, and it
responds on `localhost:8501`. Not yet tested on Ubuntu — PyInstaller does
not cross-build, so each platform must generate its own executable.

**The generated executable is never committed to this repository**
(`installer/dist/` and `installer/build/` are gitignored). Distribute the
built binary via **GitHub Releases**, not via git.

## Developers

- **[Igor Venancio](https://github.com/oliveiraimvp)** - LAM+, UFF
- **[Andre L. Belem](https://github.com/andrebelem)** - [O2](https://observatoriooceanografico.org), LAM+, UFF
- **[FRIDAY](https://observatoriooceanografico.org/pessoas/friday-bot/)** - [O2](https://observatoriooceanografico.org), UFF

---

*Created by A. L. Belem & FRIDAY*
