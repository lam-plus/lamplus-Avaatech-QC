# LAM+ Core QC

Quality Control Protocol for Avaatech XRF Core Scanner

Developed at **LAM+** — Laboratório de Análise Multiespectral e Inteligência Artificial para Sedimentos  
Universidade Federal Fluminense (UFF)

---

## Overview

This tool implements a multi-module QC pipeline for XRF core scanner data produced by the Avaatech system. It provides an interactive web interface for uploading raw scan data, running automated quality control checks, visualizing diagnostics, and downloading the annotated output.

## Modules

| Module | Method | Target |
|--------|--------|--------|
| QC1 | Robust z-score | Throughput |
| QC2 | Robust z-score | Rh-Lα |
| QC3 | Robust z-score | Rh-Lα-Inc |
| QC4 | Rolling mean deviation | Throughput, Rh-Lα, Rh-Lα-Inc |
| QC5 | Mean RPD | Replicate measurements |
| QC6 | PCA + Mahalanobis distance | Multivariate geochemistry |

Each module contributes to a weighted **Quality Index (QI)** and a **Quality Flag (QF)** per measurement point.

### About QC4 (Rolling QC)

Throughput, Rh-Lα, and Rh-Lα-Inc are not chemical concentrations — they are **instrumental/physical indicators** of the measurement itself. Throughput is the detector's total count rate; Rh-Lα and Rh-Lα-Inc are the coherent (Rayleigh) and incoherent (Compton) scatter of the X-ray tube's own Rhodium anode line off the sample surface. A physical measurement issue (a crack, an air gap, a dry/wet transition, detector drift) tends to disturb **at least one** of these three simultaneously, since all three depend on the same measurement geometry/matrix at that point.

Because of that, QC4 (by default) takes the **largest** absolute rolling z-score (`|delta_z|`) among the three variables, rather than the mean — averaging would dilute a real, localized disturbance that may only show up strongly in one of them. This default can be turned off in the app (sidebar checkbox), falling back to the legacy behavior of considering only Rh-Lα-Inc.

## Files

- `qc_core.py` — QC pipeline (importable module)
- `qc_avaatech.py` — Streamlit frontend
- `requirements.txt` — Python dependencies

## Usage

```bash
streamlit run qc_avaatech.py
```

See `INSTALL.md` for environment setup instructions.

## Developers

- **[Igor Venancio](https://github.com/oliveiraimvp)** - LAM+, UFF
- **[Andre L. Belem](https://github.com/andrebelem)** - [O2](https://observatoriooceanografico.org), LAM+, UFF
- **[FRIDAY](https://observatoriooceanografico.org/pessoas/friday-bot/)** - [O2](https://observatoriooceanografico.org), UFF

---

*Created by A. L. Belem & FRIDAY*
