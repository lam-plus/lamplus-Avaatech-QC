# QC5 — Replicates

## Purpose

QC5 evaluates measurement reproducibility by comparing repeated scans
(`Rep0`/`Rep1`/`Rep2`/…) taken at the same physical position on the core.
For each position with more than one replicate, it computes the Relative
Percent Difference (RPD) per element and averages it across the elements
available in the file, producing one `Mean_RPD` value that is attached to
the corresponding `Rep0` row. Positions that were only scanned once
(no repeat) have nothing to compare and are marked neutral, never
penalized.

## Variables per energy

Unlike QC1–QC4, the element set evaluated by QC5 is **not** derived from
`ENERGY_VARIABLES` and does not change by energy — it is the fixed list
`ELEMENTS_REPLICATES` from `qc_config.py`, evaluated on whichever of these
columns are actually present in the workbook:

| Energy | Variables used |
|---|---|
| 10 kV | `Al-Ka Area`, `Si-Ka Area`, `K -Ka Area`, `Ca-Ka Area`, `Ti-Ka Area`, `Fe-Ka Area` (whichever are present) |
| 30 kV | Same fixed element list, whichever are present |
| 50 kV | Same fixed element list, whichever are present |

## Statistical method

1. Replicates are matched by the physical key `REPLICATE_KEY_COLS =
   ("Spectrum", "CoreDepth")` — never by the continuous depth column,
   which is only populated on the first pass and is null on repeat scans.
2. For each matched position with 2+ replicate rows, RPD is computed per
   element:
   `RPD = |max(values) - min(values)| / |mean(values)| * 100`
3. `Mean_RPD` is the average of the per-element RPDs across all elements
   available in the file for that position (`np.nanmean`).
4. Positions with only one scan (no match) get `Mean_RPD = NaN` — not an
   error, a legitimate absence of a second measurement to compare against.

`calculate_rpd` also returns `NaN` (never a false zero) when fewer than 2
valid values are available, or when the mean of the valid values is
exactly zero (avoids division by zero).

## Classification thresholds

Source: `qc_config.py` — `RPD_WARNING = 10.0`, `RPD_CRITICAL = 20.0`
(percent), applied to `Mean_RPD`.

| State | Criterion |
|---|---|
| OK | `Mean_RPD < 10.0` |
| ALERT | `10.0 <= Mean_RPD < 20.0` |
| CRITICAL | `Mean_RPD >= 20.0` |
| NOT_APPLICABLE | `Mean_RPD` is `NaN` — no second replicate matched at this position (or the replicate mean was exactly zero) |
| INDETERMINATE | Never produced by QC5 — `classify_rpd` maps every non-classifiable case to `NOT_APPLICABLE`, not `INDETERMINATE` |

QC5 is an **optional** module: a `NOT_APPLICABLE` (no replicate to
compare) never penalizes the Quality Flag and never forces
`INDETERMINATE`; it is recorded as evidence only when relevant.

## Physical meaning for the operator

- **OK** — repeated scans at this position agree well; the measurement is
  reproducible, supporting confidence in the elemental values reported.
- **ALERT** — moderate disagreement between replicates, potentially from
  local sediment heterogeneity, minor sample repositioning between scans,
  or borderline counting statistics for low-count elements.
- **CRITICAL** — large disagreement between replicates, suggesting poor
  reproducibility at this position: sample surface disturbance between
  scans, packing/void issues, or an unstable reading not representative of
  a real, stable measurement.
- **NOT_APPLICABLE** — this position was only scanned once; reproducibility
  simply cannot be assessed here, which is different from having assessed
  it and found it good.
- **INDETERMINATE** — not used by this module.

## Known limitations

- Matching relies entirely on `Spectrum` + `CoreDepth` being populated and
  consistent across replicate passes; any export irregularity in those
  two columns silently breaks the match for that position (falls back to
  `NOT_APPLICABLE`, not a visible error).
- `Mean_RPD` averages across all available elements from
  `ELEMENTS_REPLICATES`; a single severely non-reproducible element can be
  diluted by several well-behaved ones, potentially masking an
  element-specific problem in the aggregate `Mean_RPD`.
- The zero-mean guard (`RPD = NaN` when the replicate mean is exactly
  zero) is a deliberate safety measure against division by zero, but it
  means a position where an element is genuinely absent/zero in all
  replicates is treated as `NOT_APPLICABLE` for that element's
  contribution rather than "perfectly reproducible zero."
- Because QC5 is optional, a poor replicate match never raises the row to
  `INDETERMINATE` — a systematically broken replicate key across an entire
  sheet would show up as widespread `NOT_APPLICABLE`, not as an error the
  pipeline surfaces loudly; operators should check `check_file`/`qc_io`
  warnings for replicate-matching issues separately.
