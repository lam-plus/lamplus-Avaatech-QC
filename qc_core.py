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

from i18n import CHECK_MESSAGES

# ============================================================
# CONFIGURAÇÕES
# ============================================================

DEPTH_COL = "CompositeDepth (mm)"
REPLICATE_COL = "Replicate Nr Count"
ROLLING_WINDOW = 5

REQUIRED_COLUMNS = [
    DEPTH_COL,
    REPLICATE_COL,
    "Throughput",
    "Rh-La Area",
    "Rh-La-Inc Area",
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

ELEMENTS_REPLICATES = [
    "Al-Ka Area",
    "Si-Ka Area",
    "K -Ka Area",
    "Ca-Ka Area",
    "Ti-Ka Area",
    "Fe-Ka Area",
]

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

    missing_pca = [e for e in ELEMENTS_PCA if e not in df.columns]
    if missing_pca:
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
    for var in ["Throughput", "Rh-La Area", "Rh-La-Inc Area"]:
        roll = rep0[var].rolling(window=window, center=True, min_periods=1).mean()
        rep0[f"{var}_rolling"] = roll
        rep0[f"{var}_delta"] = rep0[var] - roll
        rep0[f"{var}_delta_z"] = robust_zscore(rep0[f"{var}_delta"])
    return rep0


def qc_replicates(df, rep0):
    """QC5 — RPD médio entre réplicas por profundidade."""
    replica_stats = []
    for depth in sorted(df[DEPTH_COL].unique()):
        subset = df[df[DEPTH_COL] == depth]
        if len(subset) < 2:
            continue
        rpds = []
        for el in ELEMENTS_REPLICATES:
            if el not in subset.columns:
                continue
            rpd = calculate_rpd(subset[el].values)
            rpds.append(rpd)
        mean_rpd = np.nanmean(rpds) if rpds else np.nan
        replica_stats.append([depth, mean_rpd])

    replica_df = pd.DataFrame(replica_stats, columns=[DEPTH_COL, "Mean_RPD"])
    rep0 = rep0.merge(replica_df, on=DEPTH_COL, how="left")
    return rep0


def qc_pca(rep0):
    """QC6 — PCA multivariada + distância de Mahalanobis."""
    rep0 = rep0.copy()
    pca_elements = [x for x in ELEMENTS_PCA if x in rep0.columns]
    X = rep0[pca_elements].fillna(0)
    Xs = StandardScaler().fit_transform(X)
    pca = PCA(n_components=2)
    pcs = pca.fit_transform(Xs)
    rep0["PC1"] = pcs[:, 0]
    rep0["PC2"] = pcs[:, 1]

    cov = np.cov(pcs.T)
    inv_cov = np.linalg.inv(cov)
    center = pcs.mean(axis=0)
    rep0["Mahalanobis"] = [mahalanobis(row, center, inv_cov) for row in pcs]

    return rep0, pca_elements


# ============================================================
# SCORES
# ============================================================

def compute_scores(rep0):
    """Calcula scores individuais e Quality Index (QI)."""
    rep0 = rep0.copy()

    rep0["Score_Throughput"] = score_from_z(rep0["Throughput_z"])
    rep0["Score_RhLa"] = score_from_z(rep0["RhLa_z"])
    rep0["Score_RhLaInc"] = score_from_z(rep0["RhLaInc_z"])
    rep0["Score_Rolling"] = score_from_z(rep0["Rh-La-Inc Area_delta_z"])
    rep0["Score_Replica"] = np.where(
        rep0["Mean_RPD"].isna(),
        100,
        np.maximum(0, 100 - rep0["Mean_RPD"] * 4),
    )

    p95 = np.percentile(rep0["Mahalanobis"], 95)
    p99 = np.percentile(rep0["Mahalanobis"], 99)
    rep0["Score_PCA"] = np.where(
        rep0["Mahalanobis"] < p95, 100,
        np.where(rep0["Mahalanobis"] < p99, 60, 20)
    )

    rep0["QI"] = (
        0.25 * rep0["Score_Throughput"]
        + 0.15 * rep0["Score_RhLa"]
        + 0.20 * rep0["Score_RhLaInc"]
        + 0.20 * rep0["Score_Rolling"]
        + 0.15 * rep0["Score_Replica"]
        + 0.05 * rep0["Score_PCA"]
    )

    return rep0, p95, p99


# ============================================================
# QUALITY FLAG
# ============================================================

def compute_flags(rep0, p95, p99):
    """Atribui Quality Flag (QF): 0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado."""
    rep0 = rep0.copy()
    flags = []
    for _, row in rep0.iterrows():
        qf = 0
        for z_col in ["Throughput_z", "RhLa_z", "RhLaInc_z"]:
            if abs(row[z_col]) > 2:
                qf = max(qf, 2)
            if abs(row[z_col]) > 3:
                qf = 3
        if abs(row["Rh-La-Inc Area_delta_z"]) > 2:
            qf = max(qf, 2)
        if row["Mahalanobis"] > p95:
            qf = max(qf, 2)
        if row["Mahalanobis"] > p99:
            qf = 3
        if row["QI"] < 40:
            qf = 3
        if qf == 0 and row["QI"] < 80:
            qf = 1
        flags.append(qf)
    rep0["QF"] = flags
    return rep0


# ============================================================
# PIPELINE COMPLETO
# ============================================================

def run_qc(df):
    """
    Executa o pipeline QC completo sobre o DataFrame bruto.

    Retorna:
        rep0         : DataFrame com todos os campos QC calculados
        p95          : percentil 95 da distância de Mahalanobis
        p99          : percentil 99 da distância de Mahalanobis
        pca_elements : lista de elementos usados na PCA
    """
    rep0 = df[df[REPLICATE_COL] == "Rep0"].copy()
    rep0 = rep0.sort_values(DEPTH_COL)

    rep0 = qc_throughput(rep0)
    rep0 = qc_rh_la(rep0)
    rep0 = qc_rh_la_inc(rep0)
    rep0 = qc_rolling(rep0)
    rep0 = qc_replicates(df, rep0)
    rep0, pca_elements = qc_pca(rep0)
    rep0, p95, p99 = compute_scores(rep0)
    rep0 = compute_flags(rep0, p95, p99)

    return rep0, p95, p99, pca_elements
