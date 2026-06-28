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
