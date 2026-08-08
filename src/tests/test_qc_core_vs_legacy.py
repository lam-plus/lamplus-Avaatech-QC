"""
Comparação de resultados das Etapas 3 e 4 (QC1-QC5 em qc_core.py) com a
LEGACY, sobre arquivos reais.

Importante: este arquivo é o único ponto de todo o test suite da V2 que
toca `LEGACY/qc_core.py` — e só o faz para validar paridade numérica, nunca
como dependência da V2. `LEGACY/` é inserida em `sys.path` apenas durante o
carregamento do módulo (dentro da fixture, com `try/finally`) e removida
em seguida; o módulo é carregado sob o nome `legacy_qc_core` (não
`qc_core`) para não colidir com o `qc_core` da V2 já importado nos outros
testes. Isso preserva a garantia de `test_imports.py` (V2 não importa nada
de LEGACY/ e os demais testes rodam sem LEGACY/ no PYTHONPATH) — este
arquivo é pulado (`pytest.skip`) se `LEGACY/qc_core.py` não existir.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import DATA_DIR
from qc_config import ENERGY_VARIABLES, QCState, QualityFlag, REPLICATE_COL
from qc_core import (
    qc_coherent_scatter,
    qc_incoherent_scatter,
    qc_instrument_stability,
    qc_replicates,
    qc_rolling,
    run_qc,
)

LEGACY_QC_CORE_PATH = Path(__file__).resolve().parents[2] / "LEGACY" / "qc_core.py"


@lru_cache(maxsize=None)
def _load_legacy_qc_core():
    """Carrega LEGACY/qc_core.py sob o nome 'legacy_qc_core', sem deixar
    LEGACY/ no sys.path depois de carregado nem colidir com o 'qc_core' da
    V2 já presente em sys.modules."""
    legacy_dir = str(LEGACY_QC_CORE_PATH.parent)
    spec = importlib.util.spec_from_file_location("legacy_qc_core", LEGACY_QC_CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, legacy_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(legacy_dir)
    return module


pytestmark = pytest.mark.skipif(
    not LEGACY_QC_CORE_PATH.exists(),
    reason="LEGACY/qc_core.py não encontrado — comparação de referência indisponível.",
)


def _rep0_from_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Mesmo filtro simples usado por qc_io.select_rep0 e pela LEGACY
    (df[REPLICATE_COL] == 'Rep0'); z-score independe de ordenação por
    profundidade, então não há necessidade de replicar o sort_values."""
    return df[df[REPLICATE_COL] == "Rep0"].copy()


REAL_FILES_AND_SHEETS = [
    ("example_three_energies.xlsx", "10kV", "10kV"),
    ("example_three_energies.xlsx", "30kV", "30kV"),
    ("example_three_energies.xlsx", "50kV", "50kV"),
    ("example_single_energy.xlsx", "10kv", "10kV"),
]


@pytest.fixture(params=REAL_FILES_AND_SHEETS, ids=[f"{f}:{s}" for f, s, _ in REAL_FILES_AND_SHEETS])
def real_rep0_pair(request):
    filename, sheet_name, energy = request.param
    path = DATA_DIR / filename
    raw = pd.ExcelFile(path).parse(sheet_name)
    v2_rep0 = _rep0_from_raw(raw)
    legacy_rep0 = _rep0_from_raw(raw)
    return v2_rep0, legacy_rep0, energy


def test_qc1_instrument_stability_matches_legacy(real_rep0_pair):
    v2_rep0, legacy_rep0, energy = real_rep0_pair
    legacy_qc_core = _load_legacy_qc_core()

    v2_result = qc_instrument_stability(v2_rep0, energy)
    legacy_result = legacy_qc_core.qc_throughput(legacy_rep0, energy=energy)

    np.testing.assert_allclose(
        v2_result["Throughput_z"].to_numpy(dtype=float),
        legacy_result["Throughput_z"].to_numpy(dtype=float),
        equal_nan=True,
    )
    np.testing.assert_allclose(
        v2_result["Argon_z"].to_numpy(dtype=float),
        legacy_result["Argon_z"].to_numpy(dtype=float),
        equal_nan=True,
    )
    np.testing.assert_allclose(
        v2_result["Instrument_z"].to_numpy(dtype=float),
        legacy_result["Instrument_z"].to_numpy(dtype=float),
        equal_nan=True,
    )


def test_qc2_coherent_scatter_matches_legacy_rh_la(real_rep0_pair):
    v2_rep0, legacy_rep0, energy = real_rep0_pair
    legacy_qc_core = _load_legacy_qc_core()

    v2_result = qc_coherent_scatter(v2_rep0, energy)
    legacy_result = legacy_qc_core.qc_rh_la(legacy_rep0, energy=energy)

    np.testing.assert_allclose(
        v2_result["Coherent_z"].to_numpy(dtype=float),
        legacy_result["RhLa_z"].to_numpy(dtype=float),
        equal_nan=True,
    )


def test_qc3_incoherent_scatter_matches_legacy_rh_la_inc(real_rep0_pair):
    v2_rep0, legacy_rep0, energy = real_rep0_pair
    legacy_qc_core = _load_legacy_qc_core()

    v2_result = qc_incoherent_scatter(v2_rep0, energy)
    legacy_result = legacy_qc_core.qc_rh_la_inc(legacy_rep0, energy=energy)

    np.testing.assert_allclose(
        v2_result["Incoherent_z"].to_numpy(dtype=float),
        legacy_result["RhLaInc_z"].to_numpy(dtype=float),
        equal_nan=True,
    )


def test_50kv_coherent_and_incoherent_are_neutral_in_both_versions():
    legacy_qc_core = _load_legacy_qc_core()
    path = DATA_DIR / "example_three_energies.xlsx"
    raw = pd.ExcelFile(path).parse("50kV")
    v2_rep0 = _rep0_from_raw(raw)
    legacy_rep0 = _rep0_from_raw(raw)

    v2_coherent = qc_coherent_scatter(v2_rep0, "50kV")
    legacy_coherent = legacy_qc_core.qc_rh_la(legacy_rep0, energy="50kV")
    assert v2_coherent["Coherent_z"].isna().all()
    assert legacy_coherent["RhLa_z"].isna().all()

    v2_incoherent = qc_incoherent_scatter(v2_rep0, "50kV")
    legacy_incoherent = legacy_qc_core.qc_rh_la_inc(legacy_rep0, energy="50kV")
    assert v2_incoherent["Incoherent_z"].isna().all()
    assert legacy_incoherent["RhLaInc_z"].isna().all()


def test_legacy_dir_not_left_on_sys_path_after_loading():
    _load_legacy_qc_core()
    legacy_dir = str(LEGACY_QC_CORE_PATH.parent)
    assert legacy_dir not in sys.path


# ============================================================
# QC4 — Rolling QC
# ============================================================


def test_qc4_rolling_delta_z_matches_legacy_incoherent_variable(real_rep0_pair):
    v2_rep0, legacy_rep0, energy = real_rep0_pair
    legacy_qc_core = _load_legacy_qc_core()

    v2_result = qc_rolling(v2_rep0, energy)
    legacy_result = legacy_qc_core.qc_rolling(legacy_rep0, energy=energy)

    incoherent_col = ENERGY_VARIABLES[energy]["incoherent"]
    if incoherent_col is None:
        # 50 kV: nem a V2 nem a LEGACY têm uma variável incoerente para
        # essa energia -- LEGACY simplesmente não gera a coluna
        # "{var}_delta_z" correspondente (o loop pula variáveis None).
        assert v2_result["Rolling_Delta_Z"].isna().all()
        return

    legacy_col = f"{incoherent_col}_delta_z"
    np.testing.assert_allclose(
        v2_result["Rolling_Delta_Z"].to_numpy(dtype=float),
        legacy_result[legacy_col].to_numpy(dtype=float),
        equal_nan=True,
    )


# ============================================================
# QC5 — Replicates
# ============================================================


@pytest.mark.parametrize(
    "filename,sheet_name,energy",
    REAL_FILES_AND_SHEETS,
    ids=[f"{f}:{s}" for f, s, _ in REAL_FILES_AND_SHEETS],
)
def test_qc5_mean_rpd_matches_legacy(filename, sheet_name, energy):
    legacy_qc_core = _load_legacy_qc_core()
    raw = pd.ExcelFile(DATA_DIR / filename).parse(sheet_name)
    v2_rep0 = _rep0_from_raw(raw)
    legacy_rep0 = _rep0_from_raw(raw)

    v2_result = qc_replicates(raw, v2_rep0)
    legacy_result = legacy_qc_core.qc_replicates(raw, legacy_rep0)

    np.testing.assert_allclose(
        v2_result["Mean_RPD"].to_numpy(dtype=float),
        legacy_result["Mean_RPD"].to_numpy(dtype=float),
        equal_nan=True,
    )


def test_qc5_state_diverges_from_legacy_on_purpose_for_rows_without_replicate():
    """
    Documenta a divergência deliberada (decisão da Etapa 4, confirmada
    pelo usuário): a LEGACY classifica Mean_RPD == NaN como OK
    (_classify_rpd_count_mode); a V2 classifica como NOT_APPLICABLE. Os
    valores de Mean_RPD em si são idênticos nos dois (ver
    test_qc5_mean_rpd_matches_legacy) -- só o rótulo de estado muda.

    `example_three_energies.xlsx` (aba 10kV) é um caso real onde a
    maioria das posições (63 de 65) só tem Rep0, sem Rep1/Rep2 -- não é um
    cenário sintético raro, é o comportamento predominante neste arquivo.
    """
    legacy_qc_core = _load_legacy_qc_core()
    raw = pd.ExcelFile(DATA_DIR / "example_three_energies.xlsx").parse("10kV")
    v2_rep0 = _rep0_from_raw(raw)
    legacy_rep0 = _rep0_from_raw(raw)

    v2_result = qc_replicates(raw, v2_rep0)
    legacy_result = legacy_qc_core.qc_replicates(raw, legacy_rep0)

    no_replicate_mask = legacy_result["Mean_RPD"].isna()
    assert no_replicate_mask.sum() >= 60  # maioria das 65 linhas Rep0

    assert (v2_result.loc[no_replicate_mask, "QC5_State"] == QCState.NOT_APPLICABLE).all()
    legacy_states = legacy_result.loc[no_replicate_mask, "Mean_RPD"].apply(
        legacy_qc_core._classify_rpd_count_mode
    )
    assert (legacy_states == legacy_qc_core.QC_OK).all()


# ============================================================
# Etapa 5 — Quality Flag integrado (integrate_qc/run_qc) vs. LEGACY
# ============================================================


def _qf_distribution(qf_series) -> dict:
    """Conta ocorrências por valor inteiro de QF (0-3, 9=indeterminado),
    independente de vir como qc_config.QualityFlag (V2) ou int puro
    (LEGACY) -- os dois usam os mesmos valores (QF_INDETERMINATE=9)."""
    counts: dict[int, int] = {}
    for value in qf_series:
        counts[int(value)] = counts.get(int(value), 0) + 1
    return counts


@pytest.mark.parametrize(
    "filename,sheet_name,energy",
    [
        ("example_three_energies.xlsx", "10kV", "10kV"),
        ("example_three_energies.xlsx", "30kV", "30kV"),
        ("example_single_energy.xlsx", "10kv", "10kV"),
    ],
    ids=["three_energies:10kV", "three_energies:30kV", "single_energy:10kv"],
)
def test_qf_distribution_matches_legacy_count_mode_when_incoherent_variable_exists(
    filename, sheet_name, energy
):
    """
    Nas energias com variável incoerente (10 kV/30 kV), a distribuição de QF
    da V2 (run_qc/integrate_qc, por contagem) deve bater exatamente com a
    LEGACY no modo de contagem (use_count_mode=True, protocolo v4.2) -- os
    limiares são idênticos (COUNT_MODE_Z_WARNING/CRITICAL = Z_WARNING/
    Z_CRITICAL = 2.5/3.5, mesma coisa para rolling/RPD) e a única diferença
    de rótulo já conhecida (QC5 NOT_APPLICABLE na V2 vs. OK na LEGACY para
    posições sem réplica adicional -- ver
    test_qc5_state_diverges_from_legacy_on_purpose_for_rows_without_replicate)
    é neutra para a contagem de ALERT/CRITICAL nos dois casos.
    strict_missing_data=False alinha o critério de indeterminado da LEGACY
    (Throughput/coerente/incoerente ausentes) ao de integrate_qc (QC1-QC3
    obrigatórios).
    """
    legacy_qc_core = _load_legacy_qc_core()
    raw = pd.ExcelFile(DATA_DIR / filename).parse(sheet_name)

    v2_result = run_qc(raw, energy)
    legacy_result, _, _, _ = legacy_qc_core.run_qc(
        raw, use_count_mode=True, strict_missing_data=False, energy=energy
    )

    assert _qf_distribution(v2_result["QF"]) == _qf_distribution(legacy_result["QF"])


def test_qf_distribution_diverges_from_legacy_at_50kv_due_to_qc4_rolling_fallback():
    """
    Documenta uma divergência esperada em 50 kV: a energia não mede nenhuma
    variável de espalhamento (coerente/incoerente), então qc_core.qc_rolling
    (V2) marca QC4 como NOT_APPLICABLE em 100% das linhas (ver
    test_qc_core.test_qc4_not_applicable_at_50kv). A LEGACY, em vez de
    desativar o QC4 nessa energia, cai no modo combinado
    (`use_combined_rolling`, ver compute_scores) e usa a deriva do
    Throughput como substituto -- então a LEGACY pode gerar ALERTs de QC4
    em 50 kV onde a V2 nunca gera nenhum. É uma simplificação deliberada da
    V2 (ARCHITECTURE.md 4.1: "reduzir o número de opções configuráveis"),
    não um bug: a V2 não reintroduz Throughput como proxy de deriva
    espectral quando o dado espectral em si não existe para a energia.

    O que continua idêntico nas duas versões em 50 kV: QC1 (Throughput) e
    QF_INDETERMINATE (o único dado crítico obrigatório é Throughput nesta
    energia -- QC2/QC3 são estruturalmente não aplicáveis, não entram nos
    critical_cols da LEGACY nem forçam INDETERMINATE na V2). Este teste
    verifica só essa parte estável; a distribuição QF0-QF3 completa não é
    comparada aqui de propósito, por causa da divergência do QC4 acima.
    """
    legacy_qc_core = _load_legacy_qc_core()
    raw = pd.ExcelFile(DATA_DIR / "example_three_energies.xlsx").parse("50kV")

    v2_result = run_qc(raw, "50kV")
    legacy_result, _, _, _ = legacy_qc_core.run_qc(
        raw, use_count_mode=True, strict_missing_data=False, energy="50kV"
    )

    v2_indeterminate = set(v2_result.index[v2_result["QF"] == QualityFlag.INDETERMINATE])
    legacy_indeterminate = set(
        legacy_result.index[legacy_result["QF"] == legacy_qc_core.QF_INDETERMINATE]
    )
    assert v2_indeterminate == legacy_indeterminate

    # Isola a causa da divergência ao QC4/rolling: a contagem de linhas
    # com QC1 em ALERT/CRITICAL (por si só, sem o resto do QF) bate --
    # test_qc1_instrument_stability_matches_legacy já cobre a igualdade
    # numérica de Instrument_z em si.
    v2_qc1_flagged = v2_result["QC1_State"].isin([QCState.ALERT, QCState.CRITICAL]).sum()
    legacy_qc1_flagged = (
        legacy_result["Instrument_z"].abs().ge(legacy_qc_core.COUNT_MODE_Z_WARNING).sum()
    )
    assert v2_qc1_flagged == legacy_qc1_flagged
