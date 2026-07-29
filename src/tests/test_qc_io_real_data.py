"""
Testes de integração da Etapa 2 (plano-de-acao.md) contra os workbooks
Avaatech reais em `data/`.

Confirma que qc_io.py lê e valida os arquivos que já foram usados para
validar a LEGACY, sem depender dela em runtime (ver conftest.py).
"""

from __future__ import annotations

from functools import lru_cache

import pytest

from conftest import DATA_DIR
from qc_config import CORE_DEPTH_COL, DEPTH_COL, REP0_LABEL, REPLICATE_COL
from qc_io import check_columns, detect_replicates, read_workbook, select_rep0


@lru_cache(maxsize=None)
def _read_workbook_cached(path_str: str):
    """
    Alguns arquivos reais são grandes (dgl1905.xlsx: 11514 linhas x 3 abas)
    e vários testes leem o mesmo arquivo — cachear evita reabrir/reparsear
    o mesmo .xlsx repetidas vezes e mantém a suíte rápida.
    """
    return read_workbook(path_str)

REAL_FILES = sorted(DATA_DIR.glob("*.xlsx"))

# Energias esperadas por arquivo, na ordem das abas (ver inspeção manual dos
# workbooks reais — todas as abas seguem a convenção "<energia>kV").
EXPECTED_ENERGIES = {
    "Dados Consolidados-ICCE3.xlsx": ["10kV", "30kV", "50kV"],
    "Dados Consolidados-Itatiaia.xlsx": ["10kV", "30kV"],
    "Dados Consolidados-OP42GC4.xlsx": ["10kV", "30kV", "50kV"],
    "Dados Consolidados-dgl1905.xlsx": ["10kV", "30kV", "50kV"],
    "Dados Consolidados-trigoskoe.xlsx": ["10kV", "30kV"],
    "Dados ConsolidadosICCE10.xlsx": ["10kV", "30kV", "50kV"],
    "exemplo_dados_consolidados.xlsx": ["10kV"],
}

# Arquivos que exportam CompositeDepth (mm) diretamente (não devem acionar o
# fallback para CoreDepth). Confirmado por inspeção manual dos workbooks:
# a maioria dos arquivos reais só tem CoreDepth, então o fallback é o
# caminho comum, não a exceção.
FILES_WITH_COMPOSITE_DEPTH = {
    "Dados Consolidados-OP42GC4.xlsx",
    "exemplo_dados_consolidados.xlsx",
}


@pytest.fixture(params=REAL_FILES, ids=[f.name for f in REAL_FILES])
def real_file(request):
    return request.param


def test_real_files_present_for_integration_tests():
    # Guarda contra o diretório data/ mudar de lugar/ficar vazio sem que os
    # testes de integração percebam (eles ficariam vacuamente "verdes").
    assert len(REAL_FILES) >= 7


def test_read_workbook_detects_expected_energies_per_sheet(real_file):
    sheets, skipped = _read_workbook_cached(str(real_file))

    assert skipped == [], f"abas inesperadamente ignoradas em {real_file.name}: {skipped}"
    energies = [s["energy"] for s in sheets]
    assert energies == EXPECTED_ENERGIES[real_file.name]


def test_check_columns_passes_without_errors_for_every_real_sheet(real_file):
    sheets, _ = _read_workbook_cached(str(real_file))
    for sheet in sheets:
        errors, warnings = check_columns(sheet["df"], sheet["energy"])
        assert errors == [], (
            f"{real_file.name} / aba '{sheet['sheet_name']}' ({sheet['energy']}): "
            f"erros inesperados: {errors}"
        )


def test_depth_fallback_warning_matches_file_expectations(real_file):
    sheets, _ = _read_workbook_cached(str(real_file))
    expects_fallback = real_file.name not in FILES_WITH_COMPOSITE_DEPTH
    for sheet in sheets:
        _, warnings = check_columns(sheet["df"], sheet["energy"])
        has_fallback_warning = any(CORE_DEPTH_COL in w and DEPTH_COL in w for w in warnings)
        assert has_fallback_warning == expects_fallback, (
            f"{real_file.name} / aba '{sheet['sheet_name']}': "
            f"aviso de fallback de profundidade {'ausente' if expects_fallback else 'inesperado'}"
        )


def test_select_rep0_and_detect_replicates_on_every_real_sheet(real_file):
    sheets, _ = _read_workbook_cached(str(real_file))
    for sheet in sheets:
        df = sheet["df"]
        replicates = detect_replicates(df)
        assert replicates[0] == REP0_LABEL
        assert "nan" not in [str(r).lower() for r in replicates]

        rep0 = select_rep0(df)
        assert len(rep0) > 0
        assert (rep0[REPLICATE_COL] == REP0_LABEL).all()


def test_multi_energy_file_icce3_has_three_independent_sheets():
    path = DATA_DIR / "Dados Consolidados-ICCE3.xlsx"
    sheets, skipped = _read_workbook_cached(str(path))

    assert skipped == []
    assert [s["energy"] for s in sheets] == ["10kV", "30kV", "50kV"]

    kv50 = next(s for s in sheets if s["energy"] == "50kV")
    errors, warnings = check_columns(kv50["df"], "50kV")
    assert errors == []
    assert "Rh-La Area" not in kv50["df"].columns
    assert "Rh-Ka-Coh Area" not in kv50["df"].columns
