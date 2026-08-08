# QC2 — Coherent Scatter

## Purpose

QC2 evaluates the Rh-anode coherent (Rayleigh) scatter peak, which is
sensitive to sample density, matrix composition, and surface geometry
under the beam. A pointwise robust z-score is computed for this single
variable at each measured position; the module is structurally absent at
50 kV, where the Avaatech does not report a coherent-scatter peak at all.

## Variables per energy

| Energy | Variable used |
|---|---|
| 10 kV | `Rh-La Area` |
| 30 kV | `Rh-Ka-Coh Area` |
| 50 kV | *(none — structurally not applicable)* |

## Statistical method

Robust z-score based on the Median Absolute Deviation (MAD), computed
pointwise over the applicable coherent-scatter variable for the sheet:

```
z = 0.6745 * (x - median(x)) / MAD(x)
```

No temporal/depth smoothing is applied here — each row's z-score depends
only on its own value relative to the whole-run distribution (contrast
with QC4, which looks at local deviation from a rolling mean).

## Classification thresholds

Source: `qc_config.py` — `Z_WARNING = 2.5`, `Z_CRITICAL = 3.5`, applied to
`|Coherent_z|`.

| State | Criterion |
|---|---|
| OK | `\|Coherent_z\| < 2.5` |
| ALERT | `2.5 <= \|Coherent_z\| < 3.5` |
| CRITICAL | `\|Coherent_z\| >= 3.5` |
| INDETERMINATE | The energy measures coherent scatter (10 kV/30 kV) but the raw value is `NaN` for this row |
| NOT_APPLICABLE | Energy is 50 kV — coherent scatter is not measured at all, a structural absence for the whole sheet, not a missing datum |

QC2 is a **mandatory** module: `INDETERMINATE` on this row forces the
overall Quality Flag to `INDETERMINATE`. `NOT_APPLICABLE` (50 kV) is
neutral and never forces `INDETERMINATE` nor counts toward ALERT/CRITICAL.

## Physical meaning for the operator

- **OK** — coherent scattering at this position is consistent with the
  rest of the run; no evidence of an anomalous density/matrix change or
  geometry problem.
- **ALERT** — a moderate deviation, possibly reflecting a local change in
  sediment density/porosity, a minor surface irregularity, or the onset of
  a matrix transition (e.g., approaching a lithological boundary).
- **CRITICAL** — a strong deviation, more likely to indicate a real
  surface defect (crack, void, foreign object, poor core-liner contact) or
  an abrupt matrix/density change large enough to be physically notable
  rather than routine sediment variability.
- **INDETERMINATE** — the coherent-scatter value could not be read for
  this row even though the energy is expected to measure it; the row's
  instrumental/geometric behavior at this energy cannot be judged.
- **NOT_APPLICABLE** — this energy (50 kV) does not measure coherent
  scatter at all; the absence is expected and carries no QC penalty.

## Known limitations

- Purely pointwise: a single anomalous reading and a sustained shift both
  produce the same kind of flag — QC2 alone does not distinguish a
  one-off spike from a real trend (see QC4 for local trend detection,
  though QC4 tracks incoherent, not coherent, scatter).
- Not available at 50 kV, so density/matrix information from coherent
  scatter is entirely missing at that energy; QC3 (incoherent) is the only
  scatter-based signal at 30 kV, and neither is available at 50 kV.
- Because the z-score is computed over the whole sheet, a run with a
  genuine, gradual lithological transition (not an instrument problem)
  can accumulate ALERT/CRITICAL flags near the ends of the transition
  purely from being far from the run's global median.
