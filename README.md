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

Throughput, Rh-Lα, and Rh-Lα-Inc are not chemical concentrations — they are **instrumental/physical indicators** of the measurement itself. Throughput is the detector's total count rate; Rh-Lα and Rh-Lα-Inc are the coherent (Rayleigh) and incoherent (Compton) scatter of the X-ray tube's own Rhodium anode line off the sample surface.

**By default**, QC4 considers only **Rh-Lα-Inc**: it is the actual spectral signal measured at that point, whereas Throughput and Rh-Lα are secondary instrumental parameters that describe the measurement conditions rather than the spectral data itself.

The sidebar also has a checkbox to **combine all three variables** instead. A physical measurement issue (a crack, an air gap, a dry/wet transition, detector drift) tends to disturb **at least one** of the three simultaneously, since all depend on the same measurement geometry/matrix at that point. When enabled, QC4 takes the **largest** absolute rolling z-score (`|delta_z|`) among the three — rather than the mean, which would dilute a real, localized disturbance that may only show up strongly in one of them — at the cost of also reacting to instrumental drift that isn't necessarily reflected in the spectral signal itself.

## Roadmap (planned — not yet implemented)

- **PCA (QC6) as diagnostic-only**: PCA + Mahalanobis distance is always calculated and shown in the PCA diagnostic tab regardless of any setting. Today it is also always included in the QF criteria (5% of the QI weight). A planned sidebar checkbox would let PCA stay purely diagnostic — visible, but excluded from the QF decision.
- **QF mode selector**: QF is currently computed by a single rule (weighted QI thresholds combined with per-module z-score/Mahalanobis criteria — see `compute_flags` in `qc_core.py`). A planned alternative mode would compute QF from a simple count of failed modules instead of the weighted QI, as a more transparent, less compensatory criterion. The current weighted-QI mode would remain the default; the module-count mode would be opt-in.

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
