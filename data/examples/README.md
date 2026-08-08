# Example workbooks

These three `.xlsx` files are **real Avaatech XRF Core Scanner exports,
anonymized**, kept in the repository so anyone can try the QC pipeline or
run the test suite without needing access to raw data from the Laboratory
for Multispectral Analysis and Artificial Intelligence in Sedimentary
Research (LAM+). Anonymization removed core/site identifiers from file
names and sheet metadata; the measurement columns and values are
untouched.

They were chosen to cover the three workbook shapes the pipeline has to
handle, one energy tab at a time up to three:

| File | Sheets | Energies | Composite depth? |
|---|---|---|---|
| `example_single_energy.xlsx` | 1 | `10kv` | Yes — has `CompositeDepth (mm)` directly |
| `example_two_energies.xlsx` | 2 | `10kV`, `30kV` | No — only `CoreDepth`, fallback applies |
| `example_three_energies.xlsx` | 3 | `10kV`, `30kV`, `50kV` | No — only `CoreDepth`, fallback applies |

`CoreDepth` is always present. `CompositeDepth (mm)` is optional in
Avaatech exports; when it's missing, `qc_io.read_workbook` falls back to
`CoreDepth` and emits a warning (this is the common case — most real
workbooks only export `CoreDepth`). `example_single_energy.xlsx` is the
one file here that exercises the "has `CompositeDepth`" path instead of
the fallback.

## Structure of each sheet

Each sheet has one row per replicate measurement (column
`Replicate Nr Count`, values `Rep0`, `Rep1`, `Rep2`, ...). The QC pipeline
runs against the `Rep0` rows only.

| File | Sheet | Total rows | n(Rep0) |
|---|---|---|---|
| `example_single_energy.xlsx` | `10kv` | 294 | 270 |
| `example_two_energies.xlsx` | `10kV` | 83 | 77 |
| `example_two_energies.xlsx` | `30kV` | 83 | 77 |
| `example_three_energies.xlsx` | `10kV` | 72 | 65 |
| `example_three_energies.xlsx` | `30kV` | 69 | 65 |
| `example_three_energies.xlsx` | `50kV` | 69 | 65 |

## Usage

**With the app:**

```
streamlit run src/qc_avaatech.py
```

Upload any of the three files from the sidebar file picker.

**With the test suite:**

```
pytest src/tests
```

`src/tests/conftest.py` points `DATA_DIR` at this directory
(`data/examples/`), and `src/tests/test_qc_io_real_data.py` runs its
integration checks against these three files.

## About the original data

The full set of raw workbooks used to validate the pipeline during
development (larger, multi-core datasets from real LAM+ Laboratory runs)
is **not distributed in this repository** for confidentiality reasons.
`data/*.xlsx` outside of this `examples/` folder is git-ignored — if you
have your own Avaatech exports, drop them anywhere under `data/` (or
upload them directly through the app) and they will never be committed.
