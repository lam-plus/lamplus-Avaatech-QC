"""
Testes sintéticos das Etapas 3 e 4 do plano-de-acao.md (QC1-QC5 em
qc_core.py).

Casos cobertos:
    - robust_zscore: MAD == 0, NaN preservado, dataset com MAD conhecido;
    - classify_zscore: limiares OK/ALERT/CRITICAL, NaN levanta ValueError;
    - QC1: Throughput normal/anômalo/crítico, Argônio presente/ausente,
      NaN em Throughput -> INDETERMINATE;
    - QC2/QC3: 10 kV, 30 kV, 50 kV (NOT_APPLICABLE), NaN -> INDETERMINATE;
    - QC4: deriva local normal/anômala, 50 kV (NOT_APPLICABLE), NaN
      -> INDETERMINATE, anomalia isolada vs. persistente (documentação);
    - QC5: RPD OK/ALERT/CRITICAL, ausência de réplica -> NOT_APPLICABLE,
      média zero, regressão C1 (casamento por Spectrum+CoreDepth).

Não depende de LEGACY/ (ver conftest.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qc_config import (
    CAUSE_ARGON,
    CAUSE_MISSING_DATA,
    CAUSE_THROUGHPUT,
    QCState,
    RPD_CRITICAL,
    RPD_WARNING,
    Z_CRITICAL,
    Z_WARNING,
)
from qc_core import (
    calculate_rpd,
    classify_rolling,
    classify_rpd,
    classify_zscore,
    qc_coherent_scatter,
    qc_incoherent_scatter,
    qc_instrument_stability,
    qc_replicates,
    qc_rolling,
    robust_zscore,
)

# Dataset com mediana=1000.5 e MAD=3 (verificado à mão e contra
# robust_zscore): índice 8 (1014) cai em ALERT (z~3.04), índice 9 (700)
# cai em CRITICAL (z~-67.6), demais ficam OK.
THROUGHPUT_BASELINE = [997, 998, 999, 1000, 1001, 1002, 1004, 1005, 1014, 700]
ALERT_INDEX = 8
CRITICAL_INDEX = 9


def build_rep0(n: int, **columns: list) -> pd.DataFrame:
    data = {
        "Spectrum": [f"core-T01-{i}" for i in range(n)],
        "CoreDepth": [float(10 + i * 10) for i in range(n)],
    }
    data.update(columns)
    return pd.DataFrame(data)


# ============================================================
# robust_zscore
# ============================================================


def test_robust_zscore_returns_zeros_when_mad_is_zero():
    values = np.array([5.0, 5.0, 5.0, 5.0])
    z = robust_zscore(values)
    np.testing.assert_array_equal(z, [0.0, 0.0, 0.0, 0.0])


def test_robust_zscore_preserves_nan_even_when_mad_is_zero():
    values = np.array([5.0, 5.0, np.nan, 5.0])
    z = robust_zscore(values)
    assert np.isnan(z[2])
    np.testing.assert_array_equal(z[[0, 1, 3]], [0.0, 0.0, 0.0])


def test_robust_zscore_preserves_nan_with_nonzero_mad():
    values = np.array(THROUGHPUT_BASELINE, dtype=float)
    values[3] = np.nan
    z = robust_zscore(values)
    assert np.isnan(z[3])
    assert not np.isnan(z[0])


def test_robust_zscore_known_dataset_matches_hand_computed_values():
    values = np.array(THROUGHPUT_BASELINE, dtype=float)
    z = robust_zscore(values)
    # Mediana 1000.5, MAD 3.0 (calculados à mão) -> z = 0.6745*(x-1000.5)/3
    expected = 0.6745 * (values - 1000.5) / 3.0
    np.testing.assert_allclose(z, expected, rtol=1e-9)


def test_robust_zscore_all_nan_returns_all_nan_without_warning():
    values = np.array([np.nan, np.nan, np.nan])
    z = robust_zscore(values)
    assert np.all(np.isnan(z))


# ============================================================
# classify_zscore
# ============================================================


@pytest.mark.parametrize(
    "z,expected",
    [
        (0.0, QCState.OK),
        (Z_WARNING - 0.01, QCState.OK),
        (Z_WARNING, QCState.ALERT),
        (Z_CRITICAL - 0.01, QCState.ALERT),
        (Z_CRITICAL, QCState.CRITICAL),
        (-Z_WARNING, QCState.ALERT),  # simetria em valores negativos
        (-Z_CRITICAL, QCState.CRITICAL),
        (100.0, QCState.CRITICAL),
    ],
)
def test_classify_zscore_thresholds(z, expected):
    assert classify_zscore(z) == expected


def test_classify_zscore_raises_on_nan():
    with pytest.raises(ValueError, match="NaN"):
        classify_zscore(float("nan"))


# ============================================================
# QC1 — Instrument Stability
# ============================================================


def test_qc1_throughput_ok_alert_critical_without_argon():
    rep0 = build_rep0(len(THROUGHPUT_BASELINE), Throughput=THROUGHPUT_BASELINE)

    result = qc_instrument_stability(rep0, "30kV")  # 30kV: sem Argônio

    assert (result["Argon_z"].isna()).all()
    np.testing.assert_array_equal(result["Instrument_z"], result["Throughput_z"])

    states = result["QC1_State"].tolist()
    assert states[ALERT_INDEX] == QCState.ALERT
    assert states[CRITICAL_INDEX] == QCState.CRITICAL
    ok_indices = [i for i in range(len(states)) if i not in (ALERT_INDEX, CRITICAL_INDEX)]
    assert all(states[i] == QCState.OK for i in ok_indices)

    causes = result["QC1_Cause"].tolist()
    assert causes[ALERT_INDEX] == CAUSE_THROUGHPUT
    assert causes[CRITICAL_INDEX] == CAUSE_THROUGHPUT
    # pandas converte None->NaN em colunas object mistas; ausência de causa
    # (linha OK) é representada como NaN, nunca como uma string de causa.
    assert all(pd.isna(causes[i]) for i in ok_indices)


def test_qc1_argon_absent_from_10kv_file_behaves_like_throughput_alone():
    # cfg["argon"] existe para 10kV, mas a coluna não está no arquivo —
    # mesma degradação graciosa que 30/50kV (sem penalidade).
    n = len(THROUGHPUT_BASELINE)
    rep0 = build_rep0(n, Throughput=THROUGHPUT_BASELINE)

    result = qc_instrument_stability(rep0, "10kV")

    assert result["Argon_z"].isna().all()
    np.testing.assert_array_equal(result["Instrument_z"], result["Throughput_z"])
    assert result["QC1_State"].tolist()[ALERT_INDEX] == QCState.ALERT


def test_qc1_argon_worse_than_throughput_wins_and_sets_cause_argon():
    n = len(THROUGHPUT_BASELINE)
    # Throughput todo OK (achata a baseline); Argônio replica o padrão que
    # antes gerava ALERT/CRITICAL em Throughput, agora isolado no Argônio.
    throughput = [1000.0] * n
    throughput[0] = 1001.0  # evita MAD==0 sem gerar nenhum ALERT/CRITICAL
    argon = THROUGHPUT_BASELINE

    rep0 = build_rep0(n, Throughput=throughput, **{"Ar-Ka Area": argon})

    result = qc_instrument_stability(rep0, "10kV")

    assert result["QC1_State"].tolist()[CRITICAL_INDEX] == QCState.CRITICAL
    assert result["QC1_Cause"].tolist()[CRITICAL_INDEX] == CAUSE_ARGON
    # Instrument_z acompanha Argon_z nessa linha (é o pior dos dois).
    assert result["Instrument_z"].iloc[CRITICAL_INDEX] == pytest.approx(
        result["Argon_z"].iloc[CRITICAL_INDEX]
    )


def test_qc1_nan_in_throughput_is_indeterminate_regardless_of_argon():
    n = 5
    throughput = [1000.0, 1001.0, np.nan, 999.0, 1002.0]
    argon = [50.0, 51.0, 500.0, 49.0, 52.0]  # linha 2 teria Argônio "ok" localmente

    rep0 = build_rep0(n, Throughput=throughput, **{"Ar-Ka Area": argon})

    result = qc_instrument_stability(rep0, "10kV")

    assert result["QC1_State"].iloc[2] == QCState.INDETERMINATE
    assert result["QC1_Cause"].iloc[2] == CAUSE_MISSING_DATA
    # As demais linhas (Throughput presente) não são afetadas.
    assert result["QC1_State"].iloc[0] == QCState.OK


def test_qc1_does_not_mutate_input_dataframe():
    rep0 = build_rep0(4, Throughput=[1000.0, 1001.0, 999.0, 1002.0])
    original_columns = list(rep0.columns)

    qc_instrument_stability(rep0, "30kV")

    assert list(rep0.columns) == original_columns


# ============================================================
# QC2 / QC3 — Coherent / Incoherent Scatter
# ============================================================


@pytest.mark.parametrize(
    "energy,column,func",
    [
        ("10kV", "Rh-La Area", qc_coherent_scatter),
        ("30kV", "Rh-Ka-Coh Area", qc_coherent_scatter),
    ],
)
def test_qc2_ok_alert_critical(energy, column, func):
    n = len(THROUGHPUT_BASELINE)
    rep0 = build_rep0(n, **{column: THROUGHPUT_BASELINE})

    result = func(rep0, energy)

    states = result["QC2_State"].tolist()
    assert states[ALERT_INDEX] == QCState.ALERT
    assert states[CRITICAL_INDEX] == QCState.CRITICAL


@pytest.mark.parametrize(
    "energy,column,func",
    [
        ("10kV", "Rh-La-Inc Area", qc_incoherent_scatter),
        ("30kV", "Rh-Ka-Inc Area", qc_incoherent_scatter),
    ],
)
def test_qc3_ok_alert_critical(energy, column, func):
    n = len(THROUGHPUT_BASELINE)
    rep0 = build_rep0(n, **{column: THROUGHPUT_BASELINE})

    result = func(rep0, energy)

    states = result["QC3_State"].tolist()
    assert states[ALERT_INDEX] == QCState.ALERT
    assert states[CRITICAL_INDEX] == QCState.CRITICAL


def test_qc2_not_applicable_at_50kv():
    rep0 = build_rep0(6, Throughput=[1000.0] * 6)  # sem Rh-La/Rh-Ka nenhuma

    result = qc_coherent_scatter(rep0, "50kV")

    assert (result["QC2_State"] == QCState.NOT_APPLICABLE).all()
    assert result["Coherent_z"].isna().all()


def test_qc3_not_applicable_at_50kv():
    rep0 = build_rep0(6, Throughput=[1000.0] * 6)

    result = qc_incoherent_scatter(rep0, "50kV")

    assert (result["QC3_State"] == QCState.NOT_APPLICABLE).all()
    assert result["Incoherent_z"].isna().all()


def test_qc2_nan_is_indeterminate_not_not_applicable():
    values = [500.0, 501.0, np.nan, 499.0, 502.0]
    rep0 = build_rep0(5, **{"Rh-La Area": values})

    result = qc_coherent_scatter(rep0, "10kV")

    assert result["QC2_State"].iloc[2] == QCState.INDETERMINATE
    assert result["QC2_State"].iloc[0] == QCState.OK


def test_qc3_nan_is_indeterminate_not_not_applicable():
    values = [200.0, 201.0, np.nan, 199.0, 202.0]
    rep0 = build_rep0(5, **{"Rh-La-Inc Area": values})

    result = qc_incoherent_scatter(rep0, "10kV")

    assert result["QC3_State"].iloc[2] == QCState.INDETERMINATE
    assert result["QC3_State"].iloc[0] == QCState.OK


def test_qc2_does_not_mutate_input_dataframe():
    rep0 = build_rep0(4, **{"Rh-La Area": [500.0, 501.0, 499.0, 502.0]})
    original_columns = list(rep0.columns)

    qc_coherent_scatter(rep0, "10kV")

    assert list(rep0.columns) == original_columns


# ============================================================
# classify_rolling / classify_rpd
# ============================================================


def test_classify_rolling_thresholds():
    from qc_config import ROLLING_Z_ALERT

    assert classify_rolling(0.0) == QCState.OK
    assert classify_rolling(ROLLING_Z_ALERT - 0.01) == QCState.OK
    assert classify_rolling(ROLLING_Z_ALERT) == QCState.ALERT
    assert classify_rolling(-ROLLING_Z_ALERT) == QCState.ALERT
    # QC4 nunca produz CRITICAL, nem para z-scores extremos.
    assert classify_rolling(1000.0) == QCState.ALERT


def test_classify_rolling_raises_on_nan():
    with pytest.raises(ValueError, match="NaN"):
        classify_rolling(float("nan"))


def test_classify_rpd_thresholds():
    assert classify_rpd(0.0) == QCState.OK
    assert classify_rpd(RPD_WARNING - 0.01) == QCState.OK
    assert classify_rpd(RPD_WARNING) == QCState.ALERT
    assert classify_rpd(RPD_CRITICAL - 0.01) == QCState.ALERT
    assert classify_rpd(RPD_CRITICAL) == QCState.CRITICAL


def test_classify_rpd_nan_is_not_applicable_not_ok():
    # Decisão da Etapa 4: ausência de réplica é NOT_APPLICABLE, não OK
    # (diverge deliberadamente da LEGACY -- ver ARCHITECTURE.md, seção 7).
    assert classify_rpd(float("nan")) == QCState.NOT_APPLICABLE


def test_calculate_rpd_known_values():
    assert calculate_rpd(np.array([100.0, 105.0])) == pytest.approx(4.878048780487805)
    assert calculate_rpd(np.array([100.0, 115.0])) == pytest.approx(13.953488372093023)
    assert calculate_rpd(np.array([100.0, 130.0])) == pytest.approx(26.08695652173913)


def test_calculate_rpd_nan_when_fewer_than_two_valid_values():
    assert np.isnan(calculate_rpd(np.array([100.0])))
    assert np.isnan(calculate_rpd(np.array([100.0, np.nan])))


def test_calculate_rpd_nan_when_mean_is_zero():
    # Achado 1.1 da LEGACY: média zero nunca vira infinito, nunca erro.
    assert np.isnan(calculate_rpd(np.array([50.0, -50.0])))


# ============================================================
# QC4 — Rolling QC
# ============================================================

# Dataset com um pico isolado (índice 7) cercado de ruído normal em torno
# de ~500. Valores/estados abaixo conferidos rodando qc_rolling e
# inspecionando Rolling_Delta_Z (ver histórico de implementação) — o pico
# contamina a média móvel dos vizinhos (window=5, center=True), então o
# ALERT aparece num cluster de linhas ao redor do pico, não só nele.
ROLLING_ISOLATED_INCOHERENT = [500, 501, 499, 502, 498, 503, 497, 650, 500, 501, 499, 502, 498, 503, 497]
ROLLING_ISOLATED_ALERT_INDICES = {5, 6, 7, 8, 9}

# Mesma ideia, mas com 3 pontos consecutivos deslocados (deriva sustentada)
# em vez de 1 pico isolado.
ROLLING_PERSISTENT_INCOHERENT = [
    500, 501, 499, 502, 498, 503, 497, 650, 652, 648, 500, 501, 499, 502, 498, 503, 497,
]
ROLLING_PERSISTENT_ALERT_INDICES = {5, 6, 7, 8, 9, 10, 11}


def build_rolling_rep0(n: int, energy: str, values: list) -> pd.DataFrame:
    cfg_col = {"10kV": "Rh-La-Inc Area", "30kV": "Rh-Ka-Inc Area"}[energy]
    return pd.DataFrame(
        {
            "Spectrum": [f"core-T01-{i}" for i in range(n)],
            "CoreDepth": [float(10 + i * 10) for i in range(n)],
            cfg_col: values,
        }
    )


def test_qc4_isolated_spike_triggers_alert_around_it():
    n = len(ROLLING_ISOLATED_INCOHERENT)
    rep0 = build_rolling_rep0(n, "10kV", ROLLING_ISOLATED_INCOHERENT)

    result = qc_rolling(rep0, "10kV")

    states = result["QC4_State"].tolist()
    for i in range(n):
        expected = QCState.ALERT if i in ROLLING_ISOLATED_ALERT_INDICES else QCState.OK
        assert states[i] == expected, f"index {i}"


def test_qc4_persistent_drift_also_triggers_alert():
    # Documenta o comportamento atual: QC4 não distingue anomalia isolada
    # de persistente nesta etapa (a persistência da LEGACY —
    # use_rolling_persistence/_apply_rolling_persistence — não foi
    # portada). Ambos os datasets disparam ALERT nas linhas afetadas pela
    # janela; este teste apenas fixa esse comportamento documentado.
    n = len(ROLLING_PERSISTENT_INCOHERENT)
    rep0 = build_rolling_rep0(n, "10kV", ROLLING_PERSISTENT_INCOHERENT)

    result = qc_rolling(rep0, "10kV")

    states = result["QC4_State"].tolist()
    for i in range(n):
        expected = QCState.ALERT if i in ROLLING_PERSISTENT_ALERT_INDICES else QCState.OK
        assert states[i] == expected, f"index {i}"


def test_qc4_not_applicable_at_50kv():
    rep0 = pd.DataFrame(
        {
            "Spectrum": [f"core-T01-{i}" for i in range(6)],
            "CoreDepth": [float(10 + i * 10) for i in range(6)],
            "Throughput": [1000.0] * 6,
        }
    )

    result = qc_rolling(rep0, "50kV")

    assert (result["QC4_State"] == QCState.NOT_APPLICABLE).all()
    assert result["Rolling_Delta_Z"].isna().all()


def test_qc4_nan_in_incoherent_is_indeterminate():
    values = [500.0, 501.0, np.nan, 499.0, 502.0, 498.0, 503.0]
    rep0 = build_rolling_rep0(len(values), "10kV", values)

    result = qc_rolling(rep0, "10kV")

    assert result["QC4_State"].iloc[2] == QCState.INDETERMINATE
    assert result["QC4_State"].iloc[0] == QCState.OK


def test_qc4_30kv_uses_rh_ka_inc_column():
    n = len(ROLLING_ISOLATED_INCOHERENT)
    rep0 = build_rolling_rep0(n, "30kV", ROLLING_ISOLATED_INCOHERENT)

    result = qc_rolling(rep0, "30kV")

    assert result["QC4_State"].iloc[7] == QCState.ALERT


def test_qc4_does_not_mutate_input_dataframe():
    rep0 = build_rolling_rep0(6, "10kV", [500, 501, 499, 502, 498, 503])
    original_columns = list(rep0.columns)

    qc_rolling(rep0, "10kV")

    assert list(rep0.columns) == original_columns


# ============================================================
# QC5 — Replicates
# ============================================================


def build_replicates_dataset() -> pd.DataFrame:
    """
    5 posições físicas (Spectrum+CoreDepth): OK, ALERT, CRITICAL, sem
    réplica (só Rep0) e média-zero-mas-com-elemento-alternativo-válido.
    CompositeDepth (mm) propositalmente ausente/diferente em Rep1 (NaN),
    igual ao comportamento real do instrumento (só preenchida em Rep0) --
    regressão C1: o casamento tem que funcionar mesmo assim, porque usa
    Spectrum+CoreDepth, nunca CompositeDepth.
    """
    rows = [
        {"Spectrum": "s1", "CoreDepth": 10.0, "Replicate Nr Count": "Rep0", "Al-Ka Area": 100.0, "CompositeDepth (mm)": 10.0},
        {"Spectrum": "s1", "CoreDepth": 10.0, "Replicate Nr Count": "Rep1", "Al-Ka Area": 105.0, "CompositeDepth (mm)": np.nan},
        {"Spectrum": "s2", "CoreDepth": 20.0, "Replicate Nr Count": "Rep0", "Al-Ka Area": 100.0, "CompositeDepth (mm)": 20.0},
        {"Spectrum": "s2", "CoreDepth": 20.0, "Replicate Nr Count": "Rep1", "Al-Ka Area": 115.0, "CompositeDepth (mm)": np.nan},
        {"Spectrum": "s3", "CoreDepth": 30.0, "Replicate Nr Count": "Rep0", "Al-Ka Area": 100.0, "CompositeDepth (mm)": 30.0},
        {"Spectrum": "s3", "CoreDepth": 30.0, "Replicate Nr Count": "Rep1", "Al-Ka Area": 130.0, "CompositeDepth (mm)": np.nan},
        {"Spectrum": "s4", "CoreDepth": 40.0, "Replicate Nr Count": "Rep0", "Al-Ka Area": 100.0, "CompositeDepth (mm)": 40.0},
        {"Spectrum": "s5", "CoreDepth": 50.0, "Replicate Nr Count": "Rep0", "Al-Ka Area": 50.0, "Si-Ka Area": 200.0, "CompositeDepth (mm)": 50.0},
        {"Spectrum": "s5", "CoreDepth": 50.0, "Replicate Nr Count": "Rep1", "Al-Ka Area": -50.0, "Si-Ka Area": 210.0, "CompositeDepth (mm)": np.nan},
    ]
    return pd.DataFrame(rows)


def test_qc5_rpd_ok_alert_critical():
    df = build_replicates_dataset()
    rep0 = df[df["Replicate Nr Count"] == "Rep0"].copy()

    result = qc_replicates(df, rep0)
    by_spectrum = result.set_index("Spectrum")

    assert by_spectrum.loc["s1", "QC5_State"] == QCState.OK
    assert by_spectrum.loc["s2", "QC5_State"] == QCState.ALERT
    assert by_spectrum.loc["s3", "QC5_State"] == QCState.CRITICAL
    assert by_spectrum.loc["s1", "Mean_RPD"] == pytest.approx(4.878048780487805)
    assert by_spectrum.loc["s2", "Mean_RPD"] == pytest.approx(13.953488372093023)
    assert by_spectrum.loc["s3", "Mean_RPD"] == pytest.approx(26.08695652173913)


def test_qc5_no_replicate_available_is_not_applicable():
    df = build_replicates_dataset()
    rep0 = df[df["Replicate Nr Count"] == "Rep0"].copy()

    result = qc_replicates(df, rep0)
    by_spectrum = result.set_index("Spectrum")

    assert by_spectrum.loc["s4", "QC5_State"] == QCState.NOT_APPLICABLE
    assert pd.isna(by_spectrum.loc["s4", "Mean_RPD"])


def test_qc5_zero_mean_element_does_not_block_other_valid_elements():
    df = build_replicates_dataset()
    rep0 = df[df["Replicate Nr Count"] == "Rep0"].copy()

    result = qc_replicates(df, rep0)
    by_spectrum = result.set_index("Spectrum")

    # Al-Ka Area tem média zero (50/-50) em s5, mas Si-Ka Area (200/210) é
    # válido -- Mean_RPD usa só o elemento computável, não vira NaN.
    assert not pd.isna(by_spectrum.loc["s5", "Mean_RPD"])
    assert by_spectrum.loc["s5", "Mean_RPD"] == pytest.approx(4.878048780487805)
    assert by_spectrum.loc["s5", "QC5_State"] == QCState.OK


def test_qc5_regression_c1_matches_by_spectrum_and_coredepth_not_composite_depth():
    df = build_replicates_dataset()
    rep0 = df[df["Replicate Nr Count"] == "Rep0"].copy()

    # Pré-condição do teste: CompositeDepth (mm) está ausente/NaN em toda
    # réplica não-Rep0 -- se qc_replicates casasse por essa coluna (como o
    # bug histórico da LEGACY antes da correção do achado C1), nenhuma
    # réplica seria encontrada e todo mundo cairia em NOT_APPLICABLE.
    assert df.loc[df["Replicate Nr Count"] == "Rep1", "CompositeDepth (mm)"].isna().all()

    result = qc_replicates(df, rep0)
    by_spectrum = result.set_index("Spectrum")

    assert by_spectrum.loc["s1", "QC5_State"] != QCState.NOT_APPLICABLE
    assert by_spectrum.loc["s2", "QC5_State"] != QCState.NOT_APPLICABLE
    assert by_spectrum.loc["s3", "QC5_State"] != QCState.NOT_APPLICABLE


def test_qc5_does_not_mutate_input_rep0():
    df = build_replicates_dataset()
    rep0 = df[df["Replicate Nr Count"] == "Rep0"].copy()
    original_columns = list(rep0.columns)

    qc_replicates(df, rep0)

    assert list(rep0.columns) == original_columns
