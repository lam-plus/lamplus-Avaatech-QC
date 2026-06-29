# LAM+ Core QC

Quality Control Protocol for Avaatech XRF Core Scanner

Developed at **LAM+** — Laboratório de Análise Multiespectral e Inteligência Artificial para Sedimentos  
Universidade Federal Fluminense (UFF)

---

## Overview

This tool implements a multi-module QC pipeline for XRF core scanner data produced by the Avaatech system. It provides an interactive web interface for uploading raw scan data, running automated quality control checks, visualizing diagnostics, and downloading the annotated output.

## Validation Status

This pipeline must be validated internally by the LAM+ team — cross-checked against known reference cores and manually-reviewed datasets (starting with the example file in `data/`) — **before being used to QC data from external clients**. The thresholds, weights, and default module configuration described in this document reflect engineering decisions made during development; they have not yet been validated against an independent ground-truth dataset.

## Modules

| Module | Method | Target |
|--------|--------|--------|
| QC1 | Robust z-score | Throughput |
| QC2 | Robust z-score | Rh-Lα |
| QC3 | Robust z-score | Rh-Lα-Inc |
| QC4 | Rolling mean deviation | Throughput, Rh-Lα, Rh-Lα-Inc |
| QC5 | Mean RPD | Replicate measurements |
| QC6 | PCA + Mahalanobis distance | Multivariate geochemistry |

Each module contributes to a weighted **Quality Index (QI)** and a **Quality Flag (QF)** per measurement point, with two configurable exceptions described below: QC4's variable set (default Rh-Lα-Inc only) and QC6's inclusion in QI/QF (default excluded, diagnostic-only).

### About QC4 (Rolling QC)

Throughput, Rh-Lα, and Rh-Lα-Inc are not chemical concentrations — they are **instrumental/physical indicators** of the measurement itself. Throughput is the detector's total count rate; Rh-Lα and Rh-Lα-Inc are the coherent (Rayleigh) and incoherent (Compton) scatter of the X-ray tube's own Rhodium anode line off the sample surface.

**By default**, QC4 considers only **Rh-Lα-Inc**: it is the actual spectral signal measured at that point, whereas Throughput and Rh-Lα are secondary instrumental parameters that describe the measurement conditions rather than the spectral data itself.

The sidebar also has a checkbox to **combine all three variables** instead. A physical measurement issue (a crack, an air gap, a dry/wet transition, detector drift) tends to disturb **at least one** of the three simultaneously, since all depend on the same measurement geometry/matrix at that point. When enabled, QC4 takes the **largest** absolute rolling z-score (`|delta_z|`) among the three — rather than the mean, which would dilute a real, localized disturbance that may only show up strongly in one of them — at the cost of also reacting to instrumental drift that isn't necessarily reflected in the spectral signal itself.

### About QC6 (PCA)

PCA (QC6) is an **exploratory diagnostic module**, not an automated-flagging criterion by default. It is always calculated and shown in the PCA tab — projecting the available trace elements (`ELEMENTS_PCA`) onto two principal components and computing the Mahalanobis distance of each measurement to the group center — regardless of any setting.

**By default**, PCA does **not** contribute to the QI or QF: it stays purely visual/exploratory, useful for spotting geochemical groupings or multivariate anomalies without those observations driving automated rejection. A sidebar checkbox lets PCA be included in the QF criterion instead — re-adding its 5% QI weight and a direct Mahalanobis-distance threshold check (QF=2/3 on multivariate outliers) — for users who want multivariate anomalies to also drive automated flagging.

## Roadmap (planned — not yet implemented)

- **PCA biplot and clustering**: the PCA tab currently shows a PC1/PC2 scatter colored by Mahalanobis distance. Planned additions: loading vectors (biplot) showing which elements drive each principal component, and clustering (e.g. k-means) to group measurements geochemically. Purely visual/exploratory, same as the rest of QC6 — not tied to QF.
- **QF mode selector**: QF is currently computed by a single rule (weighted QI thresholds combined with per-module z-score/Mahalanobis criteria — see `compute_flags` in `qc_core.py`). A planned alternative mode would compute QF from a simple count of failed modules instead of the weighted QI, as a more transparent, less compensatory criterion. The current weighted-QI mode would remain the default; the module-count mode would be opt-in.
- **AI-based gap filling for isolated QF=3 measurements**: for isolated rejected points (a single QF=3 measurement surrounded by otherwise acceptable data, not part of a larger problem interval — see `report_pdf.detect_intervals`), a future module could estimate a plausible replacement value from neighboring valid measurements, rather than leaving a gap or naively interpolating. Suggested methods-section text:

  > *"Isolated QF=3 measurements (rejected points not part of a contiguous problem interval) were estimated using [model] trained on neighboring valid measurements within a depth window of ±N mm, with [predictor variables] as features. Estimated values are explicitly flagged as imputed and are not used to validate the model itself, which was assessed via leave-one-out cross-validation against known-good measurements."*

  Any such replacement must always be clearly flagged as imputed/estimated, never indistinguishable from a real measurement, and should only ever apply to truly isolated single points — not to multi-point problem intervals.
- **Core image integration**: align core-scan photographs (e.g. line-scan camera images, typically captured alongside the XRF scan) by depth, so QC flags and problem intervals can be visually cross-checked against the physical appearance of the core (cracks, lithological changes, color banding) — in both the Streamlit app and the PDF report.
- **Full XRF processor (future umbrella)**: longer-term, this QC pipeline could become one stage of a broader XRF data processing tool covering calibration, unit conversion, multi-core stitching, and export to standard paleoclimate/sedimentology data formats, with this QC module as its quality-gating step.

## Files

- `qc_core.py` — QC pipeline (importable module)
- `qc_avaatech.py` — Streamlit frontend
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
