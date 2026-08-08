# QC4 — Rolling QC

## Purpose

QC4 detects **local** anomalies along depth — as opposed to QC1/QC2/QC3,
which compare each row to the whole-run distribution. It computes a
centered rolling mean of the incoherent-scatter variable (the same one
used by QC3) over a small depth window, takes the deviation of each raw
value from that local mean, and applies a robust z-score to those
deviations. Sudden, localized departures from the immediate neighborhood
— a crack, an air bubble, a wet/dry transition, a core-section boundary —
show up here even when the value itself is not extreme relative to the
whole run.

## Variables per energy

| Energy | Variable used |
|---|---|
| 10 kV | `Rh-La-Inc Area` (same variable as QC3) |
| 30 kV | `Rh-Ka-Inc Area` (same variable as QC3) |
| 50 kV | *(none — structurally not applicable)* |

## Statistical method

1. Centered rolling mean over a window of `ROLLING_WINDOW = 5` rows
   (`min_periods=1`, so edge rows still get a mean from the points
   available):
   `Rolling_Mean = incoherent.rolling(window=5, center=True, min_periods=1).mean()`
2. Local deviation: `Rolling_Delta = incoherent - Rolling_Mean`
3. Robust z-score (MAD-based) of the deviation series:
   `Rolling_Delta_Z = 0.6745 * (Rolling_Delta - median) / MAD`

`rep0` is assumed to already be ordered by depth; QC4 does not reorder it
internally, so an unsorted input silently produces a meaningless rolling
window.

## Classification thresholds

Source: `qc_config.py` — `ROLLING_Z_ALERT = 4.0`, applied to
`|Rolling_Delta_Z|`. QC4 has **no CRITICAL state** — in count mode it only
distinguishes OK/ALERT.

| State | Criterion |
|---|---|
| OK | `\|Rolling_Delta_Z\| < 4.0` |
| ALERT | `\|Rolling_Delta_Z\| >= 4.0` |
| INDETERMINATE | The energy measures incoherent scatter (10 kV/30 kV) but the raw value is `NaN` for this row |
| NOT_APPLICABLE | Energy is 50 kV — no incoherent-scatter variable to roll over, a structural absence for the whole sheet |

QC4 is an **optional** module: `INDETERMINATE` on this row is recorded as
evidence but never forces the overall Quality Flag to `INDETERMINATE` —
its only source of `NaN` is the same raw column that already makes QC3
`INDETERMINATE` on the same row, so no coverage is lost by not making it
mandatory too.

## Physical meaning for the operator

- **OK** — this position behaves consistently with its immediate
  neighbors; no local anomaly detected, even if the absolute
  incoherent-scatter value is somewhat unusual for the run as a whole
  (that case is QC3's responsibility, not QC4's).
- **ALERT** — a localized jump relative to the nearby measurements:
  typical physical causes include a crack or void in the sediment, an air
  bubble under the beam, a sharp wet/dry or lithological transition, or a
  core-section boundary. This is a "something changed right here"
  signal, not necessarily an instrument fault.
- **INDETERMINATE** — the incoherent-scatter value is missing for this
  row, so local deviation cannot be computed; does not reduce the overall
  Quality Flag by itself (see Limitations).
- **NOT_APPLICABLE** — this energy (50 kV) has no incoherent-scatter
  channel to evaluate locally.

## Known limitations

- Fixed window size (`ROLLING_WINDOW = 5`), not adaptive to core-section
  transitions: a real section boundary within the window can bias the
  local mean and produce spurious ALERT flags on both sides of the
  boundary, or smear a genuine local anomaly into a false OK.
- `min_periods=1` means the first/last rows of the series near an edge
  are averaged over fewer points than the nominal window, so their rolling
  mean is less stable than interior points.
- Uses only the incoherent-scatter variable (unlike the legacy V4.2
  protocol's optional combined-rolling mode, which could also fold in
  Throughput/coherent/Argon deltas); a local anomaly that affects only
  Throughput or coherent scatter, without moving incoherent scatter, is
  not caught by QC4 at all — it may still be caught by QC1/QC2 pointwise.
- No persistence/debounce logic in this V2 implementation: a single
  isolated point above the threshold triggers ALERT immediately ("defense
  in depth"), which is more sensitive but also more prone to reacting to
  a one-row noise spike rather than a sustained local anomaly.
- Being optional, `INDETERMINATE` here never forces the row's overall
  Quality Flag to `INDETERMINATE` on its own — but since it shares its
  raw data source with QC3 (mandatory), the row is still correctly forced
  to `INDETERMINATE` overall via QC3.
