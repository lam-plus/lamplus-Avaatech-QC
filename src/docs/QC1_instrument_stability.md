# QC1 — Instrument Stability

## Purpose

QC1 monitors the stability of the X-ray tube and detection chain over the
course of a scan by tracking the robust z-score of `Throughput` — and, at
10 kV, the Argon peak area (`Ar-Ka Area`) as a secondary indicator, since
Argon comes from the air path rather than the sediment and reacts to
vacuum/atmosphere issues that do not necessarily move `Throughput`. The two
z-scores are combined row by row into `Instrument_z`, defined as whichever
of the two has the larger absolute magnitude ("worst of the two"): a
degraded seal or atmosphere can depress Argon without moving Throughput,
and vice versa, so neither signal alone is sufficient. `Throughput` is
measured at every supported energy, so QC1 is the only module of the five
that is never structurally `NOT_APPLICABLE`.

## Variables per energy

| Energy | Variable(s) used |
|---|---|
| 10 kV | `Throughput`, `Ar-Ka Area` (combined into `Instrument_z`) |
| 30 kV | `Throughput` only (no Argon channel at this energy) |
| 50 kV | `Throughput` only (no Argon channel at this energy) |

When `Ar-Ka Area` is absent from the workbook (even at 10 kV), `Argon_z`
is `NaN` and `Instrument_z` falls back to `Throughput_z` alone — the same
behavior as 30 kV/50 kV.

## Statistical method

Robust z-score based on the Median Absolute Deviation (MAD):

```
z = 0.6745 * (x - median(x)) / MAD(x)
```

Computed independently for `Throughput` and (when available) `Ar-Ka Area`.
`Instrument_z` is then the value with the larger `|z|` between
`Throughput_z` and `Argon_z`; a missing side (`NaN`) never "wins" the
comparison, so it can never mask a real deviation on the other side. If
`MAD == 0` (all valid values identical), the z-score is `0.0` at valid
positions rather than infinite or `NaN`.

## Classification thresholds

Source: `qc_config.py` — `Z_WARNING = 2.5`, `Z_CRITICAL = 3.5`, applied to
`|Instrument_z|`.

| State | Criterion |
|---|---|
| OK | `\|Instrument_z\| < 2.5` |
| ALERT | `2.5 <= \|Instrument_z\| < 3.5` |
| CRITICAL | `\|Instrument_z\| >= 3.5` |
| INDETERMINATE | Raw `Throughput` is `NaN` for this row (checked on the raw column, never on `Instrument_z`, so the Argon fallback cannot hide a missing Throughput reading) |
| NOT_APPLICABLE | Never produced by QC1 — `Throughput` is measured at all three supported energies |

QC1 is a **mandatory** module: `INDETERMINATE` on this row forces the
overall Quality Flag to `INDETERMINATE`, regardless of the other modules.

## Physical meaning for the operator

- **OK** — the tube/detector output at this position is consistent with
  the rest of the run; no evidence of instrumental drift or contamination
  at this point.
- **ALERT** — Throughput (or Argon) deviates enough from the run's typical
  behavior to warrant attention; possible causes include partial vacuum
  loss, sample surface irregularities affecting count rate, or early tube
  aging. Not yet severe enough to discard the measurement outright.
- **CRITICAL** — a strong deviation suggesting a real instrumental problem
  at this position: vacuum/seal failure, tube instability, detector
  saturation or starvation, or a gross sample-surface defect (crack, gap,
  foreign object) under the beam.
- **INDETERMINATE** — Throughput was not recorded for this row; the
  instrument's baseline stability cannot be assessed here at all, so the
  row is never allowed to default to OK.
- **NOT_APPLICABLE** — not used by this module.

## Known limitations

- The z-score is computed over the whole Rep0 series for the sheet; a
  systematic drift affecting the entire run shifts the median and MAD
  together, which can under-detect a slow, run-wide trend (this is what
  QC4 — Rolling QC is meant to catch locally).
- Argon is only available at 10 kV; at 30 kV/50 kV, QC1 relies on
  Throughput alone and loses the "worst of two" cross-check.
- "Worst of the two" is intentionally conservative: a real, localized
  Argon anomaly can flag a row even when Throughput itself looks normal,
  which is by design but can read as an over-flag if the operator expects
  Throughput to be the sole criterion.
- A completely flat Throughput series (`MAD == 0`) never triggers
  ALERT/CRITICAL by construction, even if the flat value itself is
  physically implausible — the method only detects *relative* deviation
  within the run, not absolute plausibility.
