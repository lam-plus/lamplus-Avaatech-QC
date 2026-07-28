"""
LAM+ Core QC — qc_core.py
Quality Control Pipeline for Avaatech XRF Core Scanner

Igor Oliveira / LAM+

Uso:
    from qc_core import check_file, run_qc
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from scipy.spatial.distance import mahalanobis

from i18n import CHECK_MESSAGES, TEXTS

# ============================================================
# CONFIGURAÇÕES
# ============================================================

DEPTH_COL = "CompositeDepth (mm)"
REPLICATE_COL = "Replicate Nr Count"
ROLLING_WINDOW = 5

# Nome da coluna de profundidade local/por seção (reinicia a cada tubo de
# amostragem, ao contrário de DEPTH_COL que é contínua ao longo de todo o
# testemunho). Usada apenas como opção de exibição em qc_avaatech.py/
# report_pdf.py (eixo X dos gráficos, tabela, PDF) — NUNCA no cálculo do
# pipeline. Não confundir com REPLICATE_KEY_COLS abaixo, que usa o mesmo
# nome de coluna para outro propósito (casar réplicas) e não deve mudar.
CORE_DEPTH_COL = "CoreDepth"

# Pico de Argônio — reflete a qualidade da atmosfera entre tubo, amostra e
# detector (perda de hélio, entrada de ar, vedação). Só existe em modo 10 kV
# (protocolo v4.2, seção 5/8); tratado como opcional, igual a ELEMENTS_PCA —
# sua ausência nunca invalida QC1/QC4, só reduz ao comportamento anterior
# (Throughput sozinho).
ARGON_COL = "Ar-Ka Area"

# Variáveis usadas no QC4 (rolling). As três originais tendem a reagir juntas
# a um mesmo problema físico de medição (rachadura, bolha de ar, transição
# seco/úmido) — ver compute_scores/combine_rolling_vars. Ar-Ka Area (Argônio)
# entra como quarta variável opcional (qc_rolling ignora qualquer uma que não
# esteja presente no arquivo).
ROLLING_VARS = ["Throughput", "Rh-La Area", "Rh-La-Inc Area", ARGON_COL]

# CompositeDepth (mm) só é preenchido na primeira passada (Rep0); em Rep1/Rep2
# essa coluna vem nula. Spectrum + CoreDepth identificam a posição física de
# medição e estão sempre preenchidos em todas as réplicas — é essa combinação
# que QC5 usa para casar réplicas (ver REPLICATE_KEY_COLS).
REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]

REQUIRED_COLUMNS = [
    DEPTH_COL,
    REPLICATE_COL,
    "Throughput",
    "Rh-La Area",
    "Rh-La-Inc Area",
    *REPLICATE_KEY_COLS,
]

ELEMENTS_PCA = [
    "Al-Ka Area",
    "Si-Ka Area",
    "K -Ka Area",
    "Ca-Ka Area",
    "Ti-Ka Area",
    "Fe-Ka Area",
    "Mn-Ka Area",
    "Rb-Ka Area",
    "Sr-Ka Area",
    "Zr-Ka Area",
]

# PCA(n_components=2) exige >=2 features; a matriz de covariância das 2 PCs
# degenera com poucas amostras. Abaixo desses mínimos, QC6 é pulada com um
# score neutro em vez de travar o pipeline (ver qc_pca/compute_scores).
MIN_PCA_ELEMENTS = 2
MIN_PCA_ROWS = 3

ELEMENTS_REPLICATES = [
    "Al-Ka Area",
    "Si-Ka Area",
    "K -Ka Area",
    "Ca-Ka Area",
    "Ti-Ka Area",
    "Fe-Ka Area",
]

# Colunas cuja ausência (NaN) numa linha torna o QI dessa linha indeterminado
# (QC1-QC3 — sempre obrigatórias). QC5/QC6 já têm seus próprios fallbacks e
# não entram aqui de propósito (ver TODO.md achado C2).
CRITICAL_INPUT_COLS = ["Throughput", "Rh-La Area", "Rh-La-Inc Area"]

# QI mínimo para uma linha ser considerada "agregadamente OK" — usado tanto
# em compute_flags (QF=1 se abaixo disso) quanto em is_pointwise_flag (ver
# QUALITY FLAG) para distinguir flag disparado por critério pontual vs. QI.
QI_THRESHOLD_OK = 80

# Pesos do Quality Index — nomeados para permitir recalcular o QI só com os
# módulos disponíveis quando strict_missing_data=False (ver compute_scores).
QI_WEIGHTS = {
    "Score_Throughput": 0.25,
    "Score_RhLa": 0.15,
    "Score_RhLaInc": 0.20,
    "Score_Rolling": 0.20,
    "Score_Replica": 0.15,
    "Score_PCA": 0.05,
}

# Quality Flag distinto para linhas com dado crítico faltante — nunca deve
# ser confundido com QF=0 (OK) nem com os flags 1-3 (que indicam dado medido
# e avaliado como problemático). "ND" = não determinado.
QF_INDETERMINATE = 9

# Posição visual de cada QF (0-3 + indeterminado) ao plotar/tabular numa
# escala ordenada — QF_INDETERMINATE=9 não deve ser exibido na sua altura
# literal, ou pareceria "mais grave" que QF=3 numa escala 0-3.
QF_PLOT_ORDER = {0: 0, 1: 1, 2: 2, 3: 3, QF_INDETERMINATE: 4}

# Códigos de causa atribuídos a uma linha quando ela é flagrada (QF>=2 ou
# indeterminada). Usados por compute_flags (coluna QF_Causes) e traduzidos
# na UI/relatório via locales/*.json (chave "cause_<código>").
CAUSE_THROUGHPUT = "throughput"
CAUSE_ARGON = "argon"
CAUSE_RH_LA = "rh_la"
CAUSE_RH_LA_INC = "rh_la_inc"
CAUSE_ROLLING = "rolling"
CAUSE_PCA = "pca"
CAUSE_QI_LOW = "qi_low"
CAUSE_MISSING_DATA = "missing_data"
# Só usada no modo de contagem (use_count_mode) — no modo QI ponderado,
# réplicas influenciam apenas o QI (Score_Replica), sem critério pontual
# próprio em compute_flags, então nunca precisaram de uma causa dedicada.
CAUSE_REPLICA = "replica"

# ------------------------------------------------------------------------
# Modo alternativo de QF por contagem de módulos reprovados (protocolo v4.2,
# seção 11/apêndice `qc.py` — ver DEVELOPMENT.md). Opt-in via
# use_count_mode em compute_flags/run_qc; o modo QI ponderado continua
# sendo o default. Limiares próprios do protocolo v4.2 — distintos dos
# limiares (2/3) usados internamente pelo modo QI ponderado, que não são
# alterados por esta adição.
QC_OK = "OK"
QC_ALERT = "ALERT"
QC_CRITICAL = "CRITICAL"

COUNT_MODE_Z_WARNING = 2.5
COUNT_MODE_Z_CRITICAL = 3.5
# QC4 no modo de contagem só tem OK/ALERT (sem CRITICAL), conforme o
# protocolo v4.2 (classify_rolling do apêndice).
COUNT_MODE_ROLLING_Z_ALERT = 4.0
COUNT_MODE_RPD_WARNING = 10.0
COUNT_MODE_RPD_CRITICAL = 20.0

# ============================================================
# FUNÇÕES ESTATÍSTICAS
# ============================================================

def robust_zscore(x):
    """Z-score robusto baseado em MAD."""
    median = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - median))
    if mad == 0:
        return np.zeros(len(x))
    return 0.6745 * (x - median) / mad


def score_from_z(z):
    """Converte z-score em score 0-100."""
    return np.clip(100 - np.abs(z) * 15, 0, 100)


def calculate_rpd(values):
    """Relative Percent Difference entre réplicas."""
    values = np.array(values)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return np.nan
    mean = values.mean()
    if mean == 0:
        return np.nan
    return np.abs(values.max() - values.min()) / np.abs(mean) * 100


# ============================================================
# CHECK DE CONSISTÊNCIA
# ============================================================

def check_file(df, lang="pt"):
    """
    Valida estrutura do DataFrame antes de rodar o pipeline.

    Args:
        lang: "pt" ou "en" — idioma das mensagens retornadas.

    Retorna:
        errors   : list[str] — erros que bloqueiam a execução
        warnings : list[str] — avisos que permitem continuar
    """
    errors = []
    warnings = []

    def msg(key, **kwargs):
        return CHECK_MESSAGES[key][lang].format(**kwargs)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(msg("missing_columns", cols=missing))

    if REPLICATE_COL in df.columns:
        if "Rep0" not in df[REPLICATE_COL].values:
            errors.append(msg("missing_rep0", col=REPLICATE_COL))
        else:
            n_rep0 = (df[REPLICATE_COL] == "Rep0").sum()
            if n_rep0 < MIN_PCA_ROWS:
                warnings.append(msg("pca_too_few_rows", n=n_rep0, min=MIN_PCA_ROWS))

    available_pca = [e for e in ELEMENTS_PCA if e in df.columns]
    missing_pca = [e for e in ELEMENTS_PCA if e not in df.columns]
    if len(available_pca) < MIN_PCA_ELEMENTS:
        warnings.append(msg("pca_unavailable", n=len(available_pca), min=MIN_PCA_ELEMENTS))
    elif missing_pca:
        warnings.append(msg("missing_pca", els=missing_pca))

    missing_rep = [e for e in ELEMENTS_REPLICATES if e not in df.columns]
    if missing_rep:
        warnings.append(msg("missing_rep", els=missing_rep))

    if "Throughput" in df.columns:
        n_zero = (df["Throughput"].fillna(0) == 0).sum()
        if n_zero > 0:
            warnings.append(msg("zero_throughput", n=n_zero))

    if DEPTH_COL in df.columns and REPLICATE_COL in df.columns:
        rep0 = df[df[REPLICATE_COL] == "Rep0"]
        dup = rep0[DEPTH_COL].duplicated().sum()
        if dup > 0:
            warnings.append(msg("dup_depths", n=dup))

    return errors, warnings


# ============================================================
# MÓDULOS QC INDIVIDUAIS
# ============================================================

def qc_throughput(rep0):
    """
    QC1 — Instrument Stability: z-score robusto do Throughput, combinado com
    o pico de Argônio quando presente no arquivo (protocolo v4.2, seção 5).

    "Combinado" = pior dos dois: rep0["Instrument_z"] é o z-score (Throughput
    ou Argônio) de maior magnitude absoluta linha a linha — um problema de
    vedação/atmosfera pode aparecer só no Argônio, sem necessariamente
    derrubar o Throughput, e vice-versa. rep0["Throughput_z"]/["Argon_z"]
    continuam disponíveis individualmente (diagnóstico); Instrument_z é quem
    alimenta Score_Throughput/compute_flags.
    """
    rep0 = rep0.copy()
    rep0["Throughput_z"] = robust_zscore(rep0["Throughput"])

    if ARGON_COL in rep0.columns:
        rep0["Argon_z"] = robust_zscore(rep0[ARGON_COL])
        abs_throughput = rep0["Throughput_z"].abs()
        abs_argon = rep0["Argon_z"].abs()
        # NaN nunca "vence" (fillna(-1) garante que um lado ausente não seja
        # escolhido como o pior por engano).
        argon_is_worse = abs_argon.fillna(-1) > abs_throughput.fillna(-1)
        rep0["Instrument_z"] = np.where(argon_is_worse, rep0["Argon_z"], rep0["Throughput_z"])
    else:
        rep0["Argon_z"] = np.nan
        rep0["Instrument_z"] = rep0["Throughput_z"]

    return rep0


def qc_rh_la(rep0):
    """QC2 — Z-score robusto do Rh-Lα."""
    rep0 = rep0.copy()
    rep0["RhLa_z"] = robust_zscore(rep0["Rh-La Area"])
    return rep0


def qc_rh_la_inc(rep0):
    """QC3 — Z-score robusto do Rh-Lα-Inc."""
    rep0 = rep0.copy()
    rep0["RhLaInc_z"] = robust_zscore(rep0["Rh-La-Inc Area"])
    return rep0


def qc_rolling(rep0, window=ROLLING_WINDOW):
    """
    QC4 — Rolling QC: detecta deriva local via média móvel.

    Itera ROLLING_VARS (Throughput, Rh-La Area, Rh-La-Inc Area, Ar-Ka Area);
    uma variável ausente do arquivo (ex. Ar-Ka Area fora do modo 10 kV) é
    simplesmente ignorada — mesmo padrão de degradação graciosa usado em
    qc_pca/qc_replicates.
    """
    rep0 = rep0.copy()
    for var in ROLLING_VARS:
        if var not in rep0.columns:
            continue
        roll = rep0[var].rolling(window=window, center=True, min_periods=1).mean()
        rep0[f"{var}_rolling"] = roll
        rep0[f"{var}_delta"] = rep0[var] - roll
        rep0[f"{var}_delta_z"] = robust_zscore(rep0[f"{var}_delta"])
    return rep0


def qc_replicates(df, rep0):
    """
    QC5 — RPD médio entre réplicas por posição de medição.

    Réplicas (Rep0/Rep1/Rep2/...) são casadas por REPLICATE_KEY_COLS
    (Spectrum + CoreDepth), não por DEPTH_COL: CompositeDepth (mm) só é
    calculado na primeira passada e fica nulo nas réplicas seguintes.
    """
    replica_stats = []
    for key, subset in df.groupby(REPLICATE_KEY_COLS):
        if len(subset) < 2:
            continue
        rpds = []
        for el in ELEMENTS_REPLICATES:
            if el not in subset.columns:
                continue
            rpd = calculate_rpd(subset[el].values)
            rpds.append(rpd)
        mean_rpd = np.nanmean(rpds) if rpds else np.nan
        replica_stats.append([*key, mean_rpd])

    replica_df = pd.DataFrame(replica_stats, columns=[*REPLICATE_KEY_COLS, "Mean_RPD"])
    rep0 = rep0.merge(replica_df, on=REPLICATE_KEY_COLS, how="left")
    return rep0


def qc_pca(rep0):
    """
    QC6 — PCA multivariada + distância de Mahalanobis.

    Se não houver elementos/linhas suficientes (MIN_PCA_ELEMENTS/MIN_PCA_ROWS),
    a PCA é pulada: PC1/PC2/Mahalanobis ficam NaN e compute_scores aplica um
    score neutro, em vez de deixar o pipeline travar (ver TODO.md item 2.2/1.2).
    """
    rep0 = rep0.copy()
    pca_elements = [x for x in ELEMENTS_PCA if x in rep0.columns]

    if len(pca_elements) < MIN_PCA_ELEMENTS or len(rep0) < MIN_PCA_ROWS:
        rep0["PC1"] = np.nan
        rep0["PC2"] = np.nan
        rep0["Mahalanobis"] = np.nan
        return rep0, pca_elements

    X = rep0[pca_elements].fillna(0)
    Xs = StandardScaler().fit_transform(X)
    pca = PCA(n_components=2)
    pcs = pca.fit_transform(Xs)
    rep0["PC1"] = pcs[:, 0]
    rep0["PC2"] = pcs[:, 1]

    cov = np.cov(pcs.T)
    inv_cov = np.linalg.pinv(cov)
    center = pcs.mean(axis=0)
    rep0["Mahalanobis"] = [mahalanobis(row, center, inv_cov) for row in pcs]

    return rep0, pca_elements


# ============================================================
# SCORES
# ============================================================

def compute_scores(rep0, strict_missing_data=True, combine_rolling_vars=False, include_pca_in_qf=False):
    """
    Calcula scores individuais e Quality Index (QI).

    Args:
        strict_missing_data: se True (padrão), qualquer score individual
            faltante (NaN) invalida o QI da linha inteira — postura
            conservadora. Se False, o QI é recalculado só com os módulos
            disponíveis, redistribuindo os pesos entre eles. Em ambos os
            casos a linha é sinalizada como indeterminada em compute_flags;
            o que muda é apenas se o QI fica indefinido ou aproximado.
        combine_rolling_vars: se False (padrão), o QC4 considera apenas
            Rh-Lα-Inc — é o dado espectral real medido; Throughput, Rh-Lα e
            Argônio são parâmetros instrumentais secundários. Se True, usa o
            maior |z-score| de deriva entre as ROLLING_VARS presentes no
            arquivo (Throughput, Rh-Lα, Rh-Lα-Inc, Ar-Ka Area) — um problema
            físico de medição tende a aparecer em pelo menos uma delas, então
            combinar amplia a sensibilidade às custas de poder reagir a
            deriva instrumental não relacionada ao dado espectral. O valor
            efetivamente usado fica em rep0["Rolling_z"].
        include_pca_in_qf: se False (padrão), Score_PCA continua sempre
            calculado (PCA permanece um módulo de diagnóstico exploratório,
            sempre visível na aba correspondente), mas é excluído do QI —
            o peso de QI_WEIGHTS["Score_PCA"] é redistribuído entre os
            demais módulos, renormalizado para somar 1.0. Se True, volta a
            entrar no QI com seu peso nominal (5%). Ver também compute_flags:
            o critério pontual de Mahalanobis (QF=2/3 por anomalia
            multivariada) é igualmente desligado quando False.
    """
    rep0 = rep0.copy()

    rep0["Score_Throughput"] = score_from_z(rep0["Instrument_z"])
    rep0["Score_RhLa"] = score_from_z(rep0["RhLa_z"])
    rep0["Score_RhLaInc"] = score_from_z(rep0["RhLaInc_z"])

    if combine_rolling_vars:
        delta_z_cols = [f"{v}_delta_z" for v in ROLLING_VARS if f"{v}_delta_z" in rep0.columns]
        rep0["Rolling_z"] = rep0[delta_z_cols].abs().max(axis=1)
    else:
        rep0["Rolling_z"] = rep0["Rh-La-Inc Area_delta_z"].abs()
    rep0["Score_Rolling"] = score_from_z(rep0["Rolling_z"])

    rep0["Score_Replica"] = np.where(
        rep0["Mean_RPD"].isna(),
        100,
        np.maximum(0, 100 - rep0["Mean_RPD"] * 4),
    )

    mahalanobis_valid = rep0["Mahalanobis"].notna()
    if mahalanobis_valid.any():
        valid_values = rep0.loc[mahalanobis_valid, "Mahalanobis"]
        p95 = np.percentile(valid_values, 95)
        p99 = np.percentile(valid_values, 99)
        rep0["Score_PCA"] = np.where(
            mahalanobis_valid,
            np.where(
                rep0["Mahalanobis"] < p95, 100,
                np.where(rep0["Mahalanobis"] < p99, 60, 20)
            ),
            100,
        )
    else:
        # PCA pulada para o arquivo inteiro (ver qc_pca) — score neutro,
        # mesmo padrão já usado em Score_Replica quando não há réplica.
        p95 = p99 = np.nan
        rep0["Score_PCA"] = 100

    active_weights = dict(QI_WEIGHTS)
    if not include_pca_in_qf:
        active_weights.pop("Score_PCA")
        total_weight = sum(active_weights.values())
        active_weights = {k: v / total_weight for k, v in active_weights.items()}

    score_cols = list(active_weights.keys())
    weights = np.array(list(active_weights.values()))
    scores = rep0[score_cols].to_numpy(dtype=float)

    if strict_missing_data:
        # Produto matricial: NaN em qualquer score propaga NaN para o QI.
        rep0["QI"] = scores @ weights
    else:
        available = ~np.isnan(scores)
        weighted_sum = np.nansum(scores * weights, axis=1)
        available_weight = available @ weights
        rep0["QI"] = np.where(available_weight > 0, weighted_sum / available_weight, np.nan)

    return rep0, p95, p99


# ============================================================
# QUALITY FLAG
# ============================================================

def _classify_z_count_mode(z):
    """
    OK/ALERT/CRITICAL a partir de um z-score, limiares do protocolo v4.2
    (COUNT_MODE_Z_WARNING/CRITICAL). Usada para Instrument_z/RhLa_z/
    RhLaInc_z: NaN vira OK aqui sem regredir o achado C2 porque essas
    colunas vêm de CRITICAL_INPUT_COLS — uma linha com qualquer uma delas
    faltante já foi desviada para QF_INDETERMINATE em compute_flags antes
    desta função ser chamada, então NaN nunca chega até aqui de fato.
    """
    if pd.isna(z):
        return QC_OK
    z = abs(z)
    if z >= COUNT_MODE_Z_CRITICAL:
        return QC_CRITICAL
    if z >= COUNT_MODE_Z_WARNING:
        return QC_ALERT
    return QC_OK


def _classify_rolling_count_mode(z):
    """OK/ALERT (sem CRITICAL) a partir do Rolling_z já calculado em compute_scores."""
    if pd.isna(z):
        return QC_OK
    if abs(z) >= COUNT_MODE_ROLLING_Z_ALERT:
        return QC_ALERT
    return QC_OK


def _classify_rpd_count_mode(mean_rpd):
    """
    OK/ALERT/CRITICAL a partir de Mean_RPD, limiares do protocolo v4.2.
    NaN (nenhuma réplica casada nesta posição) vira OK — ausência legítima
    de réplica, mesmo padrão de fallback já usado em Score_Replica (ver
    compute_scores), não um caso de dado faltante crítico.
    """
    if pd.isna(mean_rpd):
        return QC_OK
    if mean_rpd >= COUNT_MODE_RPD_CRITICAL:
        return QC_CRITICAL
    if mean_rpd >= COUNT_MODE_RPD_WARNING:
        return QC_ALERT
    return QC_OK


def _classify_mahalanobis_count_mode(value, p95, p99):
    """
    OK/ALERT/CRITICAL a partir da distância de Mahalanobis vs. p95/p99.
    NaN (PCA pulada para o arquivo inteiro, ou linha fora do critério) vira
    OK — mesmo padrão neutro de Score_PCA quando a PCA não é aplicável.
    """
    if pd.isna(value) or pd.isna(p95) or pd.isna(p99):
        return QC_OK
    if value > p99:
        return QC_CRITICAL
    if value > p95:
        return QC_ALERT
    return QC_OK


def _evaluate_flag_count_mode(row, p95, p99, include_pca_in_qf):
    """
    QF por contagem de módulos reprovados (protocolo v4.2, `evaluate_flag`
    do apêndice): QF0 sem alerta, QF1 = 1 ALERT, QF2 = 2-3 ALERTs ou 1
    CRITICAL, QF3 = 2+ CRITICALs ou 4+ ALERTs. Não compensatório — ao
    contrário do QI ponderado, um módulo muito bom não neutraliza outro
    ruim.

    include_pca_in_qf: mesmo padrão do modo QI ponderado — quando False, a
    PCA fica de fora da contagem (módulo puramente diagnóstico), em vez de
    virar um 6º módulo do protocolo v4.2 original (que não previa PCA).
    """
    causes = []
    states = {}

    instrument_state = _classify_z_count_mode(row["Instrument_z"])
    states["instrument"] = instrument_state
    if instrument_state != QC_OK:
        argon_z = row["Argon_z"]
        if pd.notna(argon_z) and abs(argon_z) > abs(row["Throughput_z"]):
            causes.append(CAUSE_ARGON)
        else:
            causes.append(CAUSE_THROUGHPUT)

    coherent_state = _classify_z_count_mode(row["RhLa_z"])
    states["coherent"] = coherent_state
    if coherent_state != QC_OK:
        causes.append(CAUSE_RH_LA)

    incoherent_state = _classify_z_count_mode(row["RhLaInc_z"])
    states["incoherent"] = incoherent_state
    if incoherent_state != QC_OK:
        causes.append(CAUSE_RH_LA_INC)

    rolling_state = _classify_rolling_count_mode(row["Rolling_z"])
    states["rolling"] = rolling_state
    if rolling_state != QC_OK:
        causes.append(CAUSE_ROLLING)

    replica_state = _classify_rpd_count_mode(row["Mean_RPD"])
    states["replica"] = replica_state
    if replica_state != QC_OK:
        causes.append(CAUSE_REPLICA)

    if include_pca_in_qf:
        pca_state = _classify_mahalanobis_count_mode(row["Mahalanobis"], p95, p99)
        states["pca"] = pca_state
        if pca_state != QC_OK:
            causes.append(CAUSE_PCA)

    alerts = [name for name, s in states.items() if s == QC_ALERT]
    criticals = [name for name, s in states.items() if s == QC_CRITICAL]

    if len(alerts) == 0 and len(criticals) == 0:
        qf = 0
    elif len(alerts) == 1 and len(criticals) == 0:
        qf = 1
    elif len(criticals) >= 2 or len(alerts) >= 4:
        qf = 3
    else:
        qf = 2

    return qf, causes


def compute_flags(rep0, p95, p99, include_pca_in_qf=False, use_count_mode=False):
    """
    Atribui Quality Flag (QF): 0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado,
    QF_INDETERMINATE (9)=indeterminado (dado crítico faltante — ver
    CRITICAL_INPUT_COLS). Uma linha indeterminada nunca recebe 0-3: ou se
    sabe o suficiente para classificar, ou se marca como indeterminada —
    nunca se assume "OK" por omissão (ver TODO.md achado C2).

    include_pca_in_qf: se False (padrão), o critério pontual de Mahalanobis
        (anomalia multivariada) não contribui para QF — consistente com
        Score_PCA também excluído do QI em compute_scores. PCA permanece um
        módulo de diagnóstico exploratório, não um critério de flag. Vale
        para os dois modos (use_count_mode=True ou False).

    use_count_mode: se False (padrão), usa o modo QI ponderado (limiares de
        z-score/QI + critérios pontuais, comportamento histórico desta
        função). Se True, usa o modo alternativo do protocolo v4.2 —
        contagem de módulos reprovados (OK/ALERT/CRITICAL por módulo,
        QF = f(nº de ALERTs, nº de CRITICALs), não compensatório — ver
        _evaluate_flag_count_mode). Em ambos os modos, uma linha com dado
        crítico faltante (CRITICAL_INPUT_COLS) recebe QF_INDETERMINATE
        incondicionalmente, nunca QF=0 (ver TODO.md achado C2) — o modo de
        contagem não repete o bug do apêndice v4.2 (`classify_z`/
        `classify_rolling` tratando NaN como OK).

    Também preenche rep0["QF_Causes"]: string com os códigos de causa
    (CAUSE_*) que dispararam o flag daquela linha, separados por ";" — vazia
    quando QF<2 (nenhuma causa relevante para reportar). Usada para agregar
    causas por intervalo em relatórios (ver report_pdf.detect_intervals).
    """
    rep0 = rep0.copy()
    is_indeterminate = rep0[CRITICAL_INPUT_COLS].isna().any(axis=1) | rep0["QI"].isna()

    flags = []
    causes = []
    for idx, row in rep0.iterrows():
        if is_indeterminate.loc[idx]:
            flags.append(QF_INDETERMINATE)
            causes.append(CAUSE_MISSING_DATA)
            continue

        if use_count_mode:
            qf, row_causes = _evaluate_flag_count_mode(row, p95, p99, include_pca_in_qf)
            flags.append(qf)
            causes.append(";".join(row_causes))
            continue

        qf = 0
        row_causes = []

        # QC1 — Instrument Stability (Throughput combinado com Argônio,
        # pior dos dois; ver qc_throughput/Instrument_z).
        if abs(row["Instrument_z"]) > 2:
            qf = max(qf, 2)
            argon_z = row["Argon_z"]
            if pd.notna(argon_z) and abs(argon_z) > abs(row["Throughput_z"]):
                row_causes.append(CAUSE_ARGON)
            else:
                row_causes.append(CAUSE_THROUGHPUT)
        if abs(row["Instrument_z"]) > 3:
            qf = 3

        for z_col, cause in [
            ("RhLa_z", CAUSE_RH_LA),
            ("RhLaInc_z", CAUSE_RH_LA_INC),
        ]:
            if abs(row[z_col]) > 2:
                qf = max(qf, 2)
                row_causes.append(cause)
            if abs(row[z_col]) > 3:
                qf = 3
        if row["Rolling_z"] > 2:
            qf = max(qf, 2)
            row_causes.append(CAUSE_ROLLING)
        if include_pca_in_qf:
            if row["Mahalanobis"] > p95:
                qf = max(qf, 2)
                row_causes.append(CAUSE_PCA)
            if row["Mahalanobis"] > p99:
                qf = 3
        if row["QI"] < 40:
            qf = 3
            row_causes.append(CAUSE_QI_LOW)
        if qf == 0 and row["QI"] < QI_THRESHOLD_OK:
            qf = 1
        flags.append(qf)
        causes.append(";".join(row_causes))
    rep0["QF"] = flags
    rep0["QF_Causes"] = causes
    return rep0


def is_pointwise_flag(rep0):
    """
    True para linhas onde QF é 2 ou 3, mas o QI agregado ainda está em faixa
    aceitável (>= QI_THRESHOLD_OK) — ou seja, o flag foi disparado por um
    critério pontual (z-score de uma variável específica, ou Mahalanobis),
    não pelo QI combinado. QF_INDETERMINATE é excluído de propósito: ali o
    motivo é dado faltante (CAUSE_MISSING_DATA), não um critério pontual.
    """
    return rep0["QF"].isin([2, 3]) & (rep0["QI"] >= QI_THRESHOLD_OK)


def format_causes(causes, T):
    """Traduz uma coleção de códigos CAUSE_* para texto legível (T = dict de traduções, ex. TEXTS[lang])."""
    if not causes:
        return "—"
    labels = [T.get(f"cause_{code}", code) for code in sorted(causes)]
    return ", ".join(labels)


def add_pointwise_flag_notes(rep0, lang="pt"):
    """
    Adiciona rep0["Pointwise_Flag_Note"]: para as linhas identificadas por
    is_pointwise_flag, explica que o QF foi disparado por um critério
    pontual e não pelo QI agregado, usando as causas já registradas em
    QF_Causes. String vazia para as demais linhas.
    """
    rep0 = rep0.copy()
    T = TEXTS[lang]
    mask = is_pointwise_flag(rep0)

    notes = pd.Series("", index=rep0.index, dtype=object)
    for idx in rep0.index[mask]:
        causes_str = rep0.at[idx, "QF_Causes"]
        causes = causes_str.split(";") if causes_str else []
        notes.at[idx] = T["pointwise_flag_note"].format(
            causes=format_causes(causes, T),
            qi=rep0.at[idx, "QI"],
        )
    rep0["Pointwise_Flag_Note"] = notes
    return rep0


# ============================================================
# PIPELINE COMPLETO
# ============================================================

def run_qc(
    df,
    strict_missing_data=True,
    combine_rolling_vars=False,
    include_pca_in_qf=False,
    use_count_mode=False,
):
    """
    Executa o pipeline QC completo sobre o DataFrame bruto.

    Args:
        strict_missing_data: ver compute_scores. Padrão True (conservador).
        combine_rolling_vars: ver compute_scores. Padrão False (só Rh-Lα-Inc).
        include_pca_in_qf: ver compute_scores/compute_flags. Padrão False
            (PCA é só diagnóstico, não entra no QI/QF).
        use_count_mode: ver compute_flags. Padrão False (modo QI ponderado,
            comportamento histórico). Se True, usa o modo alternativo do
            protocolo v4.2 (contagem de módulos ALERT/CRITICAL). O QI
            continua sendo calculado normalmente em ambos os modos (só o
            critério de atribuição do QF muda) — permanece disponível como
            diagnóstico mesmo quando não é ele quem decide o QF.

    Retorna:
        rep0         : DataFrame com todos os campos QC calculados
        p95          : percentil 95 da distância de Mahalanobis
        p99          : percentil 99 da distância de Mahalanobis
        pca_elements : lista de elementos usados na PCA
    """
    rep0 = df[df[REPLICATE_COL] == "Rep0"].copy()
    rep0 = rep0.sort_values(DEPTH_COL)
    rep0[DEPTH_COL] = rep0[DEPTH_COL].round(10)

    rep0 = qc_throughput(rep0)
    rep0 = qc_rh_la(rep0)
    rep0 = qc_rh_la_inc(rep0)
    rep0 = qc_rolling(rep0)
    rep0 = qc_replicates(df, rep0)
    rep0, pca_elements = qc_pca(rep0)
    rep0, p95, p99 = compute_scores(
        rep0,
        strict_missing_data=strict_missing_data,
        combine_rolling_vars=combine_rolling_vars,
        include_pca_in_qf=include_pca_in_qf,
    )
    rep0 = compute_flags(
        rep0, p95, p99, include_pca_in_qf=include_pca_in_qf, use_count_mode=use_count_mode
    )

    return rep0, p95, p99, pca_elements
