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

# CompositeDepth (mm) só é preenchido na primeira passada (Rep0); em Rep1/Rep2
# essa coluna vem nula. Spectrum + CoreDepth identificam a posição física de
# medição e estão sempre preenchidos em todas as réplicas — é essa combinação
# que QC5 usa para casar réplicas (ver REPLICATE_KEY_COLS).
REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]

# ------------------------------------------------------------------------
# Estrutura multi-energia (protocolo v4.2, DEVELOPMENT.md "io_module.py"/
# "config.py" — TODO.md item 6/seção 9, "Estrutura multi-energia"): um
# workbook Avaatech pode ter uma aba por energia de tubo (10 kV/30 kV/50 kV),
# cada uma medindo um subconjunto diferente de parâmetros — confirmado
# contra `data/Dados Consolidados-ICCE3.xlsx` (3 abas: 10kV/30kV/50kV, cada
# uma com colunas Rh-Lα/Rh-Kα diferentes). ENERGY_PARAMETERS espelha
# ENERGY_PARAMETERS do apêndice; "10kV" reproduz exatamente os literais já
# hardcoded neste arquivo antes desta mudança — qualquer função abaixo
# chamada sem especificar `energy` (default DEFAULT_ENERGY="10kV") reproduz
# o comportamento anterior byte a byte (ver ROLLING_VARS/REQUIRED_COLUMNS/
# CRITICAL_INPUT_COLS logo abaixo, agora derivados daqui em vez de literais
# soltos, para não duplicar a fonte de verdade).
DEFAULT_ENERGY = "10kV"

ENERGY_PARAMETERS = {
    "10kV": {
        "throughput": "Throughput",
        "argon": ARGON_COL,
        "coherent": "Rh-La Area",
        "incoherent": "Rh-La-Inc Area",
    },
    "30kV": {
        "throughput": "Throughput",
        "argon": None,
        "coherent": "Rh-Ka-Coh Area",
        "incoherent": "Rh-Ka-Inc Area",
    },
    "50kV": {
        "throughput": "Throughput",
        "argon": None,
        "coherent": None,
        "incoherent": None,
    },
}


def detect_energy(sheet_name):
    """
    Detecta a energia (10kV/30kV/50kV) a partir do nome da aba, seguindo o
    padrão de `detect_energy` do `io_module.py` do protocolo v4.2
    (DEVELOPMENT.md): procura o substring "10"/"30"/"50" no nome, sem
    diferenciar maiúsculas/minúsculas (cobre variações como "10kv"/"10kV").
    Levanta ValueError para abas cuja energia não pode ser inferida — quem
    chama decide se isso bloqueia o arquivo inteiro ou só aquela aba (ver
    qc_avaatech.py/read_workbook).
    """
    name = str(sheet_name).lower()
    if "10" in name:
        return "10kV"
    if "30" in name:
        return "30kV"
    if "50" in name:
        return "50kV"
    raise ValueError(f"Energia não reconhecida a partir do nome da aba: '{sheet_name}'.")


def _energy_cfg(energy):
    if energy not in ENERGY_PARAMETERS:
        raise ValueError(f"Energia desconhecida: '{energy}'. Válidas: {list(ENERGY_PARAMETERS)}.")
    return ENERGY_PARAMETERS[energy]


def _required_columns_for_energy(energy):
    """
    Colunas obrigatórias específicas da energia (ver REQUIRED_COLUMNS
    abaixo — para DEFAULT_ENERGY reproduz a mesma lista/ordem de antes).
    DEPTH_COL não entra aqui de propósito: quando ausente do arquivo, run_qc
    cai em CORE_DEPTH_COL (já obrigatório via REPLICATE_KEY_COLS) como
    substituto — ver run_qc/check_file ("depth_col_fallback"). Exigir
    DEPTH_COL aqui bloquearia arquivos de testemunho de seção única que só
    exportam CoreDepth.
    """
    cfg = _energy_cfg(energy)
    cols = [REPLICATE_COL, cfg["throughput"]]
    if cfg["coherent"] is not None:
        cols.append(cfg["coherent"])
    if cfg["incoherent"] is not None:
        cols.append(cfg["incoherent"])
    cols.extend(REPLICATE_KEY_COLS)
    return cols


def _critical_cols_for_energy(energy):
    """
    Colunas cuja ausência (NaN) por linha torna o QI/QF indeterminados nesta
    energia (ver CRITICAL_INPUT_COLS abaixo). QC2/QC3 (coerente/incoerente)
    só entram quando a energia efetivamente os mede — quando `cfg["coherent"]`/
    `cfg["incoherent"]` é None (ex. 50 kV não mede nenhum dos dois), a
    ausência é estrutural (o módulo não se aplica a essa energia, análogo a
    Argônio/PCA), não um dado faltante pontual — por isso não entra em
    CRITICAL_INPUT_COLS para essa energia (ver também compute_scores,
    módulo fica neutro + peso excluído do QI em vez de QF_INDETERMINATE).
    """
    cfg = _energy_cfg(energy)
    cols = [cfg["throughput"]]
    if cfg["coherent"] is not None:
        cols.append(cfg["coherent"])
    if cfg["incoherent"] is not None:
        cols.append(cfg["incoherent"])
    return cols


def _rolling_vars_for_energy(energy):
    """Variáveis do QC4 (rolling) para esta energia, na mesma ordem usada
    antes desta mudança (Throughput, coerente, incoerente, Argônio) — para
    DEFAULT_ENERGY reproduz exatamente ROLLING_VARS."""
    cfg = _energy_cfg(energy)
    return [v for v in (cfg["throughput"], cfg["coherent"], cfg["incoherent"], cfg["argon"]) if v is not None]


# Variáveis usadas no QC4 (rolling) para a energia padrão (10 kV). As três
# originais tendem a reagir juntas a um mesmo problema físico de medição
# (rachadura, bolha de ar, transição seco/úmido) — ver compute_scores/
# combine_rolling_vars. qc_rolling ignora graciosamente qualquer uma que não
# esteja presente no arquivo (e usa `_rolling_vars_for_energy` para outras
# energias — ver qc_rolling/compute_scores).
ROLLING_VARS = _rolling_vars_for_energy(DEFAULT_ENERGY)

REQUIRED_COLUMNS = _required_columns_for_energy(DEFAULT_ENERGY)

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
# na energia padrão (QC1-QC3 — sempre obrigatórias em 10 kV). QC5/QC6 já têm
# seus próprios fallbacks e não entram aqui de propósito (ver TODO.md achado
# C2). Ver _critical_cols_for_energy para o equivalente noutras energias.
CRITICAL_INPUT_COLS = _critical_cols_for_energy(DEFAULT_ENERGY)

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

# ------------------------------------------------------------------------
# Persistência temporal do QC4 (protocolo v4.2, DEVELOPMENT.md seção "8. QC4
# – Rolling QC" / "Persistência"): uma anomalia de deriva só deveria disparar
# ALERT quando aparece em >= ROLLING_PERSISTENCE_MIN_POINTS pontos dentro de
# uma janela de ROLLING_PERSISTENCE_WINDOW medidas consecutivas (2 pontos
# consecutivos é o caso particular de 2 pontos numa janela de 3 centrada em
# qualquer um dos dois — um único critério cobre as duas regras do texto do
# protocolo). Reduz falsos positivos de ruído estatístico pontual.
#
# Este item estava listado em TODO.md ("Bloqueados até decisão do time")
# porque tensiona com a decisão já tomada no item 1.5 (flag pontual único é
# válido por padrão, "defesa em profundidade"). Resolvido como opt-in via
# use_rolling_persistence (default False preserva o comportamento atual) —
# ver qc_rolling/run_qc.
#
# ROLLING_PERSISTENCE_Z_THRESHOLD reusa o limiar 2.0 já convencionado nesta
# base como "atenção" pontual (Instrument_z/RhLa_z/RhLaInc_z, e o próprio
# critério de Rolling_z > 2 no modo QI ponderado) — não o limiar mais alto
# do modo de contagem (COUNT_MODE_ROLLING_Z_ALERT=4.0), que é específico
# daquele modo alternativo de QF e não deve acoplar a lógica geral do QC4.
ROLLING_PERSISTENCE_Z_THRESHOLD = 2.0
ROLLING_PERSISTENCE_MIN_POINTS = 2
ROLLING_PERSISTENCE_WINDOW = 3

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

def check_file(df, lang="pt", energy=DEFAULT_ENERGY):
    """
    Valida estrutura do DataFrame antes de rodar o pipeline. Opera sobre uma
    única aba/energia por chamada — em um workbook multi-energia (10 kV/
    30 kV/50 kV), cada aba é validada independentemente, uma chamada por aba
    (ver qc_avaatech.py).

    Args:
        lang: "pt" ou "en" — idioma das mensagens retornadas.
        energy: "10kV"/"30kV"/"50kV" (ver ENERGY_PARAMETERS/detect_energy).
            Determina quais colunas são obrigatórias (ex. 50 kV não mede
            Rh-Lα/Rh-Lα-Inc nem seus equivalentes Rh-Kα, então não exige
            nenhuma das duas).

    Retorna:
        errors   : list[str] — erros que bloqueiam a execução
        warnings : list[str] — avisos que permitem continuar
    """
    errors = []
    warnings = []

    def msg(key, **kwargs):
        return CHECK_MESSAGES[key][lang].format(**kwargs)

    required_columns = _required_columns_for_energy(energy)
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        errors.append(msg("missing_columns", cols=missing))

    if DEPTH_COL not in df.columns and CORE_DEPTH_COL in df.columns:
        warnings.append(msg("depth_col_fallback", col=CORE_DEPTH_COL))

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

    # Usa DEPTH_COL quando presente; senão cai no mesmo fallback de run_qc
    # (CORE_DEPTH_COL) para que este aviso reflita a coluna efetivamente
    # usada como profundidade contínua pelo pipeline.
    depth_col_for_dup = DEPTH_COL if DEPTH_COL in df.columns else CORE_DEPTH_COL
    if depth_col_for_dup in df.columns and REPLICATE_COL in df.columns:
        rep0 = df[df[REPLICATE_COL] == "Rep0"]
        dup = rep0[depth_col_for_dup].duplicated().sum()
        if dup > 0:
            warnings.append(msg("dup_depths", n=dup))

    return errors, warnings


# ============================================================
# MÓDULOS QC INDIVIDUAIS
# ============================================================

def qc_throughput(rep0, energy=DEFAULT_ENERGY):
    """
    QC1 — Instrument Stability: z-score robusto do Throughput, combinado com
    o pico de Argônio quando presente no arquivo (protocolo v4.2, seção 5).
    Argônio só existe em modo 10 kV (`ENERGY_PARAMETERS[energy]["argon"]` é
    None para 30/50 kV) — nesses casos, Instrument_z já cai de volta para
    Throughput_z puro, mesmo comportamento de quando a coluna simplesmente
    está ausente do arquivo.

    "Combinado" = pior dos dois: rep0["Instrument_z"] é o z-score (Throughput
    ou Argônio) de maior magnitude absoluta linha a linha — um problema de
    vedação/atmosfera pode aparecer só no Argônio, sem necessariamente
    derrubar o Throughput, e vice-versa. rep0["Throughput_z"]/["Argon_z"]
    continuam disponíveis individualmente (diagnóstico); Instrument_z é quem
    alimenta Score_Throughput/compute_flags.
    """
    cfg = _energy_cfg(energy)
    throughput_col = cfg["throughput"]
    argon_col = cfg["argon"]

    rep0 = rep0.copy()
    rep0["Throughput_z"] = robust_zscore(rep0[throughput_col])

    if argon_col is not None and argon_col in rep0.columns:
        rep0["Argon_z"] = robust_zscore(rep0[argon_col])
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


def qc_rh_la(rep0, energy=DEFAULT_ENERGY):
    """
    QC2 — Z-score robusto do Coherent Scatter (Rh-Lα em 10 kV, Rh-Kα-Coh em
    30 kV — ver ENERGY_PARAMETERS). Quando a energia não mede esse parâmetro
    (`cfg["coherent"] is None`, caso de 50 kV) ou a coluna está ausente do
    arquivo, RhLa_z fica NaN em todas as linhas — módulo estruturalmente não
    aplicável para essa energia, não um dado faltante pontual (ver
    compute_scores: nesse caso o módulo fica neutro e seu peso é excluído do
    QI, em vez de QF_INDETERMINATE por linha).
    """
    cfg = _energy_cfg(energy)
    coherent_col = cfg["coherent"]

    rep0 = rep0.copy()
    if coherent_col is not None and coherent_col in rep0.columns:
        rep0["RhLa_z"] = robust_zscore(rep0[coherent_col])
    else:
        rep0["RhLa_z"] = np.nan
    return rep0


def qc_rh_la_inc(rep0, energy=DEFAULT_ENERGY):
    """
    QC3 — Z-score robusto do Incoherent Scatter (Rh-Lα-Inc em 10 kV,
    Rh-Kα-Inc em 30 kV — ver ENERGY_PARAMETERS). Mesma degradação graciosa
    de qc_rh_la quando a energia não mede esse parâmetro (50 kV) ou a coluna
    está ausente.
    """
    cfg = _energy_cfg(energy)
    incoherent_col = cfg["incoherent"]

    rep0 = rep0.copy()
    if incoherent_col is not None and incoherent_col in rep0.columns:
        rep0["RhLaInc_z"] = robust_zscore(rep0[incoherent_col])
    else:
        rep0["RhLaInc_z"] = np.nan
    return rep0


def _apply_rolling_persistence(
    delta_z,
    threshold=ROLLING_PERSISTENCE_Z_THRESHOLD,
    min_points=ROLLING_PERSISTENCE_MIN_POINTS,
    window=ROLLING_PERSISTENCE_WINDOW,
):
    """
    Suprime (zera) anomalias isoladas de |delta_z| (protocolo v4.2,
    "Persistência" — ver ROLLING_PERSISTENCE_* acima). Um ponto só mantém seu
    z-score de deriva se, numa janela de `window` medidas centrada nele
    (janela reduzida nas bordas), houver pelo menos `min_points` pontos com
    |delta_z| > threshold — incluindo ele mesmo.

    Pressupõe que `delta_z` já está na ordem de profundidade (rep0 é
    ordenado por DEPTH_COL antes de qc_rolling rodar — ver run_qc), senão
    "consecutivo"/"janela" não teriam significado físico.
    """
    anomaly = (delta_z.abs() > threshold).fillna(False).to_numpy()
    n = len(anomaly)
    half = window // 2
    persistent = np.zeros(n, dtype=bool)
    for i in range(n):
        if not anomaly[i]:
            continue
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        if anomaly[lo:hi].sum() >= min_points:
            persistent[i] = True
    # Só substitui por 0 os pontos que eram anomalia isolada (anomaly=True,
    # persistent=False); pontos já abaixo do limiar (nunca marcados como
    # anomaly) devem manter seu z-score original intacto — do contrário todo
    # ponto "normal" seria zerado por engano, distorcendo Score_Rolling.
    suppress = anomaly & ~persistent
    return delta_z.where(~pd.Series(suppress, index=delta_z.index), 0.0)


def qc_rolling(rep0, window=ROLLING_WINDOW, use_rolling_persistence=False, energy=DEFAULT_ENERGY):
    """
    QC4 — Rolling QC: detecta deriva local via média móvel.

    Itera as variáveis da energia (`_rolling_vars_for_energy` — para
    DEFAULT_ENERGY é Throughput/Rh-La Area/Rh-La-Inc Area/Ar-Ka Area, igual a
    ROLLING_VARS); uma variável ausente do arquivo (ex. Ar-Ka Area fora do
    modo 10 kV, ou coerente/incoerente ausentes em 30/50 kV) é simplesmente
    ignorada — mesmo padrão de degradação graciosa usado em qc_pca/
    qc_replicates.

    use_rolling_persistence: se False (padrão), comportamento inalterado —
        qualquer ponto com |delta_z| acima do limiar dispara o critério de
        deriva isoladamente ("defesa em profundidade", ver TODO.md item
        1.5). Se True, aplica a regra de persistência do protocolo v4.2
        (`_apply_rolling_persistence`) a cada `{var}_delta_z`: anomalias
        isoladas (sem um segundo ponto acima do limiar na janela de 3) são
        zeradas antes de seguir no pipeline. Como compute_scores/
        compute_flags sempre leem `{var}_delta_z`/`Rolling_z` a partir das
        colunas produzidas aqui, o efeito se propaga automaticamente para
        Score_Rolling e para o critério de flag do QC4 nos dois modos de QF
        (QI ponderado e contagem), sem precisar de parâmetro próprio ali.
    """
    rep0 = rep0.copy()
    for var in _rolling_vars_for_energy(energy):
        if var not in rep0.columns:
            continue
        roll = rep0[var].rolling(window=window, center=True, min_periods=1).mean()
        rep0[f"{var}_rolling"] = roll
        rep0[f"{var}_delta"] = rep0[var] - roll
        delta_z = pd.Series(robust_zscore(rep0[f"{var}_delta"]), index=rep0.index)
        if use_rolling_persistence:
            delta_z = _apply_rolling_persistence(delta_z)
        rep0[f"{var}_delta_z"] = delta_z
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

def compute_scores(rep0, strict_missing_data=True, combine_rolling_vars=False, include_pca_in_qf=False, energy=DEFAULT_ENERGY):
    """
    Calcula scores individuais e Quality Index (QI).

    Args:
        strict_missing_data: se True (padrão), qualquer score individual
            faltante (NaN) invalida o QI da linha inteira — postura
            conservadora. Se False, o QI é recalculado só com os módulos
            disponíveis, redistribuindo os pesos entre eles. Em ambos os
            casos a linha é sinalizada como indeterminada em compute_flags;
            o que muda é apenas se o QI fica indefinido ou aproximado.
        combine_rolling_vars: se False (padrão), o QC4 considera apenas a
            variável incoerente da energia (Rh-Lα-Inc em 10 kV, Rh-Kα-Inc em
            30 kV) — é o dado espectral real medido; Throughput, coerente e
            Argônio são parâmetros instrumentais secundários. Se True, usa o
            maior |z-score| de deriva entre as variáveis da energia presentes
            no arquivo (ver `_rolling_vars_for_energy`) — um problema físico
            de medição tende a aparecer em pelo menos uma delas, então
            combinar amplia a sensibilidade às custas de poder reagir a
            deriva instrumental não relacionada ao dado espectral. O valor
            efetivamente usado fica em rep0["Rolling_z"]. Em 50 kV (sem
            variável incoerente) sempre combina as disponíveis, já que não há
            variável espectral "default" para usar sozinha.
        include_pca_in_qf: se False (padrão), Score_PCA continua sempre
            calculado (PCA permanece um módulo de diagnóstico exploratório,
            sempre visível na aba correspondente), mas é excluído do QI —
            o peso de QI_WEIGHTS["Score_PCA"] é redistribuído entre os
            demais módulos, renormalizado para somar 1.0. Se True, volta a
            entrar no QI com seu peso nominal (5%). Ver também compute_flags:
            o critério pontual de Mahalanobis (QF=2/3 por anomalia
            multivariada) é igualmente desligado quando False.
        energy: "10kV"/"30kV"/"50kV" (ver ENERGY_PARAMETERS). Determina qual
            variável alimenta o QC4 por padrão e quais dos módulos QC2/QC3
            (coerente/incoerente) são estruturalmente aplicáveis — quando não
            aplicáveis (ex. 50 kV não mede nenhum dos dois), o score
            correspondente fica neutro (100, mesmo padrão já usado por
            Score_PCA/Score_Replica quando indisponíveis) e seu peso é
            excluído do QI (renormalizado), em vez de propagar NaN linha a
            linha — a ausência é estrutural do dataset inteiro, não um dado
            faltante pontual (ver TODO.md, "Estrutura multi-energia").
    """
    cfg = _energy_cfg(energy)
    rep0 = rep0.copy()

    rep0["Score_Throughput"] = score_from_z(rep0["Instrument_z"])

    rhla_active = cfg["coherent"] is not None
    rhlainc_active = cfg["incoherent"] is not None
    rep0["Score_RhLa"] = score_from_z(rep0["RhLa_z"]) if rhla_active else 100
    rep0["Score_RhLaInc"] = score_from_z(rep0["RhLaInc_z"]) if rhlainc_active else 100

    rolling_vars = _rolling_vars_for_energy(energy)
    default_rolling_var = cfg["incoherent"]
    use_combined_rolling = (
        combine_rolling_vars
        or default_rolling_var is None
        or f"{default_rolling_var}_delta_z" not in rep0.columns
    )
    if use_combined_rolling:
        delta_z_cols = [f"{v}_delta_z" for v in rolling_vars if f"{v}_delta_z" in rep0.columns]
        rep0["Rolling_z"] = rep0[delta_z_cols].abs().max(axis=1)
    else:
        rep0["Rolling_z"] = rep0[f"{default_rolling_var}_delta_z"].abs()
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
    if not rhla_active:
        active_weights.pop("Score_RhLa")
    if not rhlainc_active:
        active_weights.pop("Score_RhLaInc")
    if len(active_weights) < len(QI_WEIGHTS):
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


def compute_flags(rep0, p95, p99, include_pca_in_qf=False, use_count_mode=False, energy=DEFAULT_ENERGY):
    """
    Atribui Quality Flag (QF): 0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado,
    QF_INDETERMINATE (9)=indeterminado (dado crítico faltante — ver
    _critical_cols_for_energy). Uma linha indeterminada nunca recebe 0-3: ou
    se sabe o suficiente para classificar, ou se marca como indeterminada —
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
        crítico faltante (`_critical_cols_for_energy`) recebe QF_INDETERMINATE
        incondicionalmente, nunca QF=0 (ver TODO.md achado C2) — o modo de
        contagem não repete o bug do apêndice v4.2 (`classify_z`/
        `classify_rolling` tratando NaN como OK).

    energy: "10kV"/"30kV"/"50kV" (ver ENERGY_PARAMETERS). Determina quais
        colunas são críticas para esta energia — QC2/QC3 saem da lista
        quando a energia não os mede (ver _critical_cols_for_energy):
        nesse caso a linha nunca fica indeterminada por causa deles, já
        que compute_scores já tratou o módulo como estruturalmente
        inaplicável (score neutro, peso excluído do QI).

    Também preenche rep0["QF_Causes"]: string com os códigos de causa
    (CAUSE_*) que dispararam o flag daquela linha, separados por ";" — vazia
    quando QF<2 (nenhuma causa relevante para reportar). Usada para agregar
    causas por intervalo em relatórios (ver report_pdf.detect_intervals).
    """
    rep0 = rep0.copy()
    critical_cols = _critical_cols_for_energy(energy)
    is_indeterminate = rep0[critical_cols].isna().any(axis=1) | rep0["QI"].isna()

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
    use_rolling_persistence=False,
    energy=DEFAULT_ENERGY,
):
    """
    Executa o pipeline QC completo sobre o DataFrame bruto de UMA aba/energia.
    Num workbook multi-energia (10 kV/30 kV/50 kV — ver ENERGY_PARAMETERS/
    detect_energy), chame run_qc uma vez por aba, com o `energy` detectado
    para aquela aba.

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
        use_rolling_persistence: ver qc_rolling. Padrão False (comportamento
            histórico — qualquer ponto isolado acima do limiar dispara o
            critério de deriva do QC4). Se True, aplica a regra de
            persistência do protocolo v4.2 (>=2 pontos consecutivos ou numa
            janela de 3) antes do restante do pipeline, afetando
            automaticamente Score_Rolling e o critério de flag do QC4 nos
            dois modos de QF.
        energy: "10kV"/"30kV"/"50kV" (ver ENERGY_PARAMETERS/detect_energy).
            Padrão DEFAULT_ENERGY="10kV" — reproduz exatamente o
            comportamento anterior a esta funcionalidade para quem não
            especifica energia. Determina os parâmetros físicos usados por
            QC1-QC4 (`ENERGY_PARAMETERS`) e as colunas obrigatórias/críticas
            (`_required_columns_for_energy`/`_critical_cols_for_energy`).

    Retorna:
        rep0         : DataFrame com todos os campos QC calculados
        p95          : percentil 95 da distância de Mahalanobis
        p99          : percentil 99 da distância de Mahalanobis
        pca_elements : lista de elementos usados na PCA
    """
    rep0 = df[df[REPLICATE_COL] == "Rep0"].copy()

    if DEPTH_COL not in rep0.columns:
        # Fallback (ver check_file "depth_col_fallback"): arquivo não exporta
        # CompositeDepth (mm), só CoreDepth — correto apenas para
        # testemunho de seção única, onde CoreDepth já é contínuo. Sintetiza
        # a coluna DEPTH_COL a partir de CORE_DEPTH_COL (já obrigatório via
        # REPLICATE_KEY_COLS) para que o restante do pipeline e o frontend
        # (qc_avaatech.py/report_pdf.py, que sempre esperam DEPTH_COL)
        # funcionem sem nenhuma outra alteração.
        rep0[DEPTH_COL] = rep0[CORE_DEPTH_COL]

    rep0 = rep0.sort_values(DEPTH_COL)
    rep0[DEPTH_COL] = rep0[DEPTH_COL].round(10)

    rep0 = qc_throughput(rep0, energy=energy)
    rep0 = qc_rh_la(rep0, energy=energy)
    rep0 = qc_rh_la_inc(rep0, energy=energy)
    rep0 = qc_rolling(rep0, use_rolling_persistence=use_rolling_persistence, energy=energy)
    rep0 = qc_replicates(df, rep0)
    rep0, pca_elements = qc_pca(rep0)
    rep0, p95, p99 = compute_scores(
        rep0,
        strict_missing_data=strict_missing_data,
        combine_rolling_vars=combine_rolling_vars,
        include_pca_in_qf=include_pca_in_qf,
        energy=energy,
    )
    rep0 = compute_flags(
        rep0, p95, p99,
        include_pca_in_qf=include_pca_in_qf,
        use_count_mode=use_count_mode,
        energy=energy,
    )

    return rep0, p95, p99, pca_elements


# ============================================================
# WORKBOOK MULTI-ENERGIA (leitura de abas)
# ============================================================

def read_workbook(file_or_buffer):
    """
    Lê todas as abas de um workbook Avaatech e detecta a energia de cada uma
    pelo nome (protocolo v4.2, "io_module.py" — ver detect_energy). Não
    executa check_file/run_qc — só localiza e classifica as abas; a
    validação/cálculo continuam sendo feitos aba a aba pelo chamador (ver
    qc_avaatech.py), mantendo check_file/run_qc como funções de uma única
    aba/energia por vez.

    Se uma aba tiver energia não reconhecida pelo nome:
      - Se o workbook tiver só essa aba, assume DEFAULT_ENERGY ("10kV") —
        preserva compatibilidade com arquivos de aba única cujo nome não
        segue a convenção "10kV"/"30kV"/"50kV" (ex. exports mais antigos).
      - Se houver outras abas no workbook, a aba é ignorada (listada em
        `skipped`) — não há como inferir seu papel com segurança num
        contexto multi-energia (mesma filosofia de "pular sem travar" do
        `io_module.py` do apêndice, mas sem silenciar via print: quem chama
        decide como avisar o usuário).

    Retorna:
        sheets  : list[dict] — um por aba processável, com "sheet_name",
                  "energy", "df" (DataFrame bruto, sem nenhum filtro).
        skipped : list[str] — nomes de abas ignoradas por energia não
                  reconhecida (só ocorre em workbooks com múltiplas abas).
    """
    xls = pd.ExcelFile(file_or_buffer)
    sheet_names = xls.sheet_names
    sheets = []
    skipped = []
    for name in sheet_names:
        try:
            energy = detect_energy(name)
        except ValueError:
            if len(sheet_names) == 1:
                energy = DEFAULT_ENERGY
            else:
                skipped.append(name)
                continue
        # Reaproveita o ExcelFile já aberto (xls.parse) em vez de reabrir
        # file_or_buffer por aba — evita depender de seek(0) automático em
        # objetos file-like que já foram lidos uma vez (ex. o buffer de
        # upload do Streamlit).
        df = xls.parse(sheet_name=name)
        sheets.append({"sheet_name": name, "energy": energy, "df": df})
    return sheets, skipped
