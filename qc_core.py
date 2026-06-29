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

# Variáveis usadas no QC4 (rolling). As três tendem a reagir juntas a um
# mesmo problema físico de medição (rachadura, bolha de ar, transição
# seco/úmido) — ver compute_scores/combine_rolling_vars.
ROLLING_VARS = ["Throughput", "Rh-La Area", "Rh-La-Inc Area"]

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
CAUSE_RH_LA = "rh_la"
CAUSE_RH_LA_INC = "rh_la_inc"
CAUSE_ROLLING = "rolling"
CAUSE_PCA = "pca"
CAUSE_QI_LOW = "qi_low"
CAUSE_MISSING_DATA = "missing_data"

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
    return np.abs(values.max() - values.min()) / np.abs(values.mean()) * 100


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
    """QC1 — Z-score robusto do Throughput."""
    rep0 = rep0.copy()
    rep0["Throughput_z"] = robust_zscore(rep0["Throughput"])
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
    """QC4 — Rolling QC: detecta deriva local via média móvel."""
    rep0 = rep0.copy()
    for var in ROLLING_VARS:
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

def compute_scores(rep0, strict_missing_data=True, combine_rolling_vars=False):
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
            Rh-Lα-Inc — é o dado espectral real medido; Throughput e Rh-Lα
            são parâmetros instrumentais secundários. Se True, usa o maior
            |z-score| de deriva entre as ROLLING_VARS (Throughput, Rh-Lα,
            Rh-Lα-Inc) — um problema físico de medição tende a aparecer em
            pelo menos uma das três, então combinar amplia a sensibilidade
            às custas de poder reagir a deriva instrumental não relacionada
            ao dado espectral. O valor efetivamente usado fica em
            rep0["Rolling_z"].
    """
    rep0 = rep0.copy()

    rep0["Score_Throughput"] = score_from_z(rep0["Throughput_z"])
    rep0["Score_RhLa"] = score_from_z(rep0["RhLa_z"])
    rep0["Score_RhLaInc"] = score_from_z(rep0["RhLaInc_z"])

    if combine_rolling_vars:
        delta_z_cols = [f"{v}_delta_z" for v in ROLLING_VARS]
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

    score_cols = list(QI_WEIGHTS.keys())
    weights = np.array(list(QI_WEIGHTS.values()))
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

def compute_flags(rep0, p95, p99):
    """
    Atribui Quality Flag (QF): 0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado,
    QF_INDETERMINATE (9)=indeterminado (dado crítico faltante — ver
    CRITICAL_INPUT_COLS). Uma linha indeterminada nunca recebe 0-3: ou se
    sabe o suficiente para classificar, ou se marca como indeterminada —
    nunca se assume "OK" por omissão (ver TODO.md achado C2).

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

        qf = 0
        row_causes = []
        for z_col, cause in [
            ("Throughput_z", CAUSE_THROUGHPUT),
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

def run_qc(df, strict_missing_data=True, combine_rolling_vars=False):
    """
    Executa o pipeline QC completo sobre o DataFrame bruto.

    Args:
        strict_missing_data: ver compute_scores. Padrão True (conservador).
        combine_rolling_vars: ver compute_scores. Padrão False (só Rh-Lα-Inc).

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
        rep0, strict_missing_data=strict_missing_data, combine_rolling_vars=combine_rolling_vars
    )
    rep0 = compute_flags(rep0, p95, p99)

    return rep0, p95, p99, pca_elements
