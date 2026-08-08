# Quality Flag (QF) — Integration of QC1–QC5

## Purpose

The Quality Flag (`QF`) is the single, row-level verdict that integrates
the five QC module states ([QC1](QC1_instrument_stability.md),
[QC2](QC2_coherent_scatter.md), [QC3](QC3_incoherent_scatter.md),
[QC4](QC4_rolling_qc.md), [QC5](QC5_replicates.md)) into one value an
operator can act on without reading all five states individually. It is
computed by **counting** how many modules are in `ALERT`/`CRITICAL` for
that row — the "count mode" of protocol v4.2 — not by a weighted score.
`NOT_APPLICABLE` modules never count toward this total; they are neutral
by construction (see each module's own doc for why).

`QualityFlag` values (`qc_config.py`): `QF0`, `QF1`, `QF2`, `QF3`,
`INDETERMINATE` (internally `9`, kept separate from the ordered 0–3 scale
so it never reads as "worse than QF3" or "better than QF0" on a plot —
see `QF_PLOT_ORDER`).

## How the count is taken

For each row, `integrate_qc` (in `qc_core.py`) looks at the state of the
five modules and splits them into:

- **mandatory modules** — QC1, QC2, QC3: their `INDETERMINATE` forces the
  whole row to `QF = INDETERMINATE`, unconditionally, before anything
  else is evaluated;
- **optional modules** — QC4, QC5: their `INDETERMINATE` is recorded as
  evidence only, never forces `INDETERMINATE`, and never counts as
  ALERT/CRITICAL.

Once mandatory-`INDETERMINATE` is ruled out, the row's `alerts` and
`criticals` are the modules (from all five) sitting in `ALERT` /
`CRITICAL` respectively, and the flag is decided as follows:

| Condition | Resulting QF |
|---|---|
| Any of QC1/QC2/QC3 is `INDETERMINATE` | `INDETERMINATE` |
| 0 modules `ALERT` and 0 `CRITICAL` | `QF0` |
| Exactly 1 `ALERT`, 0 `CRITICAL` | `QF1` |
| 2+ `CRITICAL`, **or** 4+ `ALERT` | `QF3` |
| Everything else with at least one `ALERT`/`CRITICAL` (e.g. 1 `CRITICAL` alone; 2–3 `ALERT` with 0–1 `CRITICAL`) | `QF2` |

## QF criteria and operational meaning

| QF | Criterion | Operational meaning |
|---|---|---|
| **QF0** | No module in `ALERT`/`CRITICAL` | Measurement passed all applicable QC checks; no evidence of an acquisition problem at this position. |
| **QF1** | Exactly one module `ALERT`, none `CRITICAL` | A single, mild deviation in one module; not yet indicative of a real problem, but worth a quick look if it clusters with neighboring rows. |
| **QF2** | Moderate combined severity — one `CRITICAL` alone, or several `ALERT`s (2–3) with at most one `CRITICAL` | Meaningful evidence of an acquisition issue, either from one strong deviation or several moderate ones together; not yet the most severe tier. |
| **QF3** | Severe — two or more modules `CRITICAL`, or four or more modules `ALERT` | Strong, multi-module evidence of an acquisition problem at this position; the least reliable tier of usable-but-flagged data. |
| **INDETERMINATE** | QC1, QC2, or QC3 is `INDETERMINATE` for this row (a mandatory module's critical input is `NaN`, not structurally absent) | Quality cannot be judged at all for this row — a required raw value is missing, so the pipeline refuses to assign a "real" QF rather than default to `QF0` (this is the fix for the historical bug where missing critical data silently read as OK — see [DEVELOPMENT.md](../../DEVELOPMENT.md) §4.2). |

## What to do with each flag

- **QF0** — use normally. No action needed; the measurement is fit for
  downstream geochemical/statistical use as far as acquisition quality is
  concerned.
- **QF1** — mild attention. Usually safe to use as-is; worth noting if
  several consecutive QF1 rows appear together, which can hint at a
  slow-developing issue even though no single row is severe.
- **QF2** — inspect visually. Cross-check the row against the relevant
  QC plot(s) (see `QF_Cause`/`QF_Evidence` for which module(s) drove the
  flag) and, where possible, the physical core photo/log at that depth
  before deciding whether to keep, downweight, or discard the point.
- **QF3** — review before use. Treat as unreliable until manually
  reviewed; multiple independent modules agree there is a problem at this
  position, so it should not be used in downstream analysis without
  explicit justification.
- **INDETERMINATE** — a critical datum is missing, not just poor quality.
  Verify the source file: check whether the export is truncated, whether
  a column was dropped/renamed, or whether the instrument genuinely failed
  to record a value at this position. This is a data-availability problem,
  not a quality judgment — there's nothing to "review" analytically until
  the missing input itself is investigated.

## How QF relates to `Review`

`integrate_qc` also sets a `Review` column, which is a simplified
"needs a human look" summary of `QF`:

| QF | `Review` |
|---|---|
| QF0 | `NO` |
| QF1 | `NO` |
| QF2 | `YES` |
| QF3 | `YES` |
| INDETERMINATE | `YES` |

`Review = YES` is the practical trigger for the "inspect visually" /
"review before use" / "verify the file" actions above; `Review = NO`
(QF0/QF1) means the row can move on without manual intervention under
normal circumstances.

## What is *not* in the QF

**The QF measures acquisition quality only — never geochemical
plausibility.** An unusual elemental concentration, an unexpected ratio,
or a value that looks "surprising" compared to typical sediment
composition is **not**, by itself, a criterion for any QC1–QC5 module and
therefore cannot by itself produce anything other than `QF0`. All five
modules evaluate signals related to *how the measurement was taken*
(instrument stability, scatter behavior, local consistency, replicate
reproducibility) — none of them evaluate *what the measurement says*
about the sample's geochemistry.

A geochemically unusual but well-acquired data point is expected to be
`QF0`/`Review = NO`; a geochemically unremarkable point acquired under a
detector glitch, a cracked surface, or a poorly reproducible replicate is
expected to be flagged. Interpreting `QF3`/`Review = YES` as "this looks
like an odd geochemical value" is a misreading of what the flag
represents — always check `QF_Cause`/`QF_Evidence` to see which
acquisition-side module(s) actually drove the flag.
