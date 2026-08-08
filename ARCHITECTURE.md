# Architecture — LAM+ Core QC

**Laboratory for Multispectral Analysis and Artificial Intelligence in
Sedimentary Research (LAM+)**, Universidade Federal Fluminense (UFF)

This document describes the design goals, principles, contracts, and file
structure of LAM+ Core QC — a quality-control pipeline for acquisition data
from the Avaatech XRF Core Scanner. It is intended as a reference for
contributors, not a change log; for the history of changes, see the git log
and the project's GitHub Issues.

## 1. Design goals

LAM+ Core QC is a deliberately simple, modular, and auditable
implementation of quality control for Avaatech XRF Core Scanner acquisition
data. The design prioritizes:

- keeping the focus on acquisition quality control;
- keeping the number of configurable options small;
- minimizing coupling between reading, computation, interface, and export;
- producing code that is easy to understand and test;
- providing direct, traceable output;
- keeping maintenance simple.

The project started from a small, well-defined core. Additional
functionality is only considered once that core is stable, validated
against real data, and documented.

## 2. What the app does today

Beyond the QC1–QC5 core described in section 3, the interface
(`qc_avaatech.py`) and its supporting modules (`i18n.py`, `qc_audit.py`,
`qc_reports.py`) implement:

- **Bilingual EN/PT interface.** A language selector in the sidebar
  (`i18n.SUPPORTED_LANGS`) drives every interface string, validation
  message, and summary (`summary.txt`) from `src/locales/en.json` /
  `src/locales/pt.json` via `i18n.load`. A missing translation key never
  breaks the interface — it falls back to the EN value.
- **Translated validation messages.** `qc_io.check_columns` receives the
  already-loaded strings dict (it does not import `i18n.py` directly — see
  the decision in section 4.4) and uses only `validation_*` keys for
  errors/warnings about required columns, missing `Rep0`, and depth-column
  fallback.
- **SQLite audit trail with a sidebar toggle.** `qc_audit.py` logs one row
  per successfully processed sheet/energy to `data/audit.db` (operator,
  file + MD5, git commit, pipeline version, QF distribution, warnings,
  runtime). Logging only happens when the "Enable audit log" toggle is on —
  **off by default** (see the decision in section 4.4). With the toggle on,
  a "History" tab appears, querying `qc_audit.query_runs` filtered by
  file/operator.
- **Graceful degradation in hosted/web environments.** Failures while
  logging (`register_run`) or querying (`query_runs`) the audit trail —
  e.g. a read-only or ephemeral `data/` on Streamlit Community Cloud — are
  caught and never surface as an error/traceback to the user; they fall
  back to the same friendly notice shown when no runs have been logged yet.
- **Visual summary per energy.** Metric cards (`n(Rep0)`, QF0–QF3,
  INDETERMINATE), a colored QF distribution bar (HTML via `st.html`, since
  `st.progress` does not support per-segment color), an ALERT/CRITICAL
  count table per module (QC1–QC5), and a list of depths with `Review =
  YES` (root cause + evidence). Uses `st.tabs` per energy when a workbook
  has multiple sheets.
- **Bilingual `summary.txt`.** `qc_reports.format_summary_text` builds the
  downloadable summary entirely from `strings["summary_*"]` (i18n) —
  downloading with EN selected produces English text; with PT, entirely in
  Portuguese, including the filename suffix (`_summary`/`_resumo`).
- **Optional "Operator" field in the sidebar**, free text, recorded on
  every audit run.
- **QC1–QC5 and QF module documentation in the sidebar.** `src/docs/`
  holds one Markdown file per module (`QC1_instrument_stability.md` ..
  `QC5_replicates.md`) plus `QF_quality_flags.md`; the sidebar renders this
  content through a "Protocol Reference" expander
  (`_render_protocol_reference`), with an `st.selectbox` to choose the
  module. Doc content is always in English (single technical source),
  regardless of interface language — only the expander and selector labels
  are translated.
- **Email feedback button in the sidebar.** `_render_feedback_button`
  builds an `st.link_button` with a `mailto:` URL (`_feedback_mailto_url`)
  to the fixed recipients `andrebelem@id.uff.br` and `ivenancio@id.uff.br`
  (`FEEDBACK_RECIPIENTS`), with subject and body pre-filled from i18n
  (`feedback_subject`/`feedback_body`), so operators can report issues or
  suggestions without leaving the interface.

## 3. Functional scope

The core follows a simplified proposal based on the Igor protocol:

- **QC1 — Instrument Stability**
- **QC2 — Coherent Scatter**
- **QC3 — Incoherent Scatter**
- **QC4 — Rolling QC:** local anomaly detection
- **QC5 — Replicates:** reproducibility across replicate measurements
- QF assignment by counting module states
- processing of multi-energy workbooks
- export of results to Excel
- generation of a simple summary

The core deliberately excludes PCA. It does not offer multiple competing
philosophies for QF calculation, nor an excess of methodological options in
the interface (see section 7 for the full out-of-scope list).

## 4. Implementation principles

### 4.1 Organization

- Keep a single source of truth for configuration, thresholds, and states.
- Prefer small functions with explicit inputs and outputs.
- Separate reading, validation, computation, classification, and export.
- Avoid mutable global state and implicit dependencies on the interface.
- Cover scientific rules and edge cases with automated tests.

### 4.2 Missing data and applicability

- Emit clear messages when required data is missing.
- Never treat `NaN` as an OK state.
- Represent indeterminate data separately from the QF0–QF3 states.
- Treat modules that don't apply to a given energy as neutral, without
  confusing them with missing critical data.
- Make explicit which modules and variables participated in a
  classification.

### 4.3 Integrity and traceability

- Never automatically alter original columns or values.
- Append QC results in an identifiable way.
- Record the root cause and the evidence supporting each flag.
- Document methodological decisions and behavior changes.
- Keep results reproducible for a given input and configuration.

### 4.4 Recorded decisions (i18n and audit)

- **Audit logging is off by default** (`audit_enabled = False` in
  `qc_avaatech.main`). Rationale: in hosted/ephemeral environments (e.g.
  Streamlit Community Cloud), `data/` may be read-only or not persist
  across sessions, and writing automatically without explicit operator
  consent doesn't make sense. Anyone who wants local traceability turns on
  the sidebar toggle; with the toggle off, the "History" tab isn't even
  created.
- **EN is the default language** (`i18n.DEFAULT_LANG = "en"`, first in
  `i18n.SUPPORTED_LANGS`). Rationale: consistency with the international QC
  literature and protocol, and with collaborations outside Brazil; PT
  remains available as a complete alternative (every key exists in both
  locales, with fallback to EN if missing).
- **`qc_io.check_columns` receives the resolved i18n strings dict from its
  caller**, instead of importing `i18n.py` directly. Rationale: keeps
  `qc_io.py` free of interface/language dependencies — the UI layer
  (`qc_avaatech.py`) decides the language, preserving the module's contract
  (see the `qc_io.py` header: "contains no interface logic").

## 5. File structure

Current structure under `src/`:

```text
qc_core.py
qc_config.py
qc_io.py
qc_reports.py
qc_avaatech.py
qc_audit.py
i18n.py
locales/
    en.json
    pt.json
tests/
```

Responsibilities:

- `qc_config.py`: energies, variables, thresholds, and states;
- `qc_io.py`: workbook reading, energy detection, and structural
  validation;
- `qc_core.py`: QC1–QC5 computations and state integration;
- `qc_reports.py`: Excel export and simple summary;
- `qc_avaatech.py`: the interface;
- `qc_audit.py`: SQLite audit trail (`data/audit.db`);
- `i18n.py`: loading of interface strings from `locales/en.json` /
  `locales/pt.json`, with fallback to EN;
- `locales/`: EN/PT translation files used by `i18n.py`;
- `tests/`: unit, synthetic, and integration tests.

`qc_config.py` consolidates configuration constants (`DEPTH_COL`,
`ENERGY_PARAMETERS`, QI weights, thresholds, etc.) into a single source of
truth, deliberately extracted into their own module rather than left
embedded inside the calculation core. `i18n.py`, `qc_audit.py`, and
`locales/` were not part of the original design — they were added after
the core stabilized (see sections 2 and 8).

Any change to this structure should preserve the separation of
responsibilities described above.

## 6. Contract

LAM+ Core QC must:

1. read workbooks exported by the Avaatech;
2. detect the energy of each supported sheet;
3. validate the columns required for that energy;
4. select the `Rep0` measurements;
5. use additional replicates when available;
6. return an explicit state for each applicable QC module;
7. produce QF0, QF1, QF2, or QF3 by counting the states;
8. flag indeterminate data in a separate category;
9. record the root cause and supporting evidence;
10. export results without altering the original columns.

Invalid input must produce actionable messages. The legitimate absence of a
module at a given energy must not penalize the result, while the absence of
a required datum must never resolve to OK.

## 7. Validation

The pipeline is validated against:

- real files used to validate the earlier internal implementation;
- expected results defined ahead of implementation;
- synthetic cases that isolate each rule;
- regression tests for critical findings C1 and C2.

The C1 test
(`test_qc5_regression_c1_matches_by_spectrum_and_coredepth_not_composite_depth`)
ensures replicates are matched by a valid physical key (`Spectrum` +
`CoreDepth`), independent of depths missing from `Rep1` or `Rep2`.

The C2 test (`test_qc_integrate.py`) ensures a missing critical datum is
never classified as OK, regardless of the aggregation rule — including
end-to-end in `run_qc`.

There are also multi-energy tests
(`test_multi_energy_file_icce3_has_three_independent_sheets`) and malformed
data tests.

The pipeline has been validated against 7 real files in `data/` with no
failures. The test suite currently has 151 tests, all passing.

### 7.1 Legacy parity comparison (no longer reproducible)

During development, a dedicated test file
(`src/tests/test_qc_core_vs_legacy.py`, removed) loaded the earlier
internal implementation (`LEGACY/qc_core.py`) at runtime — inserted into
`sys.path` only for the duration of that load, under the module name
`legacy_qc_core` to avoid colliding with the V2 `qc_core` — and asserted
numerical parity between the two for QC1–QC5 (`Throughput_z`, `Coherent_z`,
`Incoherent_z`, `Rolling_Delta_Z`, `Mean_RPD`) and for the resulting QF
distribution, against the real files in `data/examples/`. It also
documented the deliberate divergences confirmed by the user during that
validation:

- QC5 classifies `Mean_RPD == NaN` (no additional replicate) as
  `NOT_APPLICABLE`; the LEGACY classified it as OK.
- At 50 kV, the LEGACY falls back to using Throughput drift as a stand-in
  for QC4 (`use_combined_rolling`) because there is no scatter variable at
  that energy; the V2 deliberately does not reintroduce that fallback and
  marks QC4 as `NOT_APPLICABLE` instead (see section 4.1: "keep the number
  of configurable options small").

`LEGACY/` was never committed to this repository (it is listed in
`.gitignore` and only ever existed on the original author's development
machine) — so this comparison cannot be reproduced by other contributors
or in CI, and the test file always skipped for anyone without that
directory on disk. The file has been removed rather than adapted to
synthetic data: synthetic parity against a copy of the V2 algorithm itself
would not test anything the other test files (`test_qc_core.py`,
`test_qc_integrate.py`) don't already cover, since there is no legacy
algorithm left to compare against. The two divergences above remain
enforced by `test_qc_core.py::test_classify_rpd_nan_is_not_applicable_not_ok`
and by the QC4/50 kV tests in the same file; only the direct byte-for-byte
comparison against the old implementation was lost.

## 8. Out of scope

The following are out of scope for the core:

- PCA;
- clustering;
- Mahalanobis distance;
- a complex PDF report;
- multiple QF modes;
- advanced rolling options;
- an excessively configurable interface;
- sophisticated packaging ahead of core stabilization.

These items may be revisited once the criteria for the first functional
version are met.

After the QC1–QC5 core stabilized, the following items — not originally
planned in this section — were added: bilingual EN/PT support (`i18n.py`,
`src/locales/`), a SQLite audit trail (`qc_audit.py`, off by default), a
per-energy visual summary in the interface, and graceful audit degradation
in hosted/web environments (see section 2).
