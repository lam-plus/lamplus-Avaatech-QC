"""
LAM+ Core QC V2 — qc_core.py

Responsabilidade: cálculos QC1-QC5 e integração dos estados em um Quality
Flag (QF) por contagem. Lib pura — sem dependência de UI (Streamlit) e sem
importar nada de LEGACY/.

Módulos do núcleo inicial (ver DEVELOPMENT.md, seção 3):
    QC1 — Instrument Stability   (qc_instrument_stability)
    QC2 — Coherent Scatter       (qc_coherent_scatter)
    QC3 — Incoherent Scatter     (qc_incoherent_scatter)
    QC4 — Rolling QC             (qc_rolling)
    QC5 — Replicates             (qc_replicates)

Cada módulo individual recebe/retorna um DataFrame Rep0 com colunas
adicionadas (nunca remove ou sobrescreve colunas originais do instrumento).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from qc_config import (
    CAUSE_ARGON,
    CAUSE_COHERENT,
    CAUSE_INCOHERENT,
    CAUSE_MISSING_DATA,
    CAUSE_REPLICA,
    CAUSE_ROLLING,
    CAUSE_THROUGHPUT,
    ELEMENTS_REPLICATES,
    ENERGY_VARIABLES,
    QCModule,
    QCState,
    QualityFlag,
    REPLICATE_KEY_COLS,
    ROLLING_WINDOW,
    ROLLING_Z_ALERT,
    RPD_CRITICAL,
    RPD_WARNING,
    SUPPORTED_ENERGIES,
    Z_CRITICAL,
    Z_WARNING,
)
from qc_io import select_rep0


def _energy_variables(energy: str) -> dict[str, str | None]:
    """Valida `energy` e devolve o dict de variáveis físicas correspondente."""
    if energy not in ENERGY_VARIABLES:
        raise ValueError(
            f"Energia desconhecida: '{energy}'. Válidas: {list(SUPPORTED_ENERGIES)}."
        )
    return ENERGY_VARIABLES[energy]


# ============================================================
# FUNÇÕES ESTATÍSTICAS DE BASE
# ============================================================


def robust_zscore(values: np.ndarray) -> np.ndarray:
    """
    Z-score robusto baseado em MAD (mediana dos desvios absolutos).

    Entrada:
        values: array numérico 1D, pode conter NaN.

    Saída:
        Array do mesmo tamanho de `values`, com NaN preservado nas mesmas
        posições (NaN nunca produz um z-score numérico).

    Contrato:
        - Se MAD == 0 (todos os valores válidos idênticos), retorna zeros
          nas posições válidas, não infinito nem NaN.
    """
    values = np.asarray(values, dtype=float)
    if np.all(np.isnan(values)):
        return np.full(values.shape, np.nan)

    median = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - median))
    if mad == 0:
        return np.where(np.isnan(values), np.nan, 0.0)
    return 0.6745 * (values - median) / mad


def calculate_rpd(values: np.ndarray) -> float:
    """
    Relative Percent Difference (RPD) entre réplicas de uma mesma posição.

    Entrada:
        values: valores medidos (uma réplica cada) na mesma posição física.

    Saída:
        RPD em percentual (float), ou NaN quando não computável.

    Contrato:
        - Retorna NaN se houver menos de 2 valores não-NaN.
        - Retorna NaN se a média dos valores válidos for zero (evita
          divisão por zero — nunca deve virar OK por engano).
    """
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return np.nan
    mean = values.mean()
    if mean == 0:
        return np.nan
    return np.abs(values.max() - values.min()) / np.abs(mean) * 100.0


# ============================================================
# CLASSIFICAÇÃO DE ESTADO POR MÓDULO
# ============================================================


def classify_zscore(z: float) -> QCState:
    """
    Classifica um z-score em OK/ALERT/CRITICAL (limiares Z_WARNING/
    Z_CRITICAL de qc_config).

    Contrato:
        - NaN nunca é classificado aqui diretamente: quem chama deve
          garantir que dado crítico ausente já foi desviado para
          QCState.INDETERMINATE antes de chegar a esta função (ver
          integrate_qc). Chamar com NaN é um erro de uso.
    """
    if pd.isna(z):
        raise ValueError(
            "classify_zscore não aceita NaN diretamente — trate dado "
            "crítico ausente como QCState.INDETERMINATE antes de chamar "
            "esta função."
        )
    z = abs(z)
    if z >= Z_CRITICAL:
        return QCState.CRITICAL
    if z >= Z_WARNING:
        return QCState.ALERT
    return QCState.OK


def classify_rolling(delta_z: float) -> QCState:
    """
    Classifica o z-score de deriva do QC4 em OK/ALERT (sem CRITICAL,
    limiar ROLLING_Z_ALERT de qc_config).
    """
    if pd.isna(delta_z):
        raise ValueError(
            "classify_rolling não aceita NaN diretamente — trate dado "
            "crítico ausente como QCState.INDETERMINATE antes de chamar "
            "esta função."
        )
    if abs(delta_z) >= ROLLING_Z_ALERT:
        return QCState.ALERT
    return QCState.OK


def classify_rpd(mean_rpd: float) -> QCState:
    """
    Classifica o RPD médio entre réplicas em OK/ALERT/CRITICAL (limiares
    RPD_WARNING/RPD_CRITICAL de qc_config).

    Contrato:
        - NaN (nenhuma réplica casada para essa posição) é
          QCState.NOT_APPLICABLE — ausência legítima de réplica adicional
          para comparar, não dado crítico faltante (decisão confirmada na
          Etapa 4: distinto de OK, que significaria "comparei e está
          reprodutível"). Diferente de classify_zscore/classify_rolling,
          aqui o NaN é tratado internamente em vez de delegado ao chamador
          — é um caso de negócio esperado, não um erro de uso.
    """
    if pd.isna(mean_rpd):
        return QCState.NOT_APPLICABLE
    if mean_rpd >= RPD_CRITICAL:
        return QCState.CRITICAL
    if mean_rpd >= RPD_WARNING:
        return QCState.ALERT
    return QCState.OK


# ============================================================
# MÓDULOS QC INDIVIDUAIS
# ============================================================


def qc_instrument_stability(rep0: pd.DataFrame, energy: str) -> pd.DataFrame:
    """
    QC1 — Instrument Stability: z-score robusto do Throughput, combinado
    com o pico de Argônio quando presente na energia/arquivo.

    Entrada:
        rep0: DataFrame já filtrado para Rep0, ordenado por profundidade.
        energy: uma de SUPPORTED_ENERGIES.

    Saída:
        Cópia de `rep0` com as colunas adicionadas (nomes exatos a
        confirmar na Etapa 3): z-score do Throughput, z-score do Argônio
        (NaN quando a energia não mede Argônio) e o z-score combinado que
        alimenta a classificação de estado deste módulo.

    Contrato:
        - Não modifica `rep0` original nem colunas do instrumento.
        - Quando Argônio não está disponível para a energia (ou ausente do
          arquivo), o resultado deve ser equivalente a usar Throughput
          isoladamente.
    """
    cfg = _energy_variables(energy)
    throughput_col = cfg["throughput"]
    argon_col = cfg["argon"]

    result = rep0.copy()
    throughput_raw = result[throughput_col].to_numpy(dtype=float)
    result["Throughput_z"] = robust_zscore(throughput_raw)

    has_argon = argon_col is not None and argon_col in result.columns
    if has_argon:
        result["Argon_z"] = robust_zscore(result[argon_col].to_numpy(dtype=float))
    else:
        result["Argon_z"] = np.nan

    throughput_z = result["Throughput_z"].to_numpy()
    argon_z = result["Argon_z"].to_numpy()

    if has_argon:
        abs_throughput = np.abs(throughput_z)
        abs_argon = np.abs(argon_z)
        # NaN nunca "vence": um lado ausente não é escolhido como pior.
        argon_is_worse = np.where(np.isnan(abs_argon), -1, abs_argon) > np.where(
            np.isnan(abs_throughput), -1, abs_throughput
        )
        instrument_z = np.where(argon_is_worse, argon_z, throughput_z)
    else:
        argon_is_worse = np.zeros(len(result), dtype=bool)
        instrument_z = throughput_z

    result["Instrument_z"] = instrument_z

    throughput_missing = np.isnan(throughput_raw)
    states = []
    causes = []
    for i in range(len(result)):
        if throughput_missing[i]:
            # Checagem sobre a coluna crua, não sobre Instrument_z: o
            # fallback pelo Argônio não pode mascarar Throughput ausente.
            states.append(QCState.INDETERMINATE)
            causes.append(CAUSE_MISSING_DATA)
            continue
        state = classify_zscore(instrument_z[i])
        states.append(state)
        if state == QCState.OK:
            causes.append(None)
        elif argon_is_worse[i]:
            causes.append(CAUSE_ARGON)
        else:
            causes.append(CAUSE_THROUGHPUT)

    result["QC1_State"] = states
    result["QC1_Cause"] = causes
    return result


def _qc_pointwise_scatter(
    rep0: pd.DataFrame,
    energy: str,
    variable_key: str,
    z_col: str,
    state_col: str,
) -> pd.DataFrame:
    """
    Implementação compartilhada por qc_coherent_scatter/qc_incoherent_scatter:
    z-score robusto pontual de uma única variável, com módulo
    estruturalmente não aplicável quando `cfg[variable_key] is None`.
    """
    cfg = _energy_variables(energy)
    column = cfg[variable_key]

    result = rep0.copy()
    if column is None:
        result[z_col] = np.nan
        result[state_col] = QCState.NOT_APPLICABLE
        return result

    raw = result[column].to_numpy(dtype=float)
    z = robust_zscore(raw)
    result[z_col] = z

    missing = np.isnan(raw)
    result[state_col] = [
        QCState.INDETERMINATE if missing[i] else classify_zscore(z[i])
        for i in range(len(result))
    ]
    return result


def qc_coherent_scatter(rep0: pd.DataFrame, energy: str) -> pd.DataFrame:
    """
    QC2 — Coherent Scatter: z-score robusto da variável de espalhamento
    coerente da energia (ver qc_config.ENERGY_VARIABLES["coherent"]).

    Contrato:
        - Quando a energia não mede espalhamento coerente (coherent is
          None, ex. 50 kV), o módulo é estruturalmente não aplicável: a(s)
          coluna(s) resultante(s) deve(m) permitir distinguir esse caso de
          um dado simplesmente ausente no arquivo (ver
          qc_config.QCState.NOT_APPLICABLE).
    """
    return _qc_pointwise_scatter(rep0, energy, "coherent", "Coherent_z", "QC2_State")


def qc_incoherent_scatter(rep0: pd.DataFrame, energy: str) -> pd.DataFrame:
    """
    QC3 — Incoherent Scatter: z-score robusto da variável de espalhamento
    incoerente da energia (ver qc_config.ENERGY_VARIABLES["incoherent"]).

    Mesma degradação graciosa de qc_coherent_scatter quando a energia não
    mede o parâmetro.
    """
    return _qc_pointwise_scatter(rep0, energy, "incoherent", "Incoherent_z", "QC3_State")


def qc_rolling(rep0: pd.DataFrame, energy: str, window: int = None) -> pd.DataFrame:
    """
    QC4 — Rolling QC: detecta deriva local via média móvel centrada.

    Entrada:
        rep0: DataFrame Rep0 ordenado por profundidade.
        energy: uma de SUPPORTED_ENERGIES.
        window: tamanho da janela móvel; usa qc_config.ROLLING_WINDOW
            quando None.

    Contrato:
        - Ignora graciosamente qualquer variável de rolling ausente do
          arquivo para a energia dada.
        - Pressupõe que `rep0` já está ordenado por profundidade; não
          reordena internamente.
    """
    cfg = _energy_variables(energy)
    incoherent_col = cfg["incoherent"]
    window = ROLLING_WINDOW if window is None else window

    result = rep0.copy()

    if incoherent_col is None:
        result["Rolling_Mean"] = np.nan
        result["Rolling_Delta"] = np.nan
        result["Rolling_Delta_Z"] = np.nan
        result["QC4_State"] = QCState.NOT_APPLICABLE
        return result

    raw = result[incoherent_col].to_numpy(dtype=float)
    rolling_mean = result[incoherent_col].rolling(
        window=window, center=True, min_periods=1
    ).mean()
    result["Rolling_Mean"] = rolling_mean

    delta = result[incoherent_col] - rolling_mean
    result["Rolling_Delta"] = delta

    delta_z = robust_zscore(delta.to_numpy(dtype=float))
    result["Rolling_Delta_Z"] = delta_z

    missing = np.isnan(raw)
    result["QC4_State"] = [
        QCState.INDETERMINATE if missing[i] else classify_rolling(delta_z[i])
        for i in range(len(result))
    ]
    return result


def qc_replicates(df: pd.DataFrame, rep0: pd.DataFrame) -> pd.DataFrame:
    """
    QC5 — Replicates: RPD médio entre réplicas por posição de medição.

    Entrada:
        df: DataFrame bruto da aba completa (todas as réplicas).
        rep0: DataFrame já filtrado para Rep0 (resultado dos módulos
            QC1-QC4), ao qual o RPD médio será associado.

    Saída:
        Cópia de `rep0` com a coluna de RPD médio adicionada.

    Contrato:
        - Réplicas são casadas por qc_config.REPLICATE_KEY_COLS (chave
          física), nunca por DEPTH_COL (ver plano-de-acao.md, achado C1).
        - Posições sem réplica adicional (só Rep0) recebem RPD = NaN, não
          erro nem CRITICAL.
    """
    key_cols = list(REPLICATE_KEY_COLS)
    available_elements = [el for el in ELEMENTS_REPLICATES if el in df.columns]

    replica_rows = []
    for key, subset in df.groupby(key_cols):
        if len(subset) < 2:
            # Só Rep0 nesta posição — nada para comparar (ver classify_rpd:
            # vira QCState.NOT_APPLICABLE, não erro nem penalidade).
            continue
        rpds = [calculate_rpd(subset[el].to_numpy(dtype=float)) for el in available_elements]
        mean_rpd = np.nanmean(rpds) if rpds else np.nan
        replica_rows.append((*key, mean_rpd))

    replica_df = pd.DataFrame(replica_rows, columns=[*key_cols, "Mean_RPD"])
    result = rep0.merge(replica_df, on=key_cols, how="left")

    result["QC5_State"] = [classify_rpd(v) for v in result["Mean_RPD"]]
    return result


# ============================================================
# INTEGRAÇÃO DOS ESTADOS E QUALITY FLAG
# ============================================================


# Módulos cujo INDETERMINATE por linha força QualityFlag.INDETERMINATE
# incondicionalmente (protocolo v4.2 + decisão confirmada nesta etapa: QC4
# fica de fora porque sua única fonte de NaN é a mesma coluna bruta que já
# torna QC3 indeterminado na mesma linha — não há cobertura perdida).
MANDATORY_MODULES = (
    QCModule.QC1_INSTRUMENT_STABILITY,
    QCModule.QC2_COHERENT_SCATTER,
    QCModule.QC3_INCOHERENT_SCATTER,
)

# Módulos cujo INDETERMINATE por linha nunca penaliza o QF — só vira
# evidência (ver DEVELOPMENT.md 4.2: "ausência legítima" não é dado
# crítico faltante quando o módulo é opcional).
OPTIONAL_MODULES = (
    QCModule.QC4_ROLLING,
    QCModule.QC5_REPLICATES,
)

# Ordem de prioridade dos módulos para desempate de causa principal (QC1
# antes de QC2 etc.) quando dois ou mais módulos compartilham a mesma
# severidade (ex. dois CRITICAL na mesma linha).
MODULE_ORDER = MANDATORY_MODULES + OPTIONAL_MODULES

_STATE_COLUMN_BY_MODULE = {
    QCModule.QC1_INSTRUMENT_STABILITY: "QC1_State",
    QCModule.QC2_COHERENT_SCATTER: "QC2_State",
    QCModule.QC3_INCOHERENT_SCATTER: "QC3_State",
    QCModule.QC4_ROLLING: "QC4_State",
    QCModule.QC5_REPLICATES: "QC5_State",
}

# Causa estática atribuída a um módulo em ALERT/CRITICAL/INDETERMINATE-
# opcional. QC1 é o único módulo com causa variável por linha (throughput
# vs. argônio, "pior dos dois" — ver qc_instrument_stability/QC1_Cause) e
# por isso não entra neste mapa.
_MODULE_CAUSE = {
    QCModule.QC2_COHERENT_SCATTER: CAUSE_COHERENT,
    QCModule.QC3_INCOHERENT_SCATTER: CAUSE_INCOHERENT,
    QCModule.QC4_ROLLING: CAUSE_ROLLING,
    QCModule.QC5_REPLICATES: CAUSE_REPLICA,
}


def compute_module_states(rep0: pd.DataFrame, energy: str) -> pd.DataFrame:
    """
    Deriva o estado (QCState) de cada módulo QC1-QC5 para cada linha de
    `rep0`, a partir das colunas já calculadas pelos qc_* individuais.

    Entrada:
        rep0: DataFrame Rep0 após passar por qc_instrument_stability,
            qc_coherent_scatter, qc_incoherent_scatter, qc_rolling e
            qc_replicates.
        energy: uma de SUPPORTED_ENERGIES — usada só para validar a
            entrada (ver _energy_variables); os estados por módulo já
            encodam a aplicabilidade por energia (NOT_APPLICABLE), então
            não influenciam o cálculo aqui.

    Saída:
        Cópia de `rep0` com a coluna "QC_Module_States": um dict por linha
        mapeando qc_config.QCModule -> QCState (OK, ALERT, CRITICAL,
        NOT_APPLICABLE ou INDETERMINATE — nunca NaN cru).

    Contrato:
        - Módulos não aplicáveis à energia (QC2/QC3 quando a energia não
          mede o parâmetro) recebem NOT_APPLICABLE, tratados como neutros
          na contagem de QF — nunca penalizam nem geram indeterminado.
        - Dado obrigatório ausente (não estrutural) nunca produz OK.
        - Levanta ValueError se alguma coluna QC1_State..QC5_State
          estiver ausente — chame os módulos qc_* antes desta função.
    """
    _energy_variables(energy)

    missing_cols = [
        col for col in _STATE_COLUMN_BY_MODULE.values() if col not in rep0.columns
    ]
    if missing_cols:
        raise ValueError(
            f"Colunas de estado ausentes: {', '.join(missing_cols)}. Rode "
            "qc_instrument_stability, qc_coherent_scatter, "
            "qc_incoherent_scatter, qc_rolling e qc_replicates antes de "
            "compute_module_states."
        )

    result = rep0.copy()
    result["QC_Module_States"] = [
        {
            module: result.at[idx, col]
            for module, col in _STATE_COLUMN_BY_MODULE.items()
        }
        for idx in result.index
    ]
    return result


def _module_cause(module: QCModule, row: pd.Series) -> str:
    """Código CAUSE_* de um módulo em ALERT/CRITICAL/INDETERMINATE nesta
    linha. QC1 usa a causa já calculada por linha (QC1_Cause); os demais
    módulos usam uma causa estática (_MODULE_CAUSE)."""
    if module == QCModule.QC1_INSTRUMENT_STABILITY:
        cause = row["QC1_Cause"]
        return cause if pd.notna(cause) else CAUSE_MISSING_DATA
    return _MODULE_CAUSE[module]


def integrate_qc(rep0: pd.DataFrame) -> pd.DataFrame:
    """
    Integra os estados de QC1-QC5 em um Quality Flag (QF) por linha, por
    contagem de ALERT/CRITICAL (protocolo v4.2 — ver plano-de-acao.md,
    Etapa 5, "Regra inicial proposta").

    Entrada:
        rep0: DataFrame Rep0 já passado por qc_instrument_stability,
            qc_coherent_scatter, qc_incoherent_scatter, qc_rolling e
            qc_replicates (precisa das colunas QC1_State..QC5_State e
            QC1_Cause).

    Saída:
        Cópia de `rep0` com as colunas:
            - "QC_Alert_Count" / "QC_Critical_Count": contagem de módulos
              em ALERT/CRITICAL nesta linha (NOT_APPLICABLE e INDETERMINATE
              nunca contam).
            - "QF": qc_config.QualityFlag (QF0-QF3 ou INDETERMINATE).
            - "QF_Cause": código CAUSE_* do módulo com o estado mais grave
              (None quando QF0 sem nenhum módulo opcional indeterminado).
            - "QF_Evidence": string com os demais módulos em ALERT/CRITICAL
              (códigos CAUSE_*) e, quando houver, módulos opcionais
              INDETERMINATE (formato "{QCModule.value}:indeterminate") —
              todos separados por ";"; vazia quando não há nada a reportar.
            - "Review": "YES" para QF2, QF3 e INDETERMINATE; "NO" para QF0
              e QF1.

    Contrato:
        - QC1/QC2/QC3 (MANDATORY_MODULES) em INDETERMINATE força
          QualityFlag.INDETERMINATE incondicionalmente — nunca QF0 (ver
          plano-de-acao.md, achado C2).
        - QC4/QC5 (OPTIONAL_MODULES) em INDETERMINATE nunca penaliza o QF
          — só é registrado em QF_Evidence.
        - Módulos NOT_APPLICABLE não contam nem para ALERT nem para
          CRITICAL, nem forçam INDETERMINATE.
        - Resultado é determinístico: mesma entrada produz sempre o mesmo
          QF.
    """
    required_cols = [*_STATE_COLUMN_BY_MODULE.values(), "QC1_Cause"]
    missing_cols = [col for col in required_cols if col not in rep0.columns]
    if missing_cols:
        raise ValueError(
            f"Colunas ausentes para integrate_qc: {', '.join(missing_cols)}. "
            "Rode qc_instrument_stability, qc_coherent_scatter, "
            "qc_incoherent_scatter, qc_rolling e qc_replicates antes de "
            "integrate_qc."
        )

    result = rep0.copy()

    alert_counts: list[int] = []
    critical_counts: list[int] = []
    qfs: list[QualityFlag] = []
    primary_causes: list[str | None] = []
    evidences: list[str] = []
    reviews: list[str] = []

    for idx, row in result.iterrows():
        states = {module: row[col] for module, col in _STATE_COLUMN_BY_MODULE.items()}

        alerts = [m for m in MODULE_ORDER if states[m] == QCState.ALERT]
        criticals = [m for m in MODULE_ORDER if states[m] == QCState.CRITICAL]
        mandatory_indeterminate = [
            m for m in MANDATORY_MODULES if states[m] == QCState.INDETERMINATE
        ]
        optional_indeterminate = [
            m for m in OPTIONAL_MODULES if states[m] == QCState.INDETERMINATE
        ]

        alert_counts.append(len(alerts))
        critical_counts.append(len(criticals))

        evidence_parts = [f"{m.value}:indeterminate" for m in optional_indeterminate]

        if mandatory_indeterminate:
            qf = QualityFlag.INDETERMINATE
            primary_cause = CAUSE_MISSING_DATA
            evidence_parts.extend(_module_cause(m, row) for m in criticals + alerts)
        elif not alerts and not criticals:
            qf = QualityFlag.QF0
            primary_cause = None
        else:
            if len(alerts) == 1 and not criticals:
                qf = QualityFlag.QF1
            elif len(criticals) >= 2 or len(alerts) >= 4:
                qf = QualityFlag.QF3
            else:
                qf = QualityFlag.QF2

            severity = {m: 2 for m in criticals} | {m: 1 for m in alerts}
            flagged = criticals + alerts
            primary_module = min(
                flagged, key=lambda m: (-severity[m], MODULE_ORDER.index(m))
            )
            primary_cause = _module_cause(primary_module, row)
            evidence_parts.extend(
                _module_cause(m, row) for m in flagged if m != primary_module
            )

        qfs.append(qf)
        primary_causes.append(primary_cause)
        evidences.append(";".join(evidence_parts))
        reviews.append(
            "YES"
            if qf in (QualityFlag.QF2, QualityFlag.QF3, QualityFlag.INDETERMINATE)
            else "NO"
        )

    result["QC_Alert_Count"] = alert_counts
    result["QC_Critical_Count"] = critical_counts
    result["QF"] = qfs
    result["QF_Cause"] = primary_causes
    result["QF_Evidence"] = evidences
    result["Review"] = reviews
    return result


def run_qc(df: pd.DataFrame, energy: str) -> pd.DataFrame:
    """
    Executa o pipeline QC completo (QC1-QC5 + integração) sobre o
    DataFrame bruto de UMA aba/energia.

    Entrada:
        df: DataFrame bruto de uma aba inteira (todas as réplicas —
            Rep0/Rep1/Rep2, como retornado por qc_io.read_workbook), já
            validado por qc_io.check_columns. Precisa ser a aba bruta, não
            só Rep0: qc_replicates (QC5) casa réplicas físicas entre
            Rep0/Rep1/Rep2, e não encontraria nenhuma se `df` já viesse
            filtrado.
        energy: uma de SUPPORTED_ENERGIES — determina quais variáveis e
            colunas críticas se aplicam (ver qc_config.ENERGY_VARIABLES).

    Saída:
        DataFrame Rep0 com todos os campos QC calculados: z-scores,
        estados por módulo, RPD, QF, causa principal e evidências.

    Contrato:
        - Não altera as colunas originais do instrumento; resultados de QC
          são sempre colunas adicionadas, identificáveis.
        - Não importa nem depende de LEGACY/ em nenhum ponto.
        - Seleciona Rep0 internamente via qc_io.select_rep0.
    """
    rep0 = select_rep0(df)
    rep0 = qc_instrument_stability(rep0, energy)
    rep0 = qc_coherent_scatter(rep0, energy)
    rep0 = qc_incoherent_scatter(rep0, energy)
    rep0 = qc_rolling(rep0, energy)
    rep0 = qc_replicates(df, rep0)
    rep0 = integrate_qc(rep0)
    return rep0
