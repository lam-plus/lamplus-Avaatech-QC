# src/ — Developer Guide

This is the implementation of LAM+ Core QC: a small set of single-purpose
modules, a Streamlit UI on top, and a test suite. See the root
[README.md](../README.md) for what the app does from a user's point of
view, and [../DEVELOPMENT.md](../DEVELOPMENT.md) for the full design
rationale and validation history.

## File structure

| File / directory | Responsibility |
|---|---|
| `qc_config.py` | Single source of truth: supported energies, per-energy variable names, thresholds, `QCState`/`QCModule`/`QualityFlag` enums, pipeline version. No calculation logic — every other module imports its constants from here rather than redefining them. |
| `qc_io.py` | Reading Avaatech workbooks, detecting energy from sheet name, selecting `Rep0`, and structural validation (`check_columns`) before any calculation runs. No scientific calculation, no UI. |
| `qc_core.py` | The QC1–QC5 calculations and their integration into a per-row Quality Flag (`run_qc`). Pure library code — no Streamlit dependency, so it can be tested and reused headless. |
| `qc_reports.py` | Excel export (`build_excel_report`, with conditional coloring and the `Flagged_Intervals` sheet) and the plain summary (`build_summary` / `format_summary_text`). No calculation, no UI. |
| `qc_avaatech.py` | The Streamlit UI — the only entry point (`streamlit run src/qc_avaatech.py`). Upload, validation, running the pipeline, visual summary, downloads, history tab, sidebar (language, audit toggle, protocol reference, feedback button). Contains no scientific calculation of its own. |
| `qc_audit.py` | Local audit trail in SQLite (`data/audit.db`): `init_db`, `register_run`, `query_runs`. One row per successfully processed sheet/energy. |
| `i18n.py` | Loads UI strings from `locales/<lang>.json`, with fallback to English for any missing key. Not imported by `qc_core.py`, `qc_io.py`, or `qc_config.py`. |
| `locales/` | `en.json` / `pt.json` — the UI string tables consumed by `i18n.py`. |
| `docs/` | One Markdown file per QC module (`QC1_instrument_stability.md` … `QC5_replicates.md`) plus `QF_quality_flags.md`, rendered in the app's "Protocol Reference" sidebar expander. Always in English, regardless of UI language. |
| `tests/` | Unit, synthetic, and integration tests (pytest). |

## Running the tests

From the project root, with the virtual environment activated:

```bash
pytest src/tests/
```

Notable test files:

- `test_qc_core.py` / `test_qc_integrate.py` — module-level and QF-integration
  behavior, including the regression tests for missing-data-never-OK and for
  matching replicates by physical key rather than by depth.
- `test_qc_io.py` / `test_qc_io_real_data.py` — workbook reading, column
  validation, and end-to-end runs against real files under `data/`.
- `test_qc_reports.py` — Excel export structure/coloring and summary content.
- `test_qc_audit.py` — the SQLite audit trail.
- `test_imports.py` — import hygiene (see architecture notes below).

## Adding translations

UI strings live in `locales/en.json` and `locales/pt.json`, loaded by
`i18n.load(lang)`. To add a new string:

1. Add the key and English value to `locales/en.json`.
2. Add the same key with the Portuguese value to `locales/pt.json`.
3. Reference it in `qc_avaatech.py` (or wherever it's needed) via the
   `strings` dict already threaded through the UI functions — never
   hardcode UI text directly in Python.

A key missing from a non-English locale falls back to the English value
automatically (`i18n.load`); it never raises `KeyError`. English is
always the default language and the first entry in `i18n.SUPPORTED_LANGS`.

To add a new supported language entirely, create `locales/<code>.json`
with (at minimum) every key from `en.json`, then add `<code>` to
`i18n.SUPPORTED_LANGS`.

## Adding module documentation

Each QC module's reference doc in `docs/` is a plain Markdown file,
displayed as-is in the sidebar's "Protocol Reference" expander
(`qc_avaatech._render_protocol_reference`). To add or update one:

1. Write/edit the Markdown file in `docs/` (existing files follow a
   consistent structure: Purpose, Variables per energy, Statistical
   method, Classification thresholds, Physical meaning for the operator,
   Known limitations — follow it for new modules).
2. Register it in `PROTOCOL_DOCS` in `qc_avaatech.py` (maps a short module
   key to the filename).
3. Content is always written in English — it's the technical reference
   and stays fixed regardless of the UI language; only the expander/selector
   labels are translated via i18n.

## Architecture decisions worth knowing

- **`src/` has no runtime dependency on any earlier implementation.**
  Nothing under `src/` imports code from outside `src/`; concepts or
  behavior carried over from prior work are always reimplemented
  explicitly here, never imported from elsewhere. Tests run without
  adding anything outside `src/` to `PYTHONPATH`. (One consequence you'll
  notice in `qc_avaatech.py`: `i18n` is imported locally inside functions
  rather than at module top-level, to avoid a module-name collision that
  a comparison test intentionally introduces via `sys.path` — see the
  comment above `_select_language`.)
- **`qc_io.py` does not import `i18n.py`.** `check_columns` takes an
  already-loaded `strings` dict as a parameter instead of resolving the
  language itself. This keeps `qc_io.py` free of any UI/locale
  dependency — the caller (`qc_avaatech.py`) decides the language, in
  line with `qc_io.py`'s contract of containing no interface logic.
- **The audit trail is off by default.** `audit_enabled` starts `False`
  in `qc_avaatech.main`; nothing is written to `data/audit.db` unless the
  operator explicitly enables the sidebar toggle. This matters on
  hosted/ephemeral deployments (e.g. Streamlit Community Cloud), where
  local storage may be read-only or not persisted between sessions, and
  because writing audit records without explicit consent isn't the right
  default. Failures in `register_run`/`query_runs` are caught and
  degrade gracefully — they never surface as a crash to the user.
- **Single source of truth for constants.** Energies, per-energy
  variable names, thresholds, and QC/QF enums live only in
  `qc_config.py`; no other module redefines them.
- **Missing data never reads as OK.** A required raw value that is `NaN`
  produces `QCState.INDETERMINATE`, distinct from `QCState.OK` — see
  `qc_core.classify_zscore`/`classify_rolling` (which raise if called
  with `NaN` directly, forcing the caller to handle it explicitly) and
  `integrate_qc`, which forces `QualityFlag.INDETERMINATE` whenever a
  mandatory module (QC1/QC2/QC3) is indeterminate on a row.
