"""
Testes sintéticos da Etapa 2 do plano-de-acao.md (leitura e validação de
dados em qc_io.py).

Casos cobertos:
    - leitura de workbook com uma, duas e três abas de energia;
    - detecção de energia por nome de aba (variações de caixa/espaçamento);
    - abas com nome inesperado são ignoradas (skipped), sem falhar;
    - ausência de Rep0;
    - coluna crítica ausente;
    - módulo estruturalmente não aplicável (coerente/incoerente em 50 kV);
    - detecção e seleção de réplicas (Rep0/Rep1/Rep2);
    - fallback CompositeDepth -> CoreDepth.

Não depende de LEGACY/ (ver conftest.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qc_config import (
    CORE_DEPTH_COL,
    DEPTH_COL,
    ENERGY_VARIABLES,
    REP0_LABEL,
    REPLICATE_COL,
)
from qc_io import (
    check_columns,
    detect_energy,
    detect_replicates,
    read_workbook,
    resolve_depth_column,
    select_rep0,
)

# ============================================================
# HELPERS
# ============================================================


def build_sheet_df(
    energy: str,
    replicate_labels: tuple[str, ...] = (REP0_LABEL,),
    n_rows: int = 6,
    include_depth_col: bool = True,
    drop_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Monta um DataFrame sintético plausível para uma aba/energia."""
    cfg = ENERGY_VARIABLES[energy]
    rows = []
    for label in replicate_labels:
        for i in range(n_rows):
            row = {
                "Spectrum": f"core-T01-{i}",
                "CoreDepth": float(10 + i * 10),
                REPLICATE_COL: label,
                cfg["throughput"]: 1000.0 + i,
            }
            if include_depth_col:
                # CompositeDepth (mm) só é preenchido em Rep0 (ver qc_config).
                row[DEPTH_COL] = row["CoreDepth"] if label == REP0_LABEL else np.nan
            if cfg["coherent"] is not None:
                row[cfg["coherent"]] = 500.0 + i
            if cfg["incoherent"] is not None:
                row[cfg["incoherent"]] = 200.0 + i
            if cfg["argon"] is not None:
                row[cfg["argon"]] = 50.0 + i
            rows.append(row)
    df = pd.DataFrame(rows)
    if drop_columns:
        df = df.drop(columns=list(drop_columns), errors="ignore")
    return df


def write_workbook(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)


# ============================================================
# detect_energy
# ============================================================


@pytest.mark.parametrize(
    "sheet_name,expected",
    [
        ("10kV", "10kV"),
        ("10kv", "10kV"),
        ("10 kV", "10kV"),
        ("Data-10kV-raw", "10kV"),
        ("30kV", "30kV"),
        ("30KV", "30kV"),
        ("50kV", "50kV"),
        ("50kv", "50kV"),
    ],
)
def test_detect_energy_recognizes_variants(sheet_name, expected):
    assert detect_energy(sheet_name) == expected


def test_detect_energy_raises_for_unrecognized_name():
    with pytest.raises(ValueError, match="não reconhecida"):
        detect_energy("Resumo")


# ============================================================
# read_workbook — 1, 2 e 3 abas
# ============================================================


def test_read_workbook_single_sheet_10kv(tmp_path):
    path = tmp_path / "single_10kv.xlsx"
    write_workbook(path, {"10kV": build_sheet_df("10kV")})

    sheets, skipped = read_workbook(path)

    assert skipped == []
    assert len(sheets) == 1
    assert sheets[0]["sheet_name"] == "10kV"
    assert sheets[0]["energy"] == "10kV"
    assert isinstance(sheets[0]["df"], pd.DataFrame)


def test_read_workbook_10_30(tmp_path):
    path = tmp_path / "dupla_10_30.xlsx"
    write_workbook(
        path,
        {"10kV": build_sheet_df("10kV"), "30kV": build_sheet_df("30kV")},
    )

    sheets, skipped = read_workbook(path)

    assert skipped == []
    assert [s["energy"] for s in sheets] == ["10kV", "30kV"]


def test_read_workbook_10_30_50(tmp_path):
    path = tmp_path / "tripla_10_30_50.xlsx"
    write_workbook(
        path,
        {
            "10kV": build_sheet_df("10kV"),
            "30kV": build_sheet_df("30kV"),
            "50kV": build_sheet_df("50kV"),
        },
    )

    sheets, skipped = read_workbook(path)

    assert skipped == []
    assert [s["energy"] for s in sheets] == ["10kV", "30kV", "50kV"]


def test_read_workbook_unexpected_sheet_name_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "com_aba_desconhecida.xlsx"
    write_workbook(
        path,
        {
            "10kV": build_sheet_df("10kV"),
            "Resumo": pd.DataFrame({"nota": ["texto qualquer"]}),
        },
    )

    sheets, skipped = read_workbook(path)

    assert skipped == ["Resumo"]
    assert len(sheets) == 1
    assert sheets[0]["energy"] == "10kV"


# ============================================================
# check_columns / select_rep0 — Rep0 ausente
# ============================================================


def test_check_columns_reports_error_when_rep0_missing():
    df = build_sheet_df("10kV", replicate_labels=("Rep1", "Rep2"))

    errors, warnings = check_columns(df, "10kV")

    assert any("Rep0" in e for e in errors)


def test_select_rep0_raises_when_no_rep0_row():
    df = build_sheet_df("10kV", replicate_labels=("Rep1",))

    with pytest.raises(ValueError, match="Rep0"):
        select_rep0(df)


def test_select_rep0_raises_when_column_missing():
    df = build_sheet_df("10kV").drop(columns=[REPLICATE_COL])

    with pytest.raises(ValueError, match=REPLICATE_COL):
        select_rep0(df)


# ============================================================
# check_columns — coluna crítica ausente
# ============================================================


def test_check_columns_reports_error_when_critical_column_missing():
    df = build_sheet_df("10kV", drop_columns=("Throughput",))

    errors, warnings = check_columns(df, "10kV")

    assert any("Throughput" in e for e in errors)


def test_check_columns_ok_for_well_formed_10kv_sheet():
    df = build_sheet_df("10kV", replicate_labels=("Rep0", "Rep1"))

    errors, warnings = check_columns(df, "10kV")

    assert errors == []


# ============================================================
# check_columns — módulo não aplicável em 50 kV
# ============================================================


def test_check_columns_50kv_does_not_require_coherent_or_incoherent():
    df = build_sheet_df("50kV")
    assert "Rh-La Area" not in df.columns
    assert "Rh-Ka-Coh Area" not in df.columns

    errors, warnings = check_columns(df, "50kV")

    assert errors == []
    assert not any("Rh-" in e for e in errors)


def test_check_columns_30kv_requires_its_own_coherent_incoherent_columns():
    df = build_sheet_df("30kV", drop_columns=("Rh-Ka-Coh Area",))

    errors, warnings = check_columns(df, "30kV")

    assert any("Rh-Ka-Coh Area" in e for e in errors)


# ============================================================
# Réplicas — detecção
# ============================================================


def test_detect_replicates_single_rep0():
    df = build_sheet_df("10kV", replicate_labels=("Rep0",))
    assert detect_replicates(df) == ["Rep0"]


def test_detect_replicates_rep0_rep1_rep2_in_order():
    df = build_sheet_df("10kV", replicate_labels=("Rep0", "Rep1", "Rep2"))
    assert detect_replicates(df) == ["Rep0", "Rep1", "Rep2"]


def test_detect_replicates_ignores_blank_separator_rows():
    df = build_sheet_df("10kV", replicate_labels=("Rep0", "Rep1"))
    blank_row = {col: np.nan for col in df.columns}
    df = pd.concat([df, pd.DataFrame([blank_row])], ignore_index=True)

    assert detect_replicates(df) == ["Rep0", "Rep1"]


def test_detect_replicates_raises_when_column_missing():
    df = build_sheet_df("10kV").drop(columns=[REPLICATE_COL])
    with pytest.raises(ValueError, match=REPLICATE_COL):
        detect_replicates(df)


def test_select_rep0_filters_only_rep0_rows_and_does_not_mutate_original():
    df = build_sheet_df("10kV", replicate_labels=("Rep0", "Rep1", "Rep2"), n_rows=4)
    original_len = len(df)

    rep0 = select_rep0(df)

    assert (rep0[REPLICATE_COL] == REP0_LABEL).all()
    assert len(rep0) == 4
    assert len(df) == original_len  # original não foi alterado


# ============================================================
# Fallback CompositeDepth -> CoreDepth
# ============================================================


def test_resolve_depth_column_uses_composite_depth_when_present():
    df = build_sheet_df("10kV", include_depth_col=True)
    depth_col, warnings = resolve_depth_column(df)
    assert depth_col == DEPTH_COL
    assert warnings == []


def test_resolve_depth_column_falls_back_to_core_depth_with_warning():
    df = build_sheet_df("10kV", include_depth_col=False)
    assert DEPTH_COL not in df.columns

    depth_col, warnings = resolve_depth_column(df)

    assert depth_col == CORE_DEPTH_COL
    assert len(warnings) == 1
    assert CORE_DEPTH_COL in warnings[0]
    assert DEPTH_COL in warnings[0]


def test_resolve_depth_column_raises_when_neither_column_present():
    df = build_sheet_df("10kV", include_depth_col=False).drop(columns=["CoreDepth"])
    with pytest.raises(ValueError, match=CORE_DEPTH_COL):
        resolve_depth_column(df)


def test_check_columns_surfaces_depth_fallback_warning():
    df = build_sheet_df("10kV", include_depth_col=False)

    errors, warnings = check_columns(df, "10kV")

    assert errors == []
    assert any(CORE_DEPTH_COL in w for w in warnings)
