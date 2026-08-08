# QC3 — Incoherent Scatter

## Purpose

QC3 evaluates the Rh-anode incoherent (Compton) scatter peak, sensitive to
the average atomic number and composition of the sample matrix, and to
instrument geometry (sample distance, surface flatness). A pointwise
robust z-score is computed for this variable at each measured position;
the module is structurally absent at 50 kV. The same raw variable also
feeds QC4 — Rolling QC, so an anomaly at this signal can surface in both
modules simultaneously (see Known limitations).

## Variables per energy

| Energy | Variable used |
|---|---|
| 10 kV | `Rh-La-Inc Area` |
| 30 kV | `Rh-Ka-Inc Area` |
| 50 kV | *(none — structurally not applicable)* |

## Statistical method

Robust z-score based on the Median Absolute Deviation (MAD), computed
pointwise over the applicable incoherent-scatter variable for the sheet:

```
z = 0.6745 * (x - median(x)) / MAD(x)
```

Like QC2, this is a whole-run pointwise comparison with no rolling/local
window — the depth-local counterpart of this same variable is what QC4
evaluates separately.

## Classification thresholds

Source: `qc_config.py` — `Z_WARNING = 2.5`, `Z_CRITICAL = 3.5`, applied to
`|Incoherent_z|`.

| State | Criterion |
|---|---|
| OK | `\|Incoherent_z\| < 2.5` |
| ALERT | `2.5 <= \|Incoherent_z\| < 3.5` |
| CRITICAL | `\|Incoherent_z\| >= 3.5` |
| INDETERMINATE | The energy measures incoherent scatter (10 kV/30 kV) but the raw value is `NaN` for this row |
| NOT_APPLICABLE | Energy is 50 kV — incoherent scatter is not measured at all, a structural absence for the whole sheet, not a missing datum |

QC3 is a **mandatory** module: `INDETERMINATE` on this row forces the
overall Quality Flag to `INDETERMINATE`. `NOT_APPLICABLE` (50 kV) is
neutral and never forces `INDETERMINATE` nor counts toward ALERT/CRITICAL.

## Physical meaning for the operator

- **OK** — incoherent scattering at this position is consistent with the
  rest of the run; matrix composition and geometry appear stable relative
  to the rest of the core.
- **ALERT** — a moderate deviation, possibly reflecting a local matrix
  composition change (e.g., organic content, grain size, water content) or
  a minor geometric irregularity (surface unevenness, small gap).
- **CRITICAL** — a strong deviation, more consistent with a real physical
  problem: significant sample-surface defect, large air gap between
  sample and detector, or an abrupt, large matrix change.
- **INDETERMINATE** — the incoherent-scatter value could not be read for
  this row even though the energy is expected to measure it.
- **NOT_APPLICABLE** — this energy (50 kV) does not measure incoherent
  scatter at all; the absence is expected and carries no QC penalty.

## Known limitations

- Purely pointwise, same caveat as QC2: does not distinguish a one-off
  spike from a sustained trend by itself.
- Not available at 50 kV.
- **Shared raw column with QC4**: since QC4's rolling delta is computed
  from the same incoherent-scatter variable, a single anomalous reading
  can trigger both QC3 (pointwise) and QC4 (local deviation from rolling
  mean) at the same row — the two flags are correlated, not independent
  evidence, and should not be read as "two separate confirmations" of a
  problem.
- A row with `NaN` in the raw incoherent value is `INDETERMINATE` here
  and also propagates to `NaN` in QC4's rolling calculation for that row
  — by design, QC4 is not required to force `INDETERMINATE` on its own
  for this reason, since QC3 already covers it (see QC4 doc, Known
  limitations).
