"""
Testes sintéticos da Etapa 5 do plano-de-acao.md (integração dos estados
QC1-QC5 em Quality Flag, em qc_core.py: compute_module_states, integrate_qc,
run_qc).

Casos cobertos:
    - compute_module_states: dict por linha, validação de colunas/energia;
    - integrate_qc: todas as combinações de estados que produzem QF0-QF3
      (ver plano-de-acao.md, Etapa 5, "Regra inicial proposta");
    - INDETERMINATE em módulo obrigatório (QC1/QC2/QC3) -> QF_INDETERMINATE
      incondicional, mesmo com outros módulos em CRITICAL;
    - INDETERMINATE em módulo opcional (QC4/QC5) -> não penaliza, vira
      evidência (decisão confirmada nesta etapa: QC4 tratado como opcional
      porque sua única fonte de NaN é a mesma coluna bruta que já torna
      QC3 indeterminado na mesma linha);
    - NOT_APPLICABLE nunca conta na contagem de ALERT/CRITICAL;
    - causa principal (pior severidade, desempate por ordem QC1..QC5) e
      evidências secundárias;
    - coluna Review (YES para QF2/QF3/INDETERMINATE, NO para QF0/QF1 --
      decisão confirmada nesta etapa: indeterminado também precisa de
      revisão humana);
    - run_qc: pipeline completo ponta a ponta com dado sintético,
      confirmando que recebe a aba bruta (todas as réplicas) e não só
      Rep0 (decisão confirmada nesta etapa -- QC5 não teria como casar
      réplicas caso contrário).

Não depende de LEGACY/ (ver conftest.py). A comparação de distribuição de
QF com a LEGACY em arquivos reais está em test_qc_core_vs_legacy.py (único
arquivo do suite que toca LEGACY/qc_core.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qc_config import (
    CAUSE_ARGON,
    CAUSE_COHERENT,
    CAUSE_INCOHERENT,
    CAUSE_MISSING_DATA,
    CAUSE_REPLICA,
    CAUSE_ROLLING,
    CAUSE_THROUGHPUT,
    QCModule,
    QCState,
    QualityFlag,
)
from qc_core import compute_module_states, integrate_qc, run_qc

OK = QCState.OK
ALERT = QCState.ALERT
CRITICAL = QCState.CRITICAL
NA = QCState.NOT_APPLICABLE
IND = QCState.INDETERMINATE


def build_states_rep0(rows: list[dict]) -> pd.DataFrame:
    """
    Monta um DataFrame Rep0 sintético só com as colunas que
    compute_module_states/integrate_qc precisam (QC1_State..QC5_State,
    QC1_Cause), sem passar pelos módulos qc_* individuais -- permite testar
    a integração isoladamente para qualquer combinação de estados.
    """
    data = []
    for i, row in enumerate(rows):
        data.append(
            {
                "Spectrum": f"s{i}",
                "QC1_State": row.get("QC1", OK),
                "QC1_Cause": row.get("QC1_Cause", np.nan),
                "QC2_State": row.get("QC2", OK),
                "QC3_State": row.get("QC3", OK),
                "QC4_State": row.get("QC4", OK),
                "QC5_State": row.get("QC5", OK),
            }
        )
    return pd.DataFrame(data)


# ============================================================
# compute_module_states
# ============================================================


def test_compute_module_states_builds_dict_per_row():
    rep0 = build_states_rep0([{"QC1": ALERT, "QC1_Cause": CAUSE_THROUGHPUT, "QC2": CRITICAL}])

    result = compute_module_states(rep0, "10kV")

    states = result["QC_Module_States"].iloc[0]
    assert states[QCModule.QC1_INSTRUMENT_STABILITY] == ALERT
    assert states[QCModule.QC2_COHERENT_SCATTER] == CRITICAL
    assert states[QCModule.QC3_INCOHERENT_SCATTER] == OK


def test_compute_module_states_raises_on_missing_state_column():
    rep0 = pd.DataFrame({"QC1_State": [OK]})  # faltam QC2..QC5

    with pytest.raises(ValueError, match="QC2_State"):
        compute_module_states(rep0, "10kV")


def test_compute_module_states_validates_energy():
    rep0 = build_states_rep0([{}])
    with pytest.raises(ValueError, match="Energia desconhecida"):
        compute_module_states(rep0, "15kV")


# ============================================================
# integrate_qc -- QF0-QF3 por contagem
# ============================================================


def test_qf0_when_all_modules_ok():
    rep0 = build_states_rep0([{}])  # tudo OK por padrão
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF0
    assert result["QC_Alert_Count"].iloc[0] == 0
    assert result["QC_Critical_Count"].iloc[0] == 0
    assert result["QF_Cause"].iloc[0] is None
    assert result["QF_Evidence"].iloc[0] == ""
    assert result["Review"].iloc[0] == "NO"


def test_qf1_with_exactly_one_alert():
    rep0 = build_states_rep0([{"QC4": ALERT}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF1
    assert result["QC_Alert_Count"].iloc[0] == 1
    assert result["QF_Cause"].iloc[0] == CAUSE_ROLLING
    assert result["Review"].iloc[0] == "NO"


@pytest.mark.parametrize(
    "row",
    [
        {"QC2": ALERT, "QC5": ALERT},  # 2 ALERTs
        {"QC2": ALERT, "QC3": ALERT, "QC4": ALERT},  # 3 ALERTs
        {"QC3": CRITICAL},  # 1 CRITICAL
    ],
    ids=["2_alerts", "3_alerts", "1_critical"],
)
def test_qf2_two_or_three_alerts_or_one_critical(row):
    rep0 = build_states_rep0([row])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF2
    assert result["Review"].iloc[0] == "YES"


@pytest.mark.parametrize(
    "row",
    [
        {"QC1": CRITICAL, "QC1_Cause": CAUSE_THROUGHPUT, "QC3": CRITICAL},  # 2 CRITICALs
        {"QC1": ALERT, "QC1_Cause": CAUSE_THROUGHPUT, "QC2": ALERT, "QC3": ALERT, "QC4": ALERT},  # 4 ALERTs
    ],
    ids=["2_criticals", "4_alerts"],
)
def test_qf3_two_criticals_or_four_alerts(row):
    rep0 = build_states_rep0([row])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF3
    assert result["Review"].iloc[0] == "YES"


def test_one_alert_and_one_critical_falls_back_to_qf2():
    # Combinação não coberta explicitamente pela tabela do plano (nem "1
    # ALERT" puro nem "2+ CRITICAL/4+ ALERT") -- mesmo comportamento do
    # modo de contagem da LEGACY (_evaluate_flag_count_mode: fallback é
    # sempre QF2, não compensatório).
    rep0 = build_states_rep0([{"QC2": CRITICAL, "QC4": ALERT}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF2


# ============================================================
# NOT_APPLICABLE nunca penaliza
# ============================================================


def test_not_applicable_modules_never_count_as_alert_or_critical():
    # 50 kV: QC2/QC3/QC4 estruturalmente não aplicáveis -- só QC1/QC5
    # sobram, ambos OK -> QF0, nunca QF_INDETERMINATE nem penalidade por
    # "faltarem" módulos.
    rep0 = build_states_rep0([{"QC2": NA, "QC3": NA, "QC4": NA}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF0
    assert result["QC_Alert_Count"].iloc[0] == 0
    assert result["QC_Critical_Count"].iloc[0] == 0
    assert result["QF_Evidence"].iloc[0] == ""


def test_not_applicable_does_not_prevent_qf1_from_remaining_qf1():
    rep0 = build_states_rep0([{"QC2": NA, "QC3": NA, "QC4": ALERT}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF1


# ============================================================
# INDETERMINATE -- módulo obrigatório vs opcional
# ============================================================


@pytest.mark.parametrize("mandatory_module_key", ["QC1", "QC2", "QC3"])
def test_mandatory_module_indeterminate_forces_qf_indeterminate(mandatory_module_key):
    row = {mandatory_module_key: IND, "QC5": CRITICAL}  # CRITICAL noutro módulo não muda o resultado
    rep0 = build_states_rep0([row])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.INDETERMINATE
    assert result["QF_Cause"].iloc[0] == CAUSE_MISSING_DATA
    assert result["Review"].iloc[0] == "YES"
    # o CRITICAL de QC5 continua registrado como evidência, mesmo o QF
    # tendo sido decidido só pelo dado obrigatório ausente.
    assert CAUSE_REPLICA in result["QF_Evidence"].iloc[0]


def test_mandatory_indeterminate_never_becomes_qf0_even_with_nothing_else_flagged():
    rep0 = build_states_rep0([{"QC1": IND}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.INDETERMINATE
    assert result["QF"].iloc[0] != QualityFlag.QF0


@pytest.mark.parametrize(
    "optional_module_key,cause_module_value",
    [
        ("QC4", QCModule.QC4_ROLLING.value),
        ("QC5", QCModule.QC5_REPLICATES.value),
    ],
)
def test_optional_module_indeterminate_does_not_penalize_qf(optional_module_key, cause_module_value):
    rep0 = build_states_rep0([{optional_module_key: IND}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF0
    assert result["Review"].iloc[0] == "NO"
    assert result["QF_Cause"].iloc[0] is None
    assert result["QF_Evidence"].iloc[0] == f"{cause_module_value}:indeterminate"


def test_optional_indeterminate_coexists_with_a_real_alert_elsewhere():
    rep0 = build_states_rep0([{"QC5": IND, "QC2": ALERT}])
    result = integrate_qc(rep0)
    assert result["QF"].iloc[0] == QualityFlag.QF1
    assert result["QF_Cause"].iloc[0] == CAUSE_COHERENT
    assert f"{QCModule.QC5_REPLICATES.value}:indeterminate" in result["QF_Evidence"].iloc[0]


# ============================================================
# Causa principal e evidências secundárias
# ============================================================


def test_primary_cause_is_the_most_severe_module_others_are_evidence():
    rep0 = build_states_rep0([{"QC2": CRITICAL, "QC3": ALERT, "QC4": ALERT, "QC5": ALERT}])
    result = integrate_qc(rep0)

    assert result["QF_Cause"].iloc[0] == CAUSE_COHERENT  # QC2, único CRITICAL
    evidence = result["QF_Evidence"].iloc[0].split(";")
    assert set(evidence) == {CAUSE_INCOHERENT, CAUSE_ROLLING, CAUSE_REPLICA}


def test_primary_cause_tie_break_uses_module_order_when_severity_ties():
    # QC3 e QC5 ambos CRITICAL -- QC3 vem primeiro na ordem QC1..QC5.
    rep0 = build_states_rep0([{"QC3": CRITICAL, "QC5": CRITICAL}])
    result = integrate_qc(rep0)

    assert result["QF_Cause"].iloc[0] == CAUSE_INCOHERENT
    assert result["QF_Evidence"].iloc[0] == CAUSE_REPLICA
    assert result["QF"].iloc[0] == QualityFlag.QF3  # 2 CRITICALs


def test_qc1_cause_comes_from_qc1_cause_column_not_a_static_code():
    rep0 = build_states_rep0([{"QC1": ALERT, "QC1_Cause": CAUSE_ARGON}])
    result = integrate_qc(rep0)
    assert result["QF_Cause"].iloc[0] == CAUSE_ARGON


# ============================================================
# integrate_qc -- validação e não-mutação
# ============================================================


def test_integrate_qc_does_not_mutate_input_dataframe():
    rep0 = build_states_rep0([{"QC2": ALERT}])
    original_columns = list(rep0.columns)
    integrate_qc(rep0)
    assert list(rep0.columns) == original_columns


def test_integrate_qc_raises_on_missing_state_column():
    rep0 = pd.DataFrame({"QC1_State": [OK], "QC1_Cause": [np.nan]})
    with pytest.raises(ValueError, match="QC2_State"):
        integrate_qc(rep0)


# ============================================================
# run_qc -- pipeline completo ponta a ponta (dado sintético)
# ============================================================


def build_raw_sheet_10kv() -> pd.DataFrame:
    """
    Aba bruta sintética 10 kV com Rep0 + Rep1 para 6 posições físicas --
    exercita QC1-QC5 e integrate_qc de ponta a ponta via run_qc. Uma sétima
    posição só tem Rep0 e Throughput ausente (dado crítico obrigatório
    faltante -> deve sobreviver ao pipeline inteiro como QF_INDETERMINATE,
    nunca QF0 -- achado C2).
    """
    rows = []
    for i in range(6):
        rows.append(
            {
                "Spectrum": f"core-T01-{i}",
                "CoreDepth": float(10 + i * 10),
                "CompositeDepth (mm)": float(10 + i * 10),
                "Replicate Nr Count": "Rep0",
                "Throughput": 1000.0 + i,
                "Ar-Ka Area": 50.0 + i,
                "Rh-La Area": 500.0 + i,
                "Rh-La-Inc Area": 200.0 + i,
                "Al-Ka Area": 100.0 + i,
            }
        )
        rows.append(
            {
                "Spectrum": f"core-T01-{i}",
                "CoreDepth": float(10 + i * 10),
                "CompositeDepth (mm)": np.nan,
                "Replicate Nr Count": "Rep1",
                "Throughput": 1001.0 + i,
                "Ar-Ka Area": 51.0 + i,
                "Rh-La Area": 501.0 + i,
                "Rh-La-Inc Area": 201.0 + i,
                "Al-Ka Area": 101.0 + i,
            }
        )
    rows.append(
        {
            "Spectrum": "core-T01-6",
            "CoreDepth": 80.0,
            "CompositeDepth (mm)": 80.0,
            "Replicate Nr Count": "Rep0",
            "Throughput": np.nan,
            "Ar-Ka Area": 56.0,
            "Rh-La Area": 506.0,
            "Rh-La-Inc Area": 206.0,
            "Al-Ka Area": 106.0,
        }
    )
    return pd.DataFrame(rows)


def test_run_qc_end_to_end_synthetic_10kv():
    df = build_raw_sheet_10kv()

    result = run_qc(df, "10kV")

    # colunas originais preservadas sem alteração
    rep0_throughput = df.loc[df["Replicate Nr Count"] == "Rep0", "Throughput"].to_numpy(dtype=float)
    np.testing.assert_array_equal(result["Throughput"].to_numpy(dtype=float), rep0_throughput)

    for col in [
        "QC1_State", "QC2_State", "QC3_State", "QC4_State", "QC5_State",
        "QF", "QF_Cause", "QF_Evidence", "Review",
    ]:
        assert col in result.columns

    # a posição com Throughput ausente fica indeterminada, nunca QF0
    indeterminate_row = result[result["Spectrum"] == "core-T01-6"].iloc[0]
    assert indeterminate_row["QF"] == QualityFlag.INDETERMINATE
    assert indeterminate_row["Review"] == "YES"

    # QC5 encontrou as réplicas Rep1 (prova de que run_qc recebeu a aba
    # bruta, não só Rep0 -- se recebesse só Rep0, todo mundo cairia em
    # NOT_APPLICABLE aqui).
    other_rows = result[result["Spectrum"] != "core-T01-6"]
    assert (other_rows["QC5_State"] != QCState.NOT_APPLICABLE).all()


def test_run_qc_needs_the_raw_sheet_not_rep0_only_for_qc5_to_work():
    # Documenta por que o contrato de run_qc exige a aba bruta (ver
    # docstring): passar só Rep0 não é erro, mas silenciosamente esvazia
    # QC5 inteiro (nenhuma réplica para casar).
    df = build_raw_sheet_10kv()
    rep0_only = df[df["Replicate Nr Count"] == "Rep0"].copy()

    result = run_qc(rep0_only, "10kV")

    other_rows = result[result["Spectrum"] != "core-T01-6"]
    assert (other_rows["QC5_State"] == QCState.NOT_APPLICABLE).all()


def test_run_qc_unknown_energy_raises():
    df = build_raw_sheet_10kv()
    with pytest.raises(ValueError, match="Energia desconhecida"):
        run_qc(df, "15kV")
